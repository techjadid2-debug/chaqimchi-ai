"""Yuz tanish xizmati — cloud tomonda (yopiq pilot).

Qurilma yuzni **tanimaydi**: davomat kamerasidan odam tanasining yuqori
qismini crop qilib yuboradi, tanish shu yerda bo'ladi.  Zaif do'kon
kompyuteriga (i5-4590) og'ir model tushmaydi — arxivdagi lokal Face ID
to'plami aynan shu sababdan yopilgan edi.

Og'ir `insightface` paketi ataylab ishlatilmaydi: u slim Docker image'da
kompilyator talab qiladi va ~400 MB keraksiz bog'liqlik olib keladi.
Buning o'rniga buffalo_l to'plamining ikkita ONNX modeli to'g'ridan-to'g'ri
`onnxruntime` bilan yuritiladi:

- `det_10g.onnx` (SCRFD) — yuzni topish va 5 ta tayanch nuqta;
- `w600k_r50.onnx` (ArcFace) — 112×112 tekislangan yuzdan 512-o'lchamli
  embedding.

Modellar `scripts/fetch_face_models.py` bilan sha256 tekshiruvidan o'tib
o'rnatiladi.  MUHIM: bu modellar faqat tadqiqot litsenziyasida — xizmat
`require_attendance()` darvozasi ortida, sotuvga ochilmaydi.

Embedding diskda hech qachon ochiq yotmaydi: saqlashdan oldin Fernet
(`CHAQIMCHI_EMBEDDING_KEY`) bilan shifrlanadi.  Kalit yo'q — xizmat ishlamaydi
(fail-closed).
"""

from __future__ import annotations

import base64
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Tuple

try:  # pragma: no cover - kutubxonalar faqat cloud imagega o'rnatiladi
    import cv2
    import numpy as np
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]

try:  # pragma: no cover
    import onnxruntime
except ImportError:  # pragma: no cover
    onnxruntime = None  # type: ignore[assignment]

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

#: Modellar joyi.  Prod'da cloud_state volume ichida — konteyner read-only,
#: model esa katta (~180 MB), image'ga kirmaydi.
DEFAULT_MODEL_ROOT = "data/cloud/models/faces"

DETECTOR_FILE = "det_10g.onnx"
RECOGNIZER_FILE = "w600k_r50.onnx"


#: Kosinus o'xshashlik chegarasi.  0.4 — arxivdagi kalibrlangan qiymat
#: (config/sotqin.yaml compare_threshold); galereyadagi score'larga qarab
#: env orqali sozlanadi.
def match_threshold() -> float:
    try:
        return float(os.environ.get("CHAQIMCHI_FACE_MATCH_THRESHOLD", "0.4"))
    except ValueError:
        return 0.4


def model_root() -> Path:
    return Path(os.environ.get("CHAQIMCHI_FACE_MODEL_ROOT", DEFAULT_MODEL_ROOT))


#: ArcFace'ning 112×112 kadrdagi standart 5 nuqtasi (ko'zlar, burun, og'iz
#: burchaklari) — topilgan yuz shu holatga tekislanadi.
_ARCFACE_DST = [
    [38.2946, 51.6963],
    [73.5318, 51.5014],
    [56.0252, 71.7366],
    [41.5493, 92.3655],
    [70.7299, 92.2041],
]

_DET_INPUT = 640
_DET_SCORE_MIN = 0.5
_STRIDES = (8, 16, 32)


@dataclass
class FaceEmbedding:
    vector: Any  # np.ndarray (512,), normalangan
    det_score: float


# ── Embedding shifrlash ──────────────────────────────────────────────────


def resolve_embedding_key() -> Optional[bytes]:
    raw = os.environ.get("CHAQIMCHI_EMBEDDING_KEY", "").strip()
    return raw.encode("utf-8") if raw else None


def encrypt_embedding(vector: Any) -> str:
    key = resolve_embedding_key()
    if key is None:
        raise RuntimeError("CHAQIMCHI_EMBEDDING_KEY sozlanmagan")
    payload = np.asarray(vector, dtype=np.float32).tobytes()
    token = Fernet(key).encrypt(payload)
    return base64.b64encode(token).decode("ascii")


def decrypt_embedding(encoded: str) -> Any:
    key = resolve_embedding_key()
    if key is None:
        raise RuntimeError("CHAQIMCHI_EMBEDDING_KEY sozlanmagan")
    token = base64.b64decode(encoded.encode("ascii"))
    plain = Fernet(key).decrypt(token)
    return np.frombuffer(plain, dtype=np.float32)


# ── Xizmat ───────────────────────────────────────────────────────────────


