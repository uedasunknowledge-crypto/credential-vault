from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from credential_vault import __version__
from credential_vault.config import VaultPaths
from credential_vault.crypto import VaultCryptoError, VaultIntegrityError
from credential_vault.identifiers import next_record_id
from credential_vault.input_form import launch_input_form
from credential_vault.models import (
    ApiSecretRecord,
    CheckStatus,
    Classification,
    MailboxAccountRecord,
    MachineSecretRecord,
    RecordStatus,
    RecordType,
    RotationMode,
    RotationPolicy,
    SecretRecord,
    SmtpAccountRecord,
    WebLoginRecord,
)
from credential_vault.requirements import load_requirement_spec, missing_requirements, sync_requirement_aliases
from credential_vault.template_render import SecretTemplateError, record_field_value, render_template_file
from credential_vault.vault_store import FileVaultStore, VaultDocument


EXIT_OK = 0
EXIT_ARG = 2
EXIT_LOCKED = 20
EXIT_NOT_FOUND = 21
EXIT_MISSING = 22
EXIT_CORRUPT = 30
EXIT_PERMISSION = 40
EXIT_INTERNAL = 50


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="secrets",
        description="NH1 向けのクレデンシャル管理 CLI",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="空の vault を初期化する")

    unlock_parser = subparsers.add_parser("unlock", help="vault セッションを開く")
    unlock_parser.add_argument("--ttl", default="8h", help="セッション有効期限")

    subparsers.add_parser("lock", help="vault セッションを閉じる")

    status_parser = subparsers.add_parser("status", help="vault 状態を確認する")
    status_parser.add_argument("--json", action="store_true", help="JSON 形式で出力する")

    get_parser = subparsers.add_parser("get", help="値だけを取得する")
    get_parser.add_argument("record_ref", help="record_id または互換キー名")
    get_parser.add_argument("--field", default="value", help="取得するフィールド名")

    set_parser = subparsers.add_parser("set", help="従来互換の単純キーを登録する")
    set_parser.add_argument("key", help="キー名")
    set_parser.add_argument("value", nargs="?", help="秘密値")
    set_parser.add_argument("--stdin", action="store_true", help="標準入力から値を読む")
    set_parser.add_argument("--classification", default="P1b", help="データ区分")
    set_parser.add_argument("--description", default="", help="説明")
    set_parser.add_argument("--tag", action="append", default=[], help="タグ")

    list_parser = subparsers.add_parser("list", help="一覧を表示する")
    list_parser.add_argument("--classification", help="区分で絞り込む")
    list_parser.add_argument("--tag", action="append", default=[], help="タグで絞り込む")
    list_parser.add_argument("--service", help="サービス名で絞り込む")
    list_parser.add_argument("--entity-id", help="法人IDで絞り込む")
    list_parser.add_argument("--context-ref", action="append", default=[], help="業務コンテキスト参照で絞り込む")
    list_parser.add_argument("--json", action="store_true", help="JSON 形式で出力する")

    view_parser = subparsers.add_parser("view", help="詳細を表示する")
    view_parser.add_argument("record_ref", help="record_id または互換キー名")
    view_parser.add_argument(
        "--reveal-password",
        action="store_true",
        help="秘密値系フィールドを明示表示する",
    )
    view_parser.add_argument("--json", action="store_true", help="JSON 形式で出力する")

    delete_parser = subparsers.add_parser("delete", help="レコードを削除する")
    delete_parser.add_argument("record_ref", help="record_id")

    doctor_parser = subparsers.add_parser("doctor", help="環境と vault を検査する")
    doctor_parser.add_argument("--json", action="store_true", help="JSON 形式で出力する")

    ensure_parser = subparsers.add_parser("ensure", help="必要 credential の充足を確認する")
    ensure_parser.add_argument("--spec", required=True, help="requirements spec YAML")
    ensure_parser.add_argument("--json", action="store_true", help="JSON 形式で出力する")
    ensure_parser.add_argument("--launch-form", action="store_true", help="不足時に localhost 入力フォームを起動する")
    ensure_parser.add_argument("--host", default="127.0.0.1", help="入力フォームの bind host")
    ensure_parser.add_argument("--port", type=int, default=0, help="入力フォームの bind port。0 なら自動選択")

    render_parser = subparsers.add_parser("render", help="vault 参照テンプレートを展開する")
    render_parser.add_argument("template_path", help="YAML または JSON のテンプレート")
    render_parser.add_argument("--output", help="展開後ファイルの出力先")
    render_parser.add_argument("--stdout", action="store_true", help="標準出力へ出す")

    exec_parser = subparsers.add_parser("exec", help="テンプレートを一時展開してコマンドを実行する")
    exec_parser.add_argument("--template", required=True, help="YAML または JSON のテンプレート")
    exec_parser.add_argument(
        "--placeholder",
        default="__CREDENTIAL_VAULT_RENDERED_TEMPLATE__",
        help="コマンド引数内で一時ファイルパスに置換するトークン",
    )
    exec_parser.add_argument(
        "command_args",
        nargs=argparse.REMAINDER,
        help="実行コマンド。先頭に -- を置いて続ける",
    )

    add_parser = subparsers.add_parser("add", help="型付きレコードを追加する")
    add_subparsers = add_parser.add_subparsers(dest="record_kind", required=True)

    add_api_parser = add_subparsers.add_parser("api", help="API 秘密情報を追加する")
    add_api_parser.add_argument("service_name", help="サービス名")
    add_api_parser.add_argument("--entity-id", help="法人ID")
    add_api_parser.add_argument("--account-label", required=True, help="人間向けラベル")
    add_api_parser.add_argument("--usage-purpose", help="用途")
    add_api_parser.add_argument("--secret-key-name", required=True, help="秘密値の種別")
    add_api_parser.add_argument("--environment", help="本番/検証など")
    add_api_parser.add_argument("--classification", default="P1b", help="データ区分")
    add_api_parser.add_argument("--rotation-days", type=int, help="更新周期")
    add_api_parser.add_argument("--stdin", action="store_true", help="標準入力から値を読む")
    add_api_parser.add_argument("--description", default="", help="説明")
    add_api_parser.add_argument("--tag", action="append", default=[], help="タグ")
    add_api_parser.add_argument("--owner", help="更新責任者")
    add_api_parser.add_argument("--context-ref", action="append", default=[], help="business 共通語などの参照キー")

    add_login_parser = add_subparsers.add_parser("login", help="Web ログイン情報を追加する")
    add_login_parser.add_argument("service_name", help="サービス名")
    add_login_parser.add_argument("--entity-id", help="法人ID")
    add_login_parser.add_argument("--department-id", help="部門ID")
    add_login_parser.add_argument("--account-label", required=True, help="人間向けラベル")
    add_login_parser.add_argument("--usage-purpose", help="用途")
    add_login_parser.add_argument("--login-url", required=True, help="ログイン URL")
    add_login_parser.add_argument("--tenant-code", help="テナントコード")
    add_login_parser.add_argument("--company-code", help="会社コード")
    add_login_parser.add_argument("--user-code", help="ユーザーコード")
    add_login_parser.add_argument("--username", help="ログイン名")
    add_login_parser.add_argument("--classification", default="P2a", help="データ区分")
    add_login_parser.add_argument("--rotation-days", type=int, help="更新周期")
    add_login_parser.add_argument("--stdin", action="store_true", help="標準入力からパスワードを読む")
    add_login_parser.add_argument("--description", default="", help="説明")
    add_login_parser.add_argument("--tag", action="append", default=[], help="タグ")
    add_login_parser.add_argument("--owner", help="更新責任者")
    add_login_parser.add_argument("--context-ref", action="append", default=[], help="business 共通語などの参照キー")
    add_login_parser.add_argument("--auth-flow", help="password_only / password_plus_totp など")
    add_login_parser.add_argument("--otp-contact", help="OTP の配送先や認証アプリの識別")
    add_login_parser.add_argument("--otp-owner", help="OTP を受け取る人や管理ロール")
    add_login_parser.add_argument("--recovery-url", help="再設定や復旧の URL")
    add_login_parser.add_argument("--recovery-note", help="MFA/復旧時の手順メモ")
    add_login_parser.add_argument("--mfa-note", help="MFA に関する補足")
    add_login_parser.add_argument("--login-note", help="ログイン手順の補足")

    add_mailbox_parser = add_subparsers.add_parser("mailbox", help="メール受信用アカウントを追加する")
    add_mailbox_parser.add_argument("service_name", help="サービス名")
    add_mailbox_parser.add_argument("--entity-id", help="法人ID")
    add_mailbox_parser.add_argument("--department-id", help="部門ID")
    add_mailbox_parser.add_argument("--account-label", required=True, help="人間向けラベル")
    add_mailbox_parser.add_argument("--usage-purpose", help="用途")
    add_mailbox_parser.add_argument("--host", required=True, help="POP/IMAP サーバー")
    add_mailbox_parser.add_argument("--port", type=int, help="ポート番号")
    add_mailbox_parser.add_argument("--protocol", default="pop3", help="pop3 / imap など")
    add_mailbox_parser.add_argument("--username", required=True, help="アカウント名またはメールアドレス")
    add_mailbox_parser.add_argument("--mailbox-name", help="メールボックス名")
    add_mailbox_parser.add_argument("--use-ssl", action=argparse.BooleanOptionalAction, default=True, help="SSL/TLS を使うか")
    add_mailbox_parser.add_argument("--classification", default="P2a", help="データ区分")
    add_mailbox_parser.add_argument("--rotation-days", type=int, help="更新周期")
    add_mailbox_parser.add_argument("--stdin", action="store_true", help="標準入力からパスワードを読む")
    add_mailbox_parser.add_argument("--description", default="", help="説明")
    add_mailbox_parser.add_argument("--tag", action="append", default=[], help="タグ")
    add_mailbox_parser.add_argument("--owner", help="更新責任者")
    add_mailbox_parser.add_argument("--context-ref", action="append", default=[], help="business 共通語などの参照キー")

    add_smtp_parser = add_subparsers.add_parser("smtp", help="SMTP アカウントを追加する")
    add_smtp_parser.add_argument("service_name", help="サービス名")
    add_smtp_parser.add_argument("--entity-id", help="法人ID")
    add_smtp_parser.add_argument("--department-id", help="部門ID")
    add_smtp_parser.add_argument("--account-label", required=True, help="人間向けラベル")
    add_smtp_parser.add_argument("--usage-purpose", help="用途")
    add_smtp_parser.add_argument("--host", required=True, help="SMTP サーバー")
    add_smtp_parser.add_argument("--port", type=int, help="ポート番号")
    add_smtp_parser.add_argument("--username", required=True, help="SMTP アカウント名またはメールアドレス")
    add_smtp_parser.add_argument("--from-address", required=True, help="送信元メールアドレス")
    add_smtp_parser.add_argument("--use-ssl", action=argparse.BooleanOptionalAction, default=True, help="SSL/TLS を使うか")
    add_smtp_parser.add_argument("--starttls", action=argparse.BooleanOptionalAction, default=False, help="STARTTLS を使うか")
    add_smtp_parser.add_argument("--classification", default="P2a", help="データ区分")
    add_smtp_parser.add_argument("--rotation-days", type=int, help="更新周期")
    add_smtp_parser.add_argument("--stdin", action="store_true", help="標準入力からパスワードを読む")
    add_smtp_parser.add_argument("--description", default="", help="説明")
    add_smtp_parser.add_argument("--tag", action="append", default=[], help="タグ")
    add_smtp_parser.add_argument("--owner", help="更新責任者")
    add_smtp_parser.add_argument("--context-ref", action="append", default=[], help="business 共通語などの参照キー")

    revoke_parser = subparsers.add_parser("revoke", help="レコードを失効させる")
    revoke_parser.add_argument("record_ref", help="record_id")
    revoke_parser.add_argument("--reason", default="", help="失効理由")

    due_parser = subparsers.add_parser("due", help="期限系の操作を行う")
    due_subparsers = due_parser.add_subparsers(dest="due_command", required=True)
    due_list_parser = due_subparsers.add_parser("list", help="期限一覧を表示する")
    due_list_parser.add_argument("--days", type=int, default=7, help="何日以内を表示するか")
    due_list_parser.add_argument("--json", action="store_true", help="JSON 形式で出力する")
    due_subparsers.add_parser("notify", help="期限通知を送る")

    audit_parser = subparsers.add_parser("audit", help="監査情報を表示する")
    audit_parser.add_argument("record_ref", help="record_id")
    audit_parser.add_argument("--json", action="store_true", help="JSON 形式で出力する")

    check_parser = subparsers.add_parser("check", help="ログインや接続確認の結果を記録する")
    check_parser.add_argument("record_ref", help="record_id または alias")
    check_parser.add_argument("--status", required=True, choices=[status.value for status in CheckStatus], help="確認結果")
    check_parser.add_argument("--by", required=True, help="確認者")
    check_parser.add_argument("--note", default="", help="確認メモ")
    check_parser.add_argument("--at", help="確認日時。ISO 8601 形式、省略時は現在時刻")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return dispatch(args)


