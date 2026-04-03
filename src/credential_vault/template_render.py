from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from credential_vault.models import (
    ApiSecretRecord,
    MailboxAccountRecord,
    MachineSecretRecord,
    SecretRecord,
    SmtpAccountRecord,
    WebLoginRecord,
)
from credential_vault.vault_store import VaultDocument


SECRET_REF_PATTERN = re.compile(r"^secret://(?P<record_ref>[^#]+)#(?P<field>[A-Za-z0-9_]+)$")


class SecretTemplateError(Exception):
    """テンプレート解決エラー。"""


def render_template_file(template_path: Path, document: VaultDocument) -> str:
    suffix = template_path.suffix.lower()
    raw_text = template_path.read_text(encoding="utf-8")

    if suffix in {".yaml", ".yml"}:
        data = yaml.safe_load(raw_text)
        rendered = _resolve_node(data, document)
        return yaml.safe_dump(rendered, allow_unicode=True, sort_keys=False)

    if suffix == ".json":
        data = json.loads(raw_text)
        rendered = _resolve_node(data, document)
        return json.dumps(rendered, ensure_ascii=False, indent=2) + "\n"

    raise SecretTemplateError(f"unsupported template format: {template_path.suffix}")


def resolve_secret_ref(document: VaultDocument, secret_ref: str) -> Any:
    match = SECRET_REF_PATTERN.match(secret_ref)
    if not match:
        raise SecretTemplateError(f"invalid secret ref: {secret_ref}")

    record_ref = match.group("record_ref")
    field_name = match.group("field")
    record = document.get_record(record_ref)
    if record is None:
        raise SecretTemplateError(f"record not found for template: {record_ref}")

    value = record_field_value(record, field_name)
    if value is None:
        raise SecretTemplateError(f"field not found: {record.record_id}#{field_name}")

    return value


def record_field_value(record: SecretRecord, field_name: str) -> Any | None:
    common_fields = {
        "record_id": record.record_id,
        "service_name": record.service_name,
        "entity_id": record.entity_id,
        "department_id": record.department_id,
        "account_label": record.account_label,
        "usage_purpose": record.usage_purpose,
        "context_refs": ",".join(record.context_refs),
        "classification": record.classification.value,
        "status": record.status.value,
        "description": record.description,
        "owner": record.owner,
        "last_verified_at": record.last_verified_at.isoformat() if record.last_verified_at else None,
        "last_tested_at": record.last_tested_at.isoformat() if record.last_tested_at else None,
        "last_tested_by": record.last_tested_by,
        "last_test_status": record.last_test_status.value,
        "last_test_note": record.last_test_note,
    }
    if field_name in common_fields:
        return common_fields[field_name]

    if isinstance(record, ApiSecretRecord):
        api_fields = {
            "value": record.secret_value,
            "secret_value": record.secret_value,
            "secret_key_name": record.secret_key_name,
            "environment": record.environment,
            "scope": record.scope,
            "issuer": record.issuer,
        }
        if field_name in api_fields:
            return api_fields[field_name]

    if isinstance(record, WebLoginRecord):
        login_fields = {
            "value": record.password,
            "login_url": record.login_url,
            "tenant_code": record.tenant_code,
            "company_code": record.company_code,
            "user_code": record.user_code,
            "username": record.username,
            "password": record.password,
            "auth_flow": record.auth_flow,
            "otp_contact": record.otp_contact,
            "otp_owner": record.otp_owner,
            "recovery_url": record.recovery_url,
            "recovery_note": record.recovery_note,
            "mfa_note": record.mfa_note,
            "login_note": record.login_note,
        }
        if field_name in login_fields:
            return login_fields[field_name]

    if isinstance(record, MachineSecretRecord):
        machine_fields = {
            "value": record.secret_value,
            "secret_value": record.secret_value,
            "provider": record.provider,
            "consumer": record.consumer,
            "transport_mode": record.transport_mode,
        }
        if field_name in machine_fields:
            return machine_fields[field_name]

    if isinstance(record, MailboxAccountRecord):
        mailbox_fields = {
            "value": record.password,
            "host": record.host,
            "port": record.port,
            "protocol": record.protocol,
            "username": record.username,
            "password": record.password,
            "use_ssl": record.use_ssl,
            "mailbox_name": record.mailbox_name,
        }
        if field_name in mailbox_fields:
            return mailbox_fields[field_name]

    if isinstance(record, SmtpAccountRecord):
        smtp_fields = {
            "value": record.password,
            "host": record.host,
            "port": record.port,
            "username": record.username,
            "password": record.password,
            "from_address": record.from_address,
            "use_ssl": record.use_ssl,
            "starttls": record.starttls,
        }
        if field_name in smtp_fields:
            return smtp_fields[field_name]

    return None


def _resolve_node(node: Any, document: VaultDocument) -> Any:
    if isinstance(node, dict):
        return {key: _resolve_node(value, document) for key, value in node.items()}

    if isinstance(node, list):
        return [_resolve_node(item, document) for item in node]

    if isinstance(node, str) and SECRET_REF_PATTERN.match(node):
        return resolve_secret_ref(document, node)

    return node
