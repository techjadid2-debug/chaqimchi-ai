"""Bo'sh javon nazorati — modelsiz.

Nima uchun model yo'q.  Tayyor "empty shelf" modellarining aksariyati
Ultralytics YOLO asosida va u **AGPL** — ya'ni `buffalo_l` bilan bo'lgan
tuzoqning aynan o'zi: kod ishlaydi, sotib bo'lmaydi.  O'z modelimizni
o'qitish esa 200–500 ta belgilangan javon rasmini talab qiladi va uni
haqiqiy do'kondan yig'ish kerak.

Shuning uchun avval **arzon yo'l** sinaladi: qat'iy kamera + qat'iy javon
zonasida modelning keragi yo'q.

**O'lchov — piksel farqi emas, CHEKKA ZICHLIGI.**  To'la javon ko'p
chekka beradi: mahsulot chegaralari, yorliqlar, qadoqlar.  Bo'shagan
javon esa tekis yuza — chekka kam.  Piksel farqi yorug'lik o'zgarishida
darrov yolg'on signal berardi (kunduz/kechqurun, chiroq yoqilishi),
chekka zichligi esa yorug'likka ancha chidamli: soya qorayganda ham
mahsulot chegarasi chegaraligicha qoladi.

**Etalon o'z-o'zidan o'rganiladi.**  "Javon to'la" holatini mijozdan
so'rash kerak emas: kuzatilgan eng yuqori zichlik etalon bo'ladi va u
sekin pasayadi (do'kon assortimenti o'zgarishi mumkin).  Qayta ishga
tushganda etalon nolga qaytadi va qaytadan o'rganiladi — shu sabab
birinchi soatlarda signal chiqmaydi (`MIN_SAMPLES`).

**Mijoz javon oldida turgan paytda o'lchanmaydi.**  Odam kadrni yopadi
va zichlikni ham oshirishi, ham pasaytirishi mumkin — ikkalasi ham
yolg'on.  Bloklangan kadr shunchaki tashlab yuboriladi.

Cheklovlar ochiq aytiladi: kamera qimirlasa yoki javon butunlay qayta
joylashtirilsa etalon eskiradi va bir necha soat noto'g'ri ishlaydi.
Agar amalda yolg'on signal ko'p bo'lsa — model yo'liga o'tiladi va bu
bosqichda yo'qoladigan narsa bir necha kunlik ish, xolos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

#: Etalon shuncha o'lchovdan keyin ishonchli deb hisoblanadi.
#: Undan oldin signal chiqmaydi — qurilma endi yoqilgan do'kon
#: darrov "javon bo'sh" xabarini olmasin.
MIN_SAMPLES = 30

#: Etalon har o'lchovda shu koeffitsiyentga "unutadi".  Sekin: assortiment
#: o'zgarishiga moslashadi, lekin bitta bo'sh kadr etalonni tushirmaydi.
REFERENCE_DECAY = 0.9995

#: Zichlik hisoblanadigan eng kichik kesma (piksel).  Undan kichik zona
#: shovqinga aylanadi.
MIN_CROP_PIXELS = 24


def edge_density(crop: np.ndarray) -> float:
    """Kesmadagi chekka pikselining ulushi (0..1).

    Canny chegaralari qat'iy emas, medianadan hisoblanadi: bir xil javon
    yorug' va qorong'i kadrda bir xil natija bersin.
    """
    if crop.size == 0:
        return 0.0
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    median = float(np.median(gray))
    low = max(0.0, 0.66 * median)
    high = min(255.0, 1.33 * median)
    edges = cv2.Canny(gray, low, high)
    return float(np.count_nonzero(edges)) / float(edges.size)


def crop_polygon(frame: np.ndarray, polygon: Sequence[Tuple[float, float]]) -> np.ndarray:
    """Normallashtirilgan poligonning to'g'riburchak kesmasi.

    Poligonning o'zi bo'yicha maska QO'YILMAYDI: javon to'rtburchakka
    yaqin bo'ladi, maska esa chekka hisobiga sun'iy chegara qo'shib,
    zichlikni oshirib yuborardi.
    """
    height, width = frame.shape[:2]
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    left = max(0, int(min(xs) * width))
    right = min(width, int(max(xs) * width))
    top = max(0, int(min(ys) * height))
    bottom = min(height, int(max(ys) * height))
    if right - left < MIN_CROP_PIXELS or bottom - top < MIN_CROP_PIXELS:
        return np.empty((0, 0), dtype=np.uint8)
    return frame[top:bottom, left:right]


@dataclass
class ShelfState:
    """Bitta javon zonasining o'rganilgan holati."""

    reference: float = 0.0
    samples: int = 0
    low_since: Optional[float] = None
    alerted: bool = False
    last_ratio: float = 1.0


@dataclass
class ShelfWatcher:
    """Javon zonalarini kuzatadi va bo'shaganini aytadi.

    Holat XOTIRADA: qayta ishga tushganda etalon qaytadan o'rganiladi.
    Diskka yozish qo'shilsa qurilma har daqiqada yozib turardi va
    foydasi shunga arzimaydi.
    """

    empty_ratio: float = 0.45
    empty_sec: float = 900.0
    states: Dict[str, ShelfState] = field(default_factory=dict)

    def observe(
        self,
        zone_name: str,
        crop: np.ndarray,
        *,
        blocked: bool,
        now: float,
    ) -> Optional[Dict[str, float]]:
        """Bitta o'lchov.  Javon bo'shaganda tavsif qaytaradi, aks holda None."""
        state = self.states.setdefault(zone_name, ShelfState())
        if blocked or crop.size == 0:
            # Mijoz javon oldida yoki zona juda kichik — o'lchov ham,
            # etalon ham o'zgarmaydi.  Vaqt hisobi ham to'xtaydi: odam
            # turgan daqiqalar "javon bo'sh turdi" deb hisoblanmasin.
            state.low_since = None
            return None

        density = edge_density(crop)
        state.samples += 1
        state.reference = max(density, state.reference * REFERENCE_DECAY)
        if state.reference <= 0:
            return None

        ratio = density / state.reference
        state.last_ratio = ratio

        if state.samples < MIN_SAMPLES:
            return None

        if ratio >= self.empty_ratio:
            state.low_since = None
            state.alerted = False
            return None

        if state.low_since is None:
            state.low_since = now
            return None
        if now - state.low_since < self.empty_sec or state.alerted:
            return None

        state.alerted = True
        return {
            "zone": zone_name,
            "ratio": round(ratio, 3),
            "empty_sec": round(now - state.low_since, 1),
        }

    def zones_in_view(self, zone_names: List[str]) -> List[str]:
        """Faqat o'rganib bo'lingan zonalar — panel uchun."""
        return [
            name
            for name in zone_names
            if self.states.get(name) and self.states[name].samples >= MIN_SAMPLES
        ]
