"""Encryption at rest for every stored file: FDR copies, bank letters and the letters the portal issues.

AES-256-GCM (authenticated: a file altered on disk fails to decrypt instead of returning tampered bytes). The key is
NIDHI_FILE_KEY (base64, 32 bytes) or the file named by NIDHI_FILE_KEY_FILE when set, otherwise derived from
NIDHI_SECRET_KEY (then changing the secret key makes earlier files unreadable, so set a file key in production). Fingerprints (SHA-256) are
always of the plain document, so a holder of the original can still verify it byte for byte.
"""

from __future__ import annotations

import base64
import hashlib
import os
from functools import lru_cache
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..config import get_settings

MAGIC = b"NDV1"   # marks an encrypted file; files without it (older uploads) are read as they are


class VaultError(Exception):
    pass


@lru_cache
def _key() -> bytes:
    s = get_settings()
    raw = s.file_key or (Path(s.file_key_file).read_text().strip() if s.file_key_file else "")
    if raw:
        key = base64.b64decode(raw)
        if len(key) != 32:
            raise VaultError("NIDHI_FILE_KEY must be 32 bytes, base64-encoded")
        return key
    return hashlib.sha256(b"nidhi-file-vault:" + s.secret_key.encode()).digest()


def seal(data: bytes) -> bytes:
    nonce = os.urandom(12)
    return MAGIC + nonce + AESGCM(_key()).encrypt(nonce, data, MAGIC)


def open_(blob: bytes) -> bytes:
    if not blob.startswith(MAGIC):
        return blob
    nonce, ct = blob[4:16], blob[16:]
    try:
        return AESGCM(_key()).decrypt(nonce, ct, MAGIC)
    except Exception as e:  # noqa: BLE001
        raise VaultError("The stored file could not be decrypted: wrong key or the file was altered on disk") from e


def write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(seal(data))


def read(path: Path) -> bytes:
    return open_(path.read_bytes())
