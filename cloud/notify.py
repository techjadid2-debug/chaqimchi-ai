"""Mijozga Telegram xabarini yig'ib, tormozlab yuborish.

Bungacha har `warning`/`critical` event uchun alohida xabar ketardi. Bitta
batch 500 tagacha event ko'taradi, obyektda esa bir necha a'zo bo'ladi — ya'ni
bitta so'rov 1500 tagacha Telegram chaqiruvini tug'dirardi. Telegram sekundiga
~30 tasini qabul qiladi, qolganida bot cheklanadi va **hech kim** xabar olmay
qoladi. Ya'ni ko'p xabar yuborish aslida xabarni butunlay yo'qotish edi.

Endi ikki qoida ishlaydi:

1. Bitta batch — bitta xabar (turlar bo'yicha yig'ib).
2. Bitta (obyekt, tur, kamera) uchligi uchun 10 daqiqada bir marta. Kamera
   soatlab bir xil ogohlantirishni qaytarsa mijoz telefonini o'chirib qo'ymaydi.

Tormoz xotirada — jarayon qayta ishga tushsa birinchi xabar o'tadi. Ogohlantirish
uchun bu to'g'ri tomonga xato qilish: kechikkanidan ko'ra takrorlangani yaxshi.
"""

from __future__ import annotations

import threading
import time
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from chaqimchi_ai.event_models import EdgeEvent

#: Bir xil ogohlantirish shuncha soniyada bir martadan ko'p yuborilmaydi.
DEFAULT_THROTTLE_SEC = 600

#: Xabarga sig'adigan tur soni — qolgani "va yana N ta" bo'lib qisqaradi.
MAX_LINES = 6

ALERT_SEVERITIES = frozenset({"warning", "critical"})

#: Mijoz `zone_entered` ni tushunmaydi; xabar odam tilida bo'lishi kerak.
EVENT_LABELS: Dict[str, str] = {
    "person_detected": "Odam aniqlandi",
    "employee_seen": "Xodim ko'rindi",
    "zone_entered": "Taqiqlangan zonaga kirish",
    "loitering": "Uzoq turish",
    "occupancy_exceeded": "Bandlik chegarasi oshdi",
}


def event_label(event_type: str) -> str:
    return EVENT_LABELS.get(event_type, event_type)


class AlertThrottle:
    """(obyekt, tur, kamera) bo'yicha takroriy xabarni to'sadi."""

    def __init__(self, window_sec: int = DEFAULT_THROTTLE_SEC) -> None:
        self.window_sec = window_sec
        self._sent: Dict[Tuple[str, str, str], float] = {}
        self._lock = threading.Lock()

    def allow(self, site_id: str, event_type: str, camera_id: str) -> bool:
        key = (site_id, event_type, camera_id)
        now = time.monotonic()
        with self._lock:
            last = self._sent.get(key)
            if last is not None and now - last < self.window_sec:
                return False
            self._sent[key] = now
            # Muddati o'tgan yozuvlar kerak emas — xotira o'smasin.
            if len(self._sent) > 10_000:
                self._sent = {
                    stored_key: stamp
                    for stored_key, stamp in self._sent.items()
                    if now - stamp < self.window_sec
                }
            return True

    def reset(self) -> None:
        with self._lock:
            self._sent.clear()


_throttle = AlertThrottle()


def throttle() -> AlertThrottle:
    return _throttle


def summarize(events: Sequence[EdgeEvent]) -> str:
    """Ruxsat berilgan eventlardan bitta o'qiladigan xabar.

    Qatorlar soni bo'yicha emas, **hodisa soni** bo'yicha tartiblanadi: eng
    ko'p takrorlangan muammo birinchi turadi.
    """
    groups: Dict[Tuple[str, str], int] = {}
    critical = 0
    for event in events:
        key = (event.event_type, event.camera_id)
        groups[key] = groups.get(key, 0) + 1
        if event.severity == "critical":
            critical += 1

    total = sum(groups.values())
    head = "🔴" if critical else "⚠️"
    lines = [f"{head} {total} ta ogohlantirish"]
    ordered = sorted(groups.items(), key=lambda item: (-item[1], item[0]))
    for (event_type, camera_id), count in ordered[:MAX_LINES]:
        suffix = f" ×{count}" if count > 1 else ""
        lines.append(f"• {event_label(event_type)} — {camera_id}{suffix}")
    if len(ordered) > MAX_LINES:
        lines.append(f"• va yana {len(ordered) - MAX_LINES} ta turdagi hodisa")
    return "\n".join(lines)


def build_alert(
    site_id: str,
    events: Iterable[EdgeEvent],
    *,
    throttle_service: Optional[AlertThrottle] = None,
) -> Optional[str]:
    """Batchdan yuboriladigan bitta xabar — yoki hech narsa.

    Tormoz shu yerda qo'llanadi: bir xil (tur, kamera) juftligi oynada
    allaqachon yuborilgan bo'lsa, uning **hamma** eventlari xabardan tushadi.
    """
    limiter = throttle_service or _throttle
    alerts = [event for event in events if event.severity in ALERT_SEVERITIES]
    if not alerts:
        return None

    seen: Dict[Tuple[str, str], bool] = {}
    allowed: List[EdgeEvent] = []
    for event in alerts:
        key = (event.event_type, event.camera_id)
        if key not in seen:
            seen[key] = limiter.allow(site_id, event.event_type, event.camera_id)
        if seen[key]:
            allowed.append(event)
    if not allowed:
        return None
    return summarize(allowed)
