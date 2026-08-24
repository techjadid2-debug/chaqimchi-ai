"""RTSP manzillarini brauzerga chiqarishdan oldin tozalash.

Nega bulutda alohida nusxa: qurilmadagi `chaqimchi_ai.local.camera_probe`
`cv2` ni import qiladi va uni bulut image'iga tortib kirish mumkin emas
(u yerda OpenCV yo'q va kerak ham emas).  Shu sabab bu yerda faqat
redaksiya qismi takrorlanadi.

Ikki nusxa jimgina ajralib ketmasligi uchun `tests/test_cloud_rtsp_redact.py`
ikkalasini bir xil kirishlarda solishtiradi.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse


def redact(url: str) -> str:
    """RTSP manzilidan parolni olib tashlaydi.

    Manzil panelga, logga va xato matniga tushadi.  NVR paroli o'sha
    yo'llar bilan sirtga chiqib ketmasligi kerak — bu kameraga to'liq
    kirish demak.
    """
    try:
        parts = urlparse(url)
    except ValueError:
        return "rtsp://…"
    if not parts.hostname:
        return re.sub(r"//[^@/]+@", "//…@", url)
    host = parts.hostname
    if parts.port:
        host = f"{host}:{parts.port}"
    netloc = f"…@{host}" if parts.username else host
    return urlunparse((parts.scheme, netloc, parts.path, "", parts.query, ""))


def safe_streams(streams: list[dict]) -> list[dict]:
    """Skaner natijasini panelga ko'rsatishga tayyorlaydi.

    To'liq manzil O'RNIGA `stream_ref` (indeks) qaytariladi: kamerani
    saqlashda panel o'sha indeksni yuboradi va server manzilni
    shifrlangan natijadan o'zi oladi.  Ya'ni parol brauzerga umuman
    tushmaydi.
    """
    cleaned: list[dict] = []
    for index, stream in enumerate(streams or []):
        item = {key: value for key, value in stream.items() if key not in {"uri", "rtsp_url"}}
        raw = stream.get("uri") or stream.get("rtsp_url") or ""
        item["safe_url"] = redact(raw) if raw else ""
        item["stream_ref"] = index
        cleaned.append(item)
    return cleaned
