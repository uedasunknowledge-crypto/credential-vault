from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from credential_vault.identifiers import next_record_id
from credential_vault.models import Classification, RecordType, RotationMode, RotationPolicy, SecretRecord, record_from_dict
from credential_vault.template_render import record_field_value
from credential_vault.vault_store import VaultDocument


@dataclass(slots=True)
class FieldSpec:
    label: str
    input_type: str
    secret: bool = False


FIELD_SPECS: dict[RecordType, dict[str, FieldSpec]] = {
    RecordType.API_SECRET: {
        "secret_key_name": FieldSpec("Secret Key Name", "text"),
        "secret_value": FieldSpec("Secret Value", "password", secret=True),
        "environment": FieldSpec("Environment", "text"),
    },
    RecordType.WEB_LOGIN: {
        "login_url": FieldSpec("Login URL", "text"),
        "company_code": FieldSpec("Company Code", "text"),
        "user_code": FieldSpec("User Code", "text"),
        "username": FieldSpec("Username", "text"),
        "password": FieldSpec("Password", "password", secret=True),
    },
    RecordType.MAILBOX_ACCOUNT: {
        "host": FieldSpec("Host", "text"),
        "port": FieldSpec("Port", "number"),
        "protocol": FieldSpec("Protocol", "text"),
        "username": FieldSpec("Username", "text"),
        "password": FieldSpec("Password", "password", secret=True),
        "use_ssl": FieldSpec("Use SSL", "checkbox"),
        "mailbox_name": FieldSpec("Mailbox Name", "text"),
    },
    RecordType.SMTP_ACCOUNT: {
        "host": FieldSpec("Host", "text"),
        "port": FieldSpec("Port", "number"),
        "username": FieldSpec("Username", "text"),
        "password": FieldSpec("Password", "password", secret=True),
        "from_address": FieldSpec("From Address", "text"),
        "use_ssl": FieldSpec("Use SSL", "checkbox"),
        "starttls": FieldSpec("Use STARTTLS", "checkbox"),
    },
}


@dataclass(slots=True)
class CredentialRequirement:
    record_ref: str
    record_type: RecordType
    required_fields: list[str]
    record_data: dict[str, Any]
    aliases: list[str] = field(default_factory=list)
    rotation_days: int | None = None


@dataclass(slots=True)
class RequirementStatus:
    requirement: CredentialRequirement
    record: SecretRecord | None
    missing_fields: list[str]

    @property
    def is_satisfied(self) -> bool:
        return not self.missing_fields


def load_requirement_spec(spec_path: Path) -> list[CredentialRequirement]:
    raw_data = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
    records = raw_data.get("records", [])
    if not isinstance(records, list):
        raise ValueError("requirements spec の records はリストである必要があります。")

    requirements: list[CredentialRequirement] = []
    for raw_item in records:
        if not isinstance(raw_item, dict):
            raise ValueError("requirements spec の各 record はオブジェクトである必要があります。")

        record_ref = _require_str(raw_item, "record_ref")
        record_type = RecordType(_require_str(raw_item, "record_type"))
        required_fields = [str(field_name) for field_name in raw_item.get("required_fields", [])]
        aliases = [str(alias) for alias in raw_item.get("aliases", [])]
        rotation_days = raw_item.get("rotation_days")
        record_data = raw_item.get("record", {})
        if not isinstance(record_data, dict):
            raise ValueError(f"{record_ref}.record はオブジェクトである必要があります。")
        if "service_name" not in record_data:
            raise ValueError(f"{record_ref}.record.service_name は必須です。")

        requirements.append(
            CredentialRequirement(
                record_ref=record_ref,
                record_type=record_type,
                required_fields=required_fields,
                record_data=dict(record_data),
                aliases=aliases,
                rotation_days=int(rotation_days) if rotation_days is not None else None,
            )
        )

    return requirements


def evaluate_requirements(document: VaultDocument, requirements: list[CredentialRequirement]) -> list[RequirementStatus]:
    statuses: list[RequirementStatus] = []
    for requirement in requirements:
        record = resolve_requirement_record(document, requirement)
        missing_fields = _missing_fields_for_requirement(record, requirement)
        if record is not None and record.record_type is not requirement.record_type:
            raise ValueError(
                f"record type mismatch: {requirement.record_ref} expected {requirement.record_type.value} but got {record.record_type.value}"
            )
        statuses.append(RequirementStatus(requirement=requirement, record=record, missing_fields=missing_fields))
    return statuses


def missing_requirements(document: VaultDocument, requirements: list[CredentialRequirement]) -> list[RequirementStatus]:
    return [status for status in evaluate_requirements(document, requirements) if not status.is_satisfied]


