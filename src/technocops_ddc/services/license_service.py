from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from technocops_ddc import APP_NAME
from technocops_ddc.config import (
    ACTIVATION_KEY_SECRET,
    LICENSE_STATE_PATH,
    PRODUCT_DIR_NAME,
    REGISTRY_LICENSE_PATH,
    SECURE_STORAGE_DIR,
    TRIAL_PERIOD_DAYS,
)
from technocops_ddc.services.windows_security import WindowsProtectedStorage, WindowsRegistryStore

DEFAULT_TERMS_TEXT = """
{app_name} Terms and Conditions

1. This software is licensed, not sold, for internal evaluation and approved production use only.
2. The trial license is valid for 3 calendar days from the protected installation timestamp recorded on this machine and is limited to the authorized evaluating organization.
3. Redistribution, resale, rental, sublicensing, public sharing, or unauthorized copying of this software is prohibited.
4. Reverse engineering, decompilation, modification, or attempts to bypass licensing controls are not permitted except where required by law.
5. After the trial expires, continued use requires a valid activation key issued by an authorized Technocops administrator.
6. Activation keys are machine-bound and may not be transferred without written approval from Technocops Technology & Innovation.
7. The operator remains responsible for all input documents, converted output, validation review, and publishing decisions.
8. This software is provided "as is" without any guarantee of uninterrupted operation or fitness for a specific publishing workflow.
9. Technocops Technology & Innovation is not liable for indirect, incidental, or consequential damages arising from use of the software.
10. By continuing, you confirm that you are authorized to evaluate or operate this software under these terms.
""".strip()
ACTIVATION_KEY_PATTERN = re.compile(r"^TCPRO-(?:[A-F0-9]{4}-){3}[A-F0-9]{4}$")
REGISTRY_VALUE_NAME = "LicenseState"
STATE_VERSION = 2


@dataclass(slots=True)
class LicenseState:
    installed_at: str
    trial_expires_at: str
    terms_accepted: bool
    activated: bool
    activation_key: str
    machine_id: str

    @property
    def installed_at_dt(self) -> datetime:
        return datetime.fromisoformat(self.installed_at)

    @property
    def trial_expires_at_dt(self) -> datetime:
        return datetime.fromisoformat(self.trial_expires_at)


