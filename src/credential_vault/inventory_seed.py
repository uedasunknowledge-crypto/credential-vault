from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from credential_vault.requirements import CredentialRequirement, load_requirement_spec


LOGIN_DETECTION_KEYS = {"scheduled_login", "mail_notice_login"}
PUBLIC_LOGIN_URLS = {
    "VISA_VPASS": "https://www3.vpass.ne.jp/kamei/top/index.jsp?cc=009",
    "FUJIFILM_BI_DIRECT": "https://direct-fb.fujifilm.com/ap1/ebilling/invoicelist",
    "SAGAWA_SMART_CLUB": "https://www.e-service.sagawa-exp.co.jp/portal/do/login/show?fr=bs",
}
SERVICE_NAME_BY_VENDOR = {
    "VISA_VPASS": "visa-vpass",
    "FUJIFILM_BI_DIRECT": "fujifilm-bi-direct",
    "SAGAWA_SMART_CLUB": "sagawa-smart-club",
    "SANICLEAN": "saniclean",
    "GMO": "gmo",
    "JCB": "jcb",
}

CREDENTIAL_HEADERS = [
    "migration_status",
    "source_type",
    "source_locator",
    "service_name",
    "record_type",
    "entity_id",
    "department_id",
    "account_label",
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
    "classification",
    "rotation_days",
    "owner",
    "context_refs",
    "vault_record_ref",
    "notes",
]

AUTH_HEADERS = [
    "vault_record_ref",
    "service_name",
    "account_label",
    "auth_flow",
    "otp_contact",
    "otp_owner",
    "required_device",
    "recovery_url",
    "recovery_note",
    "mfa_note",
    "login_note",
]

CHECK_HEADERS = [
    "vault_record_ref",
    "checked_at",
    "checked_by",
    "target_kind",
    "check_status",
    "check_method",
    "result_summary",
    "next_action",
]


