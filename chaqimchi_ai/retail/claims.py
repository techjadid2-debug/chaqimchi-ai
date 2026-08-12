"""Kamera da'vosi va prioritet sinflari.

Da'vo — bu "shu kadrni ko'rib chiqing" degan so'rov.  Broker qaysi da'voni
qachon bajarishni hal qiladi.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any


class Priority(IntEnum):
    """Kamera qanchalik muhim.  Kichik raqam — muhimroq.

    Prioritet kameraga emas, **vazifaga** beriladi: bitta kamera taqiqlangan
    zonani ham, navbatni ham kuzatishi mumkin.  Bunda kamera eng muhim
    vazifasining prioritetini oladi.
    """

    #: Taqiqlangan zona, ish vaqtidan tashqari harakat, kamera yopilishi.
    #: Bularni kechiktirish — mijoz pul to'layotgan asosiy va'dani buzish.
    SECURITY = 1
    #: Sanash, navbat, dwell.  Bir necha soniya kechiksa hisobot buzilmaydi.
    RETAIL = 2
    #: Heatmap, uzoq muddatli statistika.  Bo'sh vaqtda bajariladi.
    BACKGROUND = 3


#: Prioritetning byudjetdagi ulushi.  SECURITY kamerasi RETAIL'dan ikki barobar,
#: BACKGROUND'dan to'rt barobar ko'p slot oladi.
PRIORITY_WEIGHT: dict[Priority, float] = {
    Priority.SECURITY: 4.0,
    Priority.RETAIL: 2.0,
    Priority.BACKGROUND: 1.0,
}

#: Eng past kafolatlangan tezlik (inferens/sekund).  Yuklama qanchalik yuqori
#: bo'lmasin, kamera shu chastotadan sekinroq ko'rilmaydi.  Bu "ochlik"ka
#: qarshi qat'iy kafolat: xavfsizlik kamerasi hech qachon butunlay unutilmaydi.
PRIORITY_FLOOR_FPS: dict[Priority, float] = {
    Priority.SECURITY: 1.0,
    Priority.RETAIL: 0.5,
    Priority.BACKGROUND: 0.1,
}


@dataclass(frozen=True)
class Claim:
    """Broker bergan ish: shu kameraning shu kadrini tahlil qiling."""

    camera_id: str
    frame: Any
    priority: Priority
    motion_score: float
    #: Kadr `submit()` qilingan payt — tahlil qanchalik kechikkanini bilish uchun.
    submitted_at: float
    #: Ochlik kafolati ishga tushgani sababli berilgan bo'lsa `True`.
    #: Metrikada bu son o'ssa — byudjet talabdan kichik.
    rescued: bool = False