def dispatch(args: argparse.Namespace) -> int:
    store = FileVaultStore(VaultPaths.default())
    handlers = {
        "init": lambda: _handle_init(store),
        "unlock": _handle_unlock_placeholder,
        "lock": _handle_lock_placeholder,
        "status": lambda: _handle_status(args, store),
        "get": lambda: _handle_get(args, store),
        "set": lambda: _handle_set(args, store),
        "list": lambda: _handle_list(args, store),
        "view": lambda: _handle_view(args, store),
        "delete": lambda: _handle_delete(args, store),
        "doctor": lambda: _handle_doctor(args, store),
        "ensure": lambda: _handle_ensure(args, store),
        "render": lambda: _handle_render(args, store),
        "exec": lambda: _handle_exec(args, store),
        "add": lambda: _handle_add(args, store),
        "revoke": lambda: _handle_revoke(args, store),
        "due": lambda: _handle_due(args, store),
        "audit": lambda: _handle_audit(args, store),
        "check": lambda: _handle_check(args, store),
    }
    handler = handlers.get(args.command)
    if handler is None:
        print(f"未対応のコマンドです: {args.command}", file=sys.stderr)
        return EXIT_ARG

    try:
        return handler()
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_NOT_FOUND
    except FileExistsError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_PERMISSION
    except FileNotFoundError:
        print('vault is not initialized. run "secrets init" first.', file=sys.stderr)
        return EXIT_NOT_FOUND
    except VaultIntegrityError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_CORRUPT
    except VaultCryptoError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INTERNAL
    except SecretTemplateError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_ARG
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_ARG