class LicenseService:
    def __init__(self) -> None:
        self.terms_text = DEFAULT_TERMS_TEXT.format(app_name=APP_NAME)
        entropy = f"{APP_NAME}|{ACTIVATION_KEY_SECRET}".encode("utf-8")
        self.protected_storage = WindowsProtectedStorage(entropy)
        self.registry_store = WindowsRegistryStore(REGISTRY_LICENSE_PATH)
        self.storage_dir = self._resolve_storage_dir()
        self.license_state_path = self.storage_dir / LICENSE_STATE_PATH.name

    def load_state(self) -> LicenseState:
        file_error: Exception | None = None
        registry_error: Exception | None = None

        try:
            state = self._load_state_from_file()
        except Exception as exc:  # noqa: BLE001
            state = None
            file_error = exc

        if state is not None:
            self._sync_registry_copy(state)
            return state

        try:
            state = self._load_state_from_registry()
        except Exception as exc:  # noqa: BLE001
            state = None
            registry_error = exc

        if state is not None:
            self.save_state(state)
            return state

        if file_error is not None or registry_error is not None:
            locked_state = self._build_locked_state(self.machine_id())
            self.save_state(locked_state)
            return locked_state

        state = self._build_new_state()
        self.save_state(state)
        return state

    def save_state(self, state: LicenseState) -> None:
        payload = self.protected_storage.protect_text(self._serialize_state(state))
        self.license_state_path.write_text(payload, encoding="utf-8")
        self.registry_store.write_text(REGISTRY_VALUE_NAME, payload)

    def refresh_state(self, state: LicenseState) -> LicenseState:
        current_machine = self.machine_id()
        if state.machine_id == current_machine:
            return state
        replacement = self._build_locked_state(current_machine)
        self.save_state(replacement)
        return replacement

    def can_launch(self, state: LicenseState) -> bool:
        return state.activated or self.is_trial_active(state)

    def is_trial_active(self, state: LicenseState) -> bool:
        return self.now_utc() <= state.trial_expires_at_dt

    def days_remaining(self, state: LicenseState) -> int:
        remaining = state.trial_expires_at_dt - self.now_utc()
        if remaining.total_seconds() <= 0:
            return 0
        return max(1, remaining.days + (1 if remaining.seconds > 0 else 0))

    def remaining_seconds(self, state: LicenseState) -> int:
        remaining = state.trial_expires_at_dt - self.now_utc()
        return max(0, int(remaining.total_seconds()))

    def remaining_days_label(self, state: LicenseState) -> str:
        days_left = self.days_remaining(state)
        if days_left == 0:
            return "Trial expired"
        suffix = "day" if days_left == 1 else "days"
        return f"{days_left} {suffix} left"

    def remaining_time_label(self, state: LicenseState) -> str:
        total_seconds = self.remaining_seconds(state)
        if total_seconds <= 0:
            return "00d 00h 00m 00s"

        days, remainder = divmod(total_seconds, 24 * 60 * 60)
        hours, remainder = divmod(remainder, 60 * 60)
        minutes, seconds = divmod(remainder, 60)
        return f"{days:02d}d {hours:02d}h {minutes:02d}m {seconds:02d}s"

    def expected_activation_key(self, machine_id: str) -> str:
        digest = hashlib.sha256(f"{machine_id}|{ACTIVATION_KEY_SECRET}".encode("utf-8")).hexdigest().upper()
        chunks = [digest[index:index + 4] for index in range(0, 16, 4)]
        return "TCPRO-" + "-".join(chunks)

    def validate_activation_key(self, state: LicenseState, activation_key: str) -> tuple[bool, str]:
        normalized = activation_key.strip().upper()
        if not normalized:
            return False, "Enter the activation key provided by the Technocops administrator."
        if not ACTIVATION_KEY_PATTERN.fullmatch(normalized):
            return False, "Activation key format is invalid. Expected format: TCPRO-XXXX-XXXX-XXXX-XXXX."
        if normalized != self.expected_activation_key(state.machine_id):
            return False, "This activation key does not match the current machine ID."
        return True, ""

    def activate(self, state: LicenseState, activation_key: str) -> tuple[bool, str]:
        is_valid, message = self.validate_activation_key(state, activation_key)
        if not is_valid:
            return False, message
        state.activated = True
        state.activation_key = activation_key.strip().upper()
        state.terms_accepted = True
        self.save_state(state)
        return True, "Activation completed successfully."

    def accept_terms(self, state: LicenseState) -> None:
        if state.terms_accepted:
            return
        state.terms_accepted = True
        self.save_state(state)

    def machine_id(self) -> str:
        raw_value = f"{os.environ.get('COMPUTERNAME', 'UNKNOWN')}|{uuid.getnode()}"
        digest = hashlib.sha1(raw_value.encode("utf-8")).hexdigest().upper()
        return "TC-" + digest[:12]

    @staticmethod
    def now_utc() -> datetime:
        return datetime.now(UTC)

    def _build_new_state(self) -> LicenseState:
        installed_at = self._installation_timestamp()
        expires_at = installed_at + timedelta(days=TRIAL_PERIOD_DAYS)
        return LicenseState(
            installed_at=installed_at.isoformat(),
            trial_expires_at=expires_at.isoformat(),
            terms_accepted=False,
            activated=False,
            activation_key="",
            machine_id=self.machine_id(),
        )

    def _build_locked_state(self, machine_id: str) -> LicenseState:
        installed_at = self.now_utc() - timedelta(days=TRIAL_PERIOD_DAYS + 1)
        expires_at = installed_at + timedelta(days=TRIAL_PERIOD_DAYS)
        return LicenseState(
            installed_at=installed_at.isoformat(),
            trial_expires_at=expires_at.isoformat(),
            terms_accepted=False,
            activated=False,
            activation_key="",
            machine_id=machine_id,
        )

    def _installation_timestamp(self) -> datetime:
        candidate_paths: list[Path] = []
        if getattr(sys, "frozen", False):
            candidate_paths.append(Path(sys.executable).resolve())
        candidate_paths.extend(
            [
                Path(__file__).resolve(),
                Path.cwd(),
            ]
        )

        for candidate in candidate_paths:
            try:
                timestamp = candidate.stat().st_ctime
            except OSError:
                continue
            return datetime.fromtimestamp(timestamp, UTC)
        return self.now_utc()

    def _sync_registry_copy(self, state: LicenseState) -> None:
        if self.registry_store.read_text(REGISTRY_VALUE_NAME):
            return
        payload = self.protected_storage.protect_text(self._serialize_state(state))
        self.registry_store.write_text(REGISTRY_VALUE_NAME, payload)

    def _load_state_from_file(self) -> LicenseState | None:
        if not self.license_state_path.exists():
            return None
        protected_text = self.license_state_path.read_text(encoding="utf-8").strip()
        if not protected_text:
            return None
        return self._deserialize_state(self.protected_storage.unprotect_text(protected_text))

    def _load_state_from_registry(self) -> LicenseState | None:
        protected_text = self.registry_store.read_text(REGISTRY_VALUE_NAME)
        if not protected_text:
            return None
        return self._deserialize_state(self.protected_storage.unprotect_text(protected_text))

    @staticmethod
    def _resolve_storage_dir() -> Path:
        candidates = [
            SECURE_STORAGE_DIR,
            Path(tempfile.gettempdir()) / PRODUCT_DIR_NAME / "secure",
        ]
        for candidate in candidates:
            try:
                candidate.mkdir(parents=True, exist_ok=True)
            except OSError:
                continue
            if candidate.is_dir():
                return candidate
        raise OSError("Unable to initialize secure license storage.")

    def _serialize_state(self, state: LicenseState) -> str:
        payload = json.dumps(asdict(state), sort_keys=True, separators=(",", ":"))
        wrapper = {
            "version": STATE_VERSION,
            "machine_id": state.machine_id,
            "payload": payload,
            "signature": self._state_signature(state.machine_id, payload),
        }
        return json.dumps(wrapper, sort_keys=True, separators=(",", ":"))

    def _deserialize_state(self, raw_value: str) -> LicenseState:
        wrapper = json.loads(raw_value)
        payload = wrapper.get("payload", "")
        machine_id = wrapper.get("machine_id", "")
        signature = wrapper.get("signature", "")
        version = wrapper.get("version")

        if version != STATE_VERSION:
            raise ValueError("Unsupported local license state version.")
        if not payload or not machine_id or not signature:
            raise ValueError("Incomplete local license state.")
        if signature != self._state_signature(machine_id, payload):
            raise ValueError("Local license state failed integrity validation.")

        state = LicenseState(**json.loads(payload))
        if state.machine_id != machine_id:
            raise ValueError("Machine binding mismatch in local license state.")
        return state

    @staticmethod
    def _state_signature(machine_id: str, payload: str) -> str:
        return hashlib.sha256(f"{machine_id}|{payload}|{ACTIVATION_KEY_SECRET}".encode("utf-8")).hexdigest()
