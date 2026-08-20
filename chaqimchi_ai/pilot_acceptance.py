"""Mahsulotni sotuvga ochish uchun o'lchovli qabul darvozasi.

Ikki apparat yo'li bor va ularning mezonlari **bir xil emas**:

* `SOTQIN-N100-8-128-R1` — Chaqimchi Box.  Intel iGPU'da ishlaydi va
  harorat o'lchanadi (`/sys/class/thermal`).
* `CHAQIMCHI-WINDOWS-W1` — mijozning o'z Windows kompyuteri (asosiy
  mahsulot).  U yerda iGPU odatda yaroqsiz (masalan HD 4600 — OpenVINO
  qo'llab-quvvatlamaydi), ya'ni tahlil CPU'da ketadi, va Windows'da
  harorat manbasi umuman yo'q.

Bungacha faqat N100 mezoni bor edi: Windows sinovining natijasi
`device_in_use="CPU"` va `max_temperature_c=null` bilan kelib, **hech
qachon o'ta olmasdi**.  Ya'ni asosiy mahsulotni sotuvga ochishning
texnik yo'li yo'q edi.

Yumshatilgani faqat shu ikkitasi.  Qolgan hamma narsa — 72 soat, 4
kamera, restart 0, uptime 99%, yo'qolgan kritik hodisa 0 — ikkala
profilda ham bir xil, chunki mijozga beriladigan va'da bir xil.
Windows uchun uchta QO'SHIMCHA mezon bor (`docs/DOKON_MVP.md`): kunlik
sonning qo'lda sanash bilan farqi, klipning cloudga yetib borishi va
OTA yangilanishining sinovdan o'tishi.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from chaqimchi_ai.sotqin_profile import GUARANTEED_CAMERAS, HARDWARE_PROFILE

MIN_BENCHMARK_SECONDS = 60.0
MIN_SOAK_HOURS = 72.0
MIN_CAMERA_UPTIME_PERCENT = 99.0
MAX_TEMPERATURE_C = 85.0

#: Windows yo'lining profil nomi.
WINDOWS_PROFILE = "CHAQIMCHI-WINDOWS-W1"

#: Kunlik kirish soni qo'lda sanash bilan shundan ko'p farq qilmasin.
MAX_DAILY_COUNT_DELTA_PERCENT = 10.0


@dataclass(frozen=True)
class AcceptanceProfile:
    """Apparat yo'liga bog'liq farqlar (qolgani umumiy)."""

    name: str
    #: Benchmark GPU'da bajarilishi shartmi.
    requires_gpu: bool
    #: Harorat o'lchanishi shartmi (o'lchanmasa `null` keladi).
    requires_temperature: bool
    #: Windows'da qo'shimcha, odam tasdiqlaydigan mezonlar.
    requires_field_checks: bool


PROFILES: Dict[str, AcceptanceProfile] = {
    HARDWARE_PROFILE: AcceptanceProfile(
        name=HARDWARE_PROFILE,
        requires_gpu=True,
        requires_temperature=True,
        requires_field_checks=False,
    ),
    WINDOWS_PROFILE: AcceptanceProfile(
        name=WINDOWS_PROFILE,
        requires_gpu=False,
        requires_temperature=False,
        requires_field_checks=True,
    ),
}


def validate_n100_acceptance(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Qabul artefaktini tekshiradi; taxmin yoki sun'iy testni qabul qilmaydi.

    Nomi tarixiy — mexanizm ikkala apparat yo'li uchun bitta.
    """
    reasons = []
    if payload.get("schema_version") != 1:
        reasons.append("schema_version 1 bo'lishi kerak")

    profile = PROFILES.get(str(payload.get("hardware_profile") or ""))
    if profile is None:
        known = ", ".join(sorted(PROFILES))
        reasons.append(f"hardware_profile quyidagilardan biri bo'lishi kerak: {known}")
        # Profilsiz qolgan tekshiruvlarni bajarib bo'lmaydi.
        return {
            "ok": False,
            "hardware_profile": payload.get("hardware_profile"),
            "reasons": reasons,
        }

    if not str(payload.get("approved_by") or "").strip():
        reasons.append("approved_by kiritilmagan")
    if not str(payload.get("approved_at") or "").strip():
        reasons.append("approved_at kiritilmagan")

    benchmark = payload.get("benchmark") or {}
    verdict = benchmark.get("verdict") or {}
    detector = benchmark.get("detector") or {}
    if profile.requires_gpu and benchmark.get("device_in_use") != "GPU":
        reasons.append("benchmark Intel GPU'da bajarilmagan")
    if not str(benchmark.get("device_in_use") or "").strip():
        reasons.append("benchmark qaysi qurilmada bajarilgani yozilmagan")
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
        reasons.append(f"kamera uptime kamida {MIN_CAMERA_UPTIME_PERCENT:.1f}% bo'lishi kerak")
    temperature = soak.get("max_temperature_c")
    if temperature is None:
        # `null` — "o'lchanmadi".  N100 da bu nuqson (sensor bor), Windows'da
        # esa normal holat: OS harorat bermaydi.
        if profile.requires_temperature:
            reasons.append("harorat o'lchanmagan")
    elif float(temperature) > MAX_TEMPERATURE_C:
        reasons.append(f"maksimal harorat {MAX_TEMPERATURE_C:.0f}°C dan oshgan")
    if int(soak.get("undelivered_critical_events") or 0) != 0:
        reasons.append("yetkazilmagan kritik hodisa bor")

    if profile.requires_field_checks:
        reasons.extend(_field_check_reasons(payload.get("field_checks") or {}))

    return {
        "ok": not reasons,
        "hardware_profile": payload.get("hardware_profile"),
        "reasons": reasons,
    }


def _field_check_reasons(checks: Dict[str, Any]) -> list:
    """Do'konda odam tasdiqlaydigan mezonlar (`docs/DOKON_MVP.md`).

    Bularni skript o'lchay olmaydi: kunlik sonni kimdir qo'lda sanashi,
    klipni owner panelda ochib ko'rishi va OTA yangilanishini kuzatishi
    kerak.  Shuning uchun ular qabul faylida ochiq yozib qoldiriladi —
    keyin "tekshirilganmi yo'qmi" degan savol tug'ilmasin.
    """
    reasons = []
    delta = checks.get("daily_count_delta_percent")
    if delta is None:
        reasons.append("kunlik son qo'lda sanash bilan solishtirilmagan")
    elif abs(float(delta)) > MAX_DAILY_COUNT_DELTA_PERCENT:
        reasons.append(
            f"kunlik son qo'lda sanashdan {abs(float(delta)):.1f}% farq qiladi "
            f"(ruxsat {MAX_DAILY_COUNT_DELTA_PERCENT:.0f}%)"
        )
    if checks.get("clip_delivered") is not True:
        reasons.append("hodisa klipi cloudga yetib borgani tasdiqlanmagan")
    if checks.get("ota_update_ok") is not True:
        reasons.append("masofadan yangilanish sinovdan o'tmagan")
    return reasons


def pilot_acceptance_status(path: Optional[Path] = None) -> Dict[str, Any]:
    raw_path = (
        str(path)
        if path is not None
        else os.environ.get("CHAQIMCHI_N100_ACCEPTANCE_FILE", "").strip()
    )
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
