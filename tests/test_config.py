from pathlib import Path

from credential_vault.config import VaultPaths


def test_default_paths_respect_environment_overrides(monkeypatch) -> None:
    monkeypatch.setenv("CREDENTIAL_VAULT_ROOT", "/tmp/credential-vault")
    monkeypatch.setenv("CREDENTIAL_VAULT_SESSION_DIR", "/tmp/credential-vault-session")

    paths = VaultPaths.default()

    assert paths.root_dir == Path("/tmp/credential-vault")
    assert paths.vault_path == Path("/tmp/credential-vault/vault.enc")
    assert paths.session_dir == Path("/tmp/credential-vault-session")
    assert paths.session_socket == Path("/tmp/credential-vault-session/agent.sock")
