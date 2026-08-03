"""Embedding fayllarini diskda shifrlash (ixtiyoriy)."""

from __future__ import annotations

import os
from typing import Optional

import numpy as np

try:
    from cryptography.fernet import Fernet
except ImportError:  # pragma: no cover
    Fernet = None  # type: ignore[misc, assignment]


def resolve_embedding_key() -> Optional[bytes]:
    raw = os.environ.get("CHAQIMCHI_EMBEDDING_KEY", "").strip()
    if not raw:
        return None
    return raw.encode("utf-8")


def _fernet(key: bytes) -> "Fernet":
    if Fernet is None:
        raise ImportError(
            "cryptography kerak: pip install cryptography"
        )
    return Fernet(key)


def encrypt_array(embeddings: np.ndarray, key: bytes) -> bytes:
    payload = embeddings.astype(np.float32).tobytes()
    meta = f"{embeddings.shape[0]},{embeddings.shape[1]}".encode("ascii")
    return _fernet(key).encrypt(meta + b"|" + payload)


def decrypt_array(data: bytes, key: bytes) -> np.ndarray:
    plain = _fernet(key).decrypt(data)
    head, raw = plain.split(b"|", 1)
    n, dim = (int(x) for x in head.decode("ascii").split(","))
    arr = np.frombuffer(raw, dtype=np.float32).reshape(n, dim)
    return arr
