from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class VaultCryptoError(Exception):
    """暗号化処理全般のエラー。"""


class VaultIntegrityError(VaultCryptoError):
    """復号できない、または改ざんが疑われる場合のエラー。"""


@dataclass(frozen=True, slots=True)
class KdfParams:
    name: str = "scrypt"
    n: int = 32768
    r: int = 8
    p: int = 1
    salt: bytes = b""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "n": self.n,
            "r": self.r,
            "p": self.p,
            "salt_b64": _b64encode(self.salt),
        }

    @classmethod
    def generate(cls) -> "KdfParams":
        return cls(salt=os.urandom(16))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KdfParams":
        if data.get("name") != "scrypt":
            raise VaultCryptoError("未対応の KDF です。")

        return cls(
            name=data["name"],
            n=int(data["n"]),
            r=int(data["r"]),
            p=int(data["p"]),
            salt=_b64decode(data["salt_b64"]),
        )


def encrypt_json_payload(
    payload: dict[str, Any],
    master_password: str,
    *,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    kdf_params = KdfParams.generate()
    key = _derive_key(master_password, kdf_params)
    nonce = os.urandom(12)
    plaintext = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)

    now = datetime.now(UTC)
    created = created_at or now

    return {
        "version": 1,
        "cipher": "AES-256-GCM",
        "kdf": kdf_params.to_dict(),
        "nonce_b64": _b64encode(nonce),
        "ciphertext_b64": _b64encode(ciphertext),
        "created_at": created.isoformat(),
        "updated_at": now.isoformat(),
    }


def decrypt_json_payload(envelope: dict[str, Any], master_password: str) -> dict[str, Any]:
    if envelope.get("version") != 1:
        raise VaultCryptoError("未対応の vault バージョンです。")

    if envelope.get("cipher") != "AES-256-GCM":
        raise VaultCryptoError("未対応の暗号方式です。")

    kdf_params = KdfParams.from_dict(envelope["kdf"])
    key = _derive_key(master_password, kdf_params)
    nonce = _b64decode(envelope["nonce_b64"])
    ciphertext = _b64decode(envelope["ciphertext_b64"])

    try:
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, None)
    except Exception as exc:  # noqa: BLE001
        raise VaultIntegrityError("復号に失敗しました。パスワード不一致または改ざんの可能性があります。") from exc

    try:
        return json.loads(plaintext.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise VaultIntegrityError("復号後データの JSON 解析に失敗しました。") from exc


def envelope_created_at(envelope: dict[str, Any]) -> datetime | None:
    raw_value = envelope.get("created_at")
    if not raw_value:
        return None
    return datetime.fromisoformat(raw_value)


def _derive_key(master_password: str, kdf_params: KdfParams) -> bytes:
    return hashlib.scrypt(
        master_password.encode("utf-8"),
        salt=kdf_params.salt,
        n=kdf_params.n,
        r=kdf_params.r,
        p=kdf_params.p,
        dklen=32,
        maxmem=_scrypt_maxmem(kdf_params),
    )


def _b64encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _b64decode(data: str) -> bytes:
    return base64.b64decode(data.encode("ascii"))


def _scrypt_maxmem(kdf_params: KdfParams) -> int:
    estimated_bytes = 128 * kdf_params.n * kdf_params.r
    return max(estimated_bytes * 2, 64 * 1024 * 1024)
