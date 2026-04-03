from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from credential_vault.inventory_workspace import read_csv_rows
from credential_vault.models import RecordType


COMMON_RECORD_FIELDS = [
    "service_name",
    "entity_id",
    "department_id",
    "account_label",
    "usage_purpose",
    "classification",
    "owner",
]

RECORD_FIELDS_BY_TYPE = {
    RecordType.WEB_LOGIN: [
        "login_url",
        "tenant_code",
        "username",
        "company_code",
        "user_code",
    ],
    RecordType.MAILBOX_ACCOUNT: [
        "host",
        "port",
        "protocol",
        "username",
        "mailbox_name",
        "use_ssl",
    ],
    RecordType.SMTP_ACCOUNT: [
        "host",
        "port",
        "username",
        "from_address",
        "use_ssl",
        "starttls",
    ],
}

AUTH_FIELDS = [
    "auth_flow",
    "otp_contact",
    "otp_owner",
    "recovery_url",
    "recovery_note",
    "mfa_note",
    "login_note",
]

BASE_REQUIRED_FIELDS = {
    RecordType.WEB_LOGIN: ["password"],
    RecordType.MAILBOX_ACCOUNT: ["password"],
    RecordType.SMTP_ACCOUNT: ["password"],
}

FALLBACK_REQUIRED_FIELDS = {
    RecordType.WEB_LOGIN: ["login_url", "username"],
    RecordType.MAILBOX_ACCOUNT: ["host", "port", "protocol", "username", "use_ssl"],
    RecordType.SMTP_ACCOUNT: ["host", "port", "username", "from_address", "use_ssl", "starttls"],
}

COMMON_TEMPLATE_FIELDS = [
    "service_name",
    "account_label",
    "classification",
    "status",
    "context_refs",
]


def build_inventory_io_bundle(
    *,
    credential_csv: Path,
    auth_csv: Path,
    output_dir: Path,
    credential_override_csv: Path | None = None,
    priorities: tuple[str, ...] = ("P1",),
    include_candidates: bool = False,
    record_refs: list[str] | None = None,
) -> dict[str, Path]:
    credential_rows = read_csv_rows(credential_csv)
    auth_rows = read_csv_rows(auth_csv)
    priority_map = _read_priority_map(credential_override_csv)

    selected_refs = _select_record_refs(
        credential_rows=credential_rows,
        priority_map=priority_map,
        priorities=priorities,
        include_candidates=include_candidates,
        record_refs=record_refs,
    )

    credential_by_ref = {
        row["vault_record_ref"].strip(): row
        for row in credential_rows
        if row.get("vault_record_ref", "").strip()
    }
    auth_by_ref = {
        row["vault_record_ref"].strip(): row
        for row in auth_rows
        if row.get("vault_record_ref", "").strip()
    }

    requirements = {"version": 1, "records": []}
    template = {"records": {}}

    for record_ref in selected_refs:
        credential_row = credential_by_ref.get(record_ref)
        if credential_row is None:
            continue
        auth_row = auth_by_ref.get(record_ref)
        requirement_item = _build_requirement_item(credential_row, auth_row)
        requirements["records"].append(requirement_item)
        template["records"][record_ref] = _build_template_record(requirement_item)

    output_dir.mkdir(parents=True, exist_ok=True)
    requirements_path = output_dir / "mail_invoice_io.requirements.yaml"
    template_path = output_dir / "mail_invoice_io.template.yaml"
    summary_path = output_dir / "mail_invoice_io.summary.yaml"

    _write_yaml(requirements_path, requirements)
    _write_yaml(template_path, template)
    _write_yaml(
        summary_path,
        {
            "record_refs": selected_refs,
            "priorities": list(priorities),
            "include_candidates": include_candidates,
            "credential_csv": credential_csv.as_posix(),
            "auth_csv": auth_csv.as_posix(),
        },
    )

    return {
        "requirements": requirements_path,
        "template": template_path,
        "summary": summary_path,
    }


def _read_priority_map(csv_path: Path | None) -> dict[str, str]:
    if csv_path is None or not csv_path.exists():
        return {}
    rows = read_csv_rows(csv_path)
    return {
        row.get("vault_record_ref", "").strip(): row.get("fill_priority", "").strip().upper()
        for row in rows
        if row.get("vault_record_ref", "").strip()
    }


def _select_record_refs(
    *,
    credential_rows: list[dict[str, str]],
    priority_map: dict[str, str],
    priorities: tuple[str, ...],
    include_candidates: bool,
    record_refs: list[str] | None,
) -> list[str]:
    if record_refs:
        return record_refs

    normalized_priorities = {priority.upper() for priority in priorities if priority.strip()}
    selected: list[str] = []
    for row in credential_rows:
        record_ref = row.get("vault_record_ref", "").strip()
        if not record_ref:
            continue
        if not include_candidates and row.get("migration_status", "").startswith("candidate"):
            continue
        if normalized_priorities and priority_map.get(record_ref, "") not in normalized_priorities:
            continue
        selected.append(record_ref)
    return selected


