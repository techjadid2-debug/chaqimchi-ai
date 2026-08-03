"""Kamera + shaxs bo‘yicha takroriy match voqealarini cheklash."""

from __future__ import annotations

import time
from typing import Dict, Tuple


class MatchDebouncer:
    """Bir xil (camera_id, person_id) juftligi uchun minimal interval."""

    def __init__(self, interval_sec: float) -> None:
        if interval_sec < 0:
            raise ValueError("interval_sec >= 0 bo‘lishi kerak")
        self.interval_sec = interval_sec
        self._last: Dict[Tuple[str, str], float] = {}

    def should_emit(self, camera_id: str, person_id: str) -> bool:
        if self.interval_sec == 0:
            return True
        now = time.time()
        key = (camera_id, person_id)
        last = self._last.get(key)
        if last is not None and (now - last) < self.interval_sec:
            return False
        self._last[key] = now
        return True
