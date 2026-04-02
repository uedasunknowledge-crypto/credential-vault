from credential_vault.models import ApiSecretRecord, MailboxAccountRecord, WebLoginRecord


def test_web_login_dedup_identity_includes_account_context() -> None:
    record = WebLoginRecord(
        record_id="rec_web_001",
        service_name="freee-admin",
        entity_id="C02",
        department_id="D01",
        account_label="経理管理者",
        login_url="https://accounts.secure.freee.co.jp/",
        company_code="C02",
        user_code="admin@example.com",
        password="secret",
    )

    assert record.dedup_identity() == (
        "web_login",
        "freee-admin",
        "C02",
        "D01",
        "経理管理者",
        "https://accounts.secure.freee.co.jp/",
        "C02",
        "admin@example.com",
    )


def test_api_secret_display_name_uses_entity_and_label() -> None:
    record = ApiSecretRecord(
        record_id="rec_api_001",
        service_name="notion",
        entity_id="C02",
        account_label="本番API",
        secret_key_name="NOTION_TOKEN",
        secret_value="secret",
    )

    assert record.display_name() == "notion / C02 / 本番API"


def test_mailbox_account_dedup_identity_keeps_server_and_account_together() -> None:
    record = MailboxAccountRecord(
        record_id="rec_mbx_001",
        service_name="mail-invoice",
        entity_id="C02",
        department_id="OPS",
        account_label="請求書受信POP",
        host="mail.example.com",
        port=995,
        protocol="pop3",
        username="billing@example.com",
        password="secret",
        mailbox_name="INBOX",
        context_refs=["biz:C02", "project:mail-invoice"],
    )

    assert record.dedup_identity() == (
        "mailbox_account",
        "mail-invoice",
        "C02",
        "OPS",
        "請求書受信POP",
        "mail.example.com",
        "995",
        "pop3",
        "billing@example.com",
        "INBOX",
    )
