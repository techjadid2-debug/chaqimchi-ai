"""Yopiq davomat piloti uchun lokal enrollment API.

Cloud xodim nomi, jadvali va yozma rozilik qaydini boshqaradi. Yuz rasmi va
512-o'lchamli embedding esa shu edge qurilmadan chiqmaydi.
"""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING, Any, Dict

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from chaqimchi_ai.database import FaceDatabase
from chaqimchi_ai.runtime.container import AppContainer
from webapp.deps import get_container, get_db, get_engine, require_protected
from webapp.imaging import decode_upload

if TYPE_CHECKING:  # pragma: no cover
    from chaqimchi_ai.face_engine import FaceEngine

router = APIRouter(prefix="/api/attendance", tags=["attendance"])


def _require_attendance_service() -> None:
    if os.environ.get("CHAQIMCHI_SERVICE_MODE", "").strip().lower() != "attendance":
        raise HTTPException(404, "Davomat enrollmenti bu xizmatda yoqilmagan")


def _employee_view(container: AppContainer, db: FaceDatabase) -> list[Dict[str, Any]]:
    enrolled = {str(item["id"]): item for item in db.metadata}
    return [
        {
            **employee,
            "enrolled_local": employee_id in enrolled,
            "biometric_storage": "local_edge_only",
        }
        for employee_id, employee in sorted(
            container.remote_employees.items(), key=lambda item: str(item[1].get("name", ""))
        )
    ]


async def _report_status(
    container: AppContainer, employee_id: str, status: str
) -> bool:
    sync = container.settings.cloud_sync
    if not sync.enabled or not all((sync.site_id, sync.device_id, sync.device_token)):
        return False
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{sync.url.rstrip('/')}/api/v1/edge/employees/{employee_id}/enrollment",
                headers={
                    "X-Site-Id": sync.site_id or "",
                    "X-Device-Id": sync.device_id or "",
                    "X-Device-Token": sync.device_token or "",
                },
                json={"status": status},
            )
            response.raise_for_status()
        return True
    except Exception:
        return False


@router.get("/employees")
async def list_attendance_employees(
    _actor: str = Depends(require_protected),
    container: AppContainer = Depends(get_container),
    db: FaceDatabase = Depends(get_db),
) -> Dict[str, Any]:
    _require_attendance_service()
    commercial = container.settings.face.commercial_model_licensed or os.environ.get(
        "CHAQIMCHI_FACE_MODEL_LICENSED", ""
    ).lower() in {"1", "true", "yes"}
    return {
        "mode": "commercial" if commercial else "closed_pilot",
        "privacy": "Yuz rasmi va embedding faqat shu Sotqin qurilmasida saqlanadi.",
        "employees": _employee_view(container, db),
    }


@router.post("/enroll")
async def enroll_employee(
    employee_id: str = Form(...),
    file: UploadFile = File(...),
    _actor: str = Depends(require_protected),
    container: AppContainer = Depends(get_container),
    engine: "FaceEngine" = Depends(get_engine),
    db: FaceDatabase = Depends(get_db),
) -> Dict[str, Any]:
    _require_attendance_service()
    employee = container.remote_employees.get(employee_id)
    if not employee or not employee.get("active") or not employee.get("consent_recorded_at"):
        raise HTTPException(403, "Xodim faol emas yoki yozma roziligi cloud'da qayd etilmagan")
    image = await decode_upload(file)
    if image is None:
        raise HTTPException(400, "Rasm o'qilmadi")
    embedding = await asyncio.get_running_loop().run_in_executor(
        None, engine.extract_single_embedding, image
    )
    if embedding is None:
        raise HTTPException(400, "Rasmda bitta aniq yuz topilmadi")

    db.replace_face(
        employee_id,
        str(employee["name"]),
        embedding,
        {
            "kind": "employee",
            "cloud_managed": True,
            "consent_recorded_at": employee["consent_recorded_at"],
        },
    )
    synced = await _report_status(container, employee_id, "enrolled")
    return {
        "ok": True,
        "employee_id": employee_id,
        "name": employee["name"],
        "cloud_status_synced": synced,
        "biometric_storage": "local_edge_only",
    }


@router.delete("/employees/{employee_id}")
async def remove_employee_biometric(
    employee_id: str,
    _actor: str = Depends(require_protected),
    container: AppContainer = Depends(get_container),
    db: FaceDatabase = Depends(get_db),
) -> Dict[str, Any]:
    _require_attendance_service()
    removed = db.delete_face(employee_id)
    synced = await _report_status(container, employee_id, "removed") if removed else False
    return {"ok": removed, "cloud_status_synced": synced}
