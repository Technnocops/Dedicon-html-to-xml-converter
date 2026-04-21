from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import requests

from technocops_ddc.config import APPDATA_DIR, GITHUB_RELEASE_API, GITHUB_REPOSITORY, HTTP_TIMEOUT_SECONDS
from technocops_ddc.models import UpdateInfo

DownloadProgressCallback = Callable[[int, int | None], None]


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
        preferred_asset = self._select_preferred_asset(assets)
        release_notes = payload.get("body", "").strip()

        return UpdateInfo(
            version=latest_version,
            published_at=str(payload.get("published_at", "")),
            summary=release_notes[:1200],
            html_url=str(payload.get("html_url", "")),
            asset_url=str(preferred_asset.get("browser_download_url", "")),
            asset_name=str(preferred_asset.get("name", "")),
        )

    def download_update(
        self,
        update_info: UpdateInfo,
        download_dir: Path | None = None,
        progress_callback: DownloadProgressCallback | None = None,
    ) -> Path:
        if not update_info.asset_url:
            raise ValueError("No installer package is available for this release.")

        asset_name = update_info.asset_name or f"Technocops_DDC_Converter_Update_{update_info.version}.exe"
        extension = Path(asset_name).suffix.lower()
        if extension not in {".exe", ".msi"}:
            raise ValueError("Automatic updates require an installer package (.exe or .msi).")

        target_dir = download_dir or (APPDATA_DIR / "updates" / update_info.version)
        target_dir.mkdir(parents=True, exist_ok=True)
        destination = target_dir / asset_name

        with self.session.get(update_info.asset_url, stream=True, timeout=HTTP_TIMEOUT_SECONDS) as response:
            response.raise_for_status()
            total_bytes = int(response.headers.get("Content-Length", "0") or 0)
            downloaded_bytes = 0
            if progress_callback is not None:
                progress_callback(0, total_bytes or None)
            with destination.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 512):
                    if chunk:
                        handle.write(chunk)
                        downloaded_bytes += len(chunk)
                        if progress_callback is not None:
                            progress_callback(downloaded_bytes, total_bytes or None)

        return destination

    @staticmethod
    def default_restart_path() -> Path | None:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve()
        return None

    def start_background_update(
        self,
        installer_path: Path,
        parent_pid: int | None = None,
        restart_path: Path | None = None,
    ) -> None:
        if os.name != "nt":
            raise RuntimeError("Automatic updates are only supported on Windows builds.")

        installer_extension = installer_path.suffix.lower()
        if installer_extension not in {".exe", ".msi"}:
            raise ValueError("Automatic updates require an installer package (.exe or .msi).")

        helper_path = installer_path.parent / "run_technocops_update.ps1"
        helper_path.write_text(self._background_updater_script(), encoding="utf-8")

        command = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-File",
            str(helper_path),
            "-InstallerPath",
            str(installer_path),
            "-ParentPid",
            str(parent_pid or os.getpid()),
        ]
        if restart_path is not None:
            command.extend(["-RestartPath", str(restart_path)])

        creation_flags = 0
        for flag_name in ("DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP", "CREATE_NO_WINDOW"):
            creation_flags |= getattr(subprocess, flag_name, 0)

        subprocess.Popen(
            command,
            close_fds=True,
            creationflags=creation_flags,
        )

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

    @staticmethod
    def _select_preferred_asset(assets: list[dict]) -> dict:
        for extension in (".exe", ".msi", ".zip"):
            for asset in assets:
                name = str(asset.get("name", "")).lower()
                if name.endswith(extension):
                    return asset
        return assets[0] if assets else {}

    @staticmethod
    def _background_updater_script() -> str:
        return textwrap.dedent(
            """\
            param(
                [Parameter(Mandatory = $true)][string]$InstallerPath,
                [Parameter(Mandatory = $true)][int]$ParentPid,
                [string]$RestartPath = ""
            )

            $ErrorActionPreference = "Stop"

            try {
                Wait-Process -Id $ParentPid -ErrorAction SilentlyContinue
                Start-Sleep -Seconds 1

                $extension = [System.IO.Path]::GetExtension($InstallerPath).ToLowerInvariant()
                if ($extension -eq ".msi") {
                    $arguments = @("/i", ('"{0}"' -f $InstallerPath), "/qn", "/norestart")
                    $process = Start-Process -FilePath "msiexec.exe" -ArgumentList $arguments -PassThru -Wait
                }
                else {
                    $arguments = @("/SP-", "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NOCANCEL", "/NORESTART", "/CLOSEAPPLICATIONS", "/FORCECLOSEAPPLICATIONS")
                    $process = Start-Process -FilePath $InstallerPath -ArgumentList $arguments -PassThru -Wait
                }

                if ($process.ExitCode -eq 0 -and $RestartPath -and (Test-Path -LiteralPath $RestartPath)) {
                    Start-Process -FilePath $RestartPath | Out-Null
                }
            }
            finally {
                Start-Sleep -Seconds 1
                Remove-Item -LiteralPath $InstallerPath -Force -ErrorAction SilentlyContinue
                Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue
            }
            """
        )
