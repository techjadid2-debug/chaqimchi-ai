"""Holat, tayyorlik, litsenziya va metrikalar."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

from chaqimchi_ai.auth import resolve_api_key
from chaqimchi_ai.health import engine_status
from chaqimchi_ai.metrics import get_metrics
from chaqimchi_ai.prometheus_export import format_prometheus
from chaqimchi_ai.retention import purge_summary, run_purge
from chaqimchi_ai.runtime.container import AppContainer
from webapp.deps import get_container, require_protected

router = APIRouter(tags=["system"])

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@router.get("/")
async def index_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@router.get("/health")
async def health(container: AppContainer = Depends(get_container)) -> JSONResponse:
    # Diqqat: `*_or_none` ataylab — `/health` model yuklashni boshlab
    # yubormasligi kerak, u faqat holatni xabar qiladi.
    eng = container.engine_or_none
    db = container.db_or_none
    if eng is None or db is None:
        return JSONResponse(status_code=503, content={"ok": False, "status": "starting"})

    cfg = container.settings
    sec = cfg.security
    return JSONResponse(
        {
            "ok": True,
            "status": "ready",
            "engine": engine_status(eng),
            "cameras_active": len(container.camera_manager.cameras)
            if container.camera_manager
            else 0,
            "db_size": len(db.metadata),
            "events_today": container.events.get_stats_today(),
            "compare_threshold": cfg.face.compare_threshold,
            "frame_skip": cfg.camera.frame_skip,
            "api_key_required": bool(sec.api_key_enabled and resolve_api_key(sec)),
            "rate_limit_enabled": cfg.rate_limit.enabled,
            "tracking_enabled": cfg.tracking.enabled,
            "vector_backend": db.vector_backend,
            "embedding_encrypted": cfg.storage.encrypt_embeddings,
            "roi_enabled": cfg.roi.enabled,
            "antispoof_enabled": cfg.antispoof.enabled,
            "antispoof_backend": (
                getattr(
                    getattr(container.camera_manager, "antispoof_checker", None),
                    "method",
                    cfg.antispoof.backend,
                )
                if cfg.antispoof.enabled
                else None
            ),
            "jwt_enabled": sec.jwt.enabled,
            "license_enabled": cfg.license.enabled,
            "license": container.license_state.to_dict() if container.license_state else None,
            "attendance_mode": (
                "commercial"
                if cfg.face.commercial_model_licensed
                or os.environ.get("CHAQIMCHI_FACE_MODEL_LICENSED", "").lower()
                in {"1", "true", "yes"}
                else "closed_pilot"
                if os.environ.get("CHAQIMCHI_ATTENDANCE_PILOT", "").lower() in {"1", "true", "yes"}
                else "disabled"
            ),
            "ws_clients": len(container.ws_clients),
        }
    )


@router.get("/ready")
async def readiness(
    container: AppContainer = Depends(get_container),
    _actor: str = Depends(require_protected),
) -> JSONResponse:
    eng = container.engine_or_none
    if eng is None or not eng.recognition_ready:
        return JSONResponse(status_code=503, content={"ok": False, "status": "not_ready"})
    return JSONResponse({"ok": True, "status": "ready"})


@router.get("/api/license")
async def api_license_status(
    container: AppContainer = Depends(get_container),
    _actor: str = Depends(require_protected),
) -> JSONResponse:
    if not container.settings.license.enabled:
        return JSONResponse(
            {"ok": True, "enabled": False, "message": "Litsenziya o‘chirilgan (dev)"}
        )
    if container.license_state is None:
        return JSONResponse(
            {"ok": False, "enabled": True, "message": "Litsenziya holati yo‘q"},
            status_code=503,
        )
    return JSONResponse({"ok": True, "enabled": True, **container.license_state.to_dict()})


@router.get("/api/retention")
async def api_retention(
    container: AppContainer = Depends(get_container),
    _actor: str = Depends(require_protected),
) -> JSONResponse:
    """Arxiv saqlash muddati va oxirgi tozalash natijasi."""
    return JSONResponse(purge_summary(container))


@router.post("/api/retention/purge", dependencies=[Depends(require_protected)])
async def api_retention_purge(container: AppContainer = Depends(get_container)) -> JSONResponse:
    """Tozalashni darhol ishga tushirish (fon vazifasini kutmasdan)."""
    result = await run_purge(container)
    return JSONResponse({"ok": True, **result.to_dict()})


@router.get("/api/metrics")
async def api_metrics(
    container: AppContainer = Depends(get_container),
    _actor: str = Depends(require_protected),
) -> JSONResponse:
    snap = get_metrics().snapshot()
    snap["ws_clients"] = len(container.ws_clients)
    return JSONResponse(snap)


@router.get("/metrics")
async def prometheus_metrics(
    container: AppContainer = Depends(get_container),
    _actor: str = Depends(require_protected),
) -> PlainTextResponse:
    snap = get_metrics().snapshot()
    snap["ws_clients"] = len(container.ws_clients)
    return PlainTextResponse(format_prometheus(snap), media_type="text/plain; version=0.0.4")
