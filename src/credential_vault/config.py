from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from pathlib import Path


NH1_ROOT = Path("/home/horizontalhold/auto_project/credential-vault")


@dataclass(slots=True)
class VaultPaths:
    """vault と周辺ファイルの配置先をまとめる。"""

    root_dir: Path
    vault_path: Path
    session_dir: Path
    session_socket: Path
    state_path: Path
    lock_path: Path

    @classmethod
    def default(cls) -> "VaultPaths":
        root_dir = _resolve_root_dir()
        session_dir = _resolve_session_dir(root_dir)
        return cls(
            root_dir=root_dir,
            vault_path=root_dir / "vault.enc",
            session_dir=session_dir,
            session_socket=session_dir / "agent.sock",
            state_path=root_dir / "vault.state.json",
            lock_path=root_dir / "vault.lock",
        )


def _resolve_root_dir() -> Path:
    override = os.environ.get("CREDENTIAL_VAULT_ROOT")
    if override:
        return Path(override).expanduser()

    if platform.system() == "Linux":
        return NH1_ROOT

    # 開発環境では、意図せず Linux 本番パスへ書かないようにする。
    return Path.cwd()


def _resolve_session_dir(root_dir: Path) -> Path:
    override = os.environ.get("CREDENTIAL_VAULT_SESSION_DIR")
    if override:
        return Path(override).expanduser()

    xdg_runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if xdg_runtime_dir:
        return Path(xdg_runtime_dir) / "credential-vault"

    return root_dir / ".session"
