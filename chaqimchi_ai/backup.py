"""Yuz bazasining zaxira nusxasi — bitta ZIP faylga chiqarish va tiklash.

Nima uchun kerak:

`docs/INSTALLER.md` da “qurilma almashganda yangi pairing kod” jarayoni bor —
ya’ni Mini PC almashishi **kutilgan** holat. Lekin bazani yangi qurilmaga
ko‘chirish yo‘li yo‘q edi. Enterprise tarifda 2000 shaxs; har biri bir marta
kamera oldiga kelib ro‘yxatdan o‘tgan. SSD ishdan chiqsa yoki qurilma
almashsa — bu ish qaytadan boshlanardi.

Nusxa tarkibi (ZIP):

| Fayl | Mazmun |
|------|--------|
| `manifest.json` | versiya, sana, shaxslar soni, sha256, shifrlanganmi |
| `metadata.json` | shaxs ism/ID/qo‘shilgan sana |
| `embeddings.npy` yoki `embeddings.enc` | 512 o‘lchamli vektorlar |

**Diqqat:** nusxa biometrik ma’lumot. Shifrlanmagan holda u oddiy fayl —
uni himoyalangan joyda saqlang. Baza shifrlangan bo‘lsa (`storage.encrypt_embeddings`)
nusxa ham shifrlanadi va tiklashda **o‘sha** `CHAQIMCHI_EMBEDDING_KEY` kerak
bo‘ladi; kalitsiz nusxa foydasiz.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from chaqimchi_ai.database import FaceDatabase
from chaqimchi_ai.embedding_crypto import decrypt_array, encrypt_array

logger = logging.getLogger(__name__)

#: Nusxa formati versiyasi. Tiklashda mos kelmasa — aniq xato beriladi.
BACKUP_VERSION = 1

MANIFEST_NAME = "manifest.json"
METADATA_NAME = "metadata.json"
EMBEDDINGS_NAME = "embeddings.npy"
EMBEDDINGS_ENC_NAME = "embeddings.enc"

EMBED_DIM = 512


class BackupError(Exception):
    """Nusxa yaratish yoki tiklashda muammo."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _embeddings_bytes(embeddings: np.ndarray) -> bytes:
    buf = io.BytesIO()
    np.save(buf, embeddings.astype(np.float32), allow_pickle=False)
    return buf.getvalue()


def create_backup(
    db: FaceDatabase,
    *,
    encryption_key: Optional[bytes] = None,
    site_id: Optional[str] = None,
) -> bytes:
    """Bazadan ZIP nusxa yasaydi va baytlarini qaytaradi.

    Args:
        db: Yuz bazasi. Vektorlar xotirada ochiq holda — diskdagi shifr
            yechilgan bo‘ladi, shuning uchun nusxa shifri shu yerda qayta
            qo‘llanadi.
        encryption_key: Berilsa nusxa ichidagi vektorlar shifrlanadi.
        site_id: Ixtiyoriy — qaysi obyekt nusxasi ekani manifestda qoladi.
    """
    embeddings = db.embeddings
    if embeddings is None:
        embeddings = np.empty((0, EMBED_DIM), dtype=np.float32)

    if len(db.metadata) != embeddings.shape[0]:
        raise BackupError(
            f"Baza buzuq: {len(db.metadata)} shaxs, {embeddings.shape[0]} vektor. Nusxa olinmadi."
        )

    meta_bytes = json.dumps(db.metadata, ensure_ascii=False, indent=2).encode("utf-8")

    if encryption_key:
        emb_name = EMBEDDINGS_ENC_NAME
        emb_bytes = encrypt_array(embeddings, encryption_key)
    else:
        emb_name = EMBEDDINGS_NAME
        emb_bytes = _embeddings_bytes(embeddings)

    manifest = {
        "version": BACKUP_VERSION,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "persons": len(db.metadata),
        "embedding_dim": int(embeddings.shape[1]) if embeddings.size else EMBED_DIM,
        "encrypted": bool(encryption_key),
        "site_id": site_id,
        "files": {
            METADATA_NAME: _sha256(meta_bytes),
            emb_name: _sha256(emb_bytes),
        },
    }

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2))
        zf.writestr(METADATA_NAME, meta_bytes)
        zf.writestr(emb_name, emb_bytes)
    return out.getvalue()


def backup_filename(site_id: Optional[str] = None) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    prefix = f"chaqimchi-{site_id}" if site_id else "chaqimchi"
    return f"{prefix}-{stamp}.zip"