class FaceService:
    """SCRFD + ArcFace, faqat CPU, sessiyalar dangasa yuklanadi."""

    def __init__(self, root: Optional[Path] = None, *, threads: int = 2) -> None:
        self.root = root or model_root()
        self.threads = threads
        self._lock = threading.Lock()
        self._detector: Optional[Any] = None
        self._recognizer: Optional[Any] = None

    def _session(self, filename: str) -> Any:
        path = self.root / filename
        if not path.is_file():
            raise FileNotFoundError(
                f"Model topilmadi: {path} (scripts/fetch_face_models.py ishga tushiring)"
            )
        options = onnxruntime.SessionOptions()
        # API bilan bitta jarayonda ishlaydi — uvicornni och qoldirmaslik
        # uchun ORT ip soni cheklanadi.
        options.intra_op_num_threads = self.threads
        options.inter_op_num_threads = 1
        return onnxruntime.InferenceSession(
            str(path), sess_options=options, providers=["CPUExecutionProvider"]
        )

    def _ensure_loaded(self) -> None:
        with self._lock:
            if self._detector is None:
                self._detector = self._session(DETECTOR_FILE)
            if self._recognizer is None:
                self._recognizer = self._session(RECOGNIZER_FILE)

    # ── Aniqlash (SCRFD det_10g) ─────────────────────────────────────

    def _detect(self, image: Any) -> Optional[Tuple[Any, float]]:
        """Eng katta yuzning 5 nuqtasi va ishonchi.  Yuz yo'q — None."""
        height, width = image.shape[:2]
        scale = _DET_INPUT / max(height, width)
        resized = cv2.resize(image, (round(width * scale), round(height * scale)))
        canvas = np.zeros((_DET_INPUT, _DET_INPUT, 3), dtype=np.uint8)
        canvas[: resized.shape[0], : resized.shape[1]] = resized

        blob = cv2.dnn.blobFromImage(
            canvas, 1.0 / 128.0, (_DET_INPUT, _DET_INPUT), (127.5, 127.5, 127.5), swapRB=True
        )
        outputs = self._detector.run(None, {self._detector.get_inputs()[0].name: blob})

        best_kps = None
        best_score = 0.0
        best_area = 0.0
        for index, stride in enumerate(_STRIDES):
            scores = outputs[index].ravel()
            bbox_preds = outputs[index + len(_STRIDES)] * stride
            kps_preds = outputs[index + 2 * len(_STRIDES)] * stride
            cells = _DET_INPUT // stride
            # Har katakda 2 ta anchor — markazlar takrorlanadi.
            centers = (
                np.stack(np.meshgrid(np.arange(cells), np.arange(cells)), axis=-1)
                .reshape(-1, 2)
                .astype(np.float32)
                * stride
            )
            centers = np.repeat(centers, 2, axis=0)
            keep = scores >= _DET_SCORE_MIN
            if not keep.any():
                continue
            for center, score, box, kps in zip(
                centers[keep], scores[keep], bbox_preds[keep], kps_preds[keep]
            ):
                cx, cy = float(center[0]), float(center[1])
                area = (box[0] + box[2]) * (box[1] + box[3])
                if area <= best_area:
                    continue
                best_area = float(area)
                best_score = float(score)
                points = np.empty((5, 2), dtype=np.float32)
                for point in range(5):
                    points[point, 0] = (cx + kps[2 * point]) / scale
                    points[point, 1] = (cy + kps[2 * point + 1]) / scale
                best_kps = points
        if best_kps is None:
            return None
        return best_kps, best_score

    # ── Embedding (ArcFace w600k_r50) ────────────────────────────────

    def _embed_aligned(self, aligned: Any) -> Any:
        blob = cv2.dnn.blobFromImage(
            aligned, 1.0 / 127.5, (112, 112), (127.5, 127.5, 127.5), swapRB=True
        )
        output = self._recognizer.run(None, {self._recognizer.get_inputs()[0].name: blob})[0]
        vector = output.ravel().astype(np.float32)
        norm = float(np.linalg.norm(vector))
        if norm == 0:  # pragma: no cover - modeldan nol vektor chiqmaydi
            raise ValueError("Embedding nol vektor")
        return vector / norm

    def embed_jpeg(self, data: bytes) -> Optional[FaceEmbedding]:
        """JPEG → yuz embeddingi.  Rasmda yuz topilmasa None."""
        self._ensure_loaded()
        image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return None
        found = self._detect(image)
        if found is None:
            return None
        keypoints, score = found
        transform, _ = cv2.estimateAffinePartial2D(
            keypoints, np.asarray(_ARCFACE_DST, dtype=np.float32)
        )
        if transform is None:
            return None
        aligned = cv2.warpAffine(image, transform, (112, 112))
        return FaceEmbedding(vector=self._embed_aligned(aligned), det_score=score)

    @staticmethod
    def match(
        vector: Any, candidates: List[Tuple[str, Any]], *, threshold: Optional[float] = None
    ) -> Optional[Tuple[str, float]]:
        """Eng yaqin xodim (kosinus).  Chegaradan past — None."""
        limit = match_threshold() if threshold is None else threshold
        best_id: Optional[str] = None
        best_score = limit
        for employee_id, candidate in candidates:
            score = float(np.dot(vector, candidate))
            if score >= best_score:
                best_score = score
                best_id = employee_id
        if best_id is None:
            return None
        return best_id, best_score


_service: Optional[FaceService] = None
_service_lock = threading.Lock()


def get_face_service() -> FaceService:
    global _service
    with _service_lock:
        if _service is None:
            _service = FaceService()
        return _service


def available() -> Tuple[bool, str]:
    """Xizmat holati — admin panel ko'rsatadi, endpointlar tekshiradi."""
    if np is None or cv2 is None:
        return False, "numpy/opencv o'rnatilmagan"
    if onnxruntime is None:
        return False, "onnxruntime o'rnatilmagan"
    if resolve_embedding_key() is None:
        return False, "CHAQIMCHI_EMBEDDING_KEY sozlanmagan"
    root = model_root()
    for filename in (DETECTOR_FILE, RECOGNIZER_FILE):
        if not (root / filename).is_file():
            return False, f"Model yo'q: {filename} (fetch_face_models.py)"
    return True, "tayyor"