def _handle_init(store: FileVaultStore) -> int:
    master_password = _read_new_master_password()
    if not master_password:
        print("master password is required.", file=sys.stderr)
        return EXIT_ARG

    store.initialize(master_password)
    print(f"Vault path: {store.paths.vault_path}")
    print("Vault initialized.")
    return EXIT_OK


def _handle_unlock_placeholder() -> int:
    print("unlock はまだ未実装です。現状はコマンド実行時に直接パスワードを使う方式です。", file=sys.stderr)
    return EXIT_INTERNAL


def _handle_lock_placeholder() -> int:
    print("lock はまだ未実装です。現状はコマンド実行時に直接パスワードを使う方式です。", file=sys.stderr)
    return EXIT_INTERNAL


def _handle_status(args: argparse.Namespace, store: FileVaultStore) -> int:
    status_data = {
        "vault_exists": store.exists(),
        "vault_path": str(store.paths.vault_path),
        "mode": "direct_password",
        "master_password_source": "env" if os.environ.get("CREDENTIAL_VAULT_MASTER_PASSWORD") else "prompt_or_none",
    }

    if args.json:
        print(json.dumps(status_data, ensure_ascii=False, indent=2))
        return EXIT_OK

    print(f"Vault: {'initialized' if status_data['vault_exists'] else 'not initialized'}")
    print(f"Path: {status_data['vault_path']}")
    print("Mode: direct_password")
    print(f"Master password source: {status_data['master_password_source']}")
    return EXIT_OK


