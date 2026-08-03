"""BGR tasvirni o‘lcham bo‘yicha tayyorlash (test va FaceEngine uchun)."""

from __future__ import annotations

import cv2
import numpy as np


def resize_bgr_max_side(image_bgr: np.ndarray, max_side: int) -> np.ndarray:
    """
    Uzoq tomon `max_side` dan oshmasligi uchun nisbatni saqlab kichraytirish.
    """
    if image_bgr is None or image_bgr.size == 0:
        raise ValueError("Bo‘sh tasvir.")
    if max_side < 1:
        raise ValueError("max_side >= 1 bo‘lishi kerak.")

    h, w = image_bgr.shape[:2]
    long_side = max(h, w)
    if long_side <= max_side:
        return image_bgr

    scale = max_side / float(long_side)
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    return cv2.resize(image_bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)
