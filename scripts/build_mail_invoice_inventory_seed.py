from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from credential_vault.inventory_seed import (  # noqa: E402
    AUTH_HEADERS,
    CHECK_HEADERS,
    CREDENTIAL_HEADERS,
    build_mail_invoice_seed,
    write_seed_csv,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="mail-invoice-processor 由来の移行台帳 seed を生成する。")
    parser.add_argument(
        "--requirements-path",
        type=Path,
        default=PROJECT_ROOT.parent / "mail-invoice-processor" / "config" / "local.runtime.requirements.yaml",
        help="mail-invoice-processor の requirements YAML",
    )
    parser.add_argument(
        "--service-inventory-path",
        type=Path,
        default=PROJECT_ROOT.parent / "mail-invoice-processor" / "docs" / "service-automation-inventory.csv",
        help="mail-invoice-processor の service inventory CSV",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "docs" / "seeds",
        help="seed CSV の出力先ディレクトリ",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    credential_rows, auth_rows, check_rows = build_mail_invoice_seed(
        requirements_path=args.requirements_path,
        service_inventory_path=args.service_inventory_path,
    )

    write_seed_csv(args.output_dir / "mail_invoice_credential_inventory_seed.csv", CREDENTIAL_HEADERS, credential_rows)
    write_seed_csv(args.output_dir / "mail_invoice_auth_step_inventory_seed.csv", AUTH_HEADERS, auth_rows)
    write_seed_csv(args.output_dir / "mail_invoice_login_check_inventory_seed.csv", CHECK_HEADERS, check_rows)

    print(f"Generated: {args.output_dir / 'mail_invoice_credential_inventory_seed.csv'}")
    print(f"Generated: {args.output_dir / 'mail_invoice_auth_step_inventory_seed.csv'}")
    print(f"Generated: {args.output_dir / 'mail_invoice_login_check_inventory_seed.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
