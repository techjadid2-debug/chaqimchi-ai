"""Ko‘rish agenti — kadrni AI ko‘rib tushuntiradi.

Tahlil **pul sarflaydi**, shuning uchun marshrut himoyalangan va har chaqiruv
audit jurnaliga yoziladi. Holat marshruti ochiq: do‘kon egasi qancha sarflangani
va limitdan qancha qolganini ko‘rishi kerak.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse

from chaqimchi_ai.audit import AuditLog
from chaqimchi_ai.runtime.container import AppContainer
from chaqimchi_ai.vision_agent import (
    BudgetExceeded,
    VisionAgentError,
    estimate_monthly_usd,
)
from webapp.deps import get_audit, get_container, require_protected

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/vision", tags=["vision"])

_DISABLED = JSONResponse(
    {
        "ok": False,
        "error": "Ko‘rish agenti o‘chirilgan (config.yaml: vision.enabled)",
    },
    status_code=503,
)

#: 16 MB — telefon kamerasidan kelgan kadr ham sig'adi.
MAX_UPLOAD_BYTES = 16 * 1024 * 1024


@router.get("/status")
async def vision_status(
    container: AppContainer = Depends(get_container),
    _actor: str = Depends(require_protected),
) -> JSONResponse:
    """Sozlama, sarf va limitdan qolgani."""
    agent = container.vision
    if agent is None:
        cfg = container.settings.vision
        return JSONResponse(
            {
                "ok": True,
                "enabled": False,
                "model": cfg.model,
                "estimated_monthly_usd": round(
                    estimate_monthly_usd(cfg.max_calls_per_day, cfg.max_side), 2
                ),
            }
        )
    return JSONResponse({"ok": True, **agent.status()})


@router.get("/recent")
async def vision_recent(
    limit: int = 20,
    container: AppContainer = Depends(get_container),
    _actor: str = Depends(require_protected),
) -> JSONResponse:
    """Oxirgi tahlillar (narxi bilan)."""
    agent = container.vision
    if agent is None:
        return _DISABLED
    return JSONResponse({"ok": True, "calls": agent.usage.recent(max(1, min(limit, 100)))})


@router.post("/analyze")
async def vision_analyze(
    file: UploadFile = File(...),
    question: str = Form(""),
    camera_id: str = Form("upload"),
    actor: str = Depends(require_protected),
    container: AppContainer = Depends(get_container),
    audit: AuditLog = Depends(get_audit),
) -> JSONResponse:
    """Yuborilgan rasmni tahlil qiladi."""
    agent = container.vision
    if agent is None:
        return _DISABLED

    data = await file.read()
    if not data:
        return JSONResponse({"ok": False, "error": "Rasm bo‘sh"}, status_code=400)
    if len(data) > MAX_UPLOAD_BYTES:
        return JSONResponse({"ok": False, "error": "Rasm juda katta"}, status_code=413)

    try:
        # Bloklovchi HTTP chaqiruv — serverni to'xtatib qo'ymasin.
        result = await asyncio.to_thread(
            agent.analyze,
            data,
            camera_id=camera_id,
            question=question.strip() or None,
        )
    except BudgetExceeded as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=429)
    except VisionAgentError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=502)

    audit.log(
        "vision_analyze",
        actor,
        f"camera={camera_id} alert={result.ogohlantirish} cost=${result.cost_usd:.4f}",
    )
    return JSONResponse({"ok": True, **result.to_dict()})
