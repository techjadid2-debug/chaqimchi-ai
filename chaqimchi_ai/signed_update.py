"""Ed25519 imzoli edge release paketini tekshirish yordamchilari."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any, Dict

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


class UpdateVerificationError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_release_manifest(
    archive: Path, manifest_path: Path, public_key_path: Path
) -> Dict[str, Any]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        version = str(manifest["version"])
        expected_hash = str(manifest["sha256"]).lower()
        signature = base64.b64decode(str(manifest["signature"]), validate=True)
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        raise UpdateVerificationError("Release manifest noto'g'ri") from exc
    if not version or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_" for char in version):
        raise UpdateVerificationError("Release version xavfsiz formatda emas")
    actual_hash = sha256_file(archive)
    if actual_hash != expected_hash:
        raise UpdateVerificationError("Release SHA-256 mos emas")
    try:
        key = serialization.load_pem_public_key(public_key_path.read_bytes())
        if not isinstance(key, Ed25519PublicKey):
            raise TypeError("Ed25519 emas")
        key.verify(signature, f"{version}:{expected_hash}".encode("utf-8"))
    except Exception as exc:
        raise UpdateVerificationError("Release imzosi yaroqsiz") from exc
    return {**manifest, "version": version, "sha256": expected_hash}
