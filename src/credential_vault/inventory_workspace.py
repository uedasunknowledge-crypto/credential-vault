from __future__ import annotations

import csv
from pathlib import Path

from credential_vault.inventory_seed import (
    AUTH_HEADERS,
    CHECK_HEADERS,
    CREDENTIAL_HEADERS,
    build_mail_invoice_seed,
    write_seed_csv,
)


CREDENTIAL_OVERRIDE_HEADERS = [
    "vault_record_ref",
    "service_name",
    "account_label",
    "fill_priority",
    "fill_hint",
    "source_type",
    "source_locator",
    "entity_id",
    "department_id",
    "usage_purpose",
    "login_url",
    "tenant_code",
    "host",
    "port",
    "protocol",
    "username",
    "mailbox_name",
    "from_address",
    "use_ssl",
    "starttls",
    "company_code",
    "user_code",
    "owner",
    "classification",
    "rotation_days",
    "context_refs",
    "notes",
]

AUTH_OVERRIDE_HEADERS = [
    "vault_record_ref",
    "service_name",
    "account_label",
    "fill_priority",
    "fill_hint",
    "auth_flow",
    "otp_contact",
    "otp_owner",
    "required_device",
    "recovery_url",
    "recovery_note",
    "mfa_note",
    "login_note",
]

CHECK_OVERRIDE_HEADERS = CHECK_HEADERS

CONTEXT_FIELDS = {"vault_record_ref", "service_name", "account_label"}
CLEAR_TOKEN = "__CLEAR__"


def build_mail_invoice_workspace(
    *,
    requirements_path: Path,
    service_inventory_path: Path,
    docs_root: Path,
) -> dict[str, Path]:
    credential_rows, auth_rows, check_rows = build_mail_invoice_seed(
        requirements_path=requirements_path,
        service_inventory_path=service_inventory_path,
    )

    seeds_dir = docs_root / "seeds"
    overrides_dir = docs_root / "overrides"
    working_dir = docs_root / "working"

    seed_credential_path = seeds_dir / "mail_invoice_credential_inventory_seed.csv"
    seed_auth_path = seeds_dir / "mail_invoice_auth_step_inventory_seed.csv"
    seed_check_path = seeds_dir / "mail_invoice_login_check_inventory_seed.csv"
    write_seed_csv(seed_credential_path, CREDENTIAL_HEADERS, credential_rows)
    write_seed_csv(seed_auth_path, AUTH_HEADERS, auth_rows)
    write_seed_csv(seed_check_path, CHECK_HEADERS, check_rows)

    credential_override_path = overrides_dir / "mail_invoice_credential_inventory_override.csv"
    auth_override_path = overrides_dir / "mail_invoice_auth_step_inventory_override.csv"
    check_override_path = overrides_dir / "mail_invoice_login_check_inventory_override.csv"

    sync_override_template(
        base_rows=credential_rows,
        output_path=credential_override_path,
        headers=CREDENTIAL_OVERRIDE_HEADERS,
        key_field="vault_record_ref",
        row_builder=_build_credential_override_row,
    )
    sync_override_template(
        base_rows=auth_rows,
        output_path=auth_override_path,
        headers=AUTH_OVERRIDE_HEADERS,
        key_field="vault_record_ref",
        row_builder=_build_auth_override_row,
    )
    ensure_csv_exists(check_override_path, CHECK_OVERRIDE_HEADERS)

    merged_credential_rows = merge_override_rows(
        base_rows=credential_rows,
        override_rows=read_csv_rows(credential_override_path),
        key_field="vault_record_ref",
    )
    merged_auth_rows = merge_override_rows(
        base_rows=auth_rows,
        override_rows=read_csv_rows(auth_override_path),
        key_field="vault_record_ref",
    )
    merged_check_rows = merge_check_rows(
        seed_rows=check_rows,
        override_rows=read_csv_rows(check_override_path),
    )

    working_credential_path = working_dir / "mail_invoice_credential_inventory_working.csv"
    working_auth_path = working_dir / "mail_invoice_auth_step_inventory_working.csv"
    working_check_path = working_dir / "mail_invoice_login_check_inventory_working.csv"
    write_seed_csv(working_credential_path, CREDENTIAL_HEADERS, merged_credential_rows)
    write_seed_csv(working_auth_path, AUTH_HEADERS, merged_auth_rows)
    write_seed_csv(working_check_path, CHECK_HEADERS, merged_check_rows)

    return {
        "seed_credential": seed_credential_path,
        "seed_auth": seed_auth_path,
        "seed_check": seed_check_path,
        "override_credential": credential_override_path,
        "override_auth": auth_override_path,
        "override_check": check_override_path,
        "working_credential": working_credential_path,
        "working_auth": working_auth_path,
        "working_check": working_check_path,
    }


