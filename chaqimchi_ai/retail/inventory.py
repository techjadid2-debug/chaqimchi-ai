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
    ├─ role (kirish/kassa/zal/ombor)      └─ floor_fps
    └─ enabled

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

from chaqimchi_ai.camera_roles import ROLE_NONE, ROLE_PRIORITY

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InventoryCamera:
    """Cloud inventaridan kelgan kamera."""

    camera_id: str
    source: str
    label: str = ""
    enabled: bool = True
    #: Klip uchun asosiy oqim — bulutdagi ZAXIRA nusxa.
    #:
    #: 0.6.24 dan boshlab qurilma ikkala manzilni ham bulutga yuboradi.
    #: Bu maydonning butun ma'nosi tiklashda: do'kon kompyuteri qayta
    #: o'rnatilsa lokal sozlama bo'sh bo'ladi va klip manzili faqat shu
    #: yerdan kelishi mumkin.  Bo'sh bo'lsa quyidagi tartib ishlaydi.
    record_url: str = ""
    #: Kameraning mahsulot vazifasi.  Bulut — rolning asosiy manbai:
    #: sehrgar saqlaganini qurilma bulutga chiqaradi va shu yerdan
    #: qaytib keladi (qayta o'rnatilgan kompyuterda ham yo'qolmaydi).
    role: str = ROLE_NONE


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
    #: `entrance | checkout | sales | storage | none` — zanjir bundan
    #: davomat/ogohlantirish qarorlarini oladi (`service.py`).
    role: str = ROLE_NONE


def read_sotqin_cache(path: Path) -> Dict[str, Any]:
    """Sotqin config keshini o'qiydi.

    Fayl yo'q bo'lsa bo'sh natija — bu normal holat: qurilma hali
    juftlanmagan yoki analitika mustaqil (cloud'siz) ishlatilyapti.  Fayl
    **buzuq** bo'lsa esa xato ko'tariladi: jimgina bo'sh ro'yxat bilan
    davom etish "kamera yo'qolgan" holatining aynan o'zi bo'lardi.
    """
    if not path.is_file():
        return {
            "revision": None,
            "config": {},
            "attendance": {},
            "cloud_features": [],
            "cameras": [],
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Sotqin config keshi buzuq: {path}") from exc
    if not isinstance(payload, Mapping):
        raise ValueError(f"Sotqin config keshi noto'g'ri: {path}")
    return {
        "revision": payload.get("revision"),
        "config": dict(payload.get("config") or {}),
        "attendance": dict(payload.get("attendance") or {}),
        "cloud_features": list(payload.get("cloud_features") or []),
        "cameras": [
            InventoryCamera(
                camera_id=str(item.get("camera_id") or ""),
                source=str(item.get("source") or ""),
                label=str(item.get("label") or ""),
                enabled=bool(item.get("enabled", True)),
                record_url=str(item.get("record_url") or ""),
                role=str(item.get("role") or "") or ROLE_NONE,
            )
            for item in (payload.get("cameras") or [])
            if isinstance(item, Mapping)
        ],
    }


def merge_cameras(inventory: Sequence[InventoryCamera], local: Sequence[Any]) -> List[CameraPlan]:
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
        # Rol bulutdan keladi (nom bilan bir xil manba); bulut hali
        # bilmasa lokal sozlamadagi qoladi.
        role = (
            (camera.role if camera.role != ROLE_NONE else "")
            or getattr(option, "role", None)
            or ROLE_NONE
        )
        plans.append(
            CameraPlan(
                camera_id=camera.camera_id,
                stream_url=camera.source,
                origin="cloud",
                label=camera.label,
                # Klip manzili uch manbadan, shu TARTIBDA:
                #
                # 1. lokal sozlama — mijoz/usta shu kompyuterda kiritgan,
                #    ya'ni eng aniq;
                # 2. bulutdagi zaxira — qayta o'rnatilgan kompyuterda
                #    lokal sozlama bo'sh bo'ladi va klip manzili faqat
                #    shu yerdan keladi (0.6.24 dan);
                # 3. substream — hech biri bo'lmasa xavfsizlik
                #    hodisasining klipi butunlay yo'qolgandan ko'ra
                #    past sifatli klip yaxshiroq.
                record_url=(
                    getattr(option, "record_url", None) or camera.record_url or camera.source
                ),
                # Lokal sozlama bo'lsa prioritet undan (usta/support aniq
                # qo'ygan).  Bo'lmasa — qayta o'rnatilgan kompyuter — rol
                # standartni beradi: bulutda tasdiqlangan "kirish" shu
                # yerda haqiqiy `security` navbatiga aylanadi.
                priority=(
                    getattr(option, "priority", None) or ROLE_PRIORITY.get(role, "retail")
                ),
                sample_fps=float(getattr(option, "sample_fps", 5.0)),
                floor_fps=getattr(option, "floor_fps", None),
                role=role,
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
                role=getattr(item, "role", None) or ROLE_NONE,
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
