"""Yuz bazasining zaxira nusxasi — yuklab olish va tiklash.

Ikkala marshrut ham **himoyalangan** (`require_protected`): nusxa biometrik
ma’lumot, tiklash esa butun bazani almashtiradi. Har ikkalasi audit jurnaliga
yoziladi — kim, qachon, qancha shaxs.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse, Response

from chaqimchi_ai.audit import AuditLog
from chaqimchi_ai.backup import (
    BackupError,
    backup_filename,
    create_backup,
    restore_backup,
)
from chaqimchi_ai.database import FaceDatabase
from chaqimchi_ai.embedding_crypto import resolve_embedding_key
from chaqimchi_ai.runtime.container import AppContainer
from webapp.deps import get_audit, get_container, get_db, require_protected

router = APIRouter(prefix="/api/backup", tags=["backup"])

#: Nusxa hajmi chegarasi — 2000 shaxs ≈ 4 MB, 64 MB katta zaxira bilan yetadi.
MAX_UPLOAD_BYTES = 64 * 1024 * 1024


def _site_id(container: AppContainer) -> Optional[str]:
    state = container.license_state
    return state.site_id if state else container.settings.license.site_id


def _key_for(container: AppContainer) -> Optional[bytes]:
    """Baza shifrlangan bo‘lsa nusxa ham shu kalit bilan shifrlanadi."""
    if not container.settings.storage.encrypt_embeddings:
        return None
    return resolve_embedding_key()


@router.get("")
async def download_backup(
    actor: str = Depends(require_protected),
    db: FaceDatabase = Depends(get_db),
    audit: AuditLog = Depends(get_audit),
    container: AppContainer = Depends(get_container),
) -> Response:
    """Butun bazani bitta ZIP fayl qilib beradi."""
    site_id = _site_id(container)
    try:
        blob = create_backup(db, encryption_key=_key_for(container), site_id=site_id)
    except BackupError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=409)

    name = backup_filename(site_id)
    audit.log("backup_download", actor, f"persons={db.count} file={name}")
    return Response(
        content=blob,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.post("/restore")
async def restore(
    file: UploadFile = File(...),
    mode: str = Form("replace"),
    actor: str = Depends(require_protected),
    db: FaceDatabase = Depends(get_db),
    audit: AuditLog = Depends(get_audit),
    container: AppContainer = Depends(get_container),
) -> JSONResponse:
    """Nusxadan tiklash. `mode`: `replace` (standart) yoki `merge`."""
    data = await file.read()
    if not data:
        return JSONResponse({"ok": False, "error": "Fayl bo‘sh"}, status_code=400)
    if len(data) > MAX_UPLOAD_BYTES:
        return JSONResponse({"ok": False, "error": "Fayl juda katta"}, status_code=413)

    try:
        result = restore_backup(
            db, data, encryption_key=resolve_embedding_key(), mode=mode
        )
    except BackupError as e:
        # Baza o'zgarmagan: `restore_backup` avval to'liq tekshiradi.
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

    license_state = container.license_state
    if license_state and db.count > license_state.max_persons:
        result["warning"] = (
            f"Tarif limiti {license_state.max_persons} shaxs, bazada {db.count} — "
            "yangi shaxs qo‘shib bo‘lmaydi"
        )

    audit.log(
        "backup_restore",
        actor,
        f"mode={mode} added={result['added']} total={result['persons_after']}",
    )
    return JSONResponse(result)
