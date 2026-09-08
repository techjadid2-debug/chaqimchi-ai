"""Fon vazifalari uchun yetakchi — ular FAQAT bitta jarayonda yursin.

`lifespan` har uvicorn worker'ida oltita fon vazifasini ishga tushiradi:
kunlik hisobot, tozalash, rollup, lead eslatmasi, bot buyruqlari va
aloqa nazorati.  Bitta worker'da bu to'g'ri edi.  `--workers 2` bilan esa
ularning hammasi IKKI NUSXADA yurardi — ya'ni do'kon egasi kunlik
hisobotni ikki marta olardi va tozalash ikkita jarayondan bir vaqtda
o'chirardi.

Yechim — ijara (lease), advisory lock emas: `pg_try_advisory_lock` uzoq
yashaydigan ulanishni talab qiladi, `EventStore._connect()` esa har
so'rovda ochib-yopadi.  Ijara oddiy qator: kim `expires_at` ni ushlab
tursa, o'sha yetakchi.  U ikkala dialektda ham ishlaydi va testda vaqtni
surib sinash mumkin.

Yetakchi o'lsa ijara TTL dan keyin o'zi bo'shaydi va navbatdagi jarayon
oladi — hech kim qo'lda aralashmaydi.
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

#: Ijara shuncha soniya amal qiladi.  Yangilash oralig'idan sezilarli
#: uzun bo'lishi SHART: bitta o'tkazib yuborilgan yangilash (sekin baza,
#: GC pauzasi) yetakchilikni boshqaga berib yubormasin.
DEFAULT_TTL_SEC = 90

#: Shuncha soniyada bir marta uzaytiriladi.
DEFAULT_RENEW_SEC = 20


class LeaderLease:
    """Bitta nomdagi ijara.  `store` berilmasa — har doim yetakchi.

    `store=None` — bitta jarayonli ish (lokal server, testlar): u yerda
    raqobat yo'q va bazaga har 20 soniyada yozishning ma'nosi ham yo'q.
    """

    def __init__(
        self,
        store: Optional[Any] = None,
        *,
        name: str = "background",
        ttl_sec: int = DEFAULT_TTL_SEC,
        renew_sec: int = DEFAULT_RENEW_SEC,
        holder: Optional[str] = None,
    ) -> None:
        self.store = store
        self.name = name
        self.ttl_sec = ttl_sec
        self.renew_sec = renew_sec
        self.holder = holder or f"{socket.gethostname()}:{os.getpid()}"
        self._leading = store is None

    @property
    def leading(self) -> bool:
        """Shu jarayon fon ishini bajaradimi."""
        return self._leading

    def acquire(self) -> bool:
        """Ijarani oladi yoki uzaytiradi."""
        if self.store is None:
            return True
        try:
            self._leading = bool(
                self.store.claim_lease(
                    self.name, self.holder, ttl_sec=self.ttl_sec, now=int(time.time())
                )
            )
        except Exception:
            # Baza javob bermadi.  Yetakchilik SAQLANADI: raqib ham
            # ayni bazaga tegolmaydi, ya'ni ikki nusxa xavfi yo'q, fon
            # ishini esa bekorga to'xtatish kerak emas.  Yetakchi
            # bo'lmagan jarayon esa yetakchi bo'lib qolmaydi.
            logger.warning("Yetakchi ijarasi yangilanmadi (%s)", self.name, exc_info=True)
        return self._leading

    def release(self) -> None:
        """Ijarani bo'shatadi — to'xtayotgan jarayon navbatni tutib turmasin."""
        self._leading = False
        if self.store is None:
            return
        try:
            self.store.release_lease(self.name, self.holder)
        except Exception:
            logger.warning("Yetakchi ijarasi bo'shatilmadi (%s)", self.name, exc_info=True)

    async def run(self) -> None:
        """Ijarani muntazam uzaytiradigan fon halqasi.

        Alohida halqa, chunki fon vazifalarining davri har xil (60 soniyadan
        bir necha soatgacha) va ijara ularning eng sekiniga qarab
        muddatini o'tkazib yuborardi.
        """
        while True:
            try:
                await asyncio.to_thread(self.acquire)
            except asyncio.CancelledError:
                break
            except Exception:  # pragma: no cover - kutilmagan xato halqani yiqitmasin
                logger.exception("Yetakchi halqasida xato")
            try:
                await asyncio.sleep(self.renew_sec)
            except asyncio.CancelledError:
                break
