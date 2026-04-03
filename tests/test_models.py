from credential_vault.models import ApiSecretRecord, CheckStatus, MailboxAccountRecord, WebLoginRecord, record_from_dict


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


def test_record_from_dict_preserves_web_login_auth_and_check_fields() -> None:
    record = record_from_dict(
        {
            "record_id": "rec_web_001",
            "record_type": "web_login",
            "service_name": "freee-admin",
            "account_label": "経理管理者",
            "login_url": "https://accounts.secure.freee.co.jp/",
            "username": "admin@example.com",
            "password": "secret",
            "auth_flow": "password_plus_totp",
            "otp_contact": "Google Authenticator",
            "otp_owner": "経理責任者",
            "recovery_url": "https://accounts.secure.freee.co.jp/password_resets/new",
            "recovery_note": "再設定は責任者確認後のみ実施",
            "last_test_status": "attention",
            "last_tested_by": "kouhe",
            "last_test_note": "バックアップコード所在を再確認する",
        }
    )

    assert isinstance(record, WebLoginRecord)
    assert record.auth_flow == "password_plus_totp"
    assert record.otp_owner == "経理責任者"
    assert record.last_test_status is CheckStatus.ATTENTION
    assert record.last_test_note == "バックアップコード所在を再確認する"
