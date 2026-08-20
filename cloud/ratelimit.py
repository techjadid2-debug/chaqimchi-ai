"""So'rovlar tezligi cheklovi.

Bitta buzuq qurilma yoki bitta bot cloud'ni yiqita olmasligi kerak. Cheklov
xotirada turadi va jarayon qayta ishga tushganda nolga qaytadi — bu ataylab:
Redis'siz ham ishlaydigan, hech qachon so'rovni bloklab qolmaydigan eng sodda
himoya. Bir nechta cloud instansiyasi paydo bo'lganda o'rniga umumiy hisoblagich
kerak bo'ladi, lekin bitta VPS uchun shu yetadi.

Sanoq oynasi **sirpanmaydigan** (fixed window): oyna tugashi bilan hisob
nolga qaytadi. Chegarada ikki barobar o'tkazib yuborishi mumkin, lekin
har so'rov uchun bitta lug'at yozuvi — xotira o'smaydi.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, Tuple

from fastapi import HTTPException

#: Bitta kalit bo'yicha eski yozuvlar shuncha oynadan keyin supuriladi.
_SWEEP_EVERY_SEC = 300


@dataclass
class _Window:
    started_at: float
    count: int
    #: Shu oynaning o'z muddati.  Tozalash aynan shunga qarab ishlaydi:
    #: aks holda sutkalik chegara ham 5 daqiqada o'chib ketardi.
    window_sec: int


class RateLimiter:
    def __init__(self) -> None:
        self._windows: Dict[Tuple[str, str], _Window] = {}
        self._lock = threading.Lock()
        self._last_sweep = time.monotonic()

    def _sweep(self, now: float) -> None:
        """Ishlatilmay qolgan kalitlarni tashlaydi — xotira cheksiz o'smasin.

        Faqat **muddati tugagan** oynalar o'chiriladi.  Ilgari o'lchov
        oynaning o'z muddati emas, tozalash oralig'i (5 daqiqa) edi: shu
        sabab sutkalik chegara (masalan 500 ta rasm) amalda 5 daqiqada
        qayta ochilardi va buzuq qurilma kuniga terabaytlab yuklay olardi.
        """
        if now - self._last_sweep < _SWEEP_EVERY_SEC:
            return
        self._last_sweep = now
        stale = [
            key
            for key, window in self._windows.items()
            if now - window.started_at >= window.window_sec
        ]
        for key in stale:
            del self._windows[key]

    def hit(self, bucket: str, key: str, *, limit: int, window_sec: int) -> bool:
        """Bitta so'rovni hisoblaydi. Limit oshmagan bo'lsa `True`."""
        now = time.monotonic()
        with self._lock:
            self._sweep(now)
            entry = self._windows.get((bucket, key))
            if entry is None or now - entry.started_at >= window_sec:
                self._windows[(bucket, key)] = _Window(
                    started_at=now, count=1, window_sec=int(window_sec)
                )
                return True
            entry.count += 1
            return entry.count <= limit

    def size(self) -> int:
        """Kuzatilayotgan kalitlar soni — xotira o'smayotganini tekshirish uchun."""
        with self._lock:
            return len(self._windows)

    def reset(self) -> None:
        """Testlar orasida holatni tozalaydi."""
        with self._lock:
            self._windows.clear()


_limiter = RateLimiter()


def limiter() -> RateLimiter:
    return _limiter


def check(bucket: str, key: str, *, limit: int, window_sec: int, message: str) -> None:
    """Limit oshsa `429` qaytaradi.

    `message` mijozga ko'rinadi, shuning uchun o'zbekcha va tushunarli bo'lsin —
    "429" raqami do'kon egasiga hech narsa demaydi.
    """
    if not _limiter.hit(bucket, key, limit=limit, window_sec=window_sec):
        raise HTTPException(429, message, headers={"Retry-After": str(window_sec)})
