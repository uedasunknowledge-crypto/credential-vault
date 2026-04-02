from credential_vault.config import VaultPaths
from credential_vault.models import ApiSecretRecord, RecordStatus
from credential_vault.vault_store import FileVaultStore, VaultDocument


def test_upsert_and_resolve_by_alias() -> None:
    document = VaultDocument.empty()
    record = ApiSecretRecord(
        record_id="rec_api_001",
        service_name="notion",
        entity_id="C02",
        account_label="本番API",
        secret_key_name="NOTION_TOKEN",
        secret_value="secret",
    )

    document.upsert_record(record, aliases=["NOTION_TOKEN"])

    loaded = document.get_record("NOTION_TOKEN")

    assert loaded is not None
    assert loaded.record_id == "rec_api_001"
    assert loaded.display_name() == "notion / C02 / 本番API"


def test_revoke_record_updates_status() -> None:
    document = VaultDocument.empty()
    record = ApiSecretRecord(
        record_id="rec_api_001",
        service_name="notion",
        secret_key_name="NOTION_TOKEN",
        secret_value="secret",
    )
    document.upsert_record(record)

    revoked = document.revoke_record("rec_api_001")

    assert revoked.status is RecordStatus.REVOKED
    assert revoked.revoked_at is not None


def test_file_store_initialize_and_load_roundtrip(tmp_path) -> None:
    paths = VaultPaths(
        root_dir=tmp_path,
        vault_path=tmp_path / "vault.enc",
        session_dir=tmp_path / ".session",
        session_socket=tmp_path / ".session" / "agent.sock",
        state_path=tmp_path / "vault.state.json",
        lock_path=tmp_path / "vault.lock",
    )
    store = FileVaultStore(paths)

    document = VaultDocument.empty()
    document.upsert_record(
        ApiSecretRecord(
            record_id="rec_api_001",
            service_name="notion",
            secret_key_name="NOTION_TOKEN",
            secret_value="secret",
        ),
        aliases=["NOTION_TOKEN"],
    )

    store.save_document(document, "master-password")
    loaded = store.load_document("master-password")

    assert loaded.get_record("NOTION_TOKEN") is not None
