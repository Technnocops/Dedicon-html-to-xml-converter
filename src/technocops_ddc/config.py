from __future__ import annotations

import os
import sys
from pathlib import Path

from . import APP_NAME, APP_VERSION, APP_VERSION_LABEL, COMPANY_NAME

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _resolve_runtime_root() -> Path:
    candidates: list[Path] = []

    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        candidates.append(Path(meipass))

    if getattr(sys, "frozen", False):
        executable_dir = Path(sys.executable).resolve().parent
        candidates.extend([executable_dir / "_internal", executable_dir])

    candidates.append(PROJECT_ROOT)

    for candidate in candidates:
        if (candidate / "assets").exists():
            return candidate
    return PROJECT_ROOT


RUNTIME_ROOT = _resolve_runtime_root()
ASSETS_DIR = RUNTIME_ROOT / "assets"
PACKAGING_DIR = PROJECT_ROOT / "packaging"
RELEASE_DIR = PROJECT_ROOT / "release"
PRODUCT_DIR_NAME = "Technocops_DDC_Converter_HTML_to_XML_Pro"
REGISTRY_LICENSE_PATH = rf"Software\{COMPANY_NAME}\{PRODUCT_DIR_NAME}"
LOGO_PATH = ASSETS_DIR / "logo.svg"
BRANDING_DIR = ASSETS_DIR / "branding"
APP_LOGO_PATH = BRANDING_DIR / "Dedicon-removebg-preview.png"
APP_ICON_PATH = BRANDING_DIR / "technocops_app_icon.ico"
SPLASH_IMAGE_PATH = BRANDING_DIR / "technocops_splash.png"
DTBOOK_DTD_PATH = ASSETS_DIR / "dtd" / "dtbook-basic.dtd"
APPDATA_ROOT = Path(
    os.environ.get(
        "TECHNOCOPS_DDC_APPDATA_DIR",
        os.environ.get("LOCALAPPDATA", str(PROJECT_ROOT / ".appdata")),
    )
)
APPDATA_DIR = APPDATA_ROOT / PRODUCT_DIR_NAME
SECURE_STORAGE_DIR = APPDATA_DIR / "secure"
LICENSE_STATE_PATH = SECURE_STORAGE_DIR / "license_state.dat"

SUPPORTED_HTML_EXTENSIONS = {".html", ".htm"}
SUPPORTED_DROP_EXTENSIONS = SUPPORTED_HTML_EXTENSIONS | {".zip"}

DEFAULT_LANGUAGE = "en"
DEFAULT_DOC_TYPE = "sv"
TRIAL_PERIOD_DAYS = 3
ACTIVATION_KEY_SECRET = "technocops-ddc-pro-2026-admin"

DEFAULT_GITHUB_REPOSITORY = "https://github.com/Technnocops/Dedicon-html-to-xml-converter"
GITHUB_REPOSITORY = os.environ.get("TECHNOCOPS_DDC_GITHUB_REPO", DEFAULT_GITHUB_REPOSITORY).strip()
GITHUB_RELEASE_API = "https://api.github.com/repos/{repository}/releases/latest"
HTTP_TIMEOUT_SECONDS = 15
TEMP_DIR_PREFIX = "technocops_ddc_"
ALLOW_DEBUG_ENV = "TECHNOCOPS_DDC_ALLOW_DEBUG"

WINDOW_TITLE = f"{APP_NAME} ({APP_VERSION_LABEL})"
COPYRIGHT_LABEL = f"\u00a9 2026 {COMPANY_NAME}"
