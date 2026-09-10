"""Kamera tungi rejimda mi — kadrning o'zidan aniqlash.

Nega kerak.  Ko'p IP kamera qorong'ida o'zi infraqizil (IR) rejimga
o'tadi: kadr oq-qora bo'lib qoladi, yorug'lik keskin o'zgaradi.  Bu
o'tish zanjirning ikki joyini aldaydi:

* `tamper.py` me'yorga nisbatan «qorong'i» yoki «ko'rinish o'zgardi»
  deb 10 daqiqa (`accept_after_sec`) trevoga holatida turadi — kamera
  hech kim tegmasa ham;
* `MotionGate` (MOG2, `history=300`) eski rangli fonni bir daqiqa
  «harakat» deb ko'radi.

Dastur IR'ni qo'sha olmaydi — bu kameraning apparati.  Dastur qiladigani:
o'tishni SEZISH va o'sha lahzada me'yorni qayta o'rganish, hamda IR'siz
kamera tunda ko'r ekanini halol aytish (`dark`).

O'lchov: 160×90 kichik nusxada HSV to'yinganligi (S) o'rtachasi —
oq-qora kadrda u nolga yaqin; rangli sahnada 30 dan yuqori.  Yorug'lik —
kulrang o'rtachasi, `tamper.MIN_BASELINE_BRIGHTNESS` bilan bir xil
chegara: shundan past kadrda detektor ham, xarita ham ma'nosiz.

Gisterezis 30 soniya: kunduzi bir lahzalik rangsiz kadr (oq devor,
chaqnash) rejimni almashtirmasin.  Har 10-kadrda o'lchanadi — 5 FPS da
har 2 soniya; tezroq kerak emas, kamera o'tishi soniyalar oladi.
"""

from __future__ import annotations

from typing import Any, Optional, Tuple

import cv2
import numpy as np

DAY = "day"
IR = "ir"
DARK = "dark"

#: HSV S o'rtachasi shundan past — kadr oq-qora (IR).  Rangli sahna
#: odatda 30–80 beradi; JPEG/H.264 shovqini oq-qora kadrga 2–5 qo'shadi.
CHROMA_MAX_IR = 8.0
#: Kulrang o'rtachasi shundan past — kamera tunda ko'r (IR'siz).
#: `tamper.MIN_BASELINE_BRIGHTNESS` bilan bir xil sabab.
DARK_BRIGHTNESS = 25.0
HOLD_SEC = 30.0
SAMPLE_EVERY = 10
SAMPLE_WIDTH, SAMPLE_HEIGHT = 160, 90


def measure(frame: np.ndarray) -> Tuple[float, float]:
    """`(yorug'lik, to'yinganlik)` — ikkalasi 0..255 shkalada."""
    small = cv2.resize(frame, (SAMPLE_WIDTH, SAMPLE_HEIGHT), interpolation=cv2.INTER_AREA)
    if small.ndim != 3:
        return float(small.mean()), 0.0
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    return float(hsv[:, :, 2].mean()), float(hsv[:, :, 1].mean())


def classify(brightness: float, chroma: float) -> str:
    if brightness < DARK_BRIGHTNESS:
        return DARK
    if chroma < CHROMA_MAX_IR:
        return IR
    return DAY


def enhance_for_detection(frame: np.ndarray) -> np.ndarray:
    """Qorong'i kadrni DETEKTOR uchun yoritadi (CLAHE + gamma 0.6).

    Faqat tahlilga ketadigan nusxaga qo'llanadi — rasm va klip asl
    kadrdan olinadi, aks holda ega «kamera nimani ko'rdi» ni emas,
    biz bo'yagan kadrni ko'rardi.  Sifat cheklangan: bu IR'ning o'rnini
    bosmaydi, faqat chiroq o'chgan zaldagi siluetni ushlab qolish uchun.
    """
    if frame.ndim != 3:
        return frame
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    lab[:, :, 0] = clahe.apply(lab[:, :, 0])
    lit = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    table = np.array([((value / 255.0) ** 0.6) * 255 for value in range(256)], dtype=np.uint8)
    return cv2.LUT(lit, table)


class NightModeProbe:
    """Bitta kameraning tungi rejimini kuzatadi; almashganda `(eski, yangi)`."""

    def __init__(
        self,
        *,
        hold_sec: float = HOLD_SEC,
        sample_every: int = SAMPLE_EVERY,
    ) -> None:
        if hold_sec < 0 or sample_every < 1:
            raise ValueError("hold_sec manfiy, sample_every noldan kichik bo'lmasin")
        self.hold_sec = float(hold_sec)
        self.sample_every = int(sample_every)
        self.mode: str = DAY
        self.since: Optional[float] = None
        self.changes = 0
        self.brightness = 0.0
        self.chroma = 0.0
        self._frames = 0
        self._pending: Optional[str] = None
        self._pending_since = 0.0
        self._settled = False

    def update(self, frame: np.ndarray, *, now: float) -> Optional[Tuple[str, str]]:
        self._frames += 1
        if (self._frames - 1) % self.sample_every:
            return None
        self.brightness, self.chroma = measure(frame)
        candidate = classify(self.brightness, self.chroma)
        if not self._settled:
            # Birinchi o'lchov — bu me'yor, almashuv emas: tizim kechasi
            # yoqilsa IR rejimi «o'tish» deb qayta o'rganishni chaqirmasin.
            self._settled = True
            self.mode, self.since = candidate, now
            return None
        if candidate == self.mode:
            self._pending = None
            return None
        if self._pending != candidate:
            self._pending, self._pending_since = candidate, now
            return None
        if now - self._pending_since < self.hold_sec:
            return None
        previous, self.mode, self.since = self.mode, candidate, now
        self._pending = None
        self.changes += 1
        return previous, candidate

    def stats(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "since": self.since,
            "changes": self.changes,
            "brightness": round(self.brightness, 1),
            "chroma": round(self.chroma, 1),
        }
