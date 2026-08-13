"""Kamera ro'yxati qayerdan olinadi.

Muammo amaliy va jimgina zarar keltiradigan turdan.  O'rnatuvchi kamerani
**cloud panelida** qo'shadi (`camera-inventory`), Sotqin uni config poll'da
oladi va lokal keshga yozadi.  Do'kon analitikasi esa kameralarni **lokal
YAML** dan o'qirdi.  Ikkalasi mos kelmasa hech qanday xato chiqmaydi: yangi
kamera oddiygina tahlil qilinmaydi, panelda esa hammasi yashil turadi.
Mijoz oylab bilmasligi mumkin.

Yechim: manba **cloud keshi** bo'ladi, lokal konfig esa faqat qo'shimcha
sozlamalarni beradi.

    cloud keshi (sotqin-config.json)      lokal YAML (`retail.cameras`)
    ├─ camera_id                          ├─ record_url  (klip uchun main stream)
    ├─ source (substream RTSP)            ├─ priority
    ├─ label                              ├─ sample_fps
    └─ enabled                            └─ floor_fps

Nega bo'lingan: RTSP manzil va kameraning bor-yo'qligi — **inventar**
ma'lumoti, u cloudda boshqariladi va shifrlangan holda keladi.  Prioritet va
klip manbasi esa **obyektga xos sozlama** (qaysi kamera xavfsizlik uchun,
qaysi biri sanoq uchun) va u o'rnatuvchi tomonidan bir marta yoziladi.

Cloud keshida yo'q, lekin lokal konfigda `stream_url` bilan yozilgan kamera
ham qo'shiladi — u ham jimgina yo'qolmasligi kerak.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InventoryCamera:
    """Cloud inventaridan kelgan kamera."""

    camera_id: str
    source: str
    label: str = ""
    enabled: bool = True


@dataclass(frozen=True)
class CameraPlan:
    """Zanjirga beriladigan yakuniy kamera ta'rifi."""

    camera_id: str
    stream_url: str
    origin: str
    label: str = ""
    record_url: Optional[str] = None
    priority: str = "retail"
    sample_fps: float = 5.0
    floor_fps: Optional[float] = None


def read_sotqin_cache(path: Path) -> Dict[str, Any]:
    """Sotqin config keshini o'qiydi.

    Fayl yo'q bo'lsa bo'sh natija — bu normal holat: qurilma hali
    juftlanmagan yoki analitika mustaqil (cloud'siz) ishlatilyapti.  Fayl
    **buzuq** bo'lsa esa xato ko'tariladi: jimgina bo'sh ro'yxat bilan
    davom etish "kamera yo'qolgan" holatining aynan o'zi bo'lardi.
    """
    if not path.is_file():
        return {"revision": None, "cameras": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Sotqin config keshi buzuq: {path}") from exc
    if not isinstance(payload, Mapping):
        raise ValueError(f"Sotqin config keshi noto'g'ri: {path}")
    return {
        "revision": payload.get("revision"),
        "cameras": [
            InventoryCamera(
                camera_id=str(item.get("camera_id") or ""),
                source=str(item.get("source") or ""),
                label=str(item.get("label") or ""),
                enabled=bool(item.get("enabled", True)),
            )
            for item in (payload.get("cameras") or [])
            if isinstance(item, Mapping)
        ],
    }


def merge_cameras(
    inventory: Sequence[InventoryCamera], local: Sequence[Any]
) -> List[CameraPlan]:
    """Inventar va lokal sozlamani birlashtiradi.

    Tartib inventardan boshlanadi — panelda ko'ringan kamera zanjirda ham
    bo'lishi kerak.  O'chirilgan (`enabled: false`) kamera tushib qoladi:
    uni tahlil qilish byudjetni bekorga yeydi.
    """
    options = {str(item.id): item for item in local}
    plans: List[CameraPlan] = []
    used: set = set()

    for camera in inventory:
        if not camera.camera_id or not camera.source:
            logger.warning("Inventarda manzilsiz kamera: %r", camera.camera_id)
            continue
        if not camera.enabled:
            continue
        used.add(camera.camera_id)
        option = options.get(camera.camera_id)
        plans.append(
            CameraPlan(
                camera_id=camera.camera_id,
                stream_url=camera.source,
                origin="cloud",
                label=camera.label,
                record_url=getattr(option, "record_url", None),
                priority=getattr(option, "priority", "retail"),
                sample_fps=float(getattr(option, "sample_fps", 5.0)),
                floor_fps=getattr(option, "floor_fps", None),
            )
        )

    for item in local:
        if str(item.id) in used or not getattr(item, "stream_url", ""):
            continue
        # Inventarda yo'q, lekin lokal konfigda to'liq yozilgan kamera.
        # Uni tashlab yuborish aynan o'sha jimgina yo'qolish bo'lardi.
        plans.append(
            CameraPlan(
                camera_id=str(item.id),
                stream_url=item.stream_url,
                origin="config",
                record_url=item.record_url,
                priority=item.priority,
                sample_fps=float(item.sample_fps),
                floor_fps=item.floor_fps,
            )
        )
    return plans


def describe(plans: Sequence[CameraPlan]) -> str:
    """Log uchun bitta qator: qaysi kamera qayerdan kelgan."""
    cloud = sum(1 for plan in plans if plan.origin == "cloud")
    return (
        f"{len(plans)} kamera: {cloud} tasi cloud inventaridan, "
        f"{len(plans) - cloud} tasi lokal konfigdan"
    )
