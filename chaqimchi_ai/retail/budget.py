"""Inferens byudjeti — qurilma sekundiga nechta kadrni ko'ra oladi.

N100 iGPU'da odam detektori sekundiga cheklangan sondagi kadrni ulguradi.
Agar har kamera o'zi xohlagancha so'rasa, navbat cheksiz o'sadi, kechikish
o'nlab sekundga chiqadi va hodisa kech keladi — ya'ni tizim ishlayotgandek
ko'rinib, aslida foydasiz bo'lib qoladi.

Shu sabab byudjet bitta joyda hisoblanadi va **o'lchovga qarab o'zi
sozlanadi**: qurilma sekinlashsa (issiqlik, boshqa yuk, og'irroq kadr)
byudjet tushadi; bo'sh bo'lsa ko'tariladi.  Qattiq yozilgan FPS ishlamaydi,
chunki bitta raqam yozning issiq kunida ham, kechasi ham to'g'ri bo'la olmaydi.

Vaqt tashqaridan (`now`) beriladi — testlar soatga bog'lanmasin va natija
takrorlanadigan bo'lsin.
"""

from __future__ import annotations

from collections import deque
from typing import Deque, Dict, Optional

#: Adaptatsiya uchun kamida shuncha o'lchov kerak — bitta sekin kadr sababli
#: butun byudjetni tushirib yuborish noto'g'ri bo'lardi.
MIN_SAMPLES = 8


def _percentile(values: list[float], fraction: float) -> float:
    """Oddiy persentil.  numpy shart emas — bu modul toza mantiq bo'lib qolsin."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(round(fraction * (len(ordered) - 1)))
    return ordered[index]


class InferenceBudget:
    """Token bucket + o'lchovga asoslangan adaptiv target.

    `take()` bitta inferens uchun ruxsat so'raydi.  `observe()` esa inferens
    qancha vaqt olganini qaytaradi — target shu asosda tuziladi.

    **Chaqirish chastotasi muhim.**  To'planmagan tokenlar `burst` da kesiladi,
    ya'ni `take()` sekin chaqirilsa haqiqiy o'tkazuvchanlik targetdan past
    bo'lib qoladi.  Qoida: chaqiruvlar orasidagi oraliq `burst / target_fps`
    dan kichik bo'lsin.  30 FPS va `burst=2` uchun bu 66 ms — chaqiruv halqasi
    undan tez aylanishi kerak.  Bu ataylab: ishlatilmagan quvvatni cheksiz
    yig'ib, keyin qurilmani bir zumda bosib qo'yish mumkin emas.
    """

    def __init__(
        self,
        *,
        target_fps: float = 30.0,
        min_fps: float = 2.0,
        max_fps: float = 60.0,
        burst: float = 2.0,
        workers: int = 1,
        window: int = 64,
        adapt_interval_sec: float = 5.0,
    ) -> None:
        if min_fps <= 0 or max_fps < min_fps:
            raise ValueError("min_fps > 0 va max_fps >= min_fps bo'lishi kerak")
        if not min_fps <= target_fps <= max_fps:
            raise ValueError("target_fps min_fps va max_fps orasida bo'lishi kerak")
        if workers < 1:
            raise ValueError("workers kamida 1 bo'lishi kerak")
        self.min_fps = float(min_fps)
        self.max_fps = float(max_fps)
        self.burst = float(burst)
        self.workers = int(workers)
        self.adapt_interval_sec = float(adapt_interval_sec)

        self._target_fps = float(target_fps)
        self._tokens = float(burst)
        self._last_refill: Optional[float] = None
        self._latencies: Deque[float] = deque(maxlen=window)
        self._pressure = 0.0
        self._last_adapt: Optional[float] = None
        self._granted = 0
        self._denied = 0

    # ── Ruxsat ───────────────────────────────────────────────────────────

    def take(self, now: float) -> bool:
        """Bitta inferensga ruxsat.  Byudjet tugagan bo'lsa `False`."""
        if self._last_refill is None:
            self._last_refill = now
        elapsed = max(0.0, now - self._last_refill)
        self._last_refill = now
        self._tokens = min(self.burst, self._tokens + elapsed * self._target_fps)
        if self._tokens < 1.0:
            self._denied += 1
            return False
        self._tokens -= 1.0
        self._granted += 1
        return True

    # ── O'lchov va adaptatsiya ───────────────────────────────────────────

    def observe(self, latency_sec: float, *, now: float) -> None:
        """Bajarilgan inferens qancha vaqt olgani.  Target shu asosda tuziladi."""
        if latency_sec <= 0:
            raise ValueError("latency_sec musbat bo'lishi kerak")
        self._latencies.append(float(latency_sec))
        if self._last_adapt is None:
            self._last_adapt = now
            return
        if now - self._last_adapt < self.adapt_interval_sec:
            return
        self._last_adapt = now
        self._adapt()

    def set_pressure(self, value: float) -> None:
        """Tashqi yuk signali: 0 — bo'sh, 1 — CPU/harorat chegarada.

        Buni `psutil` yoki `/sys/class/thermal` o'qiydigan qatlam beradi.
        Byudjet moduli o'zi o'lchamaydi — u toza mantiq bo'lib qolsin.
        """
        self._pressure = min(1.0, max(0.0, float(value)))

    def _adapt(self) -> None:
        if len(self._latencies) < MIN_SAMPLES:
            return
        p95 = _percentile(list(self._latencies), 0.95)
        if p95 <= 0:
            return
        # Ketma-ket ishlaydigan worker sekundiga ko'pi bilan shuncha ulguradi.
        ceiling = self.workers / p95

        if self._pressure >= 0.85:
            # Qurilma qizib ketgan yoki CPU to'lgan — sabab latency'da hali
            # ko'rinmagan bo'lishi mumkin, lekin kutib turish kech bo'ladi.
            target = self._target_fps * 0.8
        elif self._target_fps > ceiling * 0.9:
            # Talab qurilmaning imkoniyatiga tegib turibdi: navbat o'sishidan
            # oldin tushamiz.  0.8 — qaytib chiqish uchun zaxira.
            target = ceiling * 0.8
        elif self._target_fps < ceiling * 0.6 and self._pressure < 0.6:
            # Ancha joy bor — asta ko'taramiz.  Keskin sakrash tebranish beradi.
            target = self._target_fps * 1.25
        else:
            return

        self._target_fps = min(self.max_fps, max(self.min_fps, target))

    # ── Holat ────────────────────────────────────────────────────────────

    @property
    def target_fps(self) -> float:
        return self._target_fps

    def stats(self) -> Dict[str, float]:
        latencies = list(self._latencies)
        return {
            "target_fps": round(self._target_fps, 3),
            "tokens": round(self._tokens, 3),
            "pressure": round(self._pressure, 3),
            "p95_latency_ms": round(_percentile(latencies, 0.95) * 1000, 2),
            "samples": len(latencies),
            "granted": self._granted,
            "denied": self._denied,
        }
