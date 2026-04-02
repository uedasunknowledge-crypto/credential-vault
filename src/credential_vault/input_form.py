from __future__ import annotations

import html
import secrets
import threading
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from credential_vault.requirements import (
    CredentialRequirement,
    RequirementStatus,
    build_record_from_requirement,
    evaluate_requirements,
    field_specs_for_requirement,
    parse_form_value,
    resolve_requirement_record,
)
from credential_vault.vault_store import FileVaultStore


@dataclass(slots=True)
class FormState:
    store: FileVaultStore
    master_password: str
    requirements: list[CredentialRequirement]
    token: str
    host: str
    port: int
    statuses: list[RequirementStatus]
    completed: bool = False
    message: str = ""
    errors: list[str] = field(default_factory=list)
    submitted_values: dict[str, dict[str, str]] = field(default_factory=dict)

    def form_url(self) -> str:
        query = urlencode({"token": self.token})
        return f"http://{self.host}:{self.port}/?{query}"


class CredentialInputServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address: tuple[str, int], state: FormState) -> None:
        super().__init__(server_address, CredentialInputHandler)
        self.state = state


class CredentialInputHandler(BaseHTTPRequestHandler):
    server: CredentialInputServer

    def do_GET(self) -> None:  # noqa: N802
        if not self._authorized():
            self.send_error(HTTPStatus.FORBIDDEN, "invalid token")
            return

        content = self._render_page()
        encoded = content.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            self.send_error(HTTPStatus.FORBIDDEN, "invalid token")
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length).decode("utf-8")
        form_data = parse_qs(raw_body, keep_blank_values=True)
        self.server.state.submitted_values = _submitted_values_from_form(form_data)

        try:
            self._save_submitted_records(form_data)
        except Exception as exc:  # noqa: BLE001
            self.server.state.errors = [str(exc)]
            self.server.state.message = ""
            self._redirect_back()
            return

        self.server.state.errors = []
        self.server.state.message = "資格情報を保存しました。必要項目は満たされています。"
        self.server.state.completed = True
        self._redirect_back()
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _authorized(self) -> bool:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        token = params.get("token", [""])[0]
        return token == self.server.state.token

    def _redirect_back(self) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", f"/?token={self.server.state.token}")
        self.end_headers()

    def _save_submitted_records(self, form_data: dict[str, list[str]]) -> None:
        state = self.server.state
        document = state.store.load_document(state.master_password)

        for status in state.statuses:
            requirement = status.requirement
            submitted_fields: dict[str, Any] = {}
            for field_name in requirement.required_fields:
                form_key = _form_key(requirement.record_ref, field_name)
                raw_value = form_data.get(form_key, [""])[0]
                if field_name in {"use_ssl", "starttls"}:
                    raw_value = "on" if form_key in form_data else ""
                submitted_fields[field_name] = parse_form_value(requirement.record_type, field_name, raw_value)

            record, aliases = build_record_from_requirement(
                requirement=requirement,
                submitted_fields=submitted_fields,
                existing_record=resolve_requirement_record(document, requirement),
                existing_ids=list(document.records.keys()),
            )
            document.upsert_record(record, aliases=aliases)

        statuses = evaluate_requirements(document, state.requirements)
        missing_after_save = [status for status in statuses if not status.is_satisfied]
        if missing_after_save:
            state.statuses = missing_after_save
            raise ValueError("まだ未入力の必須項目があります。")

        state.store.save_document(document, state.master_password)
        state.statuses = statuses

    def _render_page(self) -> str:
        state = self.server.state
        sections = []
        for status in state.statuses:
            sections.append(_render_requirement_section(status, state.submitted_values))
        errors = "".join(f"<li>{html.escape(error)}</li>" for error in state.errors)
        message = html.escape(state.message) if state.message else ""
        error_block = f"<div class='errors'><ul>{errors}</ul></div>" if errors else ""
        message_block = f"<div class='message'>{message}</div>" if message else ""

        return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <title>credential-vault input</title>
  <style>
    body {{ font-family: sans-serif; margin: 2rem; background: #f6f8f5; color: #1c281f; }}
    h1 {{ margin-bottom: 0.5rem; }}
    .hint {{ color: #415144; margin-bottom: 1.5rem; }}
    .card {{ background: #ffffff; border: 1px solid #d8e0d8; border-radius: 12px; padding: 1rem; margin-bottom: 1rem; }}
    .field {{ display: grid; gap: 0.35rem; margin-bottom: 0.9rem; }}
    .field input {{ padding: 0.6rem 0.7rem; border: 1px solid #bac5ba; border-radius: 8px; }}
    .field.checkbox {{ display: flex; align-items: center; gap: 0.5rem; }}
    .meta {{ color: #566658; font-size: 0.95rem; margin-bottom: 0.8rem; }}
    .errors {{ background: #fff1f1; border: 1px solid #e3b1b1; padding: 0.8rem 1rem; border-radius: 10px; margin-bottom: 1rem; }}
    .message {{ background: #edf9ef; border: 1px solid #99c5a0; padding: 0.8rem 1rem; border-radius: 10px; margin-bottom: 1rem; }}
    button {{ padding: 0.8rem 1.1rem; border: none; border-radius: 10px; background: #2f6b4f; color: white; cursor: pointer; }}
  </style>
</head>
<body>
  <h1>credential-vault 入力フォーム</h1>
  <div class="hint">このフォームは localhost 限定です。送信された値は vault に保存され、完了後にサーバーは停止します。</div>
  {message_block}
  {error_block}
  <form method="post" action="/?token={html.escape(state.token)}">
    {"".join(sections)}
    <button type="submit">vault に保存する</button>
  </form>
</body>
</html>
"""


def launch_input_form(
    store: FileVaultStore,
    master_password: str,
    statuses: list[RequirementStatus],
    *,
    host: str = "127.0.0.1",
    port: int = 0,
) -> FormState:
    token = secrets.token_urlsafe(24)
    requirements = [status.requirement for status in statuses]
    state = FormState(
        store=store,
        master_password=master_password,
        requirements=requirements,
        token=token,
        host=host,
        port=port,
        statuses=statuses,
    )

    server = CredentialInputServer((host, port), state)
    actual_host, actual_port = server.server_address
    state.host = actual_host
    state.port = actual_port
    print(f"Open this URL to enter missing credentials: {state.form_url()}")
    server.serve_forever()
    server.server_close()
    return state


def _render_requirement_section(status: RequirementStatus, submitted_values: dict[str, dict[str, str]]) -> str:
    requirement = status.requirement
    specs = field_specs_for_requirement(requirement)
    record_label = html.escape(
        str(requirement.record_data.get("account_label") or requirement.record_data.get("service_name") or requirement.record_ref)
    )
    meta_fragments = [
        f"record_ref={html.escape(requirement.record_ref)}",
        f"type={html.escape(requirement.record_type.value)}",
    ]
    if requirement.record_data.get("entity_id"):
        meta_fragments.append(f"entity={html.escape(str(requirement.record_data['entity_id']))}")
    if requirement.record_data.get("usage_purpose"):
        meta_fragments.append(f"purpose={html.escape(str(requirement.record_data['usage_purpose']))}")

    fields_html = []
    for field_name in requirement.required_fields:
        field_spec = specs.get(field_name, FieldSpec(label=field_name, input_type="text"))
        current_values = submitted_values.get(requirement.record_ref, {})
        raw_value = current_values.get(field_name, requirement.record_data.get(field_name, ""))
        fields_html.append(_render_field(requirement.record_ref, field_name, field_spec, raw_value))

    return f"""
<section class="card">
  <h2>{record_label}</h2>
  <div class="meta">{' / '.join(meta_fragments)}</div>
  {''.join(fields_html)}
</section>
"""


def _render_field(record_ref: str, field_name: str, field_spec: FieldSpec, raw_value: Any) -> str:
    label = html.escape(field_spec.label)
    name = html.escape(_form_key(record_ref, field_name))
    if field_spec.input_type == "checkbox":
        checked = " checked" if bool(raw_value) else ""
        return f"""
<label class="field checkbox">
  <input type="checkbox" name="{name}"{checked}>
  <span>{label}</span>
</label>
"""

    value = "" if field_spec.secret else html.escape("" if raw_value is None else str(raw_value))
    input_type = "password" if field_spec.secret else ("number" if field_spec.input_type == "number" else "text")
    return f"""
<label class="field">
  <span>{label}</span>
  <input type="{input_type}" name="{name}" value="{value}">
</label>
"""


def _form_key(record_ref: str, field_name: str) -> str:
    return f"{record_ref}__{field_name}"


def _submitted_values_from_form(form_data: dict[str, list[str]]) -> dict[str, dict[str, str]]:
    submitted: dict[str, dict[str, str]] = {}
    for key, values in form_data.items():
        if "__" not in key:
            continue
        record_ref, field_name = key.split("__", maxsplit=1)
        submitted.setdefault(record_ref, {})[field_name] = values[0] if values else ""
    return submitted
