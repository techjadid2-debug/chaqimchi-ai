"""Kamera yopildimi, burildimi yoki bo'yaldimi.

O'g'ri birinchi navbatda kamerani yopadi.  Shu sabab bu tekshiruv **harakat
filtridan oldin** turadi: yopilgan kamerada harakat yo'q, ya'ni filtr uni
o'tkazmaydi va odam aniqlash hech qachon ishlamaydi.  Tizim "hammasi joyida"
deb ko'rsatib turaveradi — eng yomon holat.

Model ishlatilmaydi.  Uchta arzon o'lchov yetadi:

| Belgi | O'lchov | Nimani ushlaydi |
|-------|---------|-----------------|
| Qorong'i | o'rtacha yorug'lik | yopilgan, bo'yalgan, o'chirilgan |
| Xira | Laplacian dispersiyasi | fokus buzilgan, sprey sepilgan |
| Ko'rinish o'zgardi | 8×8 imzo farqi | burilgan, ko'chirilgan |

Har o'lchov **o'rganilgan me'yorga** nisbatan solishtiriladi, mutlaq songa
emas: ombor doim qorong'i, savdo zali doim yorug' — bitta chegara ikkalasiga
to'g'ri kelmaydi.

## Ikki qoida shovqinga qarshi

1. **Davomiylik.**  Kamera oldidan o'tgan odam kadrni bir soniyaga to'sadi.
   Anomaliya `min_duration_sec` davom etmasa hodisa chiqmaydi.
2. **Bir marta.**  Hodisa chiqqach me'yor **muzlatiladi** va takror
   ogohlantirilmaydi.  Kamera yopilib, keyin ochilsa ko'rinish eski me'yorga
   qaytadi va ikkinchi (keraksiz) hodisa chiqmaydi.

Kamera ataylab boshqa tomonga burilgan bo'lsa anomaliya ketmaydi.  Shuning
uchun `accept_after_sec` dan keyin yangi ko'rinish me'yor deb qabul qilinadi —
aks holda detektor abadiy "buzilgan" holatda qolib, keyingi haqiqiy
buzilishni o'tkazib yuborardi.

## Ma'lum cheklov

Chiroq o'chganda kadr ham qorong'i bo'ladi (IR yorug'ligi bo'lmagan kamerada).
Buni model ajrata olmaydi — do'kon yopilgandan keyin `camera_tampered` uchun
qoidaga jadval qo'ying (`docs` dagi qoida namunasiga qarang).

Chegaralar boshlang'ich qiymatlar: haqiqiy obyektda kalibrlash kerak.  Shu
sabab hodisa `score` bilan chiqadi — panelda ko'rib chegarani sozlash mumkin.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Dict, Optional

import cv2
import numpy as np

#: O'lchov shu o'lchamda bajariladi — asl kadr kerak emas, tez bo'lsin.
SAMPLE_WIDTH = 160
SAMPLE_HEIGHT = 90

#: Me'yor o'rganilguncha o'tadigan kadrlar (5 FPS da ~6 soniya).
WARMUP_FRAMES = 30

#: Me'yorning o'zi qorong'i bo'lsa "qorong'i" testi ma'nosiz — kechasi ombor
#: doim shunday.
MIN_BASELINE_BRIGHTNESS = 25.0

#: Me'yor allaqachon xira bo'lsa (tuman, arzon kamera) blur testi shovqin beradi.
MIN_BASELINE_SHARPNESS = 15.0

DARK = "qorong'i"
BLURRED = "xira"
MOVED = "ko'rinish o'zgardi"
FROZEN = "kadr qotib qolgan"

#: `TamperAlert.kind` — hodisa turi shundan tanlanadi.
TAMPER = "tamper"
FREEZE = "freeze"

#: Oqim shuncha soniya davomida **bayt-bayt bir xil** kadr bersa qotgan
#: deb hisoblanadi.  Haqiqiy statik sahna hech qachon bayt-bayt bir xil
#: bo'lmaydi: sensor shovqini har kadrda bir-ikki birlikka o'zgaradi.
#: Shu sabab bu tekshiruv yolg'on signal bermaydi va chegara sozlash
#: talab qilmaydi.
FROZEN_SEC = 20.0


@dataclass(frozen=True)
class TamperAlert:
    reason: str
    #: Me'yordan qanchalik uzoq (0..1).  Kalibrlash uchun hodisaga qo'shiladi.
    score: float
    duration_sec: float
    #: `tamper` — kamera yopildi/burildi; `freeze` — oqim qotib qoldi.
    #: Ikkalasi bir xil yo'ldan chiqadi, lekin hodisa turi boshqa.
    kind: str = TAMPER


def _measure(frame: np.ndarray) -> tuple:
    small = cv2.resize(frame, (SAMPLE_WIDTH, SAMPLE_HEIGHT), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY) if small.ndim == 3 else small
    brightness = float(gray.mean())
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    # 8×8 blok o'rtachasi — kadrning "imzosi".  Odam o'tsa bir-ikki blok
    # o'zgaradi, kamera burilsa hammasi.
    signature = cv2.resize(gray, (8, 8), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
    # Qotib qolishni aniqlash uchun **aniq** nusxa kerak, imzo emas: imzo
    # 8×8 gacha siqilgani uchun ozgina o'zgargan kadrni ham bir xil deb
    # ko'rsatishi mumkin.
    digest = hashlib.blake2b(np.ascontiguousarray(gray).tobytes(), digest_size=16).digest()
    return brightness, sharpness, signature, digest


class TamperDetector:
    def __init__(
        self,
        *,
        min_duration_sec: float = 10.0,
        dark_ratio: float = 0.35,
        blur_ratio: float = 0.35,
        change_threshold: float = 0.20,
        accept_after_sec: float = 600.0,
        adapt: float = 0.02,
        warmup_frames: int = WARMUP_FRAMES,
        frozen_sec: float = FROZEN_SEC,
    ) -> None:
        if not 0.0 < adapt <= 1.0:
            raise ValueError("adapt 0 va 1 orasida bo'lishi kerak")
        if min_duration_sec <= 0:
            raise ValueError("min_duration_sec musbat bo'lishi kerak")
        if accept_after_sec <= min_duration_sec:
            raise ValueError("accept_after_sec min_duration_sec dan katta bo'lsin")
        self.min_duration_sec = float(min_duration_sec)
        self.dark_ratio = float(dark_ratio)
        self.blur_ratio = float(blur_ratio)
        self.change_threshold = float(change_threshold)
        self.accept_after_sec = float(accept_after_sec)
        self.adapt = float(adapt)
        self.warmup_frames = int(warmup_frames)
        if frozen_sec <= 0:
            raise ValueError("frozen_sec musbat bo'lishi kerak")
        self.frozen_sec = float(frozen_sec)

        self._frames = 0
        self._brightness = 0.0
        self._sharpness = 0.0
        self._signature: Optional[np.ndarray] = None
        self._since: Optional[float] = None
        self._alerted = False
        self._alerts = 0
        # Qotib qolish holati — buzilish holatidan mustaqil: kamera ham
        # yopilgan, ham qotgan bo'lishi mumkin va ikkalasi ham aytilishi kerak.
        self._digest: Optional[bytes] = None
        self._same_since: Optional[float] = None
        self._frozen = False
        self._freezes = 0

    # ── O'lchov ──────────────────────────────────────────────────────────

    def update(self, frame: np.ndarray, *, now: float) -> Optional[TamperAlert]:
        """Har kadr uchun chaqiriladi.  Hodisa bo'lsa `TamperAlert`."""
        brightness, sharpness, signature, digest = _measure(frame)
        self._frames += 1

        # Qotib qolish tekshiruvi eng birinchi va warmup'dan mustaqil:
        # oqim boshidanoq qotgan bo'lishi mumkin (NVR qayta yuklangan), va
        # bu holda me'yorni "o'rganish" ham ma'nosiz.
        frozen = self._check_frozen(digest, now)
        if frozen is not None:
            return frozen

        if self._signature is None or self._frames <= self.warmup_frames:
            self._learn(brightness, sharpness, signature, weight=1.0 / min(self._frames, 10))
            return None

        reason, score = self._anomaly(brightness, sharpness, signature)
        if reason is None:
            self._since = None
            self._alerted = False
            # Me'yor faqat tinch paytda o'rganiladi: kun yorishishi yoki
            # chiroq yoqilishi asta-sekin qabul qilinadi.
            self._learn(brightness, sharpness, signature, weight=self.adapt)
            return None

        if self._since is None:
            self._since = now
        elapsed = now - self._since

        if self._alerted:
            if elapsed >= self.accept_after_sec:
                # Kamera ataylab burilgan bo'lsa yangi ko'rinish me'yor bo'ladi,
                # aks holda detektor abadiy shu holatda qolib ketardi.
                self._learn(brightness, sharpness, signature, weight=1.0)
                self._since = None
                self._alerted = False
            return None

        if elapsed < self.min_duration_sec:
            # Kamera oldidan o'tgan odam hodisa emas.
            return None

        self._alerted = True
        self._alerts += 1
        return TamperAlert(reason=reason, score=round(score, 3), duration_sec=round(elapsed, 1))

    def _check_frozen(self, digest: bytes, now: float) -> Optional[TamperAlert]:
        """Oqim qotib qolganmi.

        Bu eng jimgina buziladigan holat: RTSP ulanish ochiq turadi, `grab()`
        va `retrieve()` muvaffaqiyatli qaytadi, lekin kadr o'zgarmaydi.
        Harakat yo'q degani filtr uni to'sadi, buzilish imzosi ham
        o'zgarmaydi — ya'ni tizim butunlay sog'lom ko'rinadi va do'kon
        egasi buni faqat hisobotdagi bo'shliqdan biladi.
        """
        if digest != self._digest:
            self._digest = digest
            self._same_since = now
            self._frozen = False
            return None
        if self._same_since is None:
            self._same_since = now
            return None
        elapsed = now - self._same_since
        if self._frozen or elapsed < self.frozen_sec:
            return None
        self._frozen = True
        self._freezes += 1
        return TamperAlert(
            reason=FROZEN,
            score=1.0,
            duration_sec=round(elapsed, 1),
            kind=FREEZE,
        )

    def _anomaly(self, brightness: float, sharpness: float, signature: np.ndarray):
        if (
            self._brightness >= MIN_BASELINE_BRIGHTNESS
            and brightness < self._brightness * self.dark_ratio
        ):
            return DARK, 1.0 - brightness / max(self._brightness, 1.0)
        if (
            self._sharpness >= MIN_BASELINE_SHARPNESS
            and sharpness < self._sharpness * self.blur_ratio
        ):
            return BLURRED, 1.0 - sharpness / max(self._sharpness, 1.0)
        assert self._signature is not None
        difference = float(np.abs(signature - self._signature).mean())
        if difference >= self.change_threshold:
            return MOVED, min(1.0, difference)
        return None, 0.0

    def _learn(
        self, brightness: float, sharpness: float, signature: np.ndarray, *, weight: float
    ) -> None:
        weight = min(1.0, max(0.0, weight))
        if self._signature is None:
            self._brightness, self._sharpness, self._signature = brightness, sharpness, signature
            return
        self._brightness += weight * (brightness - self._brightness)
        self._sharpness += weight * (sharpness - self._sharpness)
        self._signature += weight * (signature - self._signature)

    # ── Holat ────────────────────────────────────────────────────────────

    @property
    def alerted(self) -> bool:
        return self._alerted

    @property
    def frozen(self) -> bool:
        return self._frozen

    def stats(self) -> Dict[str, Any]:
        return {
            "frames": self._frames,
            "alerts": self._alerts,
            "alerted": self._alerted,
            "freezes": self._freezes,
            "frozen": self._frozen,
            "brightness": round(self._brightness, 1),
            "sharpness": round(self._sharpness, 1),
        }