def _handle_get(args: argparse.Namespace, store: FileVaultStore) -> int:
    document, _ = _load_document_with_password(store, allow_prompt=_is_interactive())
    if document is None:
        print('vault is locked. provide CREDENTIAL_VAULT_MASTER_PASSWORD or run interactively.', file=sys.stderr)
        return EXIT_LOCKED

    record = document.get_record(args.record_ref)
    if record is None:
        print(f"key not found: {args.record_ref}", file=sys.stderr)
        return EXIT_NOT_FOUND

    value = record_field_value(record, args.field)
    if value is None:
        raise ValueError(f"field not found: {args.record_ref}#{args.field}")

    print(value)
    return EXIT_OK


def _handle_set(args: argparse.Namespace, store: FileVaultStore) -> int:
    document, master_password = _load_document_with_password(store, allow_prompt=True)
    if document is None or master_password is None:
        return EXIT_LOCKED

    secret_value = _read_secret_value(args.value, args.stdin, prompt_text=f"Value for {args.key}: ")
    classification = Classification(args.classification)
    existing = document.get_record(args.key)
    is_update = existing is not None

    if existing is not None and not isinstance(existing, ApiSecretRecord):
        raise ValueError("legacy set can only update api_secret records.")

    if existing is None:
        record = ApiSecretRecord(
            record_id=next_record_id(RecordType.API_SECRET, document.records.keys()),
            service_name=args.key.lower(),
            account_label="legacy",
            classification=classification,
            description=args.description,
            tags=list(args.tag),
            secret_key_name=args.key,
            secret_value=secret_value,
            fingerprint=_fingerprint(secret_value),
        )
    else:
        record = existing
        record.classification = classification
        record.description = args.description or record.description
        record.tags = list(args.tag) if args.tag else record.tags
        record.secret_value = secret_value
        record.fingerprint = _fingerprint(secret_value)
        record.updated_at = datetime.now(UTC)

    document.upsert_record(record, aliases=[args.key])
    store.save_document(document, master_password)
    print(f"{'Updated' if is_update else 'Saved'}: {args.key}")
    return EXIT_OK


def _handle_add(args: argparse.Namespace, store: FileVaultStore) -> int:
    if args.record_kind == "api":
        return _handle_add_api(args, store)
    if args.record_kind == "login":
        return _handle_add_login(args, store)
    if args.record_kind == "mailbox":
        return _handle_add_mailbox(args, store)
    if args.record_kind == "smtp":
        return _handle_add_smtp(args, store)
    raise ValueError(f"未対応のレコード種別です: {args.record_kind}")


def _handle_add_api(args: argparse.Namespace, store: FileVaultStore) -> int:
    document, master_password = _load_document_with_password(store, allow_prompt=True)
    if document is None or master_password is None:
        return EXIT_LOCKED

    secret_value = _read_secret_value(None, args.stdin, prompt_text=f"Value for {args.secret_key_name}: ")
    record = ApiSecretRecord(
        record_id=next_record_id(RecordType.API_SECRET, document.records.keys()),
        service_name=args.service_name,
        entity_id=args.entity_id,
        account_label=args.account_label,
        usage_purpose=args.usage_purpose,
        context_refs=list(args.context_ref),
        classification=Classification(args.classification),
        description=args.description,
        tags=list(args.tag),
        owner=args.owner,
        rotation_policy=_rotation_policy(args.rotation_days),
        expires_at=_compute_expiry(args.rotation_days),
        secret_key_name=args.secret_key_name,
        secret_value=secret_value,
        environment=args.environment,
        fingerprint=_fingerprint(secret_value),
    )

    document.upsert_record(record, aliases=_candidate_aliases(record))
    store.save_document(document, master_password)
    print(f"Saved: {record.record_id}")
    return EXIT_OK


def _handle_add_login(args: argparse.Namespace, store: FileVaultStore) -> int:
    document, master_password = _load_document_with_password(store, allow_prompt=True)
    if document is None or master_password is None:
        return EXIT_LOCKED

    password = _read_secret_value(None, args.stdin, prompt_text="Password: ")
    record = WebLoginRecord(
        record_id=next_record_id(RecordType.WEB_LOGIN, document.records.keys()),
        service_name=args.service_name,
        entity_id=args.entity_id,
        department_id=args.department_id,
        account_label=args.account_label,
        usage_purpose=args.usage_purpose,
        context_refs=list(args.context_ref),
        classification=Classification(args.classification),
        description=args.description,
        tags=list(args.tag),
        owner=args.owner,
        rotation_policy=_rotation_policy(args.rotation_days),
        expires_at=_compute_expiry(args.rotation_days),
        login_url=args.login_url,
        tenant_code=args.tenant_code,
        company_code=args.company_code,
        user_code=args.user_code,
        username=args.username,
        password=password,
        auth_flow=args.auth_flow,
        otp_contact=args.otp_contact,
        otp_owner=args.otp_owner,
        recovery_url=args.recovery_url,
        recovery_note=args.recovery_note,
        mfa_note=args.mfa_note,
        login_note=args.login_note,
        fingerprint=_fingerprint(password),
    )

    document.upsert_record(record, aliases=_candidate_aliases(record))
    store.save_document(document, master_password)
    print(f"Saved: {record.record_id}")
    return EXIT_OK


