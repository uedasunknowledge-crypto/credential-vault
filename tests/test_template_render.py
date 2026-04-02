from credential_vault.models import ApiSecretRecord, MailboxAccountRecord, WebLoginRecord
from credential_vault.template_render import record_field_value, render_template_file
from credential_vault.vault_store import VaultDocument


def test_record_field_value_supports_web_login_password_and_username() -> None:
    record = WebLoginRecord(
        record_id="rec_web_001",
        service_name="freee-admin",
        username="admin@example.com",
        password="secret-password",
        login_url="https://accounts.secure.freee.co.jp/",
    )

    assert record_field_value(record, "username") == "admin@example.com"
    assert record_field_value(record, "password") == "secret-password"


def test_render_template_file_resolves_secret_refs(tmp_path) -> None:
    template_path = tmp_path / "runtime.template.yaml"
    template_path.write_text(
        '\n'.join(
            [
                'mailbox:',
                '  password: "secret://MAILBOX_PASS#value"',
                'portal_accounts:',
                '  FUJI:',
                '    username: "secret://rec_web_001#username"',
                '    password: "secret://rec_web_001#password"',
                '',
            ]
        ),
        encoding="utf-8",
    )

    document = VaultDocument.empty()
    document.upsert_record(
        ApiSecretRecord(
            record_id="rec_api_001",
            service_name="mailbox",
            secret_key_name="MAILBOX_PASS",
            secret_value="pop-secret",
        ),
        aliases=["MAILBOX_PASS"],
    )
    document.upsert_record(
        WebLoginRecord(
            record_id="rec_web_001",
            service_name="fuji",
            username="portal-user@example.com",
            password="portal-secret",
            login_url="https://example.com/login",
        )
    )

    rendered = render_template_file(template_path, document)

    assert "pop-secret" in rendered
    assert "portal-user@example.com" in rendered
    assert "portal-secret" in rendered


def test_render_template_file_keeps_mailbox_types(tmp_path) -> None:
    template_path = tmp_path / "runtime.template.yaml"
    template_path.write_text(
        '\n'.join(
            [
                'mailbox:',
                '  host: "secret://rec_mbx_001#host"',
                '  port: "secret://rec_mbx_001#port"',
                '  use_ssl: "secret://rec_mbx_001#use_ssl"',
                '',
            ]
        ),
        encoding="utf-8",
    )

    document = VaultDocument.empty()
    document.upsert_record(
        MailboxAccountRecord(
            record_id="rec_mbx_001",
            service_name="mail-invoice",
            host="mail.example.com",
            port=995,
            protocol="pop3",
            username="billing@example.com",
            password="pop-secret",
            use_ssl=True,
        )
    )

    rendered = render_template_file(template_path, document)

    assert "host: mail.example.com" in rendered
    assert "port: 995" in rendered
    assert "use_ssl: true" in rendered


def test_record_field_value_supports_mailbox_account_fields() -> None:
    record = MailboxAccountRecord(
        record_id="rec_mbx_001",
        service_name="mail-invoice",
        host="mail.example.com",
        port=995,
        protocol="pop3",
        username="billing@example.com",
        password="pop-secret",
        use_ssl=True,
        mailbox_name="INBOX",
    )

    assert record_field_value(record, "host") == "mail.example.com"
    assert record_field_value(record, "username") == "billing@example.com"
    assert record_field_value(record, "password") == "pop-secret"
    assert record_field_value(record, "port") == 995
