from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from technocops_ddc.services.license_service import LicenseService


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a Technocops DDC Converter Pro activation key.")
    parser.add_argument("--machine-id", required=True, help="Machine ID shown in the application")
    args = parser.parse_args()

    service = LicenseService()
    print(service.expected_activation_key(args.machine_id.strip().upper()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
