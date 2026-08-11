"""Voqealar, statistika, snapshotlar va jonli WebSocket oqimi."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse

from chaqimchi_ai.events import EventLog
from chaqimchi_ai.runtime.container import AppContainer
from webapp.deps import get_container, get_events, require_protected

logger = logging.getLogger(__name__)

router = APIRouter(tags=["events"])


@router.get("/api/events")
async def get_recent_events(
    # Bungacha `limit` cheklanmagan edi — `?limit=10000000` butun jadvalni
    # xotiraga tortardi.
    limit: int = Query(50, ge=1, le=500),
    events: EventLog = Depends(get_events),
    _actor: str = Depends(require_protected),
):
    return events.get_recent_events(limit)


@router.get("/api/stats")
async def get_stats(
    events: EventLog = Depends(get_events), _actor: str = Depends(require_protected)
):
    return events.get_stats_today()


@router.get("/api/snapshots/{filename}")
async def get_snapshot(
    filename: str,
    container: AppContainer = Depends(get_container),
    _actor: str = Depends(require_protected),
):
    if not filename or "/" in filename or "\\" in filename or ".." in filename:
        return JSONResponse({"ok": False, "error": "Noto‘g‘ri fayl nomi"}, status_code=400)

    root = (container.base_dir / container.settings.paths.snapshots_dir).resolve()
    path = (root / filename).resolve()
    if not path.is_file() or root not in path.parents:
        return JSONResponse({"ok": False, "error": "Topilmadi"}, status_code=404)
    return FileResponse(path, media_type="image/jpeg")


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    container: AppContainer = ws.app.state.container
    from chaqimchi_ai.auth import verify_access

    try:
        token = ws.query_params.get("token")
        authorization = f"Bearer {token}" if token else ws.headers.get("Authorization")
        verify_access(
            security=container.settings.security,
            x_api_key=ws.headers.get("X-API-Key"),
            authorization=authorization,
        )
    except Exception:
        await ws.close(code=1008, reason="Autentifikatsiya talab qilinadi")
        return
    await ws.accept()
    container.ws_clients.append(ws)
    try:
        while True:
            # Mijozdan xabar kutish (ping/pong yoki boshqa buyruqlar uchun)
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.debug("WebSocket xatosi", exc_info=True)
    finally:
        # `finally` majburiy: bungacha o'chirish faqat WebSocketDisconnect
        # tarmog'ida edi, shu sababli boshqa har qanday xato socket'ni
        # ro'yxatda abadiy qoldirar va u har voqeada qayta urinilardi.
        try:
            container.ws_clients.remove(ws)
        except ValueError:
            pass
