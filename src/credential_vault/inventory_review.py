from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from credential_vault.inventory_seed import AUTH_HEADERS, CHECK_HEADERS, CREDENTIAL_HEADERS


@dataclass(slots=True)
class InventoryIssue:
    level: str
    area: str
    key: str
    message: str


@dataclass(slots=True)
class InventoryAction:
    priority: str
    area: str
    key: str
    hint: str


@dataclass(slots=True)
class InventoryReviewReport:
    credential_count: int
    auth_count: int
    check_count: int
    issues: list[InventoryIssue]

    def to_dict(self) -> dict[str, object]:
        return {
            "credential_count": self.credential_count,
            "auth_count": self.auth_count,
            "check_count": self.check_count,
            "issues": [asdict(issue) for issue in self.issues],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def to_text(self) -> str:
        lines = [
            f"credentials: {self.credential_count}",
            f"auth_steps: {self.auth_count}",
            f"login_checks: {self.check_count}",
            f"issues: {len(self.issues)}",
        ]
        for issue in self.issues:
            lines.append(f"[{issue.level}] {issue.area} {issue.key}: {issue.message}")
        return "\n".join(lines) + "\n"


def read_csv_rows(csv_path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), [dict(row) for row in reader]


def build_priority_actions(
    *,
    credential_override_csv: Path | None = None,
    auth_override_csv: Path | None = None,
) -> list[InventoryAction]:
    actions: list[InventoryAction] = []
    actions.extend(_read_priority_actions(credential_override_csv, area="credential"))
    actions.extend(_read_priority_actions(auth_override_csv, area="auth"))
    return sorted(actions, key=_priority_sort_key)


def review_inventory_csvs(
    credential_csv: Path,
    auth_csv: Path,
    check_csv: Path,
) -> InventoryReviewReport:
    issues: list[InventoryIssue] = []

    credential_headers, credential_rows = read_csv_rows(credential_csv)
    auth_headers, auth_rows = read_csv_rows(auth_csv)
    check_headers, check_rows = read_csv_rows(check_csv)

    _check_headers("credential", credential_headers, CREDENTIAL_HEADERS, issues)
    _check_headers("auth", auth_headers, AUTH_HEADERS, issues)
    _check_headers("check", check_headers, CHECK_HEADERS, issues)

    credential_by_ref: dict[str, dict[str, str]] = {}
    auth_by_ref: dict[str, dict[str, str]] = {}
    identity_counts: dict[tuple[str, str, str, str, str], int] = {}

    for row in credential_rows:
        ref = row.get("vault_record_ref", "").strip()
        if not ref:
            issues.append(InventoryIssue("error", "credential", "(blank)", "vault_record_ref が空です"))
            continue
        if ref in credential_by_ref:
            issues.append(InventoryIssue("error", "credential", ref, "credential 台帳で重複しています"))
        credential_by_ref[ref] = row

        identity = (
            row.get("service_name", "").strip(),
            row.get("record_type", "").strip(),
            row.get("entity_id", "").strip(),
            row.get("department_id", "").strip(),
            row.get("account_label", "").strip(),
        )
        identity_counts[identity] = identity_counts.get(identity, 0) + 1

        _review_credential_row(row, issues)

    for identity, count in identity_counts.items():
        if count > 1:
            issues.append(
                InventoryIssue(
                    "warn",
                    "credential",
                    "|".join(identity),
                    "service_name / record_type / entity_id / department_id / account_label の組み合わせが重複しています",
                )
            )

    for row in auth_rows:
        ref = row.get("vault_record_ref", "").strip()
        if not ref:
            issues.append(InventoryIssue("error", "auth", "(blank)", "vault_record_ref が空です"))
            continue
        if ref in auth_by_ref:
            issues.append(InventoryIssue("error", "auth", ref, "認証手順台帳で重複しています"))
        auth_by_ref[ref] = row
        _review_auth_row(row, credential_by_ref.get(ref), issues)

    for ref, credential_row in credential_by_ref.items():
        if credential_row.get("record_type") == "web_login" and ref not in auth_by_ref:
            issues.append(InventoryIssue("warn", "auth", ref, "web_login に対応する認証手順台帳の行がありません"))

    seen_check_keys: set[tuple[str, str]] = set()
    for row in check_rows:
        ref = row.get("vault_record_ref", "").strip()
        checked_at = row.get("checked_at", "").strip()
        if not ref:
            issues.append(InventoryIssue("error", "check", "(blank)", "vault_record_ref が空です"))
            continue
        if ref not in credential_by_ref:
            issues.append(InventoryIssue("warn", "check", ref, "login check に対応する credential 行がありません"))
        check_key = (ref, checked_at)
        if checked_at and check_key in seen_check_keys:
            issues.append(InventoryIssue("warn", "check", ref, f"checked_at={checked_at} が重複しています"))
        seen_check_keys.add(check_key)
        _review_check_row(row, issues)

    return InventoryReviewReport(
        credential_count=len(credential_rows),
        auth_count=len(auth_rows),
        check_count=len(check_rows),
        issues=issues,
    )


def _check_headers(area: str, actual: list[str], expected: list[str], issues: list[InventoryIssue]) -> None:
    missing = [header for header in expected if header not in actual]
    if missing:
        issues.append(InventoryIssue("error", area, "(headers)", f"不足列: {', '.join(missing)}"))


def _review_credential_row(row: dict[str, str], issues: list[InventoryIssue]) -> None:
    ref = row.get("vault_record_ref", "").strip() or "(blank)"
    for field_name in ("migration_status", "source_type", "source_locator", "service_name", "record_type", "account_label"):
        if not row.get(field_name, "").strip():
            issues.append(InventoryIssue("warn", "credential", ref, f"{field_name} が未入力です"))

    if row.get("migration_status", "").startswith("candidate"):
        issues.append(InventoryIssue("todo", "credential", ref, "candidate 状態です。実際の vault 登録と record_ref 確定が必要です"))

    if row.get("source_type") in {"code_requirement", "service_inventory"}:
        issues.append(InventoryIssue("todo", "credential", ref, "source_type を実際の保存場所へ更新してください"))

    if not row.get("owner", "").strip():
        issues.append(InventoryIssue("todo", "credential", ref, "owner が未設定です"))

    if row.get("record_type") in {"web_login", "mailbox_account", "smtp_account"} and not row.get("entity_id", "").strip():
        issues.append(InventoryIssue("todo", "credential", ref, "entity_id が未設定です"))

    if row.get("record_type") == "web_login" and not row.get("login_url", "").strip():
        issues.append(InventoryIssue("todo", "credential", ref, "web_login なのに login_url が未設定です"))

    if row.get("record_type") == "mailbox_account":
        for field_name in ("host", "protocol"):
            if not row.get(field_name, "").strip():
                issues.append(InventoryIssue("todo", "credential", ref, f"mailbox_account の {field_name} が未設定です"))
        if not row.get("use_ssl", "").strip():
            issues.append(InventoryIssue("todo", "credential", ref, "mailbox_account の use_ssl が未設定です"))

    if row.get("record_type") == "smtp_account":
        for field_name in ("host", "from_address"):
            if not row.get(field_name, "").strip():
                issues.append(InventoryIssue("todo", "credential", ref, f"smtp_account の {field_name} が未設定です"))
        if not row.get("use_ssl", "").strip():
            issues.append(InventoryIssue("todo", "credential", ref, "smtp_account の use_ssl が未設定です"))
        if not row.get("starttls", "").strip():
            issues.append(InventoryIssue("todo", "credential", ref, "smtp_account の starttls が未設定です"))


def _review_auth_row(
    row: dict[str, str],
    credential_row: dict[str, str] | None,
    issues: list[InventoryIssue],
) -> None:
    ref = row.get("vault_record_ref", "").strip() or "(blank)"
    if credential_row is None:
        issues.append(InventoryIssue("warn", "auth", ref, "認証手順台帳に対応する credential 行がありません"))
        return

    if row.get("service_name", "").strip() != credential_row.get("service_name", "").strip():
        issues.append(InventoryIssue("warn", "auth", ref, "service_name が credential 台帳と一致していません"))

    if not row.get("auth_flow", "").strip():
        issues.append(InventoryIssue("todo", "auth", ref, "auth_flow が未設定です"))

    auth_flow = row.get("auth_flow", "").lower()
    mfa_note = row.get("mfa_note", "")
    if any(keyword in auth_flow for keyword in ("totp", "otp", "mfa")) or any(keyword in mfa_note.upper() for keyword in ("OTP", "TOTP")):
        if not row.get("otp_contact", "").strip() and not row.get("otp_owner", "").strip():
            issues.append(InventoryIssue("todo", "auth", ref, "OTP / MFA の配送先または担当者が未設定です"))


def _review_check_row(row: dict[str, str], issues: list[InventoryIssue]) -> None:
    ref = row.get("vault_record_ref", "").strip() or "(blank)"
    for field_name in ("checked_at", "checked_by", "check_status"):
        if not row.get(field_name, "").strip():
            issues.append(InventoryIssue("warn", "check", ref, f"{field_name} が未入力です"))

    if row.get("check_status") in {"attention", "failed"} and not row.get("next_action", "").strip():
        issues.append(InventoryIssue("todo", "check", ref, "attention / failed なのに next_action が未設定です"))


def _read_priority_actions(csv_path: Path | None, *, area: str) -> list[InventoryAction]:
    if csv_path is None or not csv_path.exists():
        return []

    _headers, rows = read_csv_rows(csv_path)
    actions: list[InventoryAction] = []
    for row in rows:
        key = row.get("vault_record_ref", "").strip()
        priority = row.get("fill_priority", "").strip()
        hint = row.get("fill_hint", "").strip()
        if not key or not priority:
            continue
        actions.append(
            InventoryAction(
                priority=priority,
                area=area,
                key=key,
                hint=hint,
            )
        )
    return actions


def _priority_sort_key(action: InventoryAction) -> tuple[int, str, str]:
    return (_priority_rank(action.priority), action.area, action.key)


def _priority_rank(priority: str) -> int:
    priority = priority.upper().strip()
    if priority == "P1":
        return 1
    if priority == "P2":
        return 2
    if priority == "P3":
        return 3
    return 9
