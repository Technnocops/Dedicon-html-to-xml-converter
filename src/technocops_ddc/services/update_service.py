from __future__ import annotations

import os
import tempfile
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

import requests

from technocops_ddc.config import GITHUB_RELEASE_API, GITHUB_REPOSITORY, HTTP_TIMEOUT_SECONDS
from technocops_ddc.models import UpdateInfo


class UpdateService:
    def __init__(self, repository: str | None = None) -> None:
        self.repository = self._normalize_repository(repository or GITHUB_REPOSITORY)
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/vnd.github+json"})

    @property
    def is_configured(self) -> bool:
        return bool(self.repository)

    def check_for_update(self, current_version: str) -> UpdateInfo | None:
        if not self.is_configured:
            return None

        response = self.session.get(
            GITHUB_RELEASE_API.format(repository=self.repository),
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        payload = response.json()
        latest_version = str(payload.get("tag_name", "")).lstrip("v")
        if not latest_version or self._version_tuple(latest_version) <= self._version_tuple(current_version):
            return None

        assets = payload.get("assets", [])
        preferred_asset = next(
            (asset for asset in assets if str(asset.get("name", "")).lower().endswith((".exe", ".msi", ".zip"))),
            assets[0] if assets else {},
        )
        release_notes = payload.get("body", "").strip()

        return UpdateInfo(
            version=latest_version,
            published_at=str(payload.get("published_at", "")),
            summary=release_notes[:1200],
            html_url=str(payload.get("html_url", "")),
            asset_url=str(preferred_asset.get("browser_download_url", "")),
            asset_name=str(preferred_asset.get("name", "")),
        )

    def download_update(self, update_info: UpdateInfo, download_dir: Path | None = None) -> Path | None:
        if not update_info.asset_url:
            self.open_release_page(update_info)
            return None

        target_dir = download_dir or Path(tempfile.mkdtemp(prefix="technocops_update_"))
        target_dir.mkdir(parents=True, exist_ok=True)
        destination = target_dir / (update_info.asset_name or "technocops_ddc_update.exe")

        with self.session.get(update_info.asset_url, stream=True, timeout=HTTP_TIMEOUT_SECONDS) as response:
            response.raise_for_status()
            with destination.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 512):
                    if chunk:
                        handle.write(chunk)

        return destination

    @staticmethod
    def open_release_page(update_info: UpdateInfo) -> None:
        if update_info.html_url:
            webbrowser.open(update_info.html_url)

    @staticmethod
    def launch_update(path: Path) -> None:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
            return
        webbrowser.open(path.as_uri())

    @staticmethod
    def _version_tuple(version: str) -> tuple[int, ...]:
        normalized = version.replace("-", ".").replace("_", ".")
        parts = []
        for part in normalized.split("."):
            if part.isdigit():
                parts.append(int(part))
            else:
                digits = "".join(character for character in part if character.isdigit())
                parts.append(int(digits) if digits else 0)
        return tuple(parts)

    @staticmethod
    def _normalize_repository(value: str) -> str:
        raw_value = value.strip()
        if not raw_value:
            return ""

        candidate = raw_value
        if "github.com" in raw_value:
            parsed = urlparse(raw_value if "://" in raw_value else f"https://{raw_value}")
            path_parts = [part for part in parsed.path.split("/") if part]
            if len(path_parts) >= 2:
                owner = path_parts[0]
                repository = path_parts[1].removesuffix(".git")
                return f"{owner}/{repository}"

        return candidate.strip("/").removesuffix(".git")