def _handle_add_mailbox(args: argparse.Namespace, store: FileVaultStore) -> int:
    document, master_password = _load_document_with_password(store, allow_prompt=True)
    if document is None or master_password is None:
        return EXIT_LOCKED

    password = _read_secret_value(None, args.stdin, prompt_text="Mailbox password: ")
    record = MailboxAccountRecord(
        record_id=next_record_id(RecordType.MAILBOX_ACCOUNT, document.records.keys()),
        service_name=args.service_name,
        entity_id=args.entity_id,
        department_id=args.department_id,
        account_label=args.account_label,
        usage_purpose=args.usage_purpose,
        context_refs=list(args.context_ref),
        classification=Classification(args.classification),
        description=args.description,
        tags=list(args.tag),
        owner=args.owner,
        rotation_policy=_rotation_policy(args.rotation_days),
        expires_at=_compute_expiry(args.rotation_days),
        host=args.host,
        port=args.port,
        protocol=args.protocol,
        username=args.username,
        password=password,
        use_ssl=args.use_ssl,
        mailbox_name=args.mailbox_name,
        fingerprint=_fingerprint(password),
    )

    document.upsert_record(record, aliases=_candidate_aliases(record))
    store.save_document(document, master_password)
    print(f"Saved: {record.record_id}")
    return EXIT_OK


def _handle_add_smtp(args: argparse.Namespace, store: FileVaultStore) -> int:
    document, master_password = _load_document_with_password(store, allow_prompt=True)
    if document is None or master_password is None:
        return EXIT_LOCKED

    password = _read_secret_value(None, args.stdin, prompt_text="SMTP password: ")
    record = SmtpAccountRecord(
        record_id=next_record_id(RecordType.SMTP_ACCOUNT, document.records.keys()),
        service_name=args.service_name,
        entity_id=args.entity_id,
        department_id=args.department_id,
        account_label=args.account_label,
        usage_purpose=args.usage_purpose,
        context_refs=list(args.context_ref),
        classification=Classification(args.classification),
        description=args.description,
        tags=list(args.tag),
        owner=args.owner,
        rotation_policy=_rotation_policy(args.rotation_days),
        expires_at=_compute_expiry(args.rotation_days),
        host=args.host,
        port=args.port,
        username=args.username,
        password=password,
        from_address=args.from_address,
        use_ssl=args.use_ssl,
        starttls=args.starttls,
        fingerprint=_fingerprint(password),
    )

    document.upsert_record(record, aliases=_candidate_aliases(record))
    store.save_document(document, master_password)
    print(f"Saved: {record.record_id}")
    return EXIT_OK


def _handle_list(args: argparse.Namespace, store: FileVaultStore) -> int:
    document, _ = _load_document_with_password(store, allow_prompt=True)
    if document is None:
        return EXIT_LOCKED

    records = _filter_records(document.list_records(), args)
    records = sorted(records, key=lambda record: (record.service_name, record.entity_id or "", record.account_label or "", record.record_id))

    if args.json:
        print(
            json.dumps(
                [_masked_record_payload(record, reveal_password=False) for record in records],
                ensure_ascii=False,
                indent=2,
            )
        )
        return EXIT_OK

    rows = [
        {
            "RECORD_ID": record.record_id,
            "TYPE": record.record_type.value,
            "SERVICE": record.service_name,
            "ENTITY": record.entity_id or "",
            "ACCOUNT_LABEL": record.account_label or "",
            "CLASSIFICATION": record.classification.value,
            "UPDATED_AT": _display_datetime(record.updated_at),
        }
        for record in records
    ]
    _print_table(rows, ["RECORD_ID", "TYPE", "SERVICE", "ENTITY", "ACCOUNT_LABEL", "CLASSIFICATION", "UPDATED_AT"])
    return EXIT_OK


def _handle_view(args: argparse.Namespace, store: FileVaultStore) -> int:
    document, _ = _load_document_with_password(store, allow_prompt=True)
    if document is None:
        return EXIT_LOCKED

    record = document.get_record(args.record_ref)
    if record is None:
        print(f"key not found: {args.record_ref}", file=sys.stderr)
        return EXIT_NOT_FOUND

    if args.json:
        payload = _masked_record_payload(record, reveal_password=args.reveal_password)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return EXIT_OK

    for key, value in _display_pairs(record, reveal_password=args.reveal_password):
        print(f"{key}: {value}")
    return EXIT_OK


def _handle_delete(args: argparse.Namespace, store: FileVaultStore) -> int:
    document, master_password = _load_document_with_password(store, allow_prompt=True)
    if document is None or master_password is None:
        return EXIT_LOCKED

    deleted = document.delete_record(args.record_ref)
    store.save_document(document, master_password)
    print(f"Deleted: {deleted.record_id}")
    return EXIT_OK


