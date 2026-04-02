from pathlib import Path

from credential_vault.models import MailboxAccountRecord
from credential_vault.requirements import build_record_from_requirement, load_requirement_spec, missing_requirements
from credential_vault.vault_store import VaultDocument


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
