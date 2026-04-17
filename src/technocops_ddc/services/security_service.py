from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

from technocops_ddc.config import ALLOW_DEBUG_ENV, ASSETS_DIR
from technocops_ddc.security_manifest import ASSET_INTEGRITY_HASHES
from technocops_ddc.services.windows_security import WindowsRuntimeGuard


@dataclass(slots=True)
class SecurityStatus:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_ok(self) -> bool:
        return not self.errors


class SecurityService:
    def run_startup_checks(self) -> SecurityStatus:
        status = SecurityStatus()
        self._append_debugger_status(status)
        self._append_asset_integrity_status(status)
        return status

    def _append_debugger_status(self, status: SecurityStatus) -> None:
        if os.environ.get(ALLOW_DEBUG_ENV, "").strip() == "1":
            return
        if WindowsRuntimeGuard.debugger_attached():
            status.errors.append("A debugger was detected. This protected build cannot continue.")

    def _append_asset_integrity_status(self, status: SecurityStatus) -> None:
        if not ASSET_INTEGRITY_HASHES:
            status.warnings.append("Asset integrity manifest is empty. Rebuild the release package before distribution.")
            return

        for relative_path, expected_hash in ASSET_INTEGRITY_HASHES.items():
            asset_path = ASSETS_DIR / Path(relative_path)
            if not asset_path.exists():
                status.errors.append(f"Required asset is missing: {relative_path}")
                continue

            current_hash = hashlib.sha256(asset_path.read_bytes()).hexdigest()
            if current_hash != expected_hash:
                status.errors.append(f"Asset integrity check failed for: {relative_path}")
