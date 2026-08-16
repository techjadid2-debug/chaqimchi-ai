"""OpenVINO detektor adapteri — `person-detection-retail-0013`.

Nega aynan shu model:

* **Litsenziya Apache 2.0.**  Ultralytics YOLOv8 AGPL-3.0 — tijoriy SaaS uchun
  yaramaydi (butun serverning manba kodini ochish talabi).  Bu birinchi va
  eng qat'iy mezon: model litsenziyasi noto'g'ri bo'lsa mahsulot sotilmaydi.
* **2.3 GFLOPs** — YOLOv8n (8.7 GFLOPs) dan ~3.8 barobar yengil.  N100 iGPU
  uchun bu 8 kamera va 3 kamera orasidagi farq.
* **Retail uchun o'qitilgan**, AP 88.62%.

Ma'lum chegarasi: minimal odam bo'yi 1080p da 100 px, ya'ni 640×360
substreamda ~33 px.  Keng ombor ko'rinishida uzoqdagi odam tushib qoladi.
Shu sabab detektor `PersonDetector` Protocol ortida turadi va almashtiriladi.

Model chiqishi SSD formatida: `(1, 1, N, 7)`, har qatorda
`[image_id, label, conf, x_min, y_min, x_max, y_max]` — koordinatalar
**normallashtirilgan** (0..1).  Dekodlash sof mantiq, shuning uchun
OpenVINO o'rnatilmagan mashinada ham test qilinadi.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import numpy as np

#: Modelning rasmiy kirish o'lchami (balandlik, kenglik).
INPUT_HEIGHT = 320
INPUT_WIDTH = 544

#: SSD chiqishidagi ustunlar soni.
_ROW_WIDTH = 7


def decode_ssd_output(
    raw: Any,
    *,
    width: int,
    height: int,
    confidence: float,
) -> List[Dict[str, Any]]:
    """SSD chiqishini `PersonDetector` kontraktiga o'giradi.

    Chiqish `[{"bbox": [x1,y1,x2,y2], "score": float}, ...]` — piksellarda,
    mavjud `SceneAnalyzer` kutgani bilan bir xil.

    NMS kerak emas: model o'zi bostirilgan natija qaytaradi.
    """
    array = np.asarray(raw)
    flat = array.reshape(-1, _ROW_WIDTH) if array.size % _ROW_WIDTH == 0 else None
    if flat is None:
        return []

    detections: List[Dict[str, Any]] = []
    for row in flat:
        score = float(row[2])
        if score < confidence:
            continue
        # Model to'ldirish uchun `image_id = -1` bo'lgan bo'sh qatorlar
        # qaytaradi — ular haqiqiy deteksiya emas.
        if float(row[0]) < 0:
            continue
        x1 = float(row[3]) * width
        y1 = float(row[4]) * height
        x2 = float(row[5]) * width
        y2 = float(row[6]) * height
        # Ramka kadrdan chiqib ketishi mumkin; kesamiz va yaroqsizini tashlaymiz.
        x1, y1 = max(0.0, x1), max(0.0, y1)
        x2, y2 = min(float(width), x2), min(float(height), y2)
        if x2 <= x1 or y2 <= y1:
            continue
        detections.append({"bbox": [x1, y1, x2, y2], "score": score})
    return detections


class OpenVINOPersonDetector:
    """`person-detection-retail-0013` uchun adapter.

    OpenVINO importi ataylab konstruktor ichida: modul faqat qurilmada
    o'rnatiladi, ishlab chiqish mashinasida (macOS/Apple Silicon) esa yo'q.
    Import yuqorida bo'lsa butun `chaqimchi_ai` paketi shu mashinada
    ishlamay qolardi.
    """

    def __init__(
        self,
        model_path: Path,
        *,
        confidence: float = 0.5,
        device: str = "GPU",
        fallback_device: str = "CPU",
        **_ignored: Any,
    ) -> None:
        if not Path(model_path).is_file():
            raise FileNotFoundError(f"OpenVINO modeli topilmadi: {model_path}")
        try:
            from openvino import Core  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - qurilmaga xos bog'liqlik
            raise RuntimeError(
                "OpenVINO o'rnatilmagan: pip install -r requirements-retail.txt"
            ) from exc

        self.confidence = float(confidence)
        core = Core()
        model = core.read_model(str(model_path))
        available = set(core.available_devices)
        # iGPU bo'lmasa (yoki drayver yo'q bo'lsa) CPU'ga tushamiz — qurilma
        # ishlamay qolgandan ko'ra sekinroq ishlagani yaxshi.  Qaysi qurilmada
        # ketayotgani `device_in_use` da ko'rinadi va benchmarkda qayd etiladi.
        self.device_in_use = device if device in available else fallback_device
        self._compiled = self._compile(core, model, fallback_device)
        self._output = self._compiled.output(0)

    def _compile(self, core: Any, model: Any, fallback_device: str) -> Any:
        """Modelni kompilyatsiya qiladi, kerak bo'lsa CPU'ga tushadi.

        Nega `try` shart: `available_devices` da "GPU" turishi uni
        **ishlaydi** degani emas.  Eski Intel grafikasi (Haswell HD 4600
        va undan avvalgilar — OpenVINO Gen8/Broadwell dan boshlab
        qo'llab-quvvatlaydi) ro'yxatda ko'rinadi, lekin kompilyatsiya
        paytida yiqiladi.  Bu istisno ushlanmasa butun xizmat qulaydi va
        supervisor uni qayta-qayta ishga tushirib, do'kon nazoratsiz
        qolardi — sekin ishlagan CPU esa ishlaydi.
        """
        import logging

        logger = logging.getLogger(__name__)
        try:
            compiled = core.compile_model(model, self.device_in_use, self._hints())
            logger.info("Detektor qurilmasi: %s", self.device_in_use)
            return compiled
        except Exception as exc:  # noqa: BLE001 — OpenVINO turli istisno beradi
            if self.device_in_use == fallback_device:
                raise
            logger.warning(
                "%s da kompilyatsiya bo'lmadi (%s) — %s ga o'tildi",
                self.device_in_use,
                exc,
                fallback_device,
            )
            self.device_in_use = fallback_device
            return core.compile_model(model, fallback_device, self._hints())

    def _hints(self) -> Dict[str, Any]:
        """Kompilyatsiya ko'rsatmalari.

        CPU'da barcha yadroni inferensga berish noto'g'ri: o'sha
        protsessorda RTSP oqimlari ham dekodlanadi.  4 yadroli mashinada
        (masalan i5-4590) OpenVINO to'rttasini ham egallab olsa, kadr
        dekodlash kechikadi va tasvir "sinadi".  Bittasini dekodlashga
        qoldiramiz.
        """
        if self.device_in_use != "CPU":
            return {}
        import os

        cores = os.cpu_count() or 4
        return {
            "INFERENCE_NUM_THREADS": max(1, cores - 1),
            # Kechikish rejimi: bizga bitta kadrning tez qaytishi kerak,
            # navbat to'ldirish emas — har kamera ketma-ket so'raydi.
            "PERFORMANCE_HINT": "LATENCY",
        }

    def detect(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        height, width = frame.shape[:2]
        return decode_ssd_output(
            self._compiled(self.preprocess(frame))[self._output],
            width=width,
            height=height,
            confidence=self.confidence,
        )

    @staticmethod
    def preprocess(frame: np.ndarray) -> np.ndarray:
        """BGR kadrni model kutgan NCHW tensoriga o'giradi.

        Model BGR kutadi (Caffe'dan konvertatsiya qilingan), shuning uchun
        kanal tartibi almashtirilmaydi — bu ko'p uchraydigan jimgina xato.
        """
        import cv2

        resized = cv2.resize(frame, (INPUT_WIDTH, INPUT_HEIGHT), interpolation=cv2.INTER_LINEAR)
        return np.expand_dims(resized.transpose(2, 0, 1), axis=0).astype(np.float32)
