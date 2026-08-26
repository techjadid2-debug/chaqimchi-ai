"""Kirgan mijozning jinsi va yoshi (Lite tarif ichida, edge'da).

Do'kon egasining savoli: "mijozlarim kimlar?" — necha foiz ayol, qaysi
yosh guruhga mahsulot mo'ljallash kerak.  Bunga javob ikki mitti model
bilan chiqadi (ikkalasi Intel OMZ, Apache-2.0 — tijoratga ochiq, Face
ID'dagi litsenziya cheklovi YO'Q):

- face-detection-retail-0004  (300×300, 1.07 GFLOP) — odam ramkasining
  yuqori qismidan yuz topadi;
- age-gender-recognition-retail-0013 (62×62, 0.09 GFLOP) — yuzdan yosh
  va jins.

MAXFIYLIK: bu yerda hech qanday rasm saqlanmaydi va yuborilmaydi —
faqat {"jins", "yosh"} raqamlari hodisa metadatasiga yoziladi.  Yuz
TANILMAYDI (embedding yo'q) — bu shunchaki anonim statistika.

Chaqiruv joyi `SceneAnalyzer.analyze()` ichida — shunda broker byudjeti
sarflangan vaqtni o'zi hisobga oladi va bosim oshsa kadr tezligini
tushiradi.  Chaqiruv faqat kirish chizig'i kesilganda bo'ladi (kuniga
bir necha yuz marta), har kadrda emas.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from chaqimchi_ai.retail.detector_ov import decode_ssd_output

logger = logging.getLogger(__name__)

#: Yuz deteksiyasi ishonch chegarasi.
FACE_CONFIDENCE = 0.5
#: Kesilgan yuz eni bundan kichik bo'lsa yosh-jins ishonchsiz — tashlaymiz.
MIN_FACE_PIXELS = 32
#: Odam ramkasining yuqori qismi (bosh shu yerda bo'ladi).
HEAD_CROP_RATIO = 0.4


def head_crop_box(bbox: List[float], frame_width: int, frame_height: int) -> Optional[List[int]]:
    """Odam ramkasidan bosh qismini (yon chekkalar bilan) hisoblaydi."""
    try:
        x1, y1, x2, y2 = (float(value) for value in bbox)
    except (TypeError, ValueError):
        return None
    margin = (x2 - x1) * 0.1
    left = int(max(0.0, x1 - margin))
    right = int(min(float(frame_width), x2 + margin))
    top = int(max(0.0, y1))
    bottom = int(min(float(frame_height), y1 + max(1.0, (y2 - y1) * HEAD_CROP_RATIO)))
    if right - left < MIN_FACE_PIXELS or bottom - top < MIN_FACE_PIXELS:
        return None
    return [left, top, right, bottom]


def parse_age_gender(outputs: Dict[str, Any]) -> Dict[str, Any]:
    """age-gender-recognition-retail-0013 chiqishini o'qiydi.

    Chiqish nomlari proshivkaga qarab farq qilishi mumkin — shakl bo'yicha
    ajratamiz: (1,2,1,1) — [ayol, erkak] ehtimollari, (1,1,1,1) — yosh/100.
    """
    age = None
    gender = None
    for value in outputs.values():
        array = np.asarray(value).ravel()
        if array.size == 2:
            gender = "ayol" if float(array[0]) >= float(array[1]) else "erkak"
        elif array.size == 1:
            age = int(round(float(array[0]) * 100))
    if age is None or gender is None:
        return {}
    return {"jins": gender, "yosh": max(1, min(99, age))}


class DemographyEstimator:
    """Ikki OpenVINO modeli, bitta umumiy nusxa (hamma kamera uchun)."""

    def __init__(
        self,
        face_model_path: Path,
        age_gender_model_path: Path,
        *,
        device: str = "CPU",
    ) -> None:
        for path in (face_model_path, age_gender_model_path):
            if not Path(path).is_file():
                raise FileNotFoundError(f"Model topilmadi: {path}")
        # Import konstruktorda: openvino o'rnatilmagan muhitda modul
        # import bo'laveradi (testlar fake bilan ishlaydi).
        from openvino import Core

        core = Core()
        # Mitti modellarga 1 ta ip yetadi — asosiy detektor bilan
        # talashmasin (u cores-1 oladi).
        hints = {"INFERENCE_NUM_THREADS": 1, "PERFORMANCE_HINT": "LATENCY"}
        self._face = core.compile_model(core.read_model(str(face_model_path)), device, hints)
        self._age_gender = core.compile_model(
            core.read_model(str(age_gender_model_path)), device, hints
        )
        self._face_output = self._face.output(0)

    @staticmethod
    def _blob(image: Any, size: int) -> Any:
        import cv2

        resized = cv2.resize(image, (size, size))
        return np.expand_dims(resized.transpose(2, 0, 1), 0).astype(np.float32)

    def estimate(self, frame: Any, person_bbox: List[float]) -> Optional[Dict[str, Any]]:
        """Odam ramkasidan {"jins","yosh"} yoki None (yuz topilmadi)."""
        height, width = frame.shape[:2]
        box = head_crop_box(person_bbox, width, height)
        if box is None:
            return None
        left, top, right, bottom = box
        head = frame[top:bottom, left:right]

        faces = decode_ssd_output(
            self._face(self._blob(head, 300))[self._face_output],
            width=right - left,
            height=bottom - top,
            confidence=FACE_CONFIDENCE,
        )
        if not faces:
            return None
        best = max(faces, key=lambda item: item["score"])
        fx1, fy1, fx2, fy2 = (int(value) for value in best["bbox"])
        if fx2 - fx1 < MIN_FACE_PIXELS or fy2 - fy1 < MIN_FACE_PIXELS:
            return None
        face = head[fy1:fy2, fx1:fx2]

        outputs = self._age_gender(self._blob(face, 62))
        result = parse_age_gender(
            {str(index): value for index, value in enumerate(outputs.values())}
        )
        return result or None


def resolve_demography_paths(scene: Any, base_dir: Path) -> Optional[tuple[Path, Path]]:
    """Model yo'llarini hal qiladi; sozlanmagan bo'lsa None.

    Nisbiy yo'l `base_dir`ga nisbatan — LEKIN bu Windows'da tuzoq:
    xizmat `--base-dir` sifatida ProgramData oladi, modellar esa o'rnatish
    papkasida.  Shu sabab `config_store.default_config()` va `_heal()`
    yo'llarni ABSOLYUT yozadi; nisbiy yo'l faqat qo'lda tuzilgan dev
    configlarda qoladi.  Ajratilgan funksiya — bu qoidani testda
    qulflab qo'yish uchun.
    """
    face_path = getattr(scene, "face_model_path", None)
    age_path = getattr(scene, "age_gender_model_path", None)
    if not face_path or not age_path:
        return None
    return (
        base_dir / face_path if not Path(face_path).is_absolute() else Path(face_path),
        base_dir / age_path if not Path(age_path).is_absolute() else Path(age_path),
    )


#: Demografiya nega o'chiq — oxirgi qurilgan holatning sababi.
#:
#: Zanjir "jim" o'chishi ATAYLAB (modeli yo'q eski o'rnatishda butun
#: analitika yiqilmasligi kerak), lekin JIMLIK sababni ham yashirardi.
#: 2026-08-26 da jonli do'konda `demography_daily` butunlay nol edi va
#: "funksiya o'chiq", "model topilmadi" hamda "yuz topilmadi" —
#: uchalasi tashqaridan bir xil ko'rinardi: hech narsa.
LAST_OFF_REASON: Dict[str, Optional[str]] = {"value": None}


def build_demography_estimator(settings: Any, base_dir: Path) -> Optional[DemographyEstimator]:
    """Sozlamadan estimator quradi; model yo'q bo'lsa jim None.

    "Jim" ataylab: demografiya qo'shimcha qulaylik — modeli yo'q eski
    o'rnatishda butun zanjir yiqilmasligi kerak.  Lekin SABAB
    `LAST_OFF_REASON` ga yoziladi va heartbeat orqali panelga chiqadi.
    """
    scene = settings.scene
    if not getattr(scene, "demographics_enabled", False):
        LAST_OFF_REASON["value"] = "sozlamada o'chirilgan"
        return None
    resolved = resolve_demography_paths(scene, base_dir)
    if resolved is None:
        LAST_OFF_REASON["value"] = "model yo'li sozlanmagan"
        return None
    face_model, age_model = resolved
    try:
        estimator = DemographyEstimator(face_model, age_model)
    except (FileNotFoundError, ImportError, RuntimeError) as exc:
        # Yo'llar log'da ANIQ ko'rinadi: "yuklanmadi" degan umumiy satr
        # bilan qaysi yo'l noto'g'riligini dala sharoitida topib bo'lmasdi.
        logger.warning(
            "Demografiya modeli yuklanmadi — funksiya o'chiq (izlangan: %s, %s)",
            face_model,
            age_model,
            exc_info=True,
        )
        LAST_OFF_REASON["value"] = f"model yuklanmadi: {type(exc).__name__}"
        return None
    LAST_OFF_REASON["value"] = None
    return estimator
