from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from credential_vault.inventory_io import build_inventory_io_bundle  # noqa: E402


def parse_args() -> argparse.Namespace:
    docs_root = PROJECT_ROOT / "docs"
    parser = argparse.ArgumentParser(description="mail-invoice の入出力テスト用 bundle を生成する。")
    parser.add_argument(
        "--credential-csv",
        type=Path,
        default=docs_root / "working" / "mail_invoice_credential_inventory_working.csv",
        help="資格情報 working CSV",
    )
    parser.add_argument(
        "--auth-csv",
        type=Path,
        default=docs_root / "working" / "mail_invoice_auth_step_inventory_working.csv",
        help="認証手順 working CSV",
    )
    parser.add_argument(
        "--credential-override-csv",
        type=Path,
        default=docs_root / "overrides" / "mail_invoice_credential_inventory_override.csv",
        help="資格情報 override CSV",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=docs_root / "generated",
        help="生成先ディレクトリ",
    )
    parser.add_argument(
        "--priority",
        action="append",
        default=["P1"],
        help="対象に含める fill_priority。複数指定可",
    )
    parser.add_argument(
        "--record-ref",
        action="append",
        default=[],
        help="個別に含める vault_record_ref。指定時は priority フィルタより優先",
    )
    parser.add_argument(
        "--include-candidates",
        action="store_true",
        help="candidate 行も対象に含める",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    outputs = build_inventory_io_bundle(
        credential_csv=args.credential_csv,
        auth_csv=args.auth_csv,
        credential_override_csv=args.credential_override_csv,
        output_dir=args.output_dir,
        priorities=tuple(args.priority),
        include_candidates=args.include_candidates,
        record_refs=args.record_ref or None,
    )
    for name, path in outputs.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