def read_csv_rows(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.exists():
        return []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def ensure_csv_exists(csv_path: Path, headers: list[str]) -> None:
    if csv_path.exists():
        return
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()


def sync_override_template(
    *,
    base_rows: list[dict[str, str]],
    output_path: Path,
    headers: list[str],
    key_field: str,
    row_builder,
) -> None:
    existing_rows = read_csv_rows(output_path)
    existing_by_key = {row.get(key_field, "").strip(): row for row in existing_rows if row.get(key_field, "").strip()}

    for base_row in base_rows:
        key = base_row.get(key_field, "").strip()
        if not key:
            continue
        generated_row = row_builder(base_row, headers)
        if key in existing_by_key:
            for header, value in generated_row.items():
                if header.startswith("fill_"):
                    existing_by_key[key][header] = value
                    continue
                if not existing_by_key[key].get(header, "").strip():
                    existing_by_key[key][header] = value
            continue
        existing_by_key[key] = generated_row

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in existing_by_key.values():
            writer.writerow({header: row.get(header, "") for header in headers})


def merge_override_rows(
    *,
    base_rows: list[dict[str, str]],
    override_rows: list[dict[str, str]],
    key_field: str,
) -> list[dict[str, str]]:
    merged_by_key = {row.get(key_field, "").strip(): dict(row) for row in base_rows if row.get(key_field, "").strip()}

    for override_row in override_rows:
        key = override_row.get(key_field, "").strip()
        if not key:
            continue
        merged_row = dict(merged_by_key.get(key, {}))
        for field_name, raw_value in override_row.items():
            if field_name == key_field:
                merged_row[field_name] = key
                continue
            if field_name not in merged_row:
                continue
            if raw_value == "":
                continue
            if raw_value == CLEAR_TOKEN:
                merged_row[field_name] = ""
            else:
                merged_row[field_name] = raw_value
        merged_by_key[key] = merged_row

    return list(merged_by_key.values())


def merge_check_rows(*, seed_rows: list[dict[str, str]], override_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    merged_by_key: dict[tuple[str, str, str, str], dict[str, str]] = {}
    for row in seed_rows:
        merged_by_key[_check_key(row)] = dict(row)
    for row in override_rows:
        if not any(value.strip() for value in row.values()):
            continue
        merged_by_key[_check_key(row)] = dict(row)
    return list(merged_by_key.values())


def _check_key(row: dict[str, str]) -> tuple[str, str, str, str]:
    return (
        row.get("vault_record_ref", "").strip(),
        row.get("checked_at", "").strip(),
        row.get("checked_by", "").strip(),
        row.get("check_method", "").strip(),
    )


def _build_credential_override_row(base_row: dict[str, str], headers: list[str]) -> dict[str, str]:
    row = {header: "" for header in headers}
    for header in CONTEXT_FIELDS:
        row[header] = base_row.get(header, "")
    row["fill_priority"] = _credential_fill_priority(base_row)
    row["fill_hint"] = _credential_fill_hint(base_row)
    return row


def _build_auth_override_row(base_row: dict[str, str], headers: list[str]) -> dict[str, str]:
    row = {header: "" for header in headers}
    for header in CONTEXT_FIELDS:
        row[header] = base_row.get(header, "")
    row["fill_priority"] = _auth_fill_priority(base_row)
    row["fill_hint"] = _auth_fill_hint(base_row)
    return row


def _credential_fill_priority(base_row: dict[str, str]) -> str:
    record_ref = base_row.get("vault_record_ref", "")
    if record_ref in {"MAILBOX_PRIMARY", "SMTP_PRIMARY", "VISA_VPASS"}:
        return "P1"
    if record_ref.startswith("candidate:"):
        return "P2"
    return "P3"


def _credential_fill_hint(base_row: dict[str, str]) -> str:
    record_ref = base_row.get("vault_record_ref", "")
    record_type = base_row.get("record_type", "")
    if record_ref == "MAILBOX_PRIMARY":
        return "source_type/source_locator/entity_id/owner を先に埋める。host は現行 POP 情報から確認。"
    if record_ref == "SMTP_PRIMARY":
        return "source_type/source_locator/entity_id/owner を先に埋める。host/from_address は現行 SMTP 設定から確認。"
    if record_ref == "VISA_VPASS":
        return "mail-invoice の現行運用で使うため最優先。entity_id/owner と source locator を確定。"
    if record_ref.startswith("candidate:") and record_type == "web_login":
        return "まず source locator と entity_id を特定し、実運用するものだけ candidate を real record へ昇格。"
    return "owner と source locator を埋める。"


def _auth_fill_priority(base_row: dict[str, str]) -> str:
    record_ref = base_row.get("vault_record_ref", "")
    if record_ref == "VISA_VPASS":
        return "P1"
    if record_ref.startswith("candidate:"):
        return "P2"
    return "P3"


def _auth_fill_hint(base_row: dict[str, str]) -> str:
    record_ref = base_row.get("vault_record_ref", "")
    if record_ref == "VISA_VPASS":
        return "auth_flow、otp_owner、追加認証要否、復旧時の担当確認を先に埋める。"
    if record_ref == "candidate:JCB":
        return "OTP/MFA 対応候補なので auth_flow と otp_owner を確認。"
    if record_ref == "candidate:GMO":
        return "OTP なし前提の候補。auth_flow を password_only などで確定。"
    return "auth_flow を先に埋め、MFA があるなら otp_contact/otp_owner を追加。"