def _handle_revoke(args: argparse.Namespace, store: FileVaultStore) -> int:
    document, master_password = _load_document_with_password(store, allow_prompt=True)
    if document is None or master_password is None:
        return EXIT_LOCKED

    record = document.revoke_record(args.record_ref)
    if args.reason:
        record.description = f"{record.description}\nRevoke reason: {args.reason}".strip()
        document.upsert_record(record)

    store.save_document(document, master_password)
    print(f"Revoked: {record.record_id}")
    return EXIT_OK


def _handle_due(args: argparse.Namespace, store: FileVaultStore) -> int:
    if args.due_command == "notify":
        print("due notify はまだ未実装です。", file=sys.stderr)
        return EXIT_INTERNAL

    document, _ = _load_document_with_password(store, allow_prompt=True)
    if document is None:
        return EXIT_LOCKED

    deadline = datetime.now(UTC) + timedelta(days=args.days)
    due_records = []
    for record in document.list_records():
        if record.expires_at and record.expires_at <= deadline:
            due_records.append(record)
        elif record.status is RecordStatus.ROTATION_DUE:
            due_records.append(record)

    due_records = sorted(due_records, key=lambda record: record.expires_at or datetime.max.replace(tzinfo=UTC))

    if args.json:
        print(json.dumps([record.to_dict() for record in due_records], ensure_ascii=False, indent=2))
        return EXIT_OK

    rows = [
        {
            "RECORD_ID": record.record_id,
            "SERVICE": record.service_name,
            "ENTITY": record.entity_id or "",
            "ACCOUNT_LABEL": record.account_label or "",
            "STATUS": record.status.value,
            "DUE_DATE": _display_datetime(record.expires_at) if record.expires_at else "",
        }
        for record in due_records
    ]
    _print_table(rows, ["RECORD_ID", "SERVICE", "ENTITY", "ACCOUNT_LABEL", "STATUS", "DUE_DATE"])
    return EXIT_OK