def read_backup(
    data: bytes, *, encryption_key: Optional[bytes] = None
) -> Tuple[List[Dict[str, Any]], np.ndarray, Dict[str, Any]]:
    """ZIP nusxani o‘qiydi va tekshiradi. (metadata, embeddings, manifest)"""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise BackupError("Fayl ZIP emas yoki buzilgan") from e

    with zf:
        names = set(zf.namelist())
        if MANIFEST_NAME not in names:
            raise BackupError("manifest.json topilmadi — bu Chaqimchi nusxasi emas")

        try:
            manifest = json.loads(zf.read(MANIFEST_NAME))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise BackupError("manifest.json o‘qilmadi") from e

        version = manifest.get("version")
        if version != BACKUP_VERSION:
            raise BackupError(f"Nusxa versiyasi mos emas: {version} (kutilgani {BACKUP_VERSION})")

        if METADATA_NAME not in names:
            raise BackupError("metadata.json topilmadi")

        encrypted = bool(manifest.get("encrypted"))
        emb_name = EMBEDDINGS_ENC_NAME if encrypted else EMBEDDINGS_NAME
        if emb_name not in names:
            raise BackupError(f"{emb_name} topilmadi")

        meta_bytes = zf.read(METADATA_NAME)
        emb_bytes = zf.read(emb_name)

    # Checksum: nusxa ko'chirishda buzilgan bo'lsa, buzuq vektorlarni bazaga
    # yozib qo'ymaslik kerak — tanish jimgina noto'g'ri ishlab ketardi.
    expected = manifest.get("files") or {}
    for name, blob in ((METADATA_NAME, meta_bytes), (emb_name, emb_bytes)):
        want = expected.get(name)
        if want and want != _sha256(blob):
            raise BackupError(f"{name} buzilgan (sha256 mos kelmadi)")

    try:
        metadata = json.loads(meta_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise BackupError("metadata.json o‘qilmadi") from e
    if not isinstance(metadata, list):
        raise BackupError("metadata.json ro‘yxat bo‘lishi kerak")

    if encrypted:
        if not encryption_key:
            raise BackupError(
                "Nusxa shifrlangan — CHAQIMCHI_EMBEDDING_KEY kerak (nusxa olingandagi kalit)"
            )
        try:
            embeddings = decrypt_array(emb_bytes, encryption_key)
        except Exception as e:
            raise BackupError("Shifr yechilmadi — kalit boshqa bo‘lishi mumkin") from e
    else:
        try:
            embeddings = np.load(io.BytesIO(emb_bytes), allow_pickle=False)
        except Exception as e:
            raise BackupError("embeddings.npy o‘qilmadi") from e

    embeddings = np.asarray(embeddings, dtype=np.float32)
    if embeddings.ndim != 2 or (embeddings.size and embeddings.shape[1] != EMBED_DIM):
        raise BackupError(f"Vektor o‘lchami noto‘g‘ri: {embeddings.shape}")
    if len(metadata) != embeddings.shape[0]:
        raise BackupError(f"Nusxa buzuq: {len(metadata)} shaxs, {embeddings.shape[0]} vektor")

    return metadata, embeddings, manifest


def restore_backup(
    db: FaceDatabase,
    data: bytes,
    *,
    encryption_key: Optional[bytes] = None,
    mode: str = "replace",
) -> Dict[str, Any]:
    """Nusxani bazaga tiklaydi.

    `mode="replace"` — hozirgi baza to‘liq almashtiriladi (qurilma almashgan
    holat). `mode="merge"` — faqat ID si yo‘q shaxslar qo‘shiladi (ikki
    do‘konning bazasini birlashtirish).

    Baza faqat nusxa to‘liq tekshirilgandan keyin o‘zgaradi.
    """
    if mode not in ("replace", "merge"):
        raise BackupError(f"Noma’lum rejim: {mode}")

    metadata, embeddings, manifest = read_backup(data, encryption_key=encryption_key)
    before = db.count

    if mode == "replace":
        db.metadata = list(metadata)
        db.embeddings = embeddings.copy()
        added = len(metadata)
        skipped = 0
    else:
        existing = {m.get("id") for m in db.metadata}
        keep = [i for i, m in enumerate(metadata) if m.get("id") not in existing]
        skipped = len(metadata) - len(keep)
        if keep:
            new_meta = [metadata[i] for i in keep]
            new_embs = embeddings[keep]
            current = db.embeddings
            if current is None or current.size == 0:
                db.embeddings = new_embs.copy()
            else:
                db.embeddings = np.vstack([current, new_embs])
            db.metadata = list(db.metadata) + new_meta
        added = len(keep)

    db.save()

    result = {
        "ok": True,
        "mode": mode,
        "persons_before": before,
        "persons_after": db.count,
        "added": added,
        "skipped": skipped,
        "backup_created_at": manifest.get("created_at"),
        "backup_site_id": manifest.get("site_id"),
    }
    logger.info("Baza tiklandi (%s): %d → %d shaxs", mode, before, db.count)
    return result


def write_backup_file(db: FaceDatabase, path: Path, **kwargs: Any) -> Path:
    """Nusxani faylga yozadi (CLI uchun)."""
    path = Path(path)
    # `.zip` bo'lmasa — papka deb qaraladi. Faqat `is_dir()` ga tayanib
    # bo'lmaydi: birinchi nusxada `data/backups` hali mavjud emas va u
    # kengaytmasiz fayl bo'lib yozilib qolardi.
    if path.is_dir() or path.suffix.lower() != ".zip":
        path = path / backup_filename(kwargs.get("site_id"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(create_backup(db, **kwargs))
    return path


__all__ = [
    "BACKUP_VERSION",
    "BackupError",
    "backup_filename",
    "create_backup",
    "read_backup",
    "restore_backup",
    "write_backup_file",
]
