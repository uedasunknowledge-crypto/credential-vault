from credential_vault.cli import build_parser


def test_add_login_accepts_multiple_account_identifiers() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "add",
            "login",
            "freee-admin",
            "--entity-id",
            "C02",
            "--department-id",
            "D01",
            "--account-label",
            "経理管理者",
            "--usage-purpose",
            "月次締め",
            "--login-url",
            "https://accounts.secure.freee.co.jp/",
            "--company-code",
            "C02",
            "--user-code",
            "admin@example.com",
            "--auth-flow",
            "password_plus_totp",
            "--otp-owner",
            "経理責任者",
        ]
    )

    assert args.command == "add"
    assert args.record_kind == "login"
    assert args.entity_id == "C02"
    assert args.department_id == "D01"
    assert args.account_label == "経理管理者"
    assert args.company_code == "C02"
    assert args.auth_flow == "password_plus_totp"
    assert args.otp_owner == "経理責任者"


def test_list_supports_service_and_entity_filters() -> None:
    parser = build_parser()

    args = parser.parse_args(["list", "--service", "freee-admin", "--entity-id", "C02"])

    assert args.command == "list"
    assert args.service == "freee-admin"
    assert args.entity_id == "C02"


def test_add_mailbox_accepts_host_account_and_context_refs() -> None:
    parser = build_parser()

    args = parser.parse_args(
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
        ]
    )

    assert args.command == "add"
    assert args.record_kind == "mailbox"
    assert args.host == "mail.example.com"
    assert args.username == "billing@example.com"
    assert args.context_ref == ["biz:C02", "project:mail-invoice"]


def test_check_parser_accepts_status_and_operator() -> None:
    parser = build_parser()

    args = parser.parse_args(["check", "MAILBOX_PRIMARY", "--status", "ok", "--by", "kouhe", "--note", "POP 接続成功"])

    assert args.command == "check"
    assert args.record_ref == "MAILBOX_PRIMARY"
    assert args.status == "ok"
    assert args.by == "kouhe"
