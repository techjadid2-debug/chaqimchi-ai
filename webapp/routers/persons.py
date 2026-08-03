"""Shaxslarni boshqarish, identifikatsiya va yuz deteksiyasi."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse

from chaqimchi_ai.audit import AuditLog
from chaqimchi_ai.database import FaceDatabase
from chaqimchi_ai.metrics import get_metrics
from chaqimchi_ai.runtime.container import AppContainer
from chaqimchi_ai.settings import AppSettings
from webapp.deps import (
    get_audit,
    get_container,
    get_db,
    get_engine,
    get_settings,
    require_protected,
)
from webapp.imaging import decode_upload

if TYPE_CHECKING:  # pragma: no cover
    from chaqimchi_ai.face_engine import FaceEngine

router = APIRouter(prefix="/api", tags=["persons"])

_NO_IMAGE = JSONResponse({"ok": False, "error": "Rasm o'qilmadi"}, status_code=400)
_NO_FACE = JSONResponse({"ok": False, "error": "Rasmda yuz topilmadi"}, status_code=400)


@router.get("/persons")
async def list_persons(db: FaceDatabase = Depends(get_db)):
    return db.metadata


@router.post("/analyze")
async def analyze_image(
    file: UploadFile = File(...),
    engine: "FaceEngine" = Depends(get_engine),
):
    """Rasmdagi yuzlar (bbox, ball) — bazaga yozmaydi."""
    img = await decode_upload(file)
    if img is None:
        return _NO_IMAGE
    faces, infer_ms = await asyncio.get_running_loop().run_in_executor(
        None, engine.analyze_frame, img
    )
    get_metrics().record_inference(None, infer_ms, faces=len(faces))
    return {
        "ok": True,
        "faces": [{"bbox": f["bbox"], "det_score": f["det_score"]} for f in faces],
        "inference_ms": infer_ms,
    }


@router.post("/identify")
async def identify_person(
    file: UploadFile = File(...),
    actor: str = Depends(require_protected),
    engine: "FaceEngine" = Depends(get_engine),
    db: FaceDatabase = Depends(get_db),
    audit: AuditLog = Depends(get_audit),
    settings: AppSettings = Depends(get_settings),
):
    """Rasmni bazadagi shaxslar bilan solishtirish."""
    img = await decode_upload(file)
    if img is None:
        return _NO_IMAGE
    emb = await asyncio.get_running_loop().run_in_executor(
        None, engine.extract_primary_embedding, img
    )
    if emb is None:
        return _NO_FACE
    threshold = settings.face.compare_threshold
    matches = db.search(emb, threshold=threshold)
    audit.log("identify", actor, f"matches={len(matches)}")
    return {"ok": True, "matches": matches, "threshold": threshold}


@router.post("/persons/add")
async def add_person(
    name: str = Form(...),
    file: UploadFile = File(...),
    actor: str = Depends(require_protected),
    engine: "FaceEngine" = Depends(get_engine),
    db: FaceDatabase = Depends(get_db),
    audit: AuditLog = Depends(get_audit),
    container: AppContainer = Depends(get_container),
):
    img = await decode_upload(file)
    if img is None:
        return _NO_IMAGE

    emb = await asyncio.get_running_loop().run_in_executor(
        None, engine.extract_primary_embedding, img
    )
    if emb is None:
        return _NO_FACE

    license_state = container.license_state
    if license_state and db.count >= license_state.max_persons:
        return JSONResponse(
            {"ok": False, "error": f"Tarif limiti: max {license_state.max_persons} shaxs"},
            status_code=403,
        )
    entry = db.add_face(name, emb)
    audit.log("person_add", actor, f"id={entry['id']} name={name}")
    return {"ok": True, "person": entry}


@router.delete("/persons/{face_id}")
async def delete_person(
    face_id: str,
    actor: str = Depends(require_protected),
    db: FaceDatabase = Depends(get_db),
    audit: AuditLog = Depends(get_audit),
) -> JSONResponse:
    if db.delete_face(face_id):
        audit.log("person_delete", actor, f"id={face_id}")
        return JSONResponse({"ok": True})
    return JSONResponse({"ok": False, "error": "Shaxs topilmadi"}, status_code=404)
