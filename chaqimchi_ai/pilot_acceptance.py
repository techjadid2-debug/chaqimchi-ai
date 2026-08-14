"""Sotqin R1 ni sotuvga ochish uchun o'lchovli qabul darvozasi."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from chaqimchi_ai.sotqin_profile import GUARANTEED_CAMERAS, HARDWARE_PROFILE

MIN_BENCHMARK_SECONDS = 60.0
MIN_SOAK_HOURS = 72.0
MIN_CAMERA_UPTIME_PERCENT = 99.0
MAX_TEMPERATURE_C = 85.0


def validate_n100_acceptance(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Qabul artefaktini tekshiradi; taxmin yoki sun'iy testni qabul qilmaydi."""
    reasons = []
    if payload.get("schema_version") != 1:
        reasons.append("schema_version 1 bo'lishi kerak")
    if payload.get("hardware_profile") != HARDWARE_PROFILE:
        reasons.append(f"hardware_profile {HARDWARE_PROFILE} bo'lishi kerak")
    if not str(payload.get("approved_by") or "").strip():
        reasons.append("approved_by kiritilmagan")
    if not str(payload.get("approved_at") or "").strip():
        reasons.append("approved_at kiritilmagan")

    benchmark = payload.get("benchmark") or {}
    verdict = benchmark.get("verdict") or {}
    detector = benchmark.get("detector") or {}
    if benchmark.get("device_in_use") != "GPU":
        reasons.append("benchmark Intel GPU'da bajarilmagan")
    if benchmark.get("frame_source") in {None, "", "sun'iy kadrlar"}:
        reasons.append("benchmark haqiqiy do'kon videosida bajarilmagan")
    if float(detector.get("elapsed_sec") or 0) < MIN_BENCHMARK_SECONDS:
        reasons.append(f"benchmark kamida {MIN_BENCHMARK_SECONDS:.0f} soniya bo'lishi kerak")
    if int(verdict.get("cameras") or 0) < GUARANTEED_CAMERAS:
        reasons.append(f"benchmark kamida {GUARANTEED_CAMERAS} kamerani tekshirishi kerak")
    if verdict.get("ok") is not True:
        reasons.append("benchmark sig'im xulosasi o'tmagan")
    if benchmark.get("warnings") or verdict.get("warnings"):
        reasons.append("benchmarkda ochiq ogohlantirish qolgan")

    soak = payload.get("soak") or {}
    if float(soak.get("duration_hours") or 0) < MIN_SOAK_HOURS:
        reasons.append(f"soak test kamida {MIN_SOAK_HOURS:.0f} soat bo'lishi kerak")
    if int(soak.get("cameras_min_active") or 0) < GUARANTEED_CAMERAS:
        reasons.append(f"soak davomida {GUARANTEED_CAMERAS} kamera uzluksiz faol bo'lishi kerak")
    if int(soak.get("unexpected_restarts") or 0) != 0:
        reasons.append("soak testda kutilmagan restart bo'lgan")
    if float(soak.get("camera_uptime_percent") or 0) < MIN_CAMERA_UPTIME_PERCENT:
        reasons.append(
            f"kamera uptime kamida {MIN_CAMERA_UPTIME_PERCENT:.1f}% bo'lishi kerak"
        )
    if float(soak.get("max_temperature_c") or 999) > MAX_TEMPERATURE_C:
        reasons.append(f"maksimal harorat {MAX_TEMPERATURE_C:.0f}°C dan oshgan")
    if int(soak.get("undelivered_critical_events") or 0) != 0:
        reasons.append("yetkazilmagan kritik hodisa bor")

    return {
        "ok": not reasons,
        "hardware_profile": payload.get("hardware_profile"),
        "reasons": reasons,
    }


def pilot_acceptance_status(path: Optional[Path] = None) -> Dict[str, Any]:
    raw_path = str(path) if path is not None else os.environ.get(
        "CHAQIMCHI_N100_ACCEPTANCE_FILE", ""
    ).strip()
    if not raw_path:
        return {"ok": False, "path": None, "reasons": ["qabul fayli sozlanmagan"]}
    configured = Path(raw_path)
    if not configured.is_file():
        return {
            "ok": False,
            "path": str(configured),
            "reasons": ["qabul fayli topilmadi"],
        }
    try:
        payload = json.loads(configured.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "path": str(configured),
            "reasons": [f"qabul fayli o'qilmadi: {exc}"],
        }
    result = validate_n100_acceptance(payload)
    result["path"] = str(configured)
    return result
