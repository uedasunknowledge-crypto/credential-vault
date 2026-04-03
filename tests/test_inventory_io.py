from __future__ import annotations

import csv
import threading
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import urlencode, urlparse

from credential_vault.cli import main
from credential_vault.input_form import launch_input_form
from credential_vault.inventory_io import build_inventory_io_bundle
from credential_vault.inventory_seed import AUTH_HEADERS, CREDENTIAL_HEADERS
from credential_vault.requirements import load_requirement_spec, missing_requirements
from credential_vault.vault_store import FileVaultStore


def test_build_inventory_io_bundle_supports_form_input_and_render_output(monkeypatch, tmp_path: Path, capsys) -> None:
    credential_csv = tmp_path / "credential_working.csv"
    auth_csv = tmp_path / "auth_working.csv"
    override_csv = tmp_path / "credential_override.csv"

    _write_csv(
        credential_csv,
        CREDENTIAL_HEADERS,
        [
            {
                "migration_status": "seed_from_requirement",
                "source_type": "spreadsheet",
                "source_locator": "Sheet1!A2",
                "service_name": "mail-invoice",
                "record_type": "mailbox_account",
                "entity_id": "C02",
                "department_id": "",
                "account_label": "請求書受信POP",
                "usage_purpose": "Bill One 請求書取込",
                "login_url": "",
                "tenant_code": "",
                "host": "mail.example.com",
                "port": "995",
                "protocol": "pop3",
                "username": "billing@example.com",
                "mailbox_name": "INBOX",
                "from_address": "",
                "use_ssl": "true",
                "starttls": "",
                "company_code": "",
                "user_code": "",
                "classification": "P2a",
                "rotation_days": "90",
                "owner": "経理担当",
                "context_refs": "project:mail-invoice|tool:billone",
                "vault_record_ref": "MAILBOX_PRIMARY",
                "notes": "seed row",
            },
            {
                "migration_status": "seed_from_requirement",
                "source_type": "chatwork",
                "source_locator": "room:abc",
                "service_name": "visa-vpass",
                "record_type": "web_login",
                "entity_id": "C02",
                "department_id": "",
                "account_label": "VISA Vpass",
                "usage_purpose": "売上明細取得",
                "login_url": "https://example.com/login",
                "tenant_code": "",
                "host": "",
                "port": "",
                "protocol": "",
                "username": "portal-user",
                "mailbox_name": "",
                "from_address": "",
                "use_ssl": "",
                "starttls": "",
                "company_code": "",
                "user_code": "",
                "classification": "P2a",
                "rotation_days": "90",
                "owner": "経理担当",
                "context_refs": "project:mail-invoice|vendor:VISA_VPASS",
                "vault_record_ref": "VISA_VPASS",
                "notes": "seed row",
            },
            {
                "migration_status": "candidate_from_service_inventory",
                "source_type": "service_inventory",
                "source_locator": "inventory.csv",
                "service_name": "jcb",
                "record_type": "web_login",
                "entity_id": "",
                "department_id": "",
                "account_label": "JCB",
                "usage_purpose": "売上明細取得",
                "login_url": "",
                "tenant_code": "",
                "host": "",
                "port": "",
                "protocol": "",
                "username": "",
                "mailbox_name": "",
                "from_address": "",
                "use_ssl": "",
                "starttls": "",
                "company_code": "",
                "user_code": "",
                "classification": "P2a",
                "rotation_days": "",
                "owner": "",
                "context_refs": "project:mail-invoice|vendor:JCB",
                "vault_record_ref": "candidate:JCB",
                "notes": "candidate row",
            },
        ],
    )
    _write_csv(
        auth_csv,
        AUTH_HEADERS,
        [
            {
                "vault_record_ref": "VISA_VPASS",
                "service_name": "visa-vpass",
                "account_label": "VISA Vpass",
                "auth_flow": "",
                "otp_contact": "",
                "otp_owner": "",
                "required_device": "Edge または Chrome",
                "recovery_url": "https://example.com/login",
                "recovery_note": "",
                "mfa_note": "",
                "login_note": "",
            }
        ],
    )
    _write_csv(
        override_csv,
        [
            "vault_record_ref",
            "service_name",
            "account_label",
            "fill_priority",
            "fill_hint",
            "source_type",
            "source_locator",
            "entity_id",
            "department_id",
            "usage_purpose",
            "login_url",
            "tenant_code",
            "host",
            "port",
            "protocol",
            "username",
            "mailbox_name",
            "from_address",
            "use_ssl",
            "starttls",
            "company_code",
            "user_code",
            "owner",
            "classification",
            "rotation_days",
            "context_refs",
            "notes",
        ],
        [
            {
                "vault_record_ref": "MAILBOX_PRIMARY",
                "service_name": "mail-invoice",
                "account_label": "請求書受信POP",
                "fill_priority": "P1",
            },
            {
                "vault_record_ref": "VISA_VPASS",
                "service_name": "visa-vpass",
                "account_label": "VISA Vpass",
                "fill_priority": "P1",
            },
            {
                "vault_record_ref": "candidate:JCB",
                "service_name": "jcb",
                "account_label": "JCB",
                "fill_priority": "P2",
            },
        ],
    )

    outputs = build_inventory_io_bundle(
        credential_csv=credential_csv,
        auth_csv=auth_csv,
        credential_override_csv=override_csv,
        output_dir=tmp_path / "generated",
        priorities=("P1",),
    )

    requirements_text = outputs["requirements"].read_text(encoding="utf-8")
    template_text = outputs["template"].read_text(encoding="utf-8")
    assert "MAILBOX_PRIMARY" in requirements_text
    assert "VISA_VPASS" in requirements_text
    assert "candidate:JCB" not in requirements_text
    assert "auth_flow" in requirements_text
    assert "secret://MAILBOX_PRIMARY#password" in template_text
    assert "secret://VISA_VPASS#auth_flow" in template_text

    vault_root = tmp_path / "vault_root"
    store = FileVaultStore.for_root(vault_root)
    master_password = "master-password"
    store.initialize(master_password)

    requirements = load_requirement_spec(outputs["requirements"])
    statuses = missing_requirements(store.load_document(master_password), requirements)
    result_box: dict[str, object] = {}
    url_box: dict[str, str] = {}
    real_print = print

    def fake_print(*args, **kwargs) -> None:  # noqa: ANN002, ANN003
        text = " ".join(str(arg) for arg in args)
        if text.startswith("Open this URL to enter missing credentials: "):
            url_box["url"] = text.split(": ", maxsplit=1)[1]

    monkeypatch.setattr("builtins.print", fake_print)

    def run_server() -> None:
        result_box["state"] = launch_input_form(
            store=store,
            master_password=master_password,
            statuses=statuses,
            host="127.0.0.1",
            port=0,
        )

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()

    while "url" not in url_box:
        if not thread.is_alive():
            raise AssertionError("入力フォームサーバーが起動前に停止しました。")

    url = urlparse(url_box["url"])
    body = urlencode(
        {
            "MAILBOX_PRIMARY__password": "pop-secret",
            "VISA_VPASS__password": "portal-secret",
            "VISA_VPASS__auth_flow": "password_only",
        }
    )
    connection = HTTPConnection(url.hostname, url.port, timeout=5)
    connection.request(
        "POST",
        f"{url.path}?{url.query}",
        body=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    response = connection.getresponse()
    response.read()
    connection.close()
    assert response.status == 303

    thread.join(timeout=5)
    assert not thread.is_alive()
    monkeypatch.setattr("builtins.print", real_print)

    monkeypatch.setenv("CREDENTIAL_VAULT_ROOT", str(vault_root))
    monkeypatch.setenv("CREDENTIAL_VAULT_MASTER_PASSWORD", master_password)
    monkeypatch.setenv("CREDENTIAL_VAULT_MASTER_PASSWORD_CONFIRM", master_password)

    assert main(["ensure", "--spec", str(outputs["requirements"])]) == 0
    capsys.readouterr()

    assert main(["render", str(outputs["template"]), "--stdout"]) == 0
    rendered_output = capsys.readouterr().out
    assert "pop-secret" in rendered_output
    assert "portal-secret" in rendered_output
    assert "password_only" in rendered_output
    assert "mail.example.com" in rendered_output
    assert "candidate:JCB" not in rendered_output


def _write_csv(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