def _handle_audit(args: argparse.Namespace, store: FileVaultStore) -> int:
    document, _ = _load_document_with_password(store, allow_prompt=True)
    if document is None:
        return EXIT_LOCKED

    record = document.get_record(args.record_ref)
    if record is None:
        print(f"key not found: {args.record_ref}", file=sys.stderr)
        return EXIT_NOT_FOUND

    payload = {
        "record_id": record.record_id,
        "status": record.status.value,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
        "last_verified_at": record.last_verified_at.isoformat() if record.last_verified_at else None,
        "last_tested_at": record.last_tested_at.isoformat() if record.last_tested_at else None,
        "last_tested_by": record.last_tested_by,
        "last_test_status": record.last_test_status.value,
        "last_test_note": record.last_test_note,
        "revoked_at": record.revoked_at.isoformat() if record.revoked_at else None,
        "owner": record.owner,
        "fingerprint": record.fingerprint,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return EXIT_OK

    for key, value in payload.items():
        print(f"{key}: {value}")
    return EXIT_OK


def _handle_check(args: argparse.Namespace, store: FileVaultStore) -> int:
    document, master_password = _load_document_with_password(store, allow_prompt=True)
    if document is None or master_password is None:
        return EXIT_LOCKED

    record = document.get_record(args.record_ref)
    if record is None:
        print(f"key not found: {args.record_ref}", file=sys.stderr)
        return EXIT_NOT_FOUND

    checked_at = datetime.fromisoformat(args.at) if args.at else datetime.now(UTC)
    check_status = CheckStatus(args.status)
    record.last_tested_at = checked_at
    record.last_tested_by = args.by
    record.last_test_status = check_status
    record.last_test_note = args.note
    if check_status is CheckStatus.OK:
        record.last_verified_at = checked_at
    record.updated_at = checked_at

    document.upsert_record(record)
    store.save_document(document, master_password)
    print(f"Checked: {record.record_id} ({check_status.value})")
    return EXIT_OK


def _handle_doctor(args: argparse.Namespace, store: FileVaultStore) -> int:
    issues: list[dict[str, str]] = []

    if store.exists():
        issues.append({"level": "OK", "message": "vault file exists"})
        if os.name == "posix":
            mode = oct(os.stat(store.paths.vault_path).st_mode & 0o777)
            if mode != "0o600":
                issues.append({"level": "WARN", "message": f"vault file permissions are too broad: {mode}"})
            else:
                issues.append({"level": "OK", "message": f"vault file permissions are restrictive: {mode}"})
    else:
        issues.append({"level": "WARN", "message": "vault file does not exist"})

    issues.append({"level": "OK", "message": f"vault path: {store.paths.vault_path}"})

    if args.json:
        print(json.dumps(issues, ensure_ascii=False, indent=2))
        return EXIT_OK

    for issue in issues:
        print(f"[{issue['level']}] {issue['message']}")
    return EXIT_OK


def _handle_ensure(args: argparse.Namespace, store: FileVaultStore) -> int:
    requirements = load_requirement_spec(Path(args.spec))
    document, master_password = _load_document_with_password(store, allow_prompt=True)
    if document is None or master_password is None:
        return EXIT_LOCKED

    if sync_requirement_aliases(document, requirements):
        store.save_document(document, master_password)

    missing_statuses = missing_requirements(document, requirements)
    if not missing_statuses:
        if args.json:
            print(json.dumps({"status": "ok", "missing": []}, ensure_ascii=False, indent=2))
        else:
            print("All required credentials are present.")
        return EXIT_OK

    if args.json:
        print(
            json.dumps(
                {
                    "status": "missing",
                    "missing": [
                        {
                            "record_ref": status.requirement.record_ref,
                            "record_type": status.requirement.record_type.value,
                            "missing_fields": status.missing_fields,
                            "service_name": status.requirement.record_data.get("service_name"),
                            "entity_id": status.requirement.record_data.get("entity_id"),
                            "account_label": status.requirement.record_data.get("account_label"),
                            "context_refs": status.requirement.record_data.get("context_refs", []),
                        }
                        for status in missing_statuses
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for status in missing_statuses:
            print(
                f"MISSING {status.requirement.record_ref} ({status.requirement.record_type.value}): "
                f"{', '.join(status.missing_fields)}"
            )

    if not args.launch_form:
        return EXIT_MISSING

    form_state = launch_input_form(
        store=store,
        master_password=master_password,
        statuses=missing_statuses,
        host=args.host,
        port=args.port,
    )
    if form_state.completed:
        print("Missing credentials have been saved.")
        return EXIT_OK
    return EXIT_MISSING


def _handle_render(args: argparse.Namespace, store: FileVaultStore) -> int:
    document, _ = _load_document_with_password(store, allow_prompt=True)
    if document is None:
        return EXIT_LOCKED

    template_path = Path(args.template_path)
    rendered_text = render_template_file(template_path, document)

    if args.stdout or not args.output:
        print(rendered_text, end="")
        if not args.output:
            return EXIT_OK

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered_text, encoding="utf-8")
    _restrict_path(output_path)
    print(f"Rendered: {output_path}")
    return EXIT_OK


def _handle_exec(args: argparse.Namespace, store: FileVaultStore) -> int:
    if not args.command_args:
        raise ValueError("exec requires a command after --")

    command_args = list(args.command_args)
    if command_args and command_args[0] == "--":
        command_args = command_args[1:]
    if not command_args:
        raise ValueError("exec requires a command after --")

    document, _ = _load_document_with_password(store, allow_prompt=True)
    if document is None:
        return EXIT_LOCKED

    rendered_text = render_template_file(Path(args.template), document)
    store.paths.session_dir.mkdir(parents=True, exist_ok=True)

    template_suffix = Path(args.template).suffix or ".tmp"
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=template_suffix,
        prefix="credential-vault-",
        dir=store.paths.session_dir,
        delete=False,
    ) as temp_file:
        temp_file.write(rendered_text)
        temp_path = Path(temp_file.name)

    _restrict_path(temp_path)

    replaced_args = [arg.replace(args.placeholder, str(temp_path)) for arg in command_args]
    env = os.environ.copy()
    env["CREDENTIAL_VAULT_RENDERED_TEMPLATE"] = str(temp_path)

    try:
        completed = subprocess.run(replaced_args, env=env, check=False)
        return completed.returncode
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


def _load_document_with_password(store: FileVaultStore, *, allow_prompt: bool) -> tuple[VaultDocument | None, str | None]:
    if not store.exists():
        raise FileNotFoundError(store.paths.vault_path)

    master_password = _read_master_password(allow_prompt=allow_prompt)
    if not master_password:
        return None, None

    document = store.load_document(master_password)
    return document, master_password


def _read_master_password(*, allow_prompt: bool) -> str | None:
    env_value = os.environ.get("CREDENTIAL_VAULT_MASTER_PASSWORD")
    if env_value:
        return env_value

    if allow_prompt and _can_prompt():
        return getpass.getpass("Master password: ")

    return None


def _read_new_master_password() -> str | None:
    env_value = os.environ.get("CREDENTIAL_VAULT_MASTER_PASSWORD")
    if env_value:
        confirm_value = os.environ.get("CREDENTIAL_VAULT_MASTER_PASSWORD_CONFIRM", env_value)
        if env_value != confirm_value:
            raise ValueError("master password confirmation mismatch.")
        return env_value

    if not _can_prompt():
        return None

    first = getpass.getpass("Master password: ")
    second = getpass.getpass("Confirm password: ")
    if first != second:
        raise ValueError("master password confirmation mismatch.")
    return first


def _read_secret_value(value: str | None, use_stdin: bool, *, prompt_text: str) -> str:
    if value is not None and use_stdin:
        raise ValueError("value argument and --stdin cannot be used together.")

    if value is not None:
        return value

    if use_stdin:
        stdin_value = sys.stdin.read()
        return stdin_value.rstrip("\r\n")

    if _can_prompt():
        return getpass.getpass(prompt_text)

    raise ValueError("secret value is required.")


def _rotation_policy(rotation_days: int | None) -> RotationPolicy:
    return RotationPolicy(
        mode=RotationMode.MANUAL,
        interval_days=rotation_days,
        notify_before_days=7,
    )


def _compute_expiry(rotation_days: int | None) -> datetime | None:
    if not rotation_days:
        return None
    return datetime.now(UTC) + timedelta(days=rotation_days)


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _candidate_aliases(record: SecretRecord) -> list[str]:
    aliases = [record.record_id]

    if isinstance(record, ApiSecretRecord):
        if record.entity_id:
            aliases.append(f"{record.entity_id}:{record.secret_key_name}")
        else:
            aliases.append(record.secret_key_name)

    if record.entity_id and record.account_label:
        aliases.append(f"{record.service_name}:{record.entity_id}:{record.account_label}")

    if isinstance(record, MailboxAccountRecord):
        aliases.append(f"{record.host}:{record.username}")

    if isinstance(record, SmtpAccountRecord):
        aliases.append(f"{record.host}:{record.username}")

    return aliases


def _filter_records(records: list[SecretRecord], args: argparse.Namespace) -> list[SecretRecord]:
    filtered = records

    if args.classification:
        classification = Classification(args.classification)
        filtered = [record for record in filtered if record.classification is classification]

    if args.tag:
        required_tags = set(args.tag)
        filtered = [record for record in filtered if required_tags.issubset(set(record.tags))]

    if args.service:
        filtered = [record for record in filtered if record.service_name == args.service]

    if args.entity_id:
        filtered = [record for record in filtered if record.entity_id == args.entity_id]

    if args.context_ref:
        required_refs = set(args.context_ref)
        filtered = [record for record in filtered if required_refs.issubset(set(record.context_refs))]

    return filtered


def _display_pairs(record: SecretRecord, *, reveal_password: bool) -> list[tuple[str, str]]:
    pairs = [
        ("Record ID", record.record_id),
        ("Record type", record.record_type.value),
        ("Service", record.service_name),
        ("Entity", record.entity_id or ""),
        ("Account label", record.account_label or ""),
        ("Context refs", ", ".join(record.context_refs)),
        ("Classification", record.classification.value),
        ("Status", record.status.value),
        ("Description", record.description),
        ("Tags", ", ".join(record.tags)),
    ]

    if isinstance(record, ApiSecretRecord):
        pairs.extend(
            [
                ("Secret key", record.secret_key_name),
                ("Environment", record.environment or ""),
                ("Value", record.secret_value if reveal_password else "********"),
            ]
        )

    if isinstance(record, MachineSecretRecord):
        pairs.extend(
            [
                ("Provider", record.provider),
                ("Consumer", record.consumer),
                ("Transport mode", record.transport_mode or ""),
                ("Value", record.secret_value if reveal_password else "********"),
            ]
        )

    if isinstance(record, WebLoginRecord):
        pairs.extend(
            [
                ("Login URL", record.login_url),
                ("Company code", record.company_code or ""),
                ("User code", record.user_code or ""),
                ("Username", record.username or ""),
                ("Auth flow", record.auth_flow or ""),
                ("OTP contact", record.otp_contact or ""),
                ("OTP owner", record.otp_owner or ""),
                ("Recovery URL", record.recovery_url or ""),
                ("Recovery note", record.recovery_note or ""),
                ("MFA note", record.mfa_note or ""),
                ("Login note", record.login_note or ""),
                ("Password", record.password if reveal_password else "********"),
            ]
        )

    if isinstance(record, MailboxAccountRecord):
        pairs.extend(
            [
                ("Host", record.host),
                ("Port", "" if record.port is None else str(record.port)),
                ("Protocol", record.protocol),
                ("Username", record.username),
                ("Mailbox name", record.mailbox_name or ""),
                ("Use SSL", str(record.use_ssl)),
                ("Password", record.password if reveal_password else "********"),
            ]
        )

    if isinstance(record, SmtpAccountRecord):
        pairs.extend(
            [
                ("Host", record.host),
                ("Port", "" if record.port is None else str(record.port)),
                ("Username", record.username),
                ("From address", record.from_address),
                ("Use SSL", str(record.use_ssl)),
                ("STARTTLS", str(record.starttls)),
                ("Password", record.password if reveal_password else "********"),
            ]
        )

    pairs.extend(
        [
            ("Last test status", record.last_test_status.value),
            ("Last tested at", _display_datetime(record.last_tested_at)),
            ("Last tested by", record.last_tested_by or ""),
            ("Last test note", record.last_test_note),
            ("Created at", _display_datetime(record.created_at)),
            ("Updated at", _display_datetime(record.updated_at)),
        ]
    )
    return pairs


def _print_table(rows: list[dict[str, str]], headers: list[str]) -> None:
    if not rows:
        print("(no records)")
        return

    widths = {header: len(header) for header in headers}
    for row in rows:
        for header in headers:
            widths[header] = max(widths[header], len(str(row.get(header, ""))))

    print("  ".join(header.ljust(widths[header]) for header in headers))
    for row in rows:
        print("  ".join(str(row.get(header, "")).ljust(widths[header]) for header in headers))


def _display_datetime(value: datetime | None) -> str:
    if not value:
        return ""
    return value.astimezone().strftime("%Y-%m-%d %H:%M")


def _is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stderr.isatty()


def _can_prompt() -> bool:
    return sys.stdin.isatty() or sys.stderr.isatty()


def _restrict_path(path: Path) -> None:
    if os.name == "posix":
        os.chmod(path, 0o600)


def _masked_record_payload(record: SecretRecord, *, reveal_password: bool) -> dict[str, Any]:
    payload = record.to_dict()
    if reveal_password:
        return payload

    if isinstance(record, ApiSecretRecord):
        payload["secret_value"] = "********"
    if isinstance(record, MachineSecretRecord):
        payload["secret_value"] = "********"
    if isinstance(record, (WebLoginRecord, MailboxAccountRecord, SmtpAccountRecord)):
        payload["password"] = "********"
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
