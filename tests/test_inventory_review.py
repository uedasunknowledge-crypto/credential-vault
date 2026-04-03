import csv
from pathlib import Path

from credential_vault.inventory_seed import AUTH_HEADERS, CHECK_HEADERS, CREDENTIAL_HEADERS
from credential_vault.inventory_review import build_priority_actions, review_inventory_csvs


def test_review_inventory_csvs_reports_missing_owner_and_candidate_rows(tmp_path: Path) -> None:
    credential_csv = tmp_path / "credential.csv"
    _write_csv(
        credential_csv,
        CREDENTIAL_HEADERS,
        [
            {
                "migration_status": "candidate_from_service_inventory",
                "source_type": "service_inventory",
                "source_locator": "C:/tmp/source.csv",
                "service_name": "visa-vpass",
                "record_type": "web_login",
                "entity_id": "",
                "department_id": "",
                "account_label": "VISA Vpass",
                "usage_purpose": "売上明細取得",
                "login_url": "https://example.com/login",
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
                "rotation_days": "90",
                "owner": "",
                "context_refs": "project:mail-invoice|vendor:VISA_VPASS",
                "vault_record_ref": "candidate:VISA_VPASS",
                "notes": "seed row",
            }
        ],
    )
    auth_csv = tmp_path / "auth.csv"
    _write_csv(
        auth_csv,
        AUTH_HEADERS,
        [
            {
                "vault_record_ref": "candidate:VISA_VPASS",
                "service_name": "visa-vpass",
                "account_label": "VISA Vpass",
                "auth_flow": "",
                "otp_contact": "",
                "otp_owner": "",
                "required_device": "Edge",
                "recovery_url": "https://example.com/login",
                "recovery_note": "",
                "mfa_note": "",
                "login_note": "",
            }
        ],
    )
    check_csv = tmp_path / "check.csv"
    _write_csv(
        check_csv,
        CHECK_HEADERS,
        [
            {
                "vault_record_ref": "candidate:VISA_VPASS",
                "checked_at": "2026-04-03",
                "checked_by": "inventory-import",
                "target_kind": "web_login",
                "check_status": "attention",
                "check_method": "manual",
                "result_summary": "未確認",
                "next_action": "source locator を更新",
            }
        ],
    )

    report = review_inventory_csvs(credential_csv, auth_csv, check_csv)

    messages = [issue.message for issue in report.issues]
    assert any("candidate 状態" in message for message in messages)
    assert any("owner が未設定" in message for message in messages)
    assert any("auth_flow が未設定" in message for message in messages)


def test_build_priority_actions_sorts_p1_before_p2(tmp_path: Path) -> None:
    credential_override_csv = tmp_path / "credential_override.csv"
    credential_override_csv.write_text(
        "\n".join(
            [
                "vault_record_ref,service_name,account_label,fill_priority,fill_hint,source_type,source_locator,entity_id,department_id,usage_purpose,login_url,tenant_code,host,port,protocol,username,mailbox_name,from_address,use_ssl,starttls,company_code,user_code,owner,classification,rotation_days,context_refs,notes",
                "candidate:JCB,jcb,JCB,P2,候補を確認,,,,,,,,,,,,,,,,,,,,,,",
                "MAILBOX_PRIMARY,mail-invoice,請求書受信POP,P1,先に埋める,,,,,,,,,,,,,,,,,,,,,,",
                "",
            ]
        ),
        encoding="utf-8-sig",
    )
    auth_override_csv = tmp_path / "auth_override.csv"
    auth_override_csv.write_text(
        "\n".join(
            [
                "vault_record_ref,service_name,account_label,fill_priority,fill_hint,auth_flow,otp_contact,otp_owner,required_device,recovery_url,recovery_note,mfa_note,login_note",
                "VISA_VPASS,visa-vpass,VISA Vpass,P1,認証フロー確認,,,,,,,,",
                "",
            ]
        ),
        encoding="utf-8-sig",
    )

    actions = build_priority_actions(
        credential_override_csv=credential_override_csv,
        auth_override_csv=auth_override_csv,
    )

    assert [action.key for action in actions] == ["VISA_VPASS", "MAILBOX_PRIMARY", "candidate:JCB"]
    assert actions[0].priority == "P1"
    assert actions[2].priority == "P2"


def _write_csv(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
