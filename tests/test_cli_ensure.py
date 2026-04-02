import io

from credential_vault.cli import main


def test_cli_ensure_reports_missing_requirements(monkeypatch, tmp_path, capsys) -> None:
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

    monkeypatch.setenv("CREDENTIAL_VAULT_ROOT", str(tmp_path))
    monkeypatch.setenv("CREDENTIAL_VAULT_MASTER_PASSWORD", "master-password")
    monkeypatch.setenv("CREDENTIAL_VAULT_MASTER_PASSWORD_CONFIRM", "master-password")

    assert main(["init"]) == 0
    assert main(["ensure", "--spec", str(spec_path), "--json"]) == 22

    output = capsys.readouterr()
    assert '"status": "missing"' in output.out
    assert '"record_ref": "MAILBOX_PRIMARY"' in output.out


def test_cli_ensure_returns_ok_after_mailbox_record_is_added(monkeypatch, tmp_path, capsys) -> None:
    spec_path = tmp_path / "requirements.yaml"
    spec_path.write_text(
        '\n'.join(
            [
                "records:",
                "  - record_ref: MAILBOX_PRIMARY",
                "    record_type: mailbox_account",
                "    aliases: ['mail-invoice:C02:請求書受信POP']",
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

    monkeypatch.setenv("CREDENTIAL_VAULT_ROOT", str(tmp_path))
    monkeypatch.setenv("CREDENTIAL_VAULT_MASTER_PASSWORD", "master-password")
    monkeypatch.setenv("CREDENTIAL_VAULT_MASTER_PASSWORD_CONFIRM", "master-password")
    monkeypatch.setattr("sys.stdin", io.StringIO("mailbox-password\n"))

    assert main(["init"]) == 0
    assert (
        main(
            [
                "add",
                "mailbox",
                "mail-invoice",
                "--entity-id",
                "C02",
                "--account-label",
                "請求書受信POP",
                "--host",
                "mail.example.com",
                "--port",
                "995",
                "--protocol",
                "pop3",
                "--username",
                "billing@example.com",
                "--context-ref",
                "biz:C02",
                "--stdin",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert main(["ensure", "--spec", str(spec_path)]) == 0

    output = capsys.readouterr()
    assert "All required credentials are present." in output.out
