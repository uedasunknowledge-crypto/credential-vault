from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from credential_vault.inventory_review import build_priority_actions, review_inventory_csvs  # noqa: E402


def parse_args() -> argparse.Namespace:
    working_dir = PROJECT_ROOT / "docs" / "working"
    seeds_dir = PROJECT_ROOT / "docs" / "seeds"
    overrides_dir = PROJECT_ROOT / "docs" / "overrides"
    parser = argparse.ArgumentParser(description="mail-invoice の移行台帳 seed を review する。")
    parser.add_argument(
        "--credential-csv",
        type=Path,
        default=_prefer_working(
            working_dir / "mail_invoice_credential_inventory_working.csv",
            seeds_dir / "mail_invoice_credential_inventory_seed.csv",
        ),
    )
    parser.add_argument(
        "--auth-csv",
        type=Path,
        default=_prefer_working(
            working_dir / "mail_invoice_auth_step_inventory_working.csv",
            seeds_dir / "mail_invoice_auth_step_inventory_seed.csv",
        ),
    )
    parser.add_argument(
        "--check-csv",
        type=Path,
        default=_prefer_working(
            working_dir / "mail_invoice_login_check_inventory_working.csv",
            seeds_dir / "mail_invoice_login_check_inventory_seed.csv",
        ),
    )
    parser.add_argument(
        "--credential-override-csv",
        type=Path,
        default=overrides_dir / "mail_invoice_credential_inventory_override.csv",
    )
    parser.add_argument(
        "--auth-override-csv",
        type=Path,
        default=overrides_dir / "mail_invoice_auth_step_inventory_override.csv",
    )
    parser.add_argument("--json", action="store_true", help="JSON 形式で出力する")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = review_inventory_csvs(args.credential_csv, args.auth_csv, args.check_csv)
    if args.json:
        print(report.to_json())
    else:
        print(report.to_text(), end="")
        actions = build_priority_actions(
            credential_override_csv=args.credential_override_csv,
            auth_override_csv=args.auth_override_csv,
        )
        if actions:
            print(f"priority_queue: {len(actions)}")
            for action in actions:
                line = f"[{action.priority}] {action.area} {action.key}"
                if action.hint:
                    line += f": {action.hint}"
                print(line)
    return 0


def _prefer_working(working_path: Path, seed_path: Path) -> Path:
    if working_path.exists():
        return working_path
    return seed_path


if __name__ == "__main__":
    raise SystemExit(main())