def resolve_requirement_record(document: VaultDocument, requirement: CredentialRequirement) -> SecretRecord | None:
    candidate_refs = [requirement.record_ref, *requirement.aliases]
    for record_ref in candidate_refs:
        record = document.get_record(record_ref)
        if record is not None:
            return record
    return None


def sync_requirement_aliases(document: VaultDocument, requirements: list[CredentialRequirement]) -> bool:
    changed = False
    for requirement in requirements:
        record = resolve_requirement_record(document, requirement)
        if record is None:
            continue

        aliases_to_add: list[str] = []
        if requirement.record_ref != record.record_id and document.resolve_record_id(requirement.record_ref) is None:
            aliases_to_add.append(requirement.record_ref)

        for alias in requirement.aliases:
            if alias != record.record_id and document.resolve_record_id(alias) is None:
                aliases_to_add.append(alias)

        if aliases_to_add:
            document.upsert_record(record, aliases=aliases_to_add)
            changed = True

    return changed


def field_specs_for_requirement(requirement: CredentialRequirement) -> dict[str, FieldSpec]:
    return FIELD_SPECS.get(requirement.record_type, {})


def build_record_from_requirement(
    requirement: CredentialRequirement,
    submitted_fields: dict[str, Any],
    existing_record: SecretRecord | None,
    existing_ids: list[str],
) -> tuple[SecretRecord, list[str]]:
    if existing_record is not None and existing_record.record_type is not requirement.record_type:
        raise ValueError(
            f"record type mismatch: {requirement.record_ref} expected {requirement.record_type.value} but got {existing_record.record_type.value}"
        )

    record_id = _resolve_record_id(requirement, existing_record, existing_ids)
    payload = existing_record.to_dict() if existing_record is not None else {}
    payload.update(requirement.record_data)
    payload.update(submitted_fields)
    payload["record_id"] = record_id
    payload["record_type"] = requirement.record_type.value
    payload["updated_at"] = datetime.now(UTC).isoformat()

    if requirement.rotation_days is not None:
        payload["rotation_policy"] = RotationPolicy(
            mode=RotationMode.MANUAL,
            interval_days=requirement.rotation_days,
            notify_before_days=7,
        ).to_dict()
        payload["expires_at"] = (datetime.now(UTC) + timedelta(days=requirement.rotation_days)).isoformat()

    secret_value = _secret_value_from_payload(requirement.record_type, payload)
    if secret_value:
        payload["fingerprint"] = hashlib.sha256(secret_value.encode("utf-8")).hexdigest()[:16]

    record = record_from_dict(payload)
    aliases = list(requirement.aliases)
    if requirement.record_ref != record.record_id:
        aliases.insert(0, requirement.record_ref)
    return record, aliases


def required_field_value(record: SecretRecord | None, field_name: str) -> Any | None:
    if record is None:
        return None
    return record_field_value(record, field_name)


def parse_form_value(record_type: RecordType, field_name: str, raw_value: str | None) -> Any:
    field_spec = field_specs_for_requirement(
        CredentialRequirement(
            record_ref="",
            record_type=record_type,
            required_fields=[],
            record_data={},
        )
    ).get(field_name)
    if field_spec is None:
        return raw_value

    if field_spec.input_type == "checkbox":
        return raw_value == "on"
    if field_spec.input_type == "number":
        if raw_value is None or not raw_value.strip():
            return None
        return int(raw_value.strip())
    if raw_value is None:
        return ""
    return raw_value.strip()


def is_missing_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict)):
        return not value
    return False


def _missing_fields_for_requirement(record: SecretRecord | None, requirement: CredentialRequirement) -> list[str]:
    missing_fields: list[str] = []
    for field_name in requirement.required_fields:
        value = required_field_value(record, field_name)
        if record is None:
            value = requirement.record_data.get(field_name)
        if is_missing_value(value):
            missing_fields.append(field_name)
    return missing_fields


def _resolve_record_id(requirement: CredentialRequirement, existing_record: SecretRecord | None, existing_ids: list[str]) -> str:
    if existing_record is not None:
        return existing_record.record_id
    if requirement.record_ref.startswith("rec_"):
        return requirement.record_ref
    return next_record_id(requirement.record_type, existing_ids)


def _secret_value_from_payload(record_type: RecordType, payload: dict[str, Any]) -> str:
    if record_type is RecordType.API_SECRET:
        return str(payload.get("secret_value", "") or "")
    if record_type in {RecordType.WEB_LOGIN, RecordType.MAILBOX_ACCOUNT, RecordType.SMTP_ACCOUNT}:
        return str(payload.get("password", "") or "")
    return ""


def _require_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} は空でない文字列である必要があります。")
    return value.strip()