def read_service_inventory(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def build_mail_invoice_seed(
    requirements_path: Path,
    service_inventory_path: Path,
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    requirements = load_requirement_spec(requirements_path)
    service_rows = read_service_inventory(service_inventory_path)

    credential_rows: list[dict[str, str]] = []
    auth_rows: list[dict[str, str]] = []
    check_rows: list[dict[str, str]] = []
    credential_row_by_ref: dict[str, dict[str, str]] = {}
    auth_row_by_ref: dict[str, dict[str, str]] = {}

    requirement_ref_by_vendor: dict[str, str] = {}

    for requirement in requirements:
        credential_row = _credential_row_from_requirement(requirement, requirements_path)
        credential_rows.append(credential_row)
        credential_row_by_ref[requirement.record_ref] = credential_row
        if requirement.record_type.value == "web_login":
            auth_row = _auth_row_from_requirement(requirement)
            auth_rows.append(auth_row)
            auth_row_by_ref[requirement.record_ref] = auth_row

        vendor_code = _vendor_code_from_requirement(requirement)
        if vendor_code:
            requirement_ref_by_vendor[vendor_code] = requirement.record_ref

    for row in service_rows:
        detection_key = row.get("取得可能化検知方式キー", "")
        if detection_key not in LOGIN_DETECTION_KEYS:
            continue

        vendor_code = row.get("取引先コード", "").strip()
        if not vendor_code:
            continue

        seed_ref = requirement_ref_by_vendor.get(vendor_code, f"candidate:{vendor_code}")
        if vendor_code not in requirement_ref_by_vendor:
            credential_row = _credential_row_from_service_inventory(row, seed_ref, service_inventory_path)
            auth_row = _auth_row_from_service_inventory(row, seed_ref)
            credential_rows.append(credential_row)
            auth_rows.append(auth_row)
            credential_row_by_ref[seed_ref] = credential_row
            auth_row_by_ref[seed_ref] = auth_row
        else:
            _enrich_rows_from_service_inventory(
                credential_row=credential_row_by_ref.get(seed_ref),
                auth_row=auth_row_by_ref.get(seed_ref),
                service_row=row,
            )

        check_row = _check_row_from_service_inventory(row, seed_ref)
        if check_row is not None:
            check_rows.append(check_row)

    return credential_rows, auth_rows, check_rows


def write_seed_csv(output_path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def _credential_row_from_requirement(requirement: CredentialRequirement, source_path: Path) -> dict[str, str]:
    record_data = requirement.record_data
    return {
        "migration_status": "seed_from_requirement",
        "source_type": "code_requirement",
        "source_locator": _portable_path(source_path),
        "service_name": str(record_data.get("service_name", "")),
        "record_type": requirement.record_type.value,
        "entity_id": str(record_data.get("entity_id", "") or ""),
        "department_id": str(record_data.get("department_id", "") or ""),
        "account_label": str(record_data.get("account_label", "") or ""),
        "usage_purpose": str(record_data.get("usage_purpose", "") or ""),
        "login_url": str(record_data.get("login_url", "") or ""),
        "tenant_code": str(record_data.get("tenant_code", "") or ""),
        "host": str(record_data.get("host", "") or ""),
        "port": _stringify(record_data.get("port")),
        "protocol": str(record_data.get("protocol", "") or ""),
        "username": str(record_data.get("username", "") or ""),
        "mailbox_name": str(record_data.get("mailbox_name", "") or ""),
        "from_address": str(record_data.get("from_address", "") or ""),
        "use_ssl": _stringify(record_data.get("use_ssl")),
        "starttls": _stringify(record_data.get("starttls")),
        "company_code": str(record_data.get("company_code", "") or ""),
        "user_code": str(record_data.get("user_code", "") or ""),
        "classification": str(record_data.get("classification", "") or ""),
        "rotation_days": _stringify(requirement.rotation_days),
        "owner": str(record_data.get("owner", "") or ""),
        "context_refs": _join_context_refs(record_data.get("context_refs", [])),
        "vault_record_ref": requirement.record_ref,
        "notes": (
            f"required_fields={','.join(requirement.required_fields)}; "
            f"aliases={','.join(requirement.aliases) or '-'}"
        ),
    }


def _auth_row_from_requirement(requirement: CredentialRequirement) -> dict[str, str]:
    record_data = requirement.record_data
    return {
        "vault_record_ref": requirement.record_ref,
        "service_name": str(record_data.get("service_name", "")),
        "account_label": str(record_data.get("account_label", "") or ""),
        "auth_flow": str(record_data.get("auth_flow", "") or ""),
        "otp_contact": str(record_data.get("otp_contact", "") or ""),
        "otp_owner": str(record_data.get("otp_owner", "") or ""),
        "required_device": "",
        "recovery_url": str(record_data.get("recovery_url", "") or ""),
        "recovery_note": str(record_data.get("recovery_note", "") or ""),
        "mfa_note": str(record_data.get("mfa_note", "") or ""),
        "login_note": str(record_data.get("login_note", "") or ""),
    }


def _credential_row_from_service_inventory(row: dict[str, str], seed_ref: str, source_path: Path) -> dict[str, str]:
    vendor_code = row["取引先コード"].strip()
    detection_key = row.get("取得可能化検知方式キー", "")
    document_key = row.get("文書種別キー", "")
    return {
        "migration_status": "candidate_from_service_inventory",
        "source_type": "service_inventory",
        "source_locator": _portable_path(source_path),
        "service_name": SERVICE_NAME_BY_VENDOR.get(vendor_code, vendor_code.lower().replace("_", "-")),
        "record_type": "web_login",
        "entity_id": "",
        "department_id": "",
        "account_label": row.get("サービス名", ""),
        "usage_purpose": f"{row.get('文書種別', '')} / {row.get('取得可能化検知方式', '')}".strip(" /"),
        "login_url": PUBLIC_LOGIN_URLS.get(vendor_code, ""),
        "tenant_code": "",
        "host": "",
        "port": "",
        "protocol": "",
        "username": "",
        "mailbox_name": "",
        "from_address": "",
        "use_ssl": "",
        "starttls": "",
        "company_code": "",
        "user_code": "",
        "classification": "P2a",
        "rotation_days": "",
        "owner": "",
        "context_refs": _join_context_refs(
            [
                "project:mail-invoice",
                f"vendor:{vendor_code}",
                f"document:{document_key}" if document_key else "",
                f"workflow:{detection_key}" if detection_key else "",
            ]
        ),
        "vault_record_ref": seed_ref,
        "notes": " / ".join(
            part
            for part in [
                row.get("実装状況", ""),
                row.get("検証状況", ""),
                row.get("進捗概要", ""),
                row.get("補足", ""),
                row.get("次のアクション", ""),
            ]
            if part
        ),
    }


def _auth_row_from_service_inventory(row: dict[str, str], seed_ref: str) -> dict[str, str]:
    vendor_code = row["取引先コード"].strip()
    auth_flow = ""
    mfa_note = ""
    if vendor_code == "GMO":
        mfa_note = row.get("補足", "")
    elif vendor_code == "JCB":
        mfa_note = row.get("補足", "")
    elif vendor_code == "VISA_VPASS":
        mfa_note = "追加認証要否は要確認"

    return {
        "vault_record_ref": seed_ref,
        "service_name": SERVICE_NAME_BY_VENDOR.get(vendor_code, vendor_code.lower().replace("_", "-")),
        "account_label": row.get("サービス名", ""),
        "auth_flow": auth_flow,
        "otp_contact": "",
        "otp_owner": "",
        "required_device": "Edge または Chrome" if vendor_code in {"VISA_VPASS", "FUJIFILM_BI_DIRECT", "SAGAWA_SMART_CLUB"} else "",
        "recovery_url": PUBLIC_LOGIN_URLS.get(vendor_code, ""),
        "recovery_note": row.get("次のアクション", ""),
        "mfa_note": mfa_note,
        "login_note": row.get("補足", ""),
    }


def _check_row_from_service_inventory(row: dict[str, str], seed_ref: str) -> dict[str, str] | None:
    checked_at = row.get("最終確認日", "").strip()
    if not checked_at:
        return None

    verification_key = row.get("検証状況キー", "")
    check_status = "ok" if verification_key == "verified" else "attention"
    return {
        "vault_record_ref": seed_ref,
        "checked_at": checked_at,
        "checked_by": "inventory-import",
        "target_kind": "web_login",
        "check_status": check_status,
        "check_method": row.get("取得可能化検知方式キー", ""),
        "result_summary": row.get("進捗概要", ""),
        "next_action": row.get("次のアクション", ""),
    }


def _enrich_rows_from_service_inventory(
    *,
    credential_row: dict[str, str] | None,
    auth_row: dict[str, str] | None,
    service_row: dict[str, str],
) -> None:
    if credential_row is not None:
        extra_note = " / ".join(
            part
            for part in [
                service_row.get("実装状況", ""),
                service_row.get("検証状況", ""),
                service_row.get("進捗概要", ""),
                service_row.get("補足", ""),
            ]
            if part
        )
        if extra_note:
            credential_row["notes"] = " / ".join(part for part in [credential_row["notes"], extra_note] if part)

    if auth_row is None:
        return

    vendor_code = service_row.get("取引先コード", "").strip()
    if not auth_row.get("required_device") and vendor_code in {"VISA_VPASS", "FUJIFILM_BI_DIRECT", "SAGAWA_SMART_CLUB"}:
        auth_row["required_device"] = "Edge または Chrome"
    if not auth_row.get("recovery_url"):
        auth_row["recovery_url"] = PUBLIC_LOGIN_URLS.get(vendor_code, "")
    if not auth_row.get("recovery_note"):
        auth_row["recovery_note"] = service_row.get("次のアクション", "")
    if not auth_row.get("login_note"):
        auth_row["login_note"] = service_row.get("補足", "")
    if not auth_row.get("mfa_note") and vendor_code == "VISA_VPASS":
        auth_row["mfa_note"] = "追加認証要否は要確認"


def _join_context_refs(values: Any) -> str:
    if not isinstance(values, list):
        return ""
    return "|".join(str(value) for value in values if str(value).strip())


def _vendor_code_from_requirement(requirement: CredentialRequirement) -> str:
    for context_ref in requirement.record_data.get("context_refs", []):
        if isinstance(context_ref, str) and context_ref.startswith("vendor:"):
            return context_ref.split(":", maxsplit=1)[1].strip()
    if requirement.record_ref.isupper():
        return requirement.record_ref
    return ""


def _portable_path(path: Path) -> str:
    return path.as_posix()


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    return str(value)
