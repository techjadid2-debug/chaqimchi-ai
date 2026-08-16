"""Kamerani sinash: haqiqatan kadr keladimi.

Sehrgarning eng muhim qadami shu.  Oldingi maket "Tanlash va Ulash" tugmasini
bosganda faqat `alert()` chiqarardi — mijoz kamerani ulaganiga ishonch hosil
qilardi, aslida esa hech narsa tekshirilmagan edi.  Natijada xato faqat bir
necha kundan keyin, "nega hisobot bo'sh?" degan savol bilan chiqardi.

Bu modul bitta savolga javob beradi: **shu manzildan rasm keladimi?**
Kelsa — JPEG qaytaradi (sehrgar uni ko'rsatadi va chiziq shu kadr ustida
chiziladi).  Kelmasa — mijoz tuzata oladigan tilda sabab qaytaradi.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Optional, Tuple
from urllib.parse import quote, urlparse, urlunparse

logger = logging.getLogger(__name__)

#: Kadr kutish vaqti.  RTSP qo'l siqishi sekin kameralarda ~5 s oladi;
#: 15 s dan ortiq kutish mijozga "osilib qoldi" bo'lib ko'rinadi.
DEFAULT_TIMEOUT_SEC = 15

#: Bir necha kanalni ketma-ket sinaganda har biri uchun qisqaroq vaqt:
#: 4 kanal × 15 s = bir daqiqa, mijoz esa kutmaydi.  Ishlaydigan kamera
#: odatda 2-3 soniyada javob beradi.
SCAN_TIMEOUT_SEC = 6

#: Sehrgarga yuboriladigan rasm kengligi.  Kadr shundan kengroq bo'lsa
#: kichraytiriladi: chiziq koordinatalari 0..1 da saqlangani uchun aniqlik
#: yo'qolmaydi, sahifa esa tez ochiladi.
PREVIEW_WIDTH = 960


@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    #: Muvaffaqiyatda JPEG baytlari.
    jpeg: Optional[bytes] = None
    width: int = 0
    height: int = 0
    #: Muvaffaqiyatsizlikda mijoz o'qiydigan sabab.
    error: str = ""
    #: Mijoz nima qilishi kerak (bitta aniq harakat).
    hint: str = ""


def redact(url: str) -> str:
    """RTSP manzilidan parolni olib tashlaydi.

    Manzil logga, panelga va xato matniga tushadi.  NVR paroli o'sha yo'llar
    bilan sirtga chiqib ketmasligi kerak — bu kameraga to'liq kirish demak.
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


def build_rtsp(
    *,
    brand: str,
    host: str,
    port: int = 554,
    username: str = "",
    password: str = "",
    channel: int = 1,
) -> str:
    """Brend shabloni bo'yicha substream manzilini yig'adi.

    O'rnatuvchi panelidagi (`installer.html`) mantiq bilan bir xil — mijoz
    ham, usta ham bitta qoidadan foydalanadi.  Substream ataylab: 640×360
    oqim oddiy ofis kompyuterida ham dekodlanadi, main stream esa yo'q.
    """
    clean_host = re.sub(r"^rtsps?://", "", host.strip(), flags=re.I).split("/")[0]
    if not clean_host:
        raise ValueError("NVR yoki kamera IP manzilini kiriting")
    auth = ""
    if username:
        auth = f"{quote(username, safe='')}:{quote(password, safe='')}@"
    paths = {
        "hikvision": f"/Streaming/channels/{channel}02",
        "dahua": f"/cam/realmonitor?channel={channel}&subtype=1",
        "uniview": f"/unicast/c{channel}/s1/live",
    }
    path = paths.get(brand.lower())
    if path is None:
        raise ValueError(f"Noma'lum brend: {brand}")
    return f"rtsp://{auth}{clean_host}:{int(port)}{path}"


