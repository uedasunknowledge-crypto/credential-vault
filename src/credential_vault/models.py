from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


def utc_now() -> datetime:
    return datetime.now(UTC)


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


class Classification(str, Enum):
    P1A = "P1a"
    P1B = "P1b"
    P2A = "P2a"
    P2B = "P2b"
    P3 = "P3"


class RecordType(str, Enum):
    API_SECRET = "api_secret"
    WEB_LOGIN = "web_login"
    MACHINE_SECRET = "machine_secret"
    MAILBOX_ACCOUNT = "mailbox_account"
    SMTP_ACCOUNT = "smtp_account"


class RecordStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ROTATION_DUE = "rotation_due"
    ROTATING = "rotating"
    REVOKED = "revoked"
    RETIRED = "retired"


class RotationMode(str, Enum):
    MANUAL = "manual"
    ASSISTED = "assisted"
    AUTOMATIC = "automatic"


class CheckStatus(str, Enum):
    UNKNOWN = "unknown"
    OK = "ok"
    ATTENTION = "attention"
    FAILED = "failed"


@dataclass(slots=True)
class RotationPolicy:
    """更新周期に関する最低限の情報。"""

    mode: RotationMode = RotationMode.MANUAL
    interval_days: int | None = None
    notify_before_days: int = 7

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "interval_days": self.interval_days,
            "notify_before_days": self.notify_before_days,
        }


