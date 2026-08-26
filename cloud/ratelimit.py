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
from typing import Dict, Optional, Tuple

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
    #: Chegara oshgani uchun rad etilgan so'rovlar soni.
    #:
    #: Ilgari 429 qaytarilib UNUTILARDI.  2026-08-26 da jonli do'konda shu
    #: sabab 3 soat davomida 6 315 ta rasm jimgina rad etildi: log faqat
    #: `INFO` access qatori edi, panelda raqam yo'q, ERROR ham yo'q.
    #: Mijoz "rasm kelmayapti" deb aytmaganda buni hech kim bilmasdi.
    rejected: int = 0


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
            if entry.count > limit:
                entry.rejected += 1
                return False
            return True

    def used(self, bucket: str, key: str) -> int:
        """Joriy oynada nechta so'rov sanalgan (muddati o'tgan bo'lsa 0)."""
        now = time.monotonic()
        with self._lock:
            entry = self._windows.get((bucket, key))
            if entry is None or now - entry.started_at >= entry.window_sec:
                return 0
            return entry.count

    def rejections(self, key: Optional[str] = None) -> Dict[str, int]:
        """Rad etilgan so'rovlar — bucket bo'yicha, faqat noldan kattalari.

        `key` berilsa bitta obyekt kesimida.  Bu raqam admin panelda va
        `/health/deep` da ko'rinadi: nol bo'lmagan qiymat "mijoz nimadir
        yo'qotyapti" degani va uni ko'rish uchun logni titish shart emas.
        """
        now = time.monotonic()
        summary: Dict[str, int] = {}
        with self._lock:
            for (bucket, entry_key), window in self._windows.items():
                if key is not None and entry_key != key:
                    continue
                if not window.rejected or now - window.started_at >= window.window_sec:
                    continue
                summary[bucket] = summary.get(bucket, 0) + window.rejected
        return summary

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
