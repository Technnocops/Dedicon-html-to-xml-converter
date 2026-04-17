from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = PROJECT_ROOT / "assets"
OUTPUT_PATH = PROJECT_ROOT / "src" / "technocops_ddc" / "security_manifest.py"
TRACKED_ASSETS = (
    "branding/Dedicon-removebg-preview.png",
    "branding/technocops_app_icon.ico",
    "branding/technocops_splash.png",
    "dtd/dtbook-basic.dtd",
)


def sha256_for(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    hashes = {relative_path: sha256_for(ASSETS_DIR / relative_path) for relative_path in TRACKED_ASSETS}
    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat()

    lines = [
        f'GENERATED_AT = "{generated_at}"',
        "ASSET_INTEGRITY_HASHES = {",
    ]
    for relative_path, digest in hashes.items():
        lines.append(f'    "{relative_path}": "{digest}",')
    lines.append("}")
    lines.append("")

    OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(OUTPUT_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
