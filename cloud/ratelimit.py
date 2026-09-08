"""So'rovlar tezligi cheklovi.

Bitta buzuq qurilma yoki bitta bot cloud'ni yiqita olmasligi kerak.

Hisob IKKI joyda turishi mumkin:

* **Xotirada** — standart yo'l.  Redis'siz ishlaydi, hech qanday
  bog'liqlik talab qilmaydi va bitta jarayon uchun aynan yetarli.
* **Umumiy bazada** (`rate_limit_windows`) — uvicorn bir nechta worker
  bilan ishlaganda.  Xotiradagi hisob har jarayonda alohida yurardi,
  ya'ni chegara jimgina worker soniga KO'PAYARDI: "kuniga 500 ta rasm"
  ikki worker bilan 1000 ta bo'lardi va buni hech narsa aytmasdi.

Sanoq oynasi **sirpanmaydigan** (fixed window): oyna tugashi bilan hisob
nolga qaytadi.  Chegarada ikki barobar o'tkazib yuborishi mumkin, lekin
har so'rov uchun bitta yozuv — xotira ham, jadval ham o'smaydi.

Vaqt **devor soati** bilan o'lchanadi (`time.time`), `time.monotonic`
bilan emas: monotonic har jarayonda o'z nuqtasidan boshlanadi, ya'ni ikki
worker'ning oynasini taqqoslab bo'lmaydi.  Devor soatining orqaga sakrashi
(NTP) eng yomon holatda bitta oynani uzaytiradi — chegarani ochib
yubormaydi.

**Baza javob bermasa so'rov O'TADI.**  Cheklov himoya vositasi, xizmatni
to'xtatuvchi emas: baza tushganda mijozni ham qo'shimcha ravishda
bloklash foyda bermaydi.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException

logger = logging.getLogger(__name__)

#: Bitta kalit bo'yicha eski yozuvlar shuncha oynadan keyin supuriladi.
_SWEEP_EVERY_SEC = 300

#: Baza xatosi haqida shuncha soniyada bir marta yoziladi — cheklov har
#: so'rovda chaqiriladi va baza tushganda log fayli sekundiga minglab
#: qator olardi.
_ERROR_LOG_EVERY_SEC = 60


def _now() -> int:
    """Oyna soati — unix soniya.

    Alohida funksiya, chunki testlar vaqtni surib ko'radi va ikkala
    (xotira va baza) yo'l AYNAN bir soatdan o'qishi kerak.
    """
    return int(time.time())


@dataclass
class _Window:
    started_at: int
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
        self._last_sweep = _now()
        #: Bog'langan bo'lsa hisob shu bazada — `bind()` ga qarang.
        self._store: Optional[Any] = None
        self._last_error_log = 0.0

    # ── Umumiy baza ──────────────────────────────────────────────────

    def bind(self, store: Any) -> None:
        """Hisobni umumiy bazaga ko'chiradi (`cloud/main.py` lifespan)."""
        with self._lock:
            self._store = store
            self._windows.clear()

    def unbind(self) -> None:
        """Xotiradagi hisobga qaytaradi (server to'xtaganda)."""
        with self._lock:
            self._store = None

    @property
    def shared(self) -> bool:
        return self._store is not None

    def _failed(self, action: str, exc: Exception) -> None:
        """Baza xatosi: so'rov o'tkaziladi, lekin jimgina emas."""
        now = time.monotonic()
        if now - self._last_error_log >= _ERROR_LOG_EVERY_SEC:
            self._last_error_log = now
            logger.error("Tezlik cheklovi bazasi javob bermadi (%s): %s", action, exc)

    # ── Xotira ───────────────────────────────────────────────────────

    def _sweep(self, now: int) -> None:
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

    # ── Ommaviy yuza ─────────────────────────────────────────────────

    def hit(self, bucket: str, key: str, *, limit: int, window_sec: int) -> bool:
        """Bitta so'rovni hisoblaydi. Limit oshmagan bo'lsa `True`."""
        now = _now()
        store = self._store
        if store is not None:
            try:
                _, allowed = store.rate_limit_hit(
                    bucket, key, limit=limit, window_sec=window_sec, now=now
                )
                return allowed
            except Exception as exc:  # pragma: no cover - baza tushgan holat
                self._failed("hit", exc)
                return True
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
        now = _now()
        store = self._store
        if store is not None:
            try:
                return store.rate_limit_used(bucket, key, now=now)
            except Exception as exc:  # pragma: no cover
                self._failed("used", exc)
                return 0
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
        now = _now()
        store = self._store
        if store is not None:
            try:
                return store.rate_limit_rejections(now=now, subject=key)
            except Exception as exc:  # pragma: no cover
                self._failed("rejections", exc)
                return {}
        summary: Dict[str, int] = {}
        with self._lock:
            for (bucket, entry_key), window in self._windows.items():
                if key is not None and entry_key != key:
                    continue
                if not window.rejected or now - window.started_at >= window.window_sec:
                    continue
                summary[bucket] = summary.get(bucket, 0) + window.rejected
        return summary

    def sweep(self) -> int:
        """Muddati tugagan oynalarni majburan tozalaydi.

        Xotira yo'li buni o'zi qiladi; bazada esa hech kim so'ramagan
        kalit abadiy qolib ketardi, shuning uchun uni fon halqasi
        (`_maintenance_loop`) chaqiradi.
        """
        now = _now()
        store = self._store
        if store is not None:
            try:
                return store.rate_limit_sweep(now=now)
            except Exception as exc:  # pragma: no cover
                self._failed("sweep", exc)
                return 0
        with self._lock:
            self._last_sweep = now - _SWEEP_EVERY_SEC
            before = len(self._windows)
            self._sweep(now)
            return before - len(self._windows)

    def size(self) -> int:
        """Kuzatilayotgan kalitlar soni — o'smayotganini tekshirish uchun."""
        store = self._store
        if store is not None:
            try:
                return store.rate_limit_size()
            except Exception as exc:  # pragma: no cover
                self._failed("size", exc)
                return 0
        with self._lock:
            return len(self._windows)

    def reset(self) -> None:
        """Testlar orasida holatni tozalaydi."""
        store = self._store
        if store is not None:
            try:
                store.rate_limit_reset()
            except Exception as exc:  # pragma: no cover
                self._failed("reset", exc)
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
