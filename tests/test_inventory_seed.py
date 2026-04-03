from pathlib import Path

from credential_vault.inventory_seed import build_mail_invoice_seed


def test_build_mail_invoice_seed_creates_requirement_and_candidate_rows(tmp_path: Path) -> None:
    requirements_path = tmp_path / "requirements.yaml"
    requirements_path.write_text(
        "\n".join(
            [
                "records:",
                "  - record_ref: VISA_VPASS",
                "    record_type: web_login",
                "    required_fields: [login_url, username, password]",
                "    record:",
                "      service_name: visa-vpass",
                "      account_label: VISA Vpass",
                "      context_refs: [project:mail-invoice, vendor:VISA_VPASS]",
                '      login_url: "https://www3.vpass.ne.jp/kamei/top/index.jsp?cc=009"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    service_inventory_path = tmp_path / "service_inventory.csv"
    service_inventory_path.write_text(
        "\n".join(
            [
                "取引先コード,サービス名,文書種別キー,文書種別,取得可能化検知方式キー,取得可能化検知方式,発行周期キー,発行周期,保存先種別キー,保存先種別,実装状況キー,実装状況,検証状況キー,検証状況,最終確認日,進捗概要,補足,次のアクション",
                "VISA_VPASS,VISA Vpass,sales_statement,売上明細,scheduled_login,定期ログイン取得,multi_cutoff,複数締め,drive_named_upload,Google Drive命名アップロード,implemented,実装済み,verified,実行確認済み,2026-04-02,headlessで取得成功,run_vpass_schedule.py と state 管理あり,Task Scheduler 登録と月次運用確認",
                "FUJIFILM_BI_DIRECT,富士フイルムBIダイレクト,invoice,請求書,mail_notice_login,メール通知ログイン取得,monthly,月次,billone_email_forward,Bill Oneメール転送,scaffolded,受け皿あり,pending,実サイト未確認,2026-03-27,ruleとportal_downloader骨格あり,url_downloader の login_required 経路までは配線済み,実サイト疎通とDOM調整",
                "",
            ]
        ),
        encoding="utf-8-sig",
    )

    credential_rows, auth_rows, check_rows = build_mail_invoice_seed(requirements_path, service_inventory_path)

    assert any(row["vault_record_ref"] == "VISA_VPASS" for row in credential_rows)
    assert any(row["vault_record_ref"] == "candidate:FUJIFILM_BI_DIRECT" for row in credential_rows)
    fuji_row = next(row for row in credential_rows if row["vault_record_ref"] == "candidate:FUJIFILM_BI_DIRECT")
    assert fuji_row["service_name"] == "fujifilm-bi-direct"
    assert fuji_row["login_url"] == "https://direct-fb.fujifilm.com/ap1/ebilling/invoicelist"

    vpass_auth = next(row for row in auth_rows if row["vault_record_ref"] == "VISA_VPASS")
    assert vpass_auth["service_name"] == "visa-vpass"
    assert vpass_auth["required_device"] == "Edge または Chrome"
    assert vpass_auth["mfa_note"] == "追加認証要否は要確認"

    fuji_check = next(row for row in check_rows if row["vault_record_ref"] == "candidate:FUJIFILM_BI_DIRECT")
    assert fuji_check["check_status"] == "attention"
    assert fuji_check["check_method"] == "mail_notice_login"
