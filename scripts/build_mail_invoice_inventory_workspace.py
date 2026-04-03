from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from credential_vault.inventory_workspace import build_mail_invoice_workspace  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="mail-invoice の seed / override / working 台帳をまとめて更新する。")
    parser.add_argument(
        "--requirements-path",
        type=Path,
        default=PROJECT_ROOT.parent / "mail-invoice-processor" / "config" / "local.runtime.requirements.yaml",
    )
    parser.add_argument(
        "--service-inventory-path",
        type=Path,
        default=PROJECT_ROOT.parent / "mail-invoice-processor" / "docs" / "service-automation-inventory.csv",
    )
    parser.add_argument(
        "--docs-root",
        type=Path,
        default=PROJECT_ROOT / "docs",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    outputs = build_mail_invoice_workspace(
        requirements_path=args.requirements_path,
        service_inventory_path=args.service_inventory_path,
        docs_root=args.docs_root,
    )
    for label, path in outputs.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