def _classify(url: str) -> Tuple[str, str]:
    """Kadr kelmaganda eng ehtimolli sababni taxmin qiladi.

    Aniq sababni OpenCV bermaydi (u faqat `False` qaytaradi), shuning uchun
    mijozga "xato 0xC00D" emas, **tekshiriladigan ro'yxat** beriladi.
    """
    parts = urlparse(url)
    if not parts.username:
        return (
            "Kameradan tasvir kelmadi.",
            "Ko'pincha sabab — foydalanuvchi nomi va parol kiritilmagan. "
            "NVR menyusidan foydalanuvchi yarating va shu yerga yozing.",
        )
    return (
        "Kameradan tasvir kelmadi.",
        "Tekshiring: (1) parol to'g'rimi, (2) NVR'da RTSP yoqilganmi, "
        "(3) kamera H.265 emas, H.264 substream berayaptimi, "
        "(4) kompyuter va NVR bitta tarmoqdami.",
    )


def grab_frame(url: str, *, timeout_sec: int = DEFAULT_TIMEOUT_SEC) -> ProbeResult:
    """Bitta kadr oladi va JPEG qilib qaytaradi."""
    try:
        import cv2
    except ImportError:  # pragma: no cover - bundle'da doim bor
        return ProbeResult(
            ok=False,
            error="Video kutubxonasi topilmadi.",
            hint="Dasturni qayta o'rnating — o'rnatuvchi kerakli fayllarni olib keladi.",
        )

    # Ikkita sozlama, ikkalasi ham kerak:
    #
    # `rtsp_transport;tcp` — UDP do'kon Wi-Fi'sida kadr yo'qotadi va tasvir
    # "sinadi".
    #
    # `timeout` (mikrosoniyada) — **haqiqiy** kutish chegarasi.  OpenCV'ning
    # `CAP_PROP_OPEN_TIMEOUT_MSEC` xossasi FFMPEG backendida e'tiborsiz
    # qolarkan: javob bermaydigan IP'da ulanish 30 soniya osilib turardi,
    # to'rt kanalni tekshirish esa ikki daqiqa olardi va mijoz dastur
    # qotib qoldi deb o'ylardi.  `stimeout` — eski FFMPEG'dagi nomi.
    micros = int(timeout_sec * 1_000_000)
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
        f"rtsp_transport;tcp|timeout;{micros}|stimeout;{micros}"
    )

    capture = None
    try:
        capture = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        for name in ("CAP_PROP_OPEN_TIMEOUT_MSEC", "CAP_PROP_READ_TIMEOUT_MSEC"):
            prop = getattr(cv2, name, None)
            if prop is not None:
                capture.set(prop, int(timeout_sec * 1000))
        if not capture.isOpened():
            error, hint = _classify(url)
            logger.info("Kamera ochilmadi: %s", redact(url))
            return ProbeResult(ok=False, error=error, hint=hint)

        ok, frame = capture.read()
        if not ok or frame is None:
            error, hint = _classify(url)
            logger.info("Kamera ochildi, lekin kadr bermadi: %s", redact(url))
            return ProbeResult(
                ok=False,
                error="Kamera ulandi, lekin tasvir bermadi.",
                hint=hint,
            )

        height, width = frame.shape[:2]
        if width > PREVIEW_WIDTH:
            scale = PREVIEW_WIDTH / float(width)
            frame = cv2.resize(frame, (PREVIEW_WIDTH, int(height * scale)))
        encoded, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
        if not encoded:
            return ProbeResult(
                ok=False,
                error="Kadr rasmga aylantirilmadi.",
                hint="Qayta urinib ko'ring.",
            )
        return ProbeResult(ok=True, jpeg=buffer.tobytes(), width=width, height=height)
    except Exception as exc:  # noqa: BLE001 — sabab har xil bo'lishi mumkin
        logger.warning("Kamera sinovida xato (%s): %s", redact(url), exc)
        return ProbeResult(
            ok=False,
            error="Kameraga ulanib bo'lmadi.",
            hint="Manzilni tekshiring yoki mutaxassisga murojaat qiling.",
        )
    finally:
        if capture is not None:
            capture.release()
