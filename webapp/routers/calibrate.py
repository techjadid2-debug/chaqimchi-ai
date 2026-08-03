"""Threshold kalibrlash: tavsiya olish va uni jonli qo'llash."""

from __future__ import annotations

import asyncio

import numpy as np
from fastapi import APIRouter, Depends

from chaqimchi_ai.audit import AuditLog
from chaqimchi_ai.runtime.container import AppContainer
from chaqimchi_ai.threshold_calibration import (
    calibrate_from_gallery,
    calibrate_from_image_dir,
)
from webapp.deps import get_audit, get_container, require_protected

router = APIRouter(prefix="/api/calibrate", tags=["calibrate"])


def _run_calibration(container: AppContainer, use_dir: bool):
    cfg = container.settings
    cal_dir = container.base_dir / cfg.paths.calibration_dir
    if use_dir and cal_dir.is_dir() and any(cal_dir.iterdir()):
        return calibrate_from_image_dir(
            container.engine,
            cal_dir,
            current_threshold=cfg.face.compare_threshold,
        )
    emb = container.db.embeddings
    return calibrate_from_gallery(
        emb if emb is not None else np.empty((0, 512)),
        current_threshold=cfg.face.compare_threshold,
    )


def apply_threshold(container: AppContainer, value: float) -> None:
    """Threshold'ni sozlamalarga yozib, jonli kameralarga tarqatish.

    Bu butun kodda runtime'da sozlama o'zgartiradigan yagona joy. Faza 1 da
    `ConfigApplier` uni umumlashtiradi va bu fan-out sikli yo'qoladi.
    """
    value = float(value)
    container.settings.face.compare_threshold = value
    manager = container.camera_manager
    if manager is not None:
        manager.compare_threshold = value
        for task in manager.cameras.values():
            task.compare_threshold = value


@router.get("/threshold")
async def calibrate_threshold(
    use_dir: bool = True,
    container: AppContainer = Depends(get_container),
):
    report = await asyncio.get_running_loop().run_in_executor(
        None, _run_calibration, container, use_dir
    )
    return {"ok": True, **report.to_dict()}


@router.post("/apply")
async def apply_calibrated_threshold(
    use_dir: bool = True,
    actor: str = Depends(require_protected),
    container: AppContainer = Depends(get_container),
    audit: AuditLog = Depends(get_audit),
):
    report = await asyncio.get_running_loop().run_in_executor(
        None, _run_calibration, container, use_dir
    )
    apply_threshold(container, report.suggested_threshold)
    audit.log("threshold_apply", actor, f"value={report.suggested_threshold:.4f}")
    return {
        "ok": True,
        "applied": report.suggested_threshold,
        "note": "config.yaml dagi face.compare_threshold ni ham yangilang (qayta ishga tushirishda saqlanishi uchun).",
        **report.to_dict(),
    }
