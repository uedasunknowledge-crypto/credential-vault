from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from credential_vault.config import VaultPaths
from credential_vault.crypto import (
    VaultIntegrityError,
    decrypt_json_payload,
    encrypt_json_payload,
    envelope_created_at,
)
from credential_vault.identifiers import normalize_alias
from credential_vault.models import RecordStatus, SecretRecord, record_from_dict


@dataclass(slots=True)
class VaultDocument:
    """暗号化前の vault ドキュメントを扱う。"""

    vault_version: int = 1
    records: dict[str, dict[str, Any]] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> "VaultDocument":
        return cls()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VaultDocument":
        return cls(
            vault_version=data.get("vault_version", 1),
            records=dict(data.get("records", {})),
            aliases=dict(data.get("aliases", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "vault_version": self.vault_version,
            "records": self.records,
            "aliases": self.aliases,
        }

    def list_records(self) -> list[SecretRecord]:
        return [record_from_dict(record) for record in self.records.values()]

    def get_record(self, record_ref: str) -> SecretRecord | None:
        record_id = self.resolve_record_id(record_ref)
        if not record_id:
            return None
        return record_from_dict(self.records[record_id])

    def resolve_record_id(self, record_ref: str) -> str | None:
        if record_ref in self.records:
            return record_ref

        alias = normalize_alias(record_ref)
        return self.aliases.get(alias)

    def upsert_record(self, record: SecretRecord, aliases: list[str] | None = None) -> None:
        self.records[record.record_id] = record.to_dict()

        for alias in aliases or []:
            normalized_alias = normalize_alias(alias)
            existing_record_id = self.aliases.get(normalized_alias)
            if existing_record_id and existing_record_id != record.record_id:
                raise ValueError(f"alias already assigned: {alias}")
            self.aliases[normalized_alias] = record.record_id

    def revoke_record(self, record_ref: str, revoked_at: datetime | None = None) -> SecretRecord:
        record = self.get_record(record_ref)
        if record is None:
            raise KeyError(f"record not found: {record_ref}")

        record.status = RecordStatus.REVOKED
        record.revoked_at = revoked_at or datetime.now(UTC)
        record.updated_at = record.revoked_at
        self.records[record.record_id] = record.to_dict()
        return record

    def delete_record(self, record_ref: str) -> SecretRecord:
        record = self.get_record(record_ref)
        if record is None:
            raise KeyError(f"record not found: {record_ref}")

        self.records.pop(record.record_id, None)
        self.aliases = {
            alias: record_id
            for alias, record_id in self.aliases.items()
            if record_id != record.record_id
        }
        return record


@dataclass(slots=True)
class FileVaultStore:
    """暗号化された vault ファイルを読み書きする。"""

    paths: VaultPaths

    @classmethod
    def for_root(cls, root_dir: Path) -> "FileVaultStore":
        session_dir = root_dir / ".session"
        return cls(
            VaultPaths(
                root_dir=root_dir,
                vault_path=root_dir / "vault.enc",
                session_dir=session_dir,
                session_socket=session_dir / "agent.sock",
                state_path=root_dir / "vault.state.json",
                lock_path=root_dir / "vault.lock",
            )
        )

    def exists(self) -> bool:
        return self.paths.vault_path.exists()

    def initialize(self, master_password: str, *, overwrite: bool = False) -> VaultDocument:
        if self.exists() and not overwrite:
            raise FileExistsError(f"vault already exists: {self.paths.vault_path}")

        document = VaultDocument.empty()
        self.save_document(document, master_password)
        return document

    def load_document(self, master_password: str) -> VaultDocument:
        envelope = self._read_envelope()
        payload = decrypt_json_payload(envelope, master_password)
        return VaultDocument.from_dict(payload)

    def save_document(self, document: VaultDocument, master_password: str) -> None:
        created_at = None
        if self.exists():
            try:
                created_at = envelope_created_at(self._read_envelope())
            except Exception:  # noqa: BLE001
                created_at = None

        envelope = encrypt_json_payload(document.to_dict(), master_password, created_at=created_at)
        self._write_envelope(envelope)

    def _read_envelope(self) -> dict[str, Any]:
        raw_text = self.paths.vault_path.read_text(encoding="utf-8")
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise VaultIntegrityError("vault file is corrupted or cannot be parsed.") from exc

    def _write_envelope(self, envelope: dict[str, Any]) -> None:
        self.paths.root_dir.mkdir(parents=True, exist_ok=True)
        self.paths.session_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_parent(self.paths.vault_path)

        temp_path = self.paths.vault_path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=True) + os.linesep,
            encoding="utf-8",
        )

        _apply_restrictive_permissions(temp_path)
        temp_path.replace(self.paths.vault_path)
        _apply_restrictive_permissions(self.paths.vault_path)

    @staticmethod
    def _ensure_parent(path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)


def _apply_restrictive_permissions(path: Path) -> None:
    if os.name == "posix":
        os.chmod(path, 0o600)
