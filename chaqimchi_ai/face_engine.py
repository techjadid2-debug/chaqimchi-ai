"""
Chaqimchi AI — yuzni tanish yadrosi (Face Recognition Core).

Buffalo_l model to‘plami: SCRFD aniqlash + ArcFace 512-o‘lchamli embedding.
Apple M3 uchun ONNX Runtime CoreML provayderi orqali tezlashtirish.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional, Sequence, Tuple, Union

import cv2
import numpy as np

from chaqimchi_ai import image_util, similarity
from chaqimchi_ai.exceptions import ModelLoadError
from chaqimchi_ai.roi import RoiConfig, apply_roi

logger = logging.getLogger(__name__)

try:
    from insightface.app import FaceAnalysis
    from insightface.utils import face_align
except ImportError as exc:  # pragma: no cover - import guard
    FaceAnalysis = None  # type: ignore[misc, assignment]
    face_align = None  # type: ignore[misc, assignment]
    _INSIGHTFACE_ERR = exc
else:
    _INSIGHTFACE_ERR = None

try:
    import onnxruntime as ort
except ImportError:  # pragma: no cover
    ort = None  # type: ignore[assignment]


def _default_onnx_providers() -> List[Union[str, Tuple[str, Dict[str, Any]]]]:
    """
    Apple Silicon (M3) uchun CoreML, keyin CPU.
    CoreML mavjud bo‘lmasa, avtomatik ravishda CPU ishlatiladi.
    """
    if ort is None:
        return ["CPUExecutionProvider"]
    available = set(ort.get_available_providers())
    providers: List[Union[str, Tuple[str, Dict[str, Any]]]] = []
    if "CoreMLExecutionProvider" in available:
        # M3 Neural Engine va GPU yo‘nalishlari ONNX build orqali avtomatik tanlanadi
        providers.append("CoreMLExecutionProvider")
    providers.append("CPUExecutionProvider")
    return providers


@dataclass
class FaceCompareResult:
    """Cosine o‘xshashlik natijasi."""

    indices: np.ndarray
    scores: np.ndarray
    matched_mask: np.ndarray

    def as_list(self) -> List[Dict[str, Union[int, float, bool]]]:
        """Python ro‘yxatiga aylantirish (API / JSON uchun qulay)."""
        out: List[Dict[str, Union[int, float, bool]]] = []
        for i, (s, m) in enumerate(zip(self.scores.tolist(), self.matched_mask.tolist())):
            out.append({"index": i, "score": float(s), "matched": bool(m)})
        return out


@dataclass
class VideoFrameResult:
    """Video oqimidan bitta freym natijasi."""

    frame_index: int
    skipped: bool
    faces: List[Dict[str, Any]] = field(default_factory=list)
    inference_ms: float = 0.0
    total_ms: float = 0.0
    error: Optional[str] = None
    frame: Optional[np.ndarray] = None


class FaceEngine:
    """
    Modellarni yuklash, inferens va vide oqimini boshqarish.

    - SCRFD (buffalo_l) orqali yuz aniqlash
    - ArcFace uchun norm_crop (alignment) + 512 embedding
    - CoreMLExecutionProvider (mavjud bo‘lsa)
    """

    def __init__(
        self,
        model_name: str = "buffalo_l",
        det_size: Tuple[int, int] = (640, 640),
        preprocess_max_side: int = 1024,
        onnx_providers: Optional[Sequence[Union[str, Tuple[str, Dict[str, Any]]]]] = None,
        ctx_id: int = -1,
        roi: Optional[RoiConfig] = None,
        model_root: Optional[Path] = None,
    ) -> None:
        if FaceAnalysis is None or face_align is None:
            raise ImportError(
                "insightface o‘rnatilmagan. `pip install -r requirements.txt` ni bajaring."
            ) from _INSIGHTFACE_ERR

        self.model_name = model_name
        self.det_size = det_size
        self._preprocess_max_side = int(preprocess_max_side)
        self._roi = roi
        self.ctx_id = ctx_id
        self.model_root = model_root
        self._providers: List[Union[str, Tuple[str, Dict[str, Any]]]] = (
            list(onnx_providers) if onnx_providers is not None else _default_onnx_providers()
        )

        logger.info("FaceEngine: model=%s, providers=%s", model_name, self._providers)

        # Faqat deteksiya va tanish — boshqa modullarni o‘chirib, tezlikni oshiramiz
        app_kwargs: Dict[str, Any] = {
            "name": model_name,
            "allowed_modules": ["detection", "recognition"],
            "providers": self._providers,
        }
        if model_root is not None:
            app_kwargs["root"] = str(model_root)
        self._app = FaceAnalysis(**app_kwargs)
        self._app.prepare(ctx_id=self.ctx_id, det_size=self.det_size)

        self._rec_model = self._app.models.get("recognition")
        if self._rec_model is None:
            raise ModelLoadError("Recognition modeli topilmadi (buffalo_l konfiguratsiyasi).")

    @property
    def providers(self) -> List[Union[str, Tuple[str, Dict[str, Any]]]]:
        return list(self._providers)

    @property
    def recognition_ready(self) -> bool:
        return self._rec_model is not None

    def preprocess_image(self, image_bgr: np.ndarray, max_side: Optional[int] = None) -> np.ndarray:
        """
        BGR tasvirni tayyorlash: uzoq tomonni cheklash + uint8.

        Args:
            image_bgr: OpenCV BGR formatidagi numpy massiv.
            max_side: Agar berilsa, shu qiymat ishlatiladi; aks holda konstruktordagi `preprocess_max_side`.
        """
        if image_bgr is None or image_bgr.size == 0:
            raise ValueError("Bo‘sh tasvir (preprocess_image).")

        work = image_bgr
        if self._roi is not None and self._roi.enabled:
            work = apply_roi(work, self._roi)

        limit = self._preprocess_max_side if max_side is None else int(max_side)
        out = image_util.resize_bgr_max_side(work, limit)
        if out is not image_bgr:
            nh, nw = out.shape[:2]
            logger.debug("preprocess_image: %sx%s -> %sx%s", image_bgr.shape[1], image_bgr.shape[0], nw, nh)
        return out

    def _aligned_crop(self, image_bgr: np.ndarray, kps: np.ndarray) -> np.ndarray:
        """ArcFace uchun standart 112x112 norm_crop (alignment)."""
        return face_align.norm_crop(image_bgr, landmark=kps, image_size=112, mode="arcface")

    def extract_embeddings(self, image_bgr: np.ndarray) -> Tuple[List[np.ndarray], List[np.ndarray]]:
        """
        Tasvirdan barcha yuzlar uchun 512-o‘lchamli embeddinglar.

        Returns:
            (embeddings, keypoints_list) — har bir yuz uchun L2-normalizatsiya qilingan vektor.
        """
        t0 = time.perf_counter()
        img = self.preprocess_image(image_bgr)
        faces = self._app.get(img)
        det_ms = (time.perf_counter() - t0) * 1000.0
        logger.debug("extract_embeddings: det+parse %.2f ms, faces=%d", det_ms, len(faces))

        embeddings: List[np.ndarray] = []
        kps_list: List[np.ndarray] = []

        for face in faces:
            t1 = time.perf_counter()
            aimg = self._aligned_crop(img, face.kps)
            feat = self._rec_model.get_feat(aimg)
            rec_ms = (time.perf_counter() - t1) * 1000.0
            vec = feat.flatten().astype(np.float32, copy=False)
            n = float(np.linalg.norm(vec) + 1e-8)
            vec = vec / n
            embeddings.append(vec)
            kps_list.append(face.kps.copy())
            logger.debug("extract_embeddings: rec %.2f ms (aligned)", rec_ms)

        return embeddings, kps_list

    def extract_primary_embedding(self, image_bgr: np.ndarray) -> Optional[np.ndarray]:
        """Eng ishonchli (det_score eng yuqori) yuzning embeddingi."""
        img = self.preprocess_image(image_bgr)
        faces = self._app.get(img)
        if not faces:
            return None
        best = max(faces, key=lambda f: float(f.det_score))
        aimg = self._aligned_crop(img, best.kps)
        feat = self._rec_model.get_feat(aimg)
        vec = feat.flatten().astype(np.float32, copy=False)
        vec = vec / (float(np.linalg.norm(vec)) + 1e-8)
        return vec

    def compare_faces(
        self,
        source_embedding: np.ndarray,
        target_embeddings_list: Sequence[np.ndarray],
        threshold: float = 0.4,
    ) -> FaceCompareResult:
        """
        Cosine o‘xshashlik: vektorlar L2-normalizatsiya qilingan deb taxlanadi, shuning uchun skalyar ko‘paytma yetarli.

        Args:
            source_embedding: (512,) yoki (1, 512)
            target_embeddings_list: Har bir (512,) bo‘lgan ro‘yxat
            threshold: minimal o‘xshashlik (cosine) chegara

        Returns:
            FaceCompareResult — indekslar, ballar, mos kelish maskasi
        """
        indices, scores, matched = similarity.cosine_compare_arrays(
            source_embedding, target_embeddings_list, threshold
        )
        return FaceCompareResult(indices=indices, scores=scores, matched_mask=matched)

    def _process_frame_sync(self, frame_bgr: np.ndarray) -> Tuple[List[Dict[str, Any]], float]:
        """Bitta freymni sinxron inferens (executor ichida chaqiriladi)."""
        t0 = time.perf_counter()
        img = self.preprocess_image(frame_bgr)
        faces = self._app.get(img)
        out_faces: List[Dict[str, Any]] = []
        for face in faces:
            t_rec = time.perf_counter()
            aimg = self._aligned_crop(img, face.kps)
            feat = self._rec_model.get_feat(aimg)
            rec_ms = (time.perf_counter() - t_rec) * 1000.0
            vec = feat.flatten().astype(np.float32, copy=False)
            vec = vec / (float(np.linalg.norm(vec)) + 1e-8)
            out_faces.append(
                {
                    "bbox": face.bbox.astype(float).tolist(),
                    "det_score": float(face.det_score),
                    "embedding": vec,
                    "rec_infer_ms": rec_ms,
                }
            )
        total_ms = (time.perf_counter() - t0) * 1000.0
        logger.info(
            "inferens: %.2f ms | yuzlar: %d | det_size=%s",
            total_ms,
            len(out_faces),
            self.det_size,
        )
        return out_faces, total_ms

    def analyze_frame(self, image_bgr: np.ndarray) -> Tuple[List[Dict[str, Any]], float]:
        """
        Bitta BGR freymni tahlil qilish (veb-kamera / API uchun ochiq interfeys).

        Returns:
            (yuzlar_roʻyxati, inferens_ms) — har bir elementda bbox, det_score, embedding.
        """
        return self._process_frame_sync(image_bgr)

    async def process_video_stream(
        self,
        video_source: Union[str, int],
        frame_skip: int = 2,
        max_frames: Optional[int] = None,
        queue_size: int = 1,
    ) -> AsyncGenerator[VideoFrameResult, None]:
        """
        OpenCV orqali video oqimini async generator sifatida qayta ishlash.

        frame_skip: har N ta freymdan 1 tasini inferens qilish (1 = har doim).
        Bloklanmaslik uchun o‘qish va inferens `run_in_executor` orqali fon potokda.

        Args:
            video_source: fayl yo‘li yoki kamera indeksi (masalan, 0).
            frame_skip: N (har N freymdan bittasi).
            max_frames: cheklash (None = cheksiz).
            queue_size: kelajakda kengaytirish uchun rezerv (hozir ishlatilmaydi).
        """
        _ = queue_size  # API barqarorligi uchun saqlanadi
        if frame_skip < 1:
            raise ValueError("frame_skip >= 1 bo‘lishi kerak.")

        loop = asyncio.get_running_loop()

        def _open_capture() -> cv2.VideoCapture:
            cap_local = cv2.VideoCapture(video_source)
            if not cap_local.isOpened():
                raise RuntimeError(f"Video manbasi ochilmadi: {video_source}")
            return cap_local

        cap = await loop.run_in_executor(None, _open_capture)
        frame_index = 0
        processed = 0

        try:
            while True:
                if max_frames is not None and processed >= max_frames:
                    break

                t_read = time.perf_counter()
                ret, frame = await loop.run_in_executor(None, cap.read)
                read_ms = (time.perf_counter() - t_read) * 1000.0
                if not ret or frame is None:
                    logger.info("Video oqimi tugadi yoki freym o‘qilmadi (idx=%d).", frame_index)
                    break

                should_infer = frame_index % frame_skip == 0
                if not should_infer:
                    logger.debug(
                        "freym o‘tkazildi idx=%d (frame_skip=%d), read=%.2f ms",
                        frame_index,
                        frame_skip,
                        read_ms,
                    )
                    # Scene analytics motion gate'i yuz inferensi o'tkazib yuborilgan
                    # freymlarni ham ko'rishi kerak.
                    yield VideoFrameResult(
                        frame_index=frame_index,
                        skipped=True,
                        total_ms=read_ms,
                        frame=frame,
                    )
                    frame_index += 1
                    continue

                t_inf = time.perf_counter()
                faces, infer_ms = await loop.run_in_executor(None, self._process_frame_sync, frame)
                total_ms = (time.perf_counter() - t_inf) * 1000.0
                logger.info(
                    "freym %d: o‘qish+inferens jami %.2f ms (inferens hisobi: %.2f ms)",
                    frame_index,
                    read_ms + total_ms,
                    infer_ms,
                )

                yield VideoFrameResult(
                    frame_index=frame_index,
                    skipped=False,
                    faces=faces,
                    inference_ms=float(infer_ms),
                    total_ms=float(read_ms + total_ms),
                    frame=frame,
                )
                frame_index += 1
                processed += 1
        finally:

            def _release() -> None:
                cap.release()

            await loop.run_in_executor(None, _release)
            logger.info("VideoCapture yopildi.")
