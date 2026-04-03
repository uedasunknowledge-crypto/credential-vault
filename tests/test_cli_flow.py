import io

from credential_vault.cli import main


def test_cli_init_set_get_flow(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("CREDENTIAL_VAULT_ROOT", str(tmp_path))
    monkeypatch.setenv("CREDENTIAL_VAULT_MASTER_PASSWORD", "master-password")
    monkeypatch.setenv("CREDENTIAL_VAULT_MASTER_PASSWORD_CONFIRM", "master-password")
    monkeypatch.setattr("sys.stdin", io.StringIO("secret-password\n"))

    assert main(["init"]) == 0
    assert main(["set", "NOTION_TOKEN", "secret-value", "--classification", "P1b"]) == 0
    assert main(["get", "NOTION_TOKEN"]) == 0

    output = capsys.readouterr()

    assert "Vault initialized." in output.out
    assert "Saved: NOTION_TOKEN" in output.out
    assert "secret-value" in output.out


def test_cli_add_login_and_revoke(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("CREDENTIAL_VAULT_ROOT", str(tmp_path))
    monkeypatch.setenv("CREDENTIAL_VAULT_MASTER_PASSWORD", "master-password")
    monkeypatch.setenv("CREDENTIAL_VAULT_MASTER_PASSWORD_CONFIRM", "master-password")
    monkeypatch.setattr("sys.stdin", io.StringIO("secret-password\n"))

    assert main(["init"]) == 0
    assert (
        main(
            [
                "add",
                "login",
                "freee-admin",
                "--entity-id",
                "C02",
                "--account-label",
                "経理管理者",
                "--login-url",
                "https://accounts.secure.freee.co.jp/",
                "--company-code",
                "C02",
                "--user-code",
                "admin@example.com",
                "--stdin",
            ]
        )
        == 0
    )

    captured = capsys.readouterr()
    record_id = next(
        line.split(": ", 1)[1]
        for line in captured.out.splitlines()
        if line.startswith("Saved: rec_web_")
    )

    assert main(["revoke", record_id, "--reason", "token regenerated"]) == 0

    output = capsys.readouterr()
    assert f"Revoked: {record_id}" in output.out


def test_cli_add_mailbox_and_get_password(monkeypatch, tmp_path, capsys) -> None:
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
                "--context-ref",
                "project:mail-invoice",
                "--stdin",
            ]
        )
        == 0
    )

    captured = capsys.readouterr()
    record_id = next(
        line.split(": ", 1)[1]
        for line in captured.out.splitlines()
        if line.startswith("Saved: rec_mbx_")
    )

    assert main(["get", record_id, "--field", "password"]) == 0

    output = capsys.readouterr()
    assert "mailbox-password" in output.out


def test_cli_check_updates_last_test_status(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("CREDENTIAL_VAULT_ROOT", str(tmp_path))
    monkeypatch.setenv("CREDENTIAL_VAULT_MASTER_PASSWORD", "master-password")
    monkeypatch.setenv("CREDENTIAL_VAULT_MASTER_PASSWORD_CONFIRM", "master-password")
    monkeypatch.setattr("sys.stdin", io.StringIO("secret-password\n"))

    assert main(["init"]) == 0
    assert (
        main(
            [
                "add",
                "login",
                "freee-admin",
                "--entity-id",
                "C02",
                "--account-label",
                "経理管理者",
                "--login-url",
                "https://accounts.secure.freee.co.jp/",
                "--username",
                "admin@example.com",
                "--auth-flow",
                "password_plus_totp",
                "--otp-owner",
                "経理責任者",
                "--stdin",
            ]
        )
        == 0
    )

    captured = capsys.readouterr()
    record_id = next(
        line.split(": ", 1)[1]
        for line in captured.out.splitlines()
        if line.startswith("Saved: rec_web_")
    )

    assert (
        main(
            [
                "check",
                record_id,
                "--status",
                "ok",
                "--by",
                "kouhe",
                "--note",
                "TOTP と会社コードでログイン成功",
                "--at",
                "2026-04-03T10:15:00+09:00",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert main(["audit", record_id, "--json"]) == 0
    output = capsys.readouterr()
    assert '"last_test_status": "ok"' in output.out
    assert '"last_tested_by": "kouhe"' in output.out
