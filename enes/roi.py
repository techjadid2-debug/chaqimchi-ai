"""Qiziqish zonasi (ROI) — deteksiya faqat kadrning bir qismida."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class RoiConfig:
    enabled: bool = False
    normalized: bool = True
    x1: float = 0.0
    y1: float = 0.0
    x2: float = 1.0
    y2: float = 1.0

    def clamp(self) -> "RoiConfig":
        x1 = max(0.0, min(1.0, self.x1)) if self.normalized else self.x1
        y1 = max(0.0, min(1.0, self.y1)) if self.normalized else self.y1
        x2 = max(0.0, min(1.0, self.x2)) if self.normalized else self.x2
        y2 = max(0.0, min(1.0, self.y2)) if self.normalized else self.y2
        if x2 <= x1 or y2 <= y1:
            raise ValueError("ROI: x2>x1 va y2>y1 bo‘lishi kerak")
        return RoiConfig(self.enabled, self.normalized, x1, y1, x2, y2)


def apply_roi(image_bgr: np.ndarray, roi: RoiConfig) -> np.ndarray:
    if not roi.enabled:
        return image_bgr
    r = roi.clamp()
    h, w = image_bgr.shape[:2]
    if r.normalized:
        x1, y1 = int(r.x1 * w), int(r.y1 * h)
        x2, y2 = int(r.x2 * w), int(r.y2 * h)
    else:
        x1, y1, x2, y2 = int(r.x1), int(r.y1), int(r.x2), int(r.y2)
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    if x2 <= x1 or y2 <= y1:
        return image_bgr
    crop = image_bgr[y1:y2, x1:x2]
    return crop if crop.size else image_bgr
