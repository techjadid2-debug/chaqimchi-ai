"""Yuz tanish xizmati — cloud tomonda.

Qurilma yuzni **tanimaydi**: davomat kamerasidan odam tanasining yuqori
qismini crop qilib yuboradi, tanish shu yerda bo'ladi.  Zaif do'kon
kompyuteriga (i5-4590) og'ir model tushmaydi — arxivdagi lokal Face ID
to'plami aynan shu sababdan yopilgan edi.

**Modellar Apache-2.0 (2026-08-21).**  Bungacha bu yerda InsightFace
`buffalo_l` (SCRFD + ArcFace) turardi va u faqat **tadqiqot
litsenziyasida** edi — ya'ni davomatni pulli tarif ichida sotish huquqiy
risk edi va butun xizmat `require_attendance()` darvozasi ortida
qulflanib turardi.  Endi uchala model ham OpenVINO Open Model Zoo'dan,
tijoratga ochiq:

- `face-detection-retail-0005` — yuzni topish (1×3×300×300 BGR →
  SSD 1×1×200×7);
- `landmarks-regression-retail-0009` — 5 tayanch nuqta (1×3×48×48 BGR →
  1×10), yuzni tekislash uchun;
- `face-reidentification-retail-0095` — 128×128 tekislangan yuzdan
  **256 o'lchamli** embedding.

Uchtaga bo'lingani ataylab emas — OMZ'da yuz topish va nuqta topish
alohida modellar.  SCRFD ikkalasini birga qilardi, lekin litsenziyasi
bilan birga.

`onnxruntime` o'rniga **OpenVINO Runtime**: OMZ'ning `retail-*` modellari
faqat IR formatida (.xml + .bin) tarqatiladi va ONNX'ga o'girib
bo'lmaydi.  Qurilma tomonida OpenVINO allaqachon ishlatiladi, ya'ni yangi
begona bog'liqlik emas.

Modellar `scripts/fetch_face_models.py` bilan sha256 tekshiruvidan o'tib
o'rnatiladi.

Embedding diskda hech qachon ochiq yotmaydi: saqlashdan oldin Fernet
(`CHAQIMCHI_EMBEDDING_KEY`) bilan shifrlanadi.  Kalit yo'q — xizmat
ishlamaydi (fail-closed).
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
    import openvino as ov
except ImportError:  # pragma: no cover
    ov = None  # type: ignore[assignment]

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

#: Modellar joyi.  Prod'da cloud_state volume ichida — konteyner read-only,
#: modellar esa image'ga kirmaydi.
DEFAULT_MODEL_ROOT = "data/cloud/models/faces"

DETECTOR_MODEL = "face-detection-retail-0005"
LANDMARKS_MODEL = "landmarks-regression-retail-0009"
RECOGNIZER_MODEL = "face-reidentification-retail-0095"

#: Model fayllari — har ikkalasi ham kerak (IR = tuzilma + og'irliklar).
MODEL_FILES = tuple(
    f"{name}.{ext}"
    for name in (DETECTOR_MODEL, LANDMARKS_MODEL, RECOGNIZER_MODEL)
    for ext in ("xml", "bin")
)

#: `face-reidentification-retail-0095` chiqaradigan vektor o'lchami.
#:
#: Bazada saqlanadi (`employee_faces.embedding_dim`) va moslashda
#: tekshiriladi: eski ArcFace yozuvlari **512** o'lchamli va ular bilan
#: skalyar ko'paytma umuman hisoblanmaydi.  Bir xil raqamlar deb
#: taqqoslash o'rniga ular jimgina chetlab o'tiladi va xodim "tanilmadi"
#: bo'lib qoladi — model almashgach rasmlar qayta hisoblanishi kerak
#: (`scripts/reembed_faces.py`).
EMBEDDING_DIM = 256

#: Eski (arxiv) model o'lchami — faqat aniqlash va ogohlantirish uchun.
LEGACY_EMBEDDING_DIM = 512

#: Modellar tijoratga ochiqmi.
#:
#: Bu env sozlamasi EMAS va ataylab: litsenziya — kodda qaysi model
#: yuklanishiga bog'liq fakt, sozlamaga bog'liq tanlov emas.  Ilgari
#: `CHAQIMCHI_FACE_MODEL_LICENSED` degan bayroq bor edi va uni
#: production'da qo'yib qo'yish tadqiqot litsenziyasidagi modelni
#: "tijoriy" qilib ko'rsatib qo'yardi.
#:
#: Uchala model ham OpenVINO Open Model Zoo, Apache-2.0 —
#: `models/faces_manifest.json` da URL va sha256 bilan qayd etilgan.
MODELS_LICENSED_FOR_COMMERCIAL_USE = True


def match_threshold() -> float:
    """Kosinus o'xshashlik chegarasi.

    OMZ demo'sining standarti 0.7 (`--t_id 0.3` kosinus MASOFA).  Bizda
    **0.6** — sabab o'lchangan:

        boshqa odam                       0.01
        bir xil odam, yorug'lik o'zgargan 0.95
        bir xil odam, xira rasm           0.74
        bir xil odam, yarim o'lchamda     0.67
        bir xil odam, 8 daraja burilgan   0.94

    Do'kon kamerasidan kelgan crop aynan "kichik va xira" toifasida —
    0.7 da bunday kadr rad etilardi va xodim "tanilmadi" bo'lib qolardi.
    Boshqa odam bilan farq (0.01 va 0.67) shu qadar kattaki, 0.6 ga
    tushirish yolg'on moslashni oshirmaydi.

    Eski ArcFace uchun 0.4 turardi — modellar boshqacha, chegara
    ko'chirilmaydi.

    Sotuvga chiqarishdan oldin bu raqam HAQIQIY do'kon kadrlarida qayta
    o'lchanishi kerak: `scripts/calibrate_face_threshold.py`.
    """
    try:
        return float(os.environ.get("CHAQIMCHI_FACE_MATCH_THRESHOLD", "0.6"))
    except ValueError:
        return 0.6


def model_root() -> Path:
    return Path(os.environ.get("CHAQIMCHI_FACE_MODEL_ROOT", DEFAULT_MODEL_ROOT))


#: Tekislangan 128×128 kadrdagi tayanch nuqtalar (ko'zlar, burun, og'iz
#: burchaklari), OMZ demo'sidagi qiymatlar — 96×112 to'rida berilgan va
#: normallashtirilgan.  Topilgan yuz shu holatga burab-cho'zib keltiriladi.
_REFERENCE_LANDMARKS = [
    (30.2946 / 96, 51.6963 / 112),
    (65.5318 / 96, 51.5014 / 112),
    (48.0252 / 96, 71.7366 / 112),
    (33.5493 / 96, 92.3655 / 112),
    (62.7299 / 96, 92.2041 / 112),
]

_DET_INPUT = 300
_DET_SCORE_MIN = 0.5
_LANDMARK_INPUT = 48
_ALIGNED_SIZE = 128


@dataclass
class FaceEmbedding:
    vector: Any  # np.ndarray (256,), normalangan
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
    """Yuz topish → tayanch nuqta → tekislash → embedding.  Faqat CPU."""

    #: Bazaga yoziladigan o'lcham.  Xizmat almashtirilganda (test
    #: dublyori ham) shu maydon orqali bilinadi.
    embedding_dim = EMBEDDING_DIM

    def __init__(self, root: Optional[Path] = None, *, threads: int = 2) -> None:
        self.root = root or model_root()
        self.threads = threads
        self._lock = threading.Lock()
        # CompiledModel ning `__call__` yo'li bitta InferRequest'ni qayta
        # ishlatadi. API endpointlari esa `asyncio.to_thread()` orqali bir
        # vaqtning o'zida kelishi mumkin; shunda OpenVINO "Infer Request is
        # busy" deb, ayrim davomat kadrlarini tashlab yuborardi. Modellarni
        # yuklash locki bunga yetmaydi — butun inferens zanjiri ketma-ket
        # bo'lishi shart. Davomat kamerasi o'zi cooldown bilan ishlaydi,
        # shuning uchun bitta CPU worker V1 uchun yetarli va ishonchli.
        self._inference_lock = threading.Lock()
        self._core: Optional[Any] = None
        self._detector: Optional[Any] = None
        self._landmarks: Optional[Any] = None
        self._recognizer: Optional[Any] = None

    def _compile(self, name: str) -> Any:
        path = self.root / f"{name}.xml"
        if not path.is_file():
            raise FileNotFoundError(
                f"Model topilmadi: {path} (scripts/fetch_face_models.py ishga tushiring)"
            )
        # API bilan bitta jarayonda ishlaydi — uvicornni och qoldirmaslik
        # uchun ip soni cheklanadi.
        return self._core.compile_model(
            str(path),
            "CPU",
            {"INFERENCE_NUM_THREADS": self.threads, "NUM_STREAMS": 1},
        )

    def _ensure_loaded(self) -> None:
        with self._lock:
            if self._core is None:
                self._core = ov.Core()
            if self._detector is None:
                self._detector = self._compile(DETECTOR_MODEL)
            if self._landmarks is None:
                self._landmarks = self._compile(LANDMARKS_MODEL)
            if self._recognizer is None:
                self._recognizer = self._compile(RECOGNIZER_MODEL)

    @staticmethod
    def _blob(image: Any, size: int) -> Any:
        """BGR rasm → 1×3×size×size.

        OMZ `retail-*` modellari xom BGR 0..255 kutadi: o'rtacha ayirish
        ham, masshtablash ham yo'q.  (ArcFace'da bo'lgan `1/127.5` shu
        yerda XATO bo'lardi.)
        """
        resized = cv2.resize(image, (size, size), interpolation=cv2.INTER_LINEAR)
        return resized.transpose(2, 0, 1)[None].astype(np.float32)

    # ── Yuzni topish ─────────────────────────────────────────────────

    def _detect(self, image: Any) -> Optional[Tuple[Any, float]]:
        """Eng katta yuzning to'rtburchagi va ishonchi.  Yuz yo'q — None."""
        height, width = image.shape[:2]
        outputs = self._detector([self._blob(image, _DET_INPUT)])
        detections = next(iter(outputs.values())).reshape(-1, 7)

        best_box = None
        best_score = 0.0
        best_area = 0.0
        for _image_id, _label, confidence, x_min, y_min, x_max, y_max in detections:
            if confidence < _DET_SCORE_MIN:
                continue
            # Koordinatalar 0..1 — kadr chegarasidan chiqib ketmasin.
            left = max(0.0, float(x_min)) * width
            top = max(0.0, float(y_min)) * height
            right = min(1.0, float(x_max)) * width
            bottom = min(1.0, float(y_max)) * height
            area = (right - left) * (bottom - top)
            # Eng KATTA yuz — kadrda tasodifan ko'ringan uzoqdagi mijoz
            # emas, kameraga kelgan xodim tanilishi kerak.
            if area <= best_area or area <= 0:
                continue
            best_area = area
            best_score = float(confidence)
            best_box = (left, top, right, bottom)
        if best_box is None:
            return None
        return best_box, best_score

    # ── Tayanch nuqtalar ─────────────────────────────────────────────

    def _keypoints(self, image: Any, box: Tuple[float, float, float, float]) -> Optional[Any]:
        """Yuz to'rtburchagi ichidagi 5 nuqta, butun kadr koordinatasida."""
        left, top, right, bottom = (int(round(v)) for v in box)
        left, top = max(0, left), max(0, top)
        right = min(image.shape[1], right)
        bottom = min(image.shape[0], bottom)
        if right - left < 2 or bottom - top < 2:
            return None
        crop = image[top:bottom, left:right]

        outputs = self._landmarks([self._blob(crop, _LANDMARK_INPUT)])
        raw = next(iter(outputs.values())).ravel()
        if raw.size < 10:  # pragma: no cover - model doim 10 ta son beradi
            return None

        # Model crop ICHIDA normallashtirilgan qiymat beradi — butun
        # kadrga qaytariladi, aks holda tekislash matritsasi noto'g'ri
        # chiqadi va yuz qiyshiq keladi.
        points = np.empty((5, 2), dtype=np.float32)
        for index in range(5):
            points[index, 0] = left + float(raw[2 * index]) * (right - left)
            points[index, 1] = top + float(raw[2 * index + 1]) * (bottom - top)
        return points

    # ── Embedding ────────────────────────────────────────────────────

    def _embed_aligned(self, aligned: Any) -> Any:
        outputs = self._recognizer([self._blob(aligned, _ALIGNED_SIZE)])
        vector = next(iter(outputs.values())).ravel().astype(np.float32)
        norm = float(np.linalg.norm(vector))
        if norm == 0:  # pragma: no cover - modeldan nol vektor chiqmaydi
            raise ValueError("Embedding nol vektor")
        return vector / norm

    def embed_jpeg(self, data: bytes) -> Optional[FaceEmbedding]:
        """Rasm baytlari → yuz embeddingi.  Rasmda yuz topilmasa None."""
        self._ensure_loaded()
        image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return None
        with self._inference_lock:
            found = self._detect(image)
            if found is None:
                return None
            box, score = found
            keypoints = self._keypoints(image, box)
            if keypoints is None:
                return None

            destination = np.asarray(_REFERENCE_LANDMARKS, dtype=np.float32) * _ALIGNED_SIZE
            transform, _ = cv2.estimateAffinePartial2D(keypoints, destination)
            if transform is None:
                return None
            aligned = cv2.warpAffine(image, transform, (_ALIGNED_SIZE, _ALIGNED_SIZE))
            return FaceEmbedding(vector=self._embed_aligned(aligned), det_score=score)

    @staticmethod
    def match(
        vector: Any, candidates: List[Tuple[str, Any]], *, threshold: Optional[float] = None
    ) -> Optional[Tuple[str, float]]:
        """Eng yaqin xodim (kosinus).  Chegaradan past — None."""
        limit = match_threshold() if threshold is None else threshold
        probe = np.asarray(vector, dtype=np.float32).ravel()
        best_id: Optional[str] = None
        best_score = limit
        skipped = 0
        for employee_id, candidate in candidates:
            gallery = np.asarray(candidate, dtype=np.float32).ravel()
            # O'lchami boshqa yozuv — eski modeldan qolgan.  Skalyar
            # ko'paytma xato ko'taradi va butun moslash to'xtardi;
            # kesib qo'yish esa MA'NOSIZ raqam beradi.  Chetlab o'tamiz.
            if gallery.shape != probe.shape:
                skipped += 1
                continue
            score = float(np.dot(probe, gallery))
            if score >= best_score:
                best_score = score
                best_id = employee_id
        if skipped:
            logger.warning(
                "%d ta embedding eski modeldan — qayta hisoblanishi kerak "
                "(scripts/reembed_faces.py)",
                skipped,
            )
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


def current_embedding_dim() -> int:
    """Bazaga yoziladigan o'lcham.

    Xizmatdan so'raladi, doimiydan emas: testda dublyor turadi va u
    boshqa o'lcham berishi mumkin.
    """
    return int(getattr(get_face_service(), "embedding_dim", EMBEDDING_DIM))


def available() -> Tuple[bool, str]:
    """Xizmat holati — admin panel ko'rsatadi, endpointlar tekshiradi."""
    if np is None or cv2 is None:
        return False, "numpy/opencv o'rnatilmagan"
    if ov is None:
        return False, "openvino o'rnatilmagan"
    if resolve_embedding_key() is None:
        return False, "CHAQIMCHI_EMBEDDING_KEY sozlanmagan"
    root = model_root()
    for filename in MODEL_FILES:
        if not (root / filename).is_file():
            return False, f"Model yo'q: {filename} (fetch_face_models.py)"
    return True, "tayyor"
