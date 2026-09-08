"""Ed25519 imzoli Sotqin release paketini tekshirish yordamchilari."""

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


SUPPORTED_MANIFEST_SCHEMAS = {1, 2}

#: Qurilma qabul qiladigan mahsulotlar.  Ro'yxat **yopiq**: noma'lum
#: `product` bilan imzolangan paket rad etiladi, ya'ni bir mahsulot uchun
#: chiqarilgan reliz boshqasiga tasodifan o'rnatilib ketmaydi.
#:
#: `chaqimchi-windows` — mijozning o'z kompyuteriga o'rnatiladigan
#: `.exe` paketi (`scripts/build_windows_payload.py`).
KNOWN_PRODUCTS = frozenset({"chaqimchi-sotqin", "chaqimchi-lite", "chaqimchi-windows"})


def canonical_manifest_payload(manifest: Dict[str, Any]) -> bytes:
    """Imzolanadigan manifest baytlari.

    V1 eski qurilmalar bilan moslik uchun `version:sha256` formatida qoladi.
    V2 esa signature'dan boshqa barcha maydonlarni canonical JSON ko'rinishida
    imzolaydi; product/architecture metadata'sini almashtirib bo'lmaydi.
    """
    try:
        schema = int(manifest.get("schema_version", 1))
        version = str(manifest["version"])
        digest = str(manifest["sha256"]).lower()
    except (KeyError, TypeError, ValueError) as exc:
        raise UpdateVerificationError("Release manifest noto'g'ri") from exc
    if schema not in SUPPORTED_MANIFEST_SCHEMAS:
        raise UpdateVerificationError("Release manifest schema qo'llab-quvvatlanmaydi")
    if schema == 1:
        return f"{version}:{digest}".encode("utf-8")
    unsigned = {key: value for key, value in manifest.items() if key != "signature"}
    return json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


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
        schema = int(manifest.get("schema_version", 1))
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise UpdateVerificationError("Release manifest noto'g'ri") from exc
    if not version or any(
        char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_"
        for char in version
    ):
        raise UpdateVerificationError("Release version xavfsiz formatda emas")
    if schema not in SUPPORTED_MANIFEST_SCHEMAS:
        raise UpdateVerificationError("Release manifest schema qo'llab-quvvatlanmaydi")
    if schema >= 2:
        if manifest.get("product") not in KNOWN_PRODUCTS:
            raise UpdateVerificationError(f"Release product noma'lum: {manifest.get('product')!r}")
        if not str(manifest.get("target_arch", "")).strip():
            raise UpdateVerificationError("Release target_arch berilmagan")
    actual_hash = sha256_file(archive)
    if actual_hash != expected_hash:
        raise UpdateVerificationError("Release SHA-256 mos emas")
    try:
        key = serialization.load_pem_public_key(public_key_path.read_bytes())
        if not isinstance(key, Ed25519PublicKey):
            raise TypeError("Ed25519 emas")
        key.verify(signature, canonical_manifest_payload(manifest))
    except Exception as exc:
        raise UpdateVerificationError("Release imzosi yaroqsiz") from exc
    return {
        **manifest,
        "schema_version": schema,
        "version": version,
        "sha256": expected_hash,
    }
