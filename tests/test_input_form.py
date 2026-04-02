from __future__ import annotations

import threading
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import urlencode, urlparse

from credential_vault.input_form import launch_input_form
from credential_vault.requirements import load_requirement_spec, missing_requirements
from credential_vault.vault_store import FileVaultStore


def test_launch_input_form_saves_missing_mailbox_record(monkeypatch, tmp_path: Path) -> None:
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
                "      usage_purpose: Bill One 請求書取込",
                "      protocol: pop3",
                "      use_ssl: true",
                "",
            ]
        ),
        encoding="utf-8",
    )

    store = FileVaultStore.for_root(tmp_path)
    master_password = "master-password"
    store.initialize(master_password)

    requirements = load_requirement_spec(spec_path)
    statuses = missing_requirements(store.load_document(master_password), requirements)
    result_box: dict[str, object] = {}
    url_box: dict[str, str] = {}

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
            "MAILBOX_PRIMARY__host": "mail.example.com",
            "MAILBOX_PRIMARY__port": "995",
            "MAILBOX_PRIMARY__protocol": "pop3",
            "MAILBOX_PRIMARY__username": "billing@example.com",
            "MAILBOX_PRIMARY__password": "super-secret",
            "MAILBOX_PRIMARY__use_ssl": "on",
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

    final_state = result_box["state"]
    assert final_state is not None
    assert final_state.completed is True
    assert "資格情報を保存しました" in final_state.message

    document = store.load_document(master_password)
    record = document.get_record("MAILBOX_PRIMARY")
    assert record is not None
    assert record.record_type.value == "mailbox_account"
    assert record.password == "super-secret"
    assert record.host == "mail.example.com"
    assert document.get_record("mail-invoice:C02:請求書受信POP") is not None
