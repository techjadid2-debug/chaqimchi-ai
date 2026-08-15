"""Threshold kalibrlash — galereya va ixtiyoriy rasm to‘plami bo‘yicha."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List

import numpy as np

if TYPE_CHECKING:
    from chaqimchi_ai.face_engine import FaceEngine


@dataclass
class CalibrationReport:
    suggested_threshold: float
    current_threshold: float
    gallery_size: int
    negative_scores: List[float]
    positive_scores: List[float]
    method: str
    notes: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "suggested_threshold": round(self.suggested_threshold, 4),
            "current_threshold": self.current_threshold,
            "gallery_size": self.gallery_size,
            "negative_scores": {
                "count": len(self.negative_scores),
                "min": round(float(min(self.negative_scores)), 4) if self.negative_scores else None,
                "max": round(float(max(self.negative_scores)), 4) if self.negative_scores else None,
                "mean": round(float(np.mean(self.negative_scores)), 4)
                if self.negative_scores
                else None,
                "p95": round(float(np.percentile(self.negative_scores, 95)), 4)
                if self.negative_scores
                else None,
            },
            "positive_scores": {
                "count": len(self.positive_scores),
                "min": round(float(min(self.positive_scores)), 4) if self.positive_scores else None,
                "max": round(float(max(self.positive_scores)), 4) if self.positive_scores else None,
                "mean": round(float(np.mean(self.positive_scores)), 4)
                if self.positive_scores
                else None,
            },
            "method": self.method,
            "notes": self.notes,
        }


def _pairwise_cross_scores(embeddings: np.ndarray) -> List[float]:
    n = embeddings.shape[0]
    scores: List[float] = []
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            scores.append(float(np.dot(embeddings[i], embeddings[j])))
    return scores


def calibrate_from_gallery(
    embeddings: np.ndarray,
    *,
    current_threshold: float = 0.4,
    margin: float = 0.05,
    percentile: float = 95.0,
) -> CalibrationReport:
    """
    Har bir shaxs uchun bitta embedding bo‘lganda:
    musbat juftlar yo‘q, manfiy = boshqa shaxslar bilan kosinus.
    """
    n = int(embeddings.shape[0]) if embeddings is not None else 0
    if n < 2:
        return CalibrationReport(
            suggested_threshold=current_threshold,
            current_threshold=current_threshold,
            gallery_size=n,
            negative_scores=[],
            positive_scores=[],
            method="gallery_insufficient",
            notes="Kamida 2 ta shaxs bazada bo‘lishi kerak (yoki calibration papkasidan foydalaning).",
        )

    emb = np.asarray(embeddings, dtype=np.float32)
    norms = np.linalg.norm(emb, axis=1, keepdims=True) + 1e-8
    emb = emb / norms

    neg = _pairwise_cross_scores(emb)
    p95 = float(np.percentile(neg, percentile))
    suggested = min(0.99, max(0.1, p95 + margin))

    return CalibrationReport(
        suggested_threshold=suggested,
        current_threshold=current_threshold,
        gallery_size=n,
        negative_scores=neg,
        positive_scores=[],
        method="gallery_cross_negative_p95",
        notes=(
            f"Manfiy juftlar soni: {len(neg)}. "
            f"Tavsiya: p{percentile:.0f}(neg) + {margin} = {suggested:.4f}."
        ),
    )


def _load_images_from_dir(root: Path) -> List[tuple[str, Path]]:
    items: List[tuple[str, Path]] = []
    if not root.is_dir():
        return items
    for person_dir in sorted(root.iterdir()):
        if not person_dir.is_dir():
            continue
        label = person_dir.name
        for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
            for p in person_dir.glob(ext):
                items.append((label, p))
    return items


def calibrate_from_image_dir(
    engine: "FaceEngine",
    calibration_dir: Path,
    *,
    current_threshold: float = 0.4,
    margin: float = 0.05,
) -> CalibrationReport:
    """data/calibration/Ism/*.jpg — bir papkada bir nechta surat."""
    items = _load_images_from_dir(calibration_dir)
    if len(items) < 2:
        return CalibrationReport(
            suggested_threshold=current_threshold,
            current_threshold=current_threshold,
            gallery_size=0,
            negative_scores=[],
            positive_scores=[],
            method="calibration_dir_insufficient",
            notes=f"Katalogda kamida 2 ta rasm kerak: {calibration_dir}",
        )

    import cv2

    labels: List[str] = []
    embeddings: List[np.ndarray] = []
    for label, path in items:
        img = cv2.imread(str(path))
        if img is None:
            continue
        emb = engine.extract_primary_embedding(img)
        if emb is None:
            continue
        labels.append(label)
        v = emb.flatten().astype(np.float32)
        v = v / (float(np.linalg.norm(v)) + 1e-8)
        embeddings.append(v)

    if len(embeddings) < 2:
        return CalibrationReport(
            suggested_threshold=current_threshold,
            current_threshold=current_threshold,
            gallery_size=len(embeddings),
            negative_scores=[],
            positive_scores=[],
            method="calibration_embeddings_insufficient",
            notes="Rasmlardan yetarli embedding olinmadi (yuz topilmadi?).",
        )

    pos: List[float] = []
    neg: List[float] = []
    for i in range(len(embeddings)):
        for j in range(len(embeddings)):
            s = float(np.dot(embeddings[i], embeddings[j]))
            if i == j:
                continue
            if labels[i] == labels[j]:
                pos.append(s)
            else:
                neg.append(s)

    if not neg:
        return CalibrationReport(
            suggested_threshold=current_threshold,
            current_threshold=current_threshold,
            gallery_size=len(embeddings),
            negative_scores=[],
            positive_scores=pos,
            method="calibration_no_negatives",
            notes="Turli shaxslar uchun kamida 2 ta label kerak.",
        )

    p95_neg = float(np.percentile(neg, 95))
    p05_pos = float(np.percentile(pos, 5)) if pos else 1.0
    midpoint = (p95_neg + p05_pos) / 2.0
    suggested = min(0.99, max(0.1, max(midpoint, p95_neg + margin)))

    return CalibrationReport(
        suggested_threshold=suggested,
        current_threshold=current_threshold,
        gallery_size=len(embeddings),
        negative_scores=neg,
        positive_scores=pos,
        method="calibration_dir_pos_neg",
        notes=(
            f"Rasmlar: {len(items)}, embedding: {len(embeddings)}. "
            f"Manfiy: {len(neg)}, musbat: {len(pos)}."
        ),
    )
