"""Yuklangan fayllarni rasmga aylantirish."""

from __future__ import annotations

from typing import Optional

import cv2
import numpy as np
from fastapi import UploadFile

# Yuklanadigan rasm uchun yuqori chegara. Bungacha chegara yo'q edi va butun
# fayl xotiraga o'qilardi — 4 GB mini-PC da bu oddiy DoS vektori.
MAX_UPLOAD_BYTES = 12 * 1024 * 1024


class UploadTooLarge(ValueError):
    """Yuklangan fayl `MAX_UPLOAD_BYTES` dan katta."""


async def decode_upload(file: UploadFile) -> Optional[np.ndarray]:
    """Yuklangan faylni BGR massivga aylantiradi.

    Returns:
        BGR `np.ndarray`, yoki rasm o'qilmasa `None`.

    Raises:
        UploadTooLarge: fayl hajmi chegaradan oshsa.
    """
    contents = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(contents) > MAX_UPLOAD_BYTES:
        raise UploadTooLarge(
            f"Rasm hajmi {MAX_UPLOAD_BYTES // (1024 * 1024)} MB dan oshmasligi kerak"
        )
    if not contents:
        return None
    arr = np.frombuffer(contents, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)