@dataclass(slots=True)
class SecretRecord:
    """共通メタデータを持つ基底レコード。"""

    record_id: str
    record_type: RecordType = field(init=False)
    service_name: str
    entity_id: str | None = None
    department_id: str | None = None
    account_label: str | None = None
    usage_purpose: str | None = None
    context_refs: list[str] = field(default_factory=list)
    classification: Classification = Classification.P1B
    status: RecordStatus = RecordStatus.ACTIVE
    description: str = ""
    tags: list[str] = field(default_factory=list)
    owner: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    last_verified_at: datetime | None = None
    last_tested_at: datetime | None = None
    last_tested_by: str | None = None
    last_test_status: CheckStatus = CheckStatus.UNKNOWN
    last_test_note: str = ""
    rotation_policy: RotationPolicy = field(default_factory=RotationPolicy)
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    fingerprint: str | None = None

    def display_name(self) -> str:
        parts = [self.service_name]
        if self.entity_id:
            parts.append(self.entity_id)
        if self.account_label:
            parts.append(self.account_label)
        return " / ".join(parts)

    def dedup_identity(self) -> tuple[str, ...]:
        return tuple(
            value
            for value in (
                self.record_type.value,
                self.service_name,
                self.entity_id,
                self.department_id,
                self.account_label,
                self.usage_purpose,
            )
            if value
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.update(
            {
                "record_type": self.record_type.value,
                "classification": self.classification.value,
                "status": self.status.value,
                "last_test_status": self.last_test_status.value,
                "rotation_policy": self.rotation_policy.to_dict(),
            }
        )
        for key in ("created_at", "updated_at", "last_verified_at", "last_tested_at", "expires_at", "revoked_at"):
            value = getattr(self, key)
            data[key] = value.isoformat() if value else None
        return data


@dataclass(slots=True)
class ApiSecretRecord(SecretRecord):
    secret_key_name: str = ""
    secret_value: str = ""
    scope: str | None = None
    issuer: str | None = None
    environment: str | None = None

    def __post_init__(self) -> None:
        self.record_type = RecordType.API_SECRET

    def dedup_identity(self) -> tuple[str, ...]:
        return tuple(
            value
            for value in (
                self.record_type.value,
                self.service_name,
                self.entity_id,
                self.environment,
                self.secret_key_name,
            )
            if value
        )


@dataclass(slots=True)
class WebLoginRecord(SecretRecord):
    login_url: str = ""
    tenant_code: str | None = None
    company_code: str | None = None
    user_code: str | None = None
    username: str | None = None
    password: str = ""
    auth_flow: str | None = None
    otp_contact: str | None = None
    otp_owner: str | None = None
    recovery_url: str | None = None
    recovery_note: str | None = None
    mfa_note: str | None = None
    login_note: str | None = None

    def __post_init__(self) -> None:
        self.record_type = RecordType.WEB_LOGIN

    def dedup_identity(self) -> tuple[str, ...]:
        return tuple(
            value
            for value in (
                self.record_type.value,
                self.service_name,
                self.entity_id,
                self.department_id,
                self.account_label,
                self.login_url,
                self.tenant_code,
                self.company_code,
                self.user_code,
                self.username,
            )
            if value
        )


@dataclass(slots=True)
class MachineSecretRecord(SecretRecord):
    consumer: str = ""
    provider: str = ""
    secret_value: str = ""
    transport_mode: str | None = None

    def __post_init__(self) -> None:
        self.record_type = RecordType.MACHINE_SECRET

    def dedup_identity(self) -> tuple[str, ...]:
        return tuple(
            value
            for value in (
                self.record_type.value,
                self.provider,
                self.consumer,
                self.transport_mode,
            )
            if value
        )


@dataclass(slots=True)
class MailboxAccountRecord(SecretRecord):
    host: str = ""
    port: int | None = None
    protocol: str = "pop3"
    username: str = ""
    password: str = ""
    use_ssl: bool = True
    mailbox_name: str | None = None

    def __post_init__(self) -> None:
        self.record_type = RecordType.MAILBOX_ACCOUNT

    def dedup_identity(self) -> tuple[str, ...]:
        values = [
            self.record_type.value,
            self.service_name,
            self.entity_id,
            self.department_id,
            self.account_label,
            self.host,
            str(self.port) if self.port is not None else None,
            self.protocol,
            self.username,
            self.mailbox_name,
        ]
        return tuple(value for value in values if value)


@dataclass(slots=True)
class SmtpAccountRecord(SecretRecord):
    host: str = ""
    port: int | None = None
    username: str = ""
    password: str = ""
    from_address: str = ""
    use_ssl: bool = True
    starttls: bool = False

    def __post_init__(self) -> None:
        self.record_type = RecordType.SMTP_ACCOUNT

    def dedup_identity(self) -> tuple[str, ...]:
        values = [
            self.record_type.value,
            self.service_name,
            self.entity_id,
            self.department_id,
            self.account_label,
            self.host,
            str(self.port) if self.port is not None else None,
            self.username,
            self.from_address,
        ]
        return tuple(value for value in values if value)


def record_from_dict(data: dict[str, Any]) -> SecretRecord:
    common_kwargs = {
        "record_id": data["record_id"],
        "service_name": data["service_name"],
        "entity_id": data.get("entity_id"),
        "department_id": data.get("department_id"),
        "account_label": data.get("account_label"),
        "usage_purpose": data.get("usage_purpose"),
        "context_refs": list(data.get("context_refs", [])),
        "classification": Classification(data.get("classification", Classification.P1B.value)),
        "status": RecordStatus(data.get("status", RecordStatus.ACTIVE.value)),
        "description": data.get("description", ""),
        "tags": list(data.get("tags", [])),
        "owner": data.get("owner"),
        "created_at": parse_datetime(data.get("created_at")) or utc_now(),
        "updated_at": parse_datetime(data.get("updated_at")) or utc_now(),
        "last_verified_at": parse_datetime(data.get("last_verified_at")),
        "last_tested_at": parse_datetime(data.get("last_tested_at")),
        "last_tested_by": data.get("last_tested_by"),
        "last_test_status": CheckStatus(data.get("last_test_status", CheckStatus.UNKNOWN.value)),
        "last_test_note": data.get("last_test_note", ""),
        "rotation_policy": RotationPolicy(
            mode=RotationMode(data.get("rotation_policy", {}).get("mode", RotationMode.MANUAL.value)),
            interval_days=data.get("rotation_policy", {}).get("interval_days"),
            notify_before_days=data.get("rotation_policy", {}).get("notify_before_days", 7),
        ),
        "expires_at": parse_datetime(data.get("expires_at")),
        "revoked_at": parse_datetime(data.get("revoked_at")),
        "fingerprint": data.get("fingerprint"),
    }

    record_type = RecordType(data["record_type"])

    if record_type is RecordType.API_SECRET:
        return ApiSecretRecord(
            **common_kwargs,
            secret_key_name=data.get("secret_key_name", ""),
            secret_value=data.get("secret_value", ""),
            scope=data.get("scope"),
            issuer=data.get("issuer"),
            environment=data.get("environment"),
        )

    if record_type is RecordType.WEB_LOGIN:
        return WebLoginRecord(
            **common_kwargs,
            login_url=data.get("login_url", ""),
            tenant_code=data.get("tenant_code"),
            company_code=data.get("company_code"),
            user_code=data.get("user_code"),
            username=data.get("username"),
            password=data.get("password", ""),
            auth_flow=data.get("auth_flow"),
            otp_contact=data.get("otp_contact"),
            otp_owner=data.get("otp_owner"),
            recovery_url=data.get("recovery_url"),
            recovery_note=data.get("recovery_note"),
            mfa_note=data.get("mfa_note"),
            login_note=data.get("login_note"),
        )

    if record_type is RecordType.MACHINE_SECRET:
        return MachineSecretRecord(
            **common_kwargs,
            consumer=data.get("consumer", ""),
            provider=data.get("provider", ""),
            secret_value=data.get("secret_value", ""),
            transport_mode=data.get("transport_mode"),
        )

    if record_type is RecordType.MAILBOX_ACCOUNT:
        return MailboxAccountRecord(
            **common_kwargs,
            host=data.get("host", ""),
            port=data.get("port"),
            protocol=data.get("protocol", "pop3"),
            username=data.get("username", ""),
            password=data.get("password", ""),
            use_ssl=bool(data.get("use_ssl", True)),
            mailbox_name=data.get("mailbox_name"),
        )

    if record_type is RecordType.SMTP_ACCOUNT:
        return SmtpAccountRecord(
            **common_kwargs,
            host=data.get("host", ""),
            port=data.get("port"),
            username=data.get("username", ""),
            password=data.get("password", ""),
            from_address=data.get("from_address", ""),
            use_ssl=bool(data.get("use_ssl", True)),
            starttls=bool(data.get("starttls", False)),
        )

    raise ValueError(f"未対応の record_type です: {record_type}")
