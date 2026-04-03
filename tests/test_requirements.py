from pathlib import Path

from credential_vault.models import MailboxAccountRecord, RecordType, WebLoginRecord
from credential_vault.requirements import (
    CredentialRequirement,
    build_record_from_requirement,
    load_requirement_spec,
    missing_requirements,
    resolve_requirement_record,
    sync_requirement_aliases,
)
from credential_vault.vault_store import VaultDocument


def test_resolve_requirement_record_falls_back_to_unique_metadata_match() -> None:
    document = VaultDocument.empty()
    document.upsert_record(
        MailboxAccountRecord(
            record_id="rec_mbx_001",
            service_name="mail-invoice",
            entity_id="C02",
            account_label="請求書受信POP",
            usage_purpose="Bill One 請求書取込",
            context_refs=["project:mail-invoice", "tool:billone"],
            host="mail.example.com",
            port=995,
            protocol="pop3",
            username="billing@example.com",
            password="secret",
            use_ssl=True,
        )
    )

    requirement = CredentialRequirement(
        record_ref="MAILBOX_PRIMARY",
        record_type=RecordType.MAILBOX_ACCOUNT,
        required_fields=["host", "port", "protocol", "username", "password", "use_ssl"],
        aliases=[],
        record_data={
            "service_name": "mail-invoice",
            "entity_id": "C02",
            "account_label": "請求書受信POP",
            "usage_purpose": "Bill One 請求書取込",
            "context_refs": ["project:mail-invoice"],
            "protocol": "pop3",
            "use_ssl": True,
        },
    )

    record = resolve_requirement_record(document, requirement)

    assert record is not None
    assert record.record_id == "rec_mbx_001"
    assert sync_requirement_aliases(document, [requirement]) is True
    assert document.get_record("MAILBOX_PRIMARY") is not None


def test_resolve_requirement_record_skips_ambiguous_metadata_match() -> None:
    document = VaultDocument.empty()
    document.upsert_record(
        WebLoginRecord(
            record_id="rec_web_001",
            service_name="visa-vpass",
            account_label="本部",
            login_url="https://www3.vpass.ne.jp/kamei/top/index.jsp?cc=009",
            username="head@example.com",
            password="secret-1",
        )
    )
    document.upsert_record(
        WebLoginRecord(
            record_id="rec_web_002",
            service_name="visa-vpass",
            account_label="営業",
            login_url="https://www3.vpass.ne.jp/kamei/top/index.jsp?cc=009",
            username="sales@example.com",
            password="secret-2",
        )
    )

    requirement = CredentialRequirement(
        record_ref="VISA_VPASS",
        record_type=RecordType.WEB_LOGIN,
        required_fields=["login_url", "username", "password"],
        aliases=[],
        record_data={
            "service_name": "visa-vpass",
            "login_url": "https://www3.vpass.ne.jp/kamei/top/index.jsp?cc=009",
        },
    )

    assert resolve_requirement_record(document, requirement) is None
    assert sync_requirement_aliases(document, [requirement]) is False


def test_missing_requirements_detects_absent_mailbox_record(tmp_path: Path) -> None:
    spec_path = tmp_path / "requirements.yaml"
    spec_path.write_text(
        '\n'.join(
            [
                "records:",
                "  - record_ref: MAILBOX_PRIMARY",
                "    record_type: mailbox_account",
                "    required_fields: [host, port, protocol, username, password, use_ssl]",
                "    record:",
                "      service_name: mail-invoice",
                "      entity_id: C02",
                "      account_label: 請求書受信POP",
                "      protocol: pop3",
                "      use_ssl: true",
                "",
            ]
        ),
        encoding="utf-8",
    )

    requirements = load_requirement_spec(spec_path)
    missing = missing_requirements(VaultDocument.empty(), requirements)

    assert len(missing) == 1
    assert missing[0].requirement.record_ref == "MAILBOX_PRIMARY"
    assert missing[0].missing_fields == ["host", "port", "username", "password"]


def test_build_record_from_requirement_uses_alias_when_record_ref_is_not_record_id(tmp_path: Path) -> None:
    spec_path = tmp_path / "requirements.yaml"
    spec_path.write_text(
        '\n'.join(
            [
                "records:",
                "  - record_ref: MAILBOX_PRIMARY",
                "    record_type: mailbox_account",
                "    aliases: [mail-invoice:C02:請求書受信POP]",
                "    required_fields: [host, port, protocol, username, password, use_ssl]",
                "    record:",
                "      service_name: mail-invoice",
                "      entity_id: C02",
                "      account_label: 請求書受信POP",
                "      protocol: pop3",
                "      use_ssl: true",
                "      context_refs: [biz:C02, project:mail-invoice]",
                "",
            ]
        ),
        encoding="utf-8",
    )

    requirement = load_requirement_spec(spec_path)[0]
    record, aliases = build_record_from_requirement(
        requirement=requirement,
        submitted_fields={
            "host": "mail.example.com",
            "port": 995,
            "protocol": "pop3",
            "username": "billing@example.com",
            "password": "secret",
            "use_ssl": True,
        },
        existing_record=None,
        existing_ids=[],
    )

    assert isinstance(record, MailboxAccountRecord)
    assert record.record_id.startswith("rec_mbx_")
    assert "MAILBOX_PRIMARY" in aliases
    assert "mail-invoice:C02:請求書受信POP" in aliases
