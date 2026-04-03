from pathlib import Path

from credential_vault.inventory_workspace import build_mail_invoice_workspace


def test_build_mail_invoice_workspace_creates_override_and_working_files(tmp_path: Path) -> None:
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
                "",
            ]
        ),
        encoding="utf-8-sig",
    )
    docs_root = tmp_path / "docs"

    outputs = build_mail_invoice_workspace(
        requirements_path=requirements_path,
        service_inventory_path=service_inventory_path,
        docs_root=docs_root,
    )

    assert outputs["override_credential"].exists()
    assert outputs["override_auth"].exists()
    assert outputs["override_check"].exists()
    assert outputs["working_credential"].exists()
    assert outputs["working_auth"].exists()
    assert outputs["working_check"].exists()

    credential_override_text = outputs["override_credential"].read_text(encoding="utf-8-sig")
    assert "VISA_VPASS" in credential_override_text
    assert "fill_priority" in credential_override_text
    assert "P1" in credential_override_text

    auth_working_text = outputs["working_auth"].read_text(encoding="utf-8-sig")
    assert "Edge または Chrome" in auth_working_text

    auth_override_text = outputs["override_auth"].read_text(encoding="utf-8-sig")
    assert "auth_flow、otp_owner" in auth_override_text