def _build_requirement_item(credential_row: dict[str, str], auth_row: dict[str, str] | None) -> dict[str, Any]:
    record_type = RecordType(credential_row["record_type"])
    record_data: dict[str, Any] = {}

    for field_name in COMMON_RECORD_FIELDS:
        value = _typed_value(field_name, credential_row.get(field_name, ""))
        if _is_present(value):
            record_data[field_name] = value

    context_refs = _split_context_refs(credential_row.get("context_refs", ""))
    if context_refs:
        record_data["context_refs"] = context_refs

    for field_name in RECORD_FIELDS_BY_TYPE.get(record_type, []):
        value = _typed_value(field_name, credential_row.get(field_name, ""))
        if _is_present(value):
            record_data[field_name] = value

    if auth_row is not None:
        for field_name in AUTH_FIELDS:
            value = _typed_value(field_name, auth_row.get(field_name, ""))
            if _is_present(value):
                record_data[field_name] = value

    required_fields = _required_fields(record_type, credential_row, auth_row)

    item: dict[str, Any] = {
        "record_ref": credential_row["vault_record_ref"],
        "record_type": record_type.value,
        "required_fields": required_fields,
        "record": record_data,
    }
    rotation_days = _typed_value("rotation_days", credential_row.get("rotation_days", ""))
    if rotation_days is not None:
        item["rotation_days"] = rotation_days
    return item


def _required_fields(
    record_type: RecordType,
    credential_row: dict[str, str],
    auth_row: dict[str, str] | None,
) -> list[str]:
    required_fields = list(BASE_REQUIRED_FIELDS.get(record_type, []))
    for field_name in FALLBACK_REQUIRED_FIELDS.get(record_type, []):
        if not _is_present(_typed_value(field_name, credential_row.get(field_name, ""))):
            required_fields.append(field_name)

    if record_type is RecordType.WEB_LOGIN and auth_row is not None:
        auth_flow = auth_row.get("auth_flow", "").strip()
        if not auth_flow:
            required_fields.append("auth_flow")
        if _needs_otp_owner(auth_row) and not auth_row.get("otp_owner", "").strip():
            required_fields.append("otp_owner")

    return list(dict.fromkeys(required_fields))


def _needs_otp_owner(auth_row: dict[str, str]) -> bool:
    joined = " ".join(
        auth_row.get(field_name, "")
        for field_name in ("auth_flow", "mfa_note", "login_note", "recovery_note")
    ).upper()
    return any(keyword in joined for keyword in ("OTP", "MFA", "TOTP", "追加認証"))


def _build_template_record(requirement_item: dict[str, Any]) -> dict[str, Any]:
    record_ref = requirement_item["record_ref"]
    record_type = RecordType(requirement_item["record_type"])
    record_data = requirement_item["record"]
    required_fields = set(requirement_item["required_fields"])

    template_record: dict[str, Any] = {
        "record_type": record_type.value,
    }

    for field_name in COMMON_TEMPLATE_FIELDS:
        if field_name in {"classification", "status"} or _is_present(record_data.get(field_name)):
            template_record[field_name] = _secret_ref(record_ref, field_name)

    for field_name in RECORD_FIELDS_BY_TYPE.get(record_type, []):
        if field_name in required_fields or _is_present(record_data.get(field_name)):
            template_record[field_name] = _secret_ref(record_ref, field_name)

    if record_type is RecordType.WEB_LOGIN:
        template_record["password"] = _secret_ref(record_ref, "password")
        for field_name in AUTH_FIELDS:
            if field_name in required_fields or _is_present(record_data.get(field_name)):
                template_record[field_name] = _secret_ref(record_ref, field_name)
    elif record_type in {RecordType.MAILBOX_ACCOUNT, RecordType.SMTP_ACCOUNT}:
        template_record["password"] = _secret_ref(record_ref, "password")

    return template_record


def _secret_ref(record_ref: str, field_name: str) -> str:
    return f"secret://{record_ref}#{field_name}"


def _typed_value(field_name: str, raw_value: str) -> Any:
    value = raw_value.strip()
    if not value:
        return None
    if field_name in {"port", "rotation_days"}:
        return int(value)
    if field_name in {"use_ssl", "starttls"}:
        return value.lower() in {"1", "true", "yes", "on"}
    return value


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _split_context_refs(raw_value: str) -> list[str]:
    return [value.strip() for value in raw_value.split("|") if value.strip()]


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
