from credential_vault.crypto import decrypt_json_payload, encrypt_json_payload


def test_encrypt_and_decrypt_roundtrip() -> None:
    payload = {"vault_version": 1, "records": {}, "aliases": {}}

    envelope = encrypt_json_payload(payload, "master-password")
    restored = decrypt_json_payload(envelope, "master-password")

    assert restored == payload
