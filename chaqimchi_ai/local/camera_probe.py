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

import hashlib
import logging
import os
import re
import socket
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote, unquote, urlparse, urlunparse

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
        # Katta "Channels" — Hikvision hujjatlaridagi rasmiy ko'rinish;
        # KNOWN_PATHS bilan bir xil bo'lishi shart (ilgari kichik harf
        # bilan farq qilardi va ayrim qattiqqo'l proshivkalar 404 berardi).
        "hikvision": f"/Streaming/Channels/{channel}02",
        "dahua": f"/cam/realmonitor?channel={channel}&subtype=1",
        "uniview": f"/unicast/c{channel}/s1/live",
    }
    path = paths.get(brand.lower())
    if path is None:
        raise ValueError(f"Noma'lum brend: {brand}")
    return f"rtsp://{auth}{clean_host}:{int(port)}{path}"


#: `rtsp_describe` natijasining qisqa keshi: {url: (code, raw, monotonic)}.
_DESCRIBE_CACHE: Dict[str, Tuple[int, str, float]] = {}
DESCRIBE_CACHE_TTL_SEC = 10.0


def _remember(url: str, code: int, raw: str) -> Tuple[int, str]:
    if len(_DESCRIBE_CACHE) > 256:
        _DESCRIBE_CACHE.clear()
    _DESCRIBE_CACHE[url] = (code, raw, time.monotonic())
    return code, raw


def rtsp_describe(url: str, *, timeout_sec: float = 5.0) -> Tuple[int, str]:
    """RTSP serverga to'g'ridan-to'g'ri `DESCRIBE` yuboradi.

    Nega kerak: OpenCV muvaffaqiyatsizlikda faqat `False` qaytaradi va
    sabab noma'lum qoladi.  Mijozga esa "tasvir kelmadi" emas, **nima
    qilish kerakligi** aytilishi kerak — parolmi, yo'lmi, tarmoqmi.

    RTSP javob kodi buni aniq ajratadi:

        200  ishlaydi
        401  parol yoki foydalanuvchi noto'g'ri
        404  bu manzilda oqim yo'q (yo'l noto'g'ri)
        0    umuman ulanmadi (port yopiq, boshqa tarmoq, NVR o'chiq)

    Digest autentifikatsiya qo'lda bajariladi: kutubxona qo'shishdan
    ko'ra yigirma qator kod arzonroq va bog'liqlik keltirmaydi.
    """
    # Qisqa kesh: bitta URL uchun DESCRIBE natijasi 10 soniya yashaydi.
    # NVR kanal skanerida har muvaffaqiyatsiz nomzod uchun `_classify`
    # xuddi shu so'rovni qaytarardi — har xato ikki barobar qimmat edi.
    cached = _DESCRIBE_CACHE.get(url)
    if cached is not None and time.monotonic() - cached[2] < DESCRIBE_CACHE_TTL_SEC:
        return cached[0], cached[1]

    parts = urlparse(url)
    host, port = parts.hostname, parts.port or 554
    if not host:
        return 0, "manzil noto'g'ri"

    target = urlunparse((parts.scheme, f"{host}:{port}", parts.path, "", parts.query, ""))
    user = unquote(parts.username or "")
    password = unquote(parts.password or "")

    def _request(auth_header: str = "", seq: int = 1) -> str:
        lines = [f"DESCRIBE {target} RTSP/1.0", f"CSeq: {seq}", "User-Agent: Chaqimchi"]
        if auth_header:
            lines.append(auth_header)
        return "\r\n".join(lines) + "\r\n\r\n"

    try:
        with socket.create_connection((host, port), timeout=timeout_sec) as sock:
            sock.settimeout(timeout_sec)
            sock.sendall(_request().encode("ascii", "ignore"))
            first = sock.recv(4096).decode("utf-8", "replace")

            if " 401 " not in first.split("\r\n")[0]:
                return _remember(url, _status_code(first), first)

            # 401 keldi — endi Digest bilan qayta so'raymiz.
            challenge = _digest_challenge(first)
            if challenge is None or not user:
                return _remember(url, 401, first)
            header = _digest_header(user, password, target, challenge)
            sock.sendall(_request(header, seq=2).encode("ascii", "ignore"))
            second = sock.recv(4096).decode("utf-8", "replace")
            return _remember(url, _status_code(second), second)
    except (OSError, socket.timeout) as exc:
        logger.info("RTSP DESCRIBE ulanmadi (%s): %s", redact(url), exc)
        return _remember(url, 0, str(exc))


def _status_code(response: str) -> int:
    try:
        return int(response.split(" ", 2)[1])
    except (IndexError, ValueError):
        return 0


def _digest_challenge(response: str) -> Optional[Dict[str, str]]:
    match = re.search(r"WWW-Authenticate:\s*Digest\s*(.+)", response, re.I)
    if not match:
        return None
    return dict(re.findall(r'(\w+)="([^"]*)"', match.group(1)))


def _digest_header(user: str, password: str, uri: str, challenge: Dict[str, str]) -> str:
    realm = challenge.get("realm", "")
    nonce = challenge.get("nonce", "")
    ha1 = hashlib.md5(f"{user}:{realm}:{password}".encode()).hexdigest()  # noqa: S324
    ha2 = hashlib.md5(f"DESCRIBE:{uri}".encode()).hexdigest()  # noqa: S324
    digest = hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode()).hexdigest()  # noqa: S324
    return (
        f'Authorization: Digest username="{user}", realm="{realm}", '
        f'nonce="{nonce}", uri="{uri}", response="{digest}"'
    )


def _classify(url: str) -> Tuple[str, str]:
    """Kadr kelmaganda **aniq** sababni aytadi.

    Ilgari bu yerda umumiy "tekshiriladigan ro'yxat" berilardi — mijoz
    to'rtta narsani birdan tekshirishga majbur bo'lardi va odatda
    hech birini tuzatolmasdi.  Endi RTSP serverning o'z javobi so'raladi.
    """
    parts = urlparse(url)
    code, _raw = rtsp_describe(url)

    if code == 0:
        return (
            "Kameraga umuman ulanib bo'lmadi.",
            "Manzil yoki port noto'g'ri, NVR o'chiq, yoki kompyuter va NVR "
            "boshqa tarmoqda. Kompyuterda `ping " + str(parts.hostname or "") + "` "
            "buyrug'ini sinab ko'ring.",
        )
    if code == 401:
        if not parts.username:
            return (
                "Kamera foydalanuvchi nomi va parol so'rayapti.",
                "NVR menyusidan foydalanuvchi yarating (faqat ko'rish huquqi "
                "yetarli) va shu yerga kiriting.",
            )
        return (
            "Foydalanuvchi nomi yoki parol noto'g'ri.",
            "NVR menyusidagi login bilan bir xil ekaniga ishonch hosil qiling. "
            "Ko'p NVR'da katta-kichik harf farq qiladi.",
        )
    if code == 404:
        return (
            "Ulanish bor, lekin bu manzilda kamera oqimi yo'q.",
            "Kanal raqami noto'g'ri yoki NVR boshqa formatdan foydalanadi. "
            "«Barcha kameralarni topish» tugmasini bosing — dastur ma'lum "
            "formatlarni o'zi sinab ko'radi.",
        )
    if code == 200:
        return (
            "Kamera javob berdi, lekin tasvirni ochib bo'lmadi.",
            "Ko'pincha sabab — H.265 (HEVC) siqish. NVR menyusida shu kamera "
            "uchun substream'ni H.264 ga o'zgartiring: "
            "Configuration → Video → Sub Stream → H.264.",
        )
    return (
        f"Kamera kutilmagan javob qaytardi (kod {code}).",
        "NVR sozlamalarida RTSP yoqilganini tekshiring.",
    )


#: Ma'lum RTSP yo'llari, ehtimolligi bo'yicha tartiblangan.
#:
#: Nega kerak: sehrgar ilgari faqat **bitta** yo'lni sinardi — mijoz
#: tanlagan brendnikini.  Brend noto'g'ri tanlansa yoki NVR nostandart
#: format ishlatsa, "tasvir kelmadi" degan foydasiz xato chiqardi va
#: mijoz nima qilishni bilmasdi.  Endi hammasi sinaladi.
#:
#: Substream birinchi: u yengil (640x360) va oddiy ofis kompyuterida ham
#: dekodlanadi; main stream 1080p bo'lib, tahlil uchun og'ir.
KNOWN_PATHS: Tuple[Tuple[str, str], ...] = (
    ("Hikvision / HiLook", "/Streaming/Channels/{ch}02"),
    ("Dahua / IMOU", "/cam/realmonitor?channel={ch}&subtype=1"),
    ("Uniview (UNV)", "/unicast/c{ch}/s1/live"),
    ("Xiongmai / Besder", "/h264Preview_0{ch}_sub"),
    ("TP-Link Tapo / Vigi", "/stream2"),
    ("Umumiy (ch0_1)", "/live/ch0_1"),
    ("Umumiy (av0)", "/live/av0"),
    ("ONVIF profil", "/onvif1"),
    # Substream topilmasa main stream ham yaraydi — sekinroq, lekin
    # ishlaydi.  Mijozga "umuman ishlamaydi" dan ko'ra yaxshiroq.
    ("Hikvision (asosiy oqim)", "/Streaming/Channels/{ch}01"),
    ("Dahua (asosiy oqim)", "/cam/realmonitor?channel={ch}&subtype=0"),
    ("Uniview (asosiy oqim)", "/unicast/c{ch}/s0/live"),
)


#: Substream manzilidan ASOSIY oqim manzilini chiqarish qoidalari.
#:
#: Klip yozish (`record_url`) asosiy oqimdan bo'ladi: substream 640x360
#: da klip mijozga "buzuq video"day ko'rinadi.  Brendlar substream va
#: main stream'ni bitta naqsh bilan farqlaydi — shu naqshni teskari
#: qo'llasak, mijozdan ikkinchi manzil so'ramaymiz.
MAIN_STREAM_REWRITES: Tuple[Tuple[str, str], ...] = (
    (r"(/Streaming/Channels/\d*?)02(?=$|\?)", r"\g<1>01"),  # Hikvision / HiLook
    (r"subtype=1\b", "subtype=0"),  # Dahua / IMOU
    (r"/s1/", "/s0/"),  # Uniview unicast
    (r"/stream2(?=$|\?)", "/stream1"),  # TP-Link Tapo / Vigi
    (r"_sub(?=$|\?)", "_main"),  # Xiongmai / Besder
    (r"/ch0_1(?=$|\?)", "/ch0_0"),  # Umumiy
)


def suggest_record_url(stream_url: str) -> Optional[str]:
    """Substream URL'idan asosiy oqim taklifi — topilmasa None."""
    for pattern, replacement in MAIN_STREAM_REWRITES:
        rewritten, count = re.subn(pattern, replacement, stream_url, count=1)
        if count and rewritten != stream_url:
            return rewritten
    return None


def candidate_urls(
    host: str,
    *,
    port: int = 554,
    username: str = "",
    password: str = "",
    channel: int = 1,
    brand: str = "",
) -> List[Tuple[str, str]]:
    """Sinab ko'riladigan barcha manzillar: `(nom, url)`.

    `brand` berilsa o'sha brendning yo'llari **oldinga** o'tadi.  Brend
    kameraning o'z javobidan aniqlanadi (`onvif_client.brand_from_banner`),
    ya'ni mijozdan hech narsa so'ralmaydi.  Natijada odatda birinchi
    urinishdayoq topiladi: o'n bir variantni sinash ~30 soniya, bittasi
    esa 2-3 soniya.
    """
    clean_host = re.sub(r"^rtsps?://", "", host.strip(), flags=re.I).split("/")[0]
    auth = f"{quote(username, safe='')}:{quote(password, safe='')}@" if username else ""
    paths = order_paths(brand)
    return [
        (name, f"rtsp://{auth}{clean_host}:{int(port)}{path.format(ch=channel)}")
        for name, path in paths
    ]


def order_paths(brand: str) -> Tuple[Tuple[str, str], ...]:
    """`KNOWN_PATHS` ni brend bo'yicha tartiblaydi."""
    if not brand:
        return KNOWN_PATHS
    from chaqimchi_ai.local import onvif_client

    keys = onvif_client.path_order_for(brand)
    if not keys:
        return KNOWN_PATHS
    preferred = [
        item for item in KNOWN_PATHS if any(key.lower() in item[0].lower() for key in keys)
    ]
    if not preferred:
        return KNOWN_PATHS
    rest = [item for item in KNOWN_PATHS if item not in preferred]
    return tuple(preferred + rest)


def find_working_url(
    host: str,
    *,
    port: int = 554,
    username: str = "",
    password: str = "",
    channel: int = 1,
    timeout_sec: int = SCAN_TIMEOUT_SEC,
) -> Tuple[Optional[str], Optional[str], ProbeResult]:
    """Ishlaydigan RTSP manzilini qidiradi.

    Qaytaradi: `(nom, url, natija)`.  Topilmasa `(None, None, oxirgi
    natija)` — oxirgi natijada mijozga ko'rsatiladigan sabab bo'ladi.

    Avval bitta `DESCRIBE` bilan parol tekshiriladi: agar u noto'g'ri
    bo'lsa o'nta yo'lni sinash bir daqiqa vaqtni behuda sarflardi va
    mijozga baribir noto'g'ri sabab ko'rsatilardi.
    """
    from chaqimchi_ai.local import onvif_client

    probe = candidate_urls(host, port=port, username=username, password=password, channel=channel)
    code, raw = rtsp_describe(probe[0][1])
    if code in (0, 401):
        error, hint = _classify(probe[0][1])
        return None, None, ProbeResult(ok=False, error=error, hint=hint)

    # Brend kameraning o'z javobidan aniqlanadi: `Server:` sarlavhasi va
    # `realm="IP Camera(…)"` ni har bir ishlab chiqaruvchi o'zicha
    # to'ldiradi.  Bu bepul ma'lumot ilgari ishlatilmasdi.
    brand = onvif_client.brand_from_banner(raw)
    if brand:
        logger.info("Brend aniqlandi: %s", brand)
    urls = candidate_urls(
        host, port=port, username=username, password=password, channel=channel, brand=brand
    )

    last = ProbeResult(ok=False, error="Kamera topilmadi.", hint="")
    for name, url in urls:
        result = grab_frame(url, timeout_sec=timeout_sec)
        if result.ok:
            logger.info("Ishlaydigan format topildi: %s", name)
            return name, url, result
        last = result

    # Ma'lum yo'llarning hech biri ishlamadi.  Endi taxmin qilishni
    # to'xtatib, kameradan **so'raymiz**: ONVIF aynan shu savolga javob
    # beradi.  Ro'yxatda yo'q yoki nostandart sozlangan kamera faqat shu
    # yo'l bilan qo'shiladi — ilgari bunday kamera umuman ishlamasdi.
    name, url, result = _try_onvif(
        host, username=username, password=password, timeout_sec=timeout_sec
    )
    if url:
        return name, url, result
    return None, None, last


#: ONVIF bergan oqimlardan ko'pi bilan shuncha tasi sinaladi.  Ko'p
#: kanalli NVR'da har profil uchun 6 soniya kutish sehrgarni juda
#: sekinlashtirardi; amalda ishlaydigan oqim doim birinchi uchtada.
MAX_ONVIF_PROFILE_TRIES = 3


def _try_onvif(
    host: str, *, username: str, password: str, timeout_sec: int
) -> Tuple[Optional[str], Optional[str], ProbeResult]:
    """ONVIF oqimlarini birma-bir sinab, ROSTDAN ishlaydiganini tanlaydi.

    Ilgari faqat BITTA (tavsiya etilgan) oqim sinalardi va kadr kelmasa
    "NVR'ni H.264 ga o'zgartiring" deyilardi.  H.265 substream'li kamera
    shu sababli qo'shilmasdi — garchi FFmpeg uni dekodlay olsa ham, va
    garchi o'sha kamerada ishlaydigan boshqa oqim bo'lsa ham.
    """
    from chaqimchi_ai.local import onvif_client

    clean_host = re.sub(r"^rtsps?://", "", host.strip(), flags=re.I).split("/")[0].split(":")[0]
    # port=0 — describe o'zi 80/8899/8000 dan ochig'ini topadi (yopiq
    # portlarga 6 soniyalik SOAP yuborilmaydi).
    answer = onvif_client.describe(clean_host, username=username, password=password, port=0)
    if not answer.ok:
        return None, None, ProbeResult(ok=False, error="", hint="")
    ordered = [item for item in onvif_client.rank_profiles(answer.profiles) if item.uri]
    if not ordered:
        return None, None, ProbeResult(ok=False, error="", hint="")

    brand = onvif_client.normalise_brand(answer.device.brand) or "ONVIF"
    for profile in ordered[:MAX_ONVIF_PROFILE_TRIES]:
        url = onvif_client.with_credentials(profile.uri, username, password, host=clean_host)
        result = grab_frame(url, timeout_sec=timeout_sec)
        if result.ok:
            logger.info("ONVIF orqali topildi: %s (%s)", brand, profile.encoding)
            return f"{brand} (ONVIF)", url, result
        logger.info("ONVIF oqimi ochilmadi (%s) — keyingisi sinaladi", profile.encoding)

    # Hech biri ochilmadi.  Sabab birinchi (eng mos) oqim bo'yicha
    # tushuntiriladi — odatda H.265+ (Smart Codec).
    warning, advice = onvif_client.compatibility_note(ordered[0])
    if warning:
        return None, None, ProbeResult(ok=False, error=warning, hint=advice)
    return None, None, ProbeResult(ok=False, error="", hint="")


def path_template(url: str, channel: int) -> str:
    """Ishlaydigan manzildan kanal o'rni belgilangan shablon yasaydi.

    Bitta NVR barcha kanallarda **bitta** formatdan foydalanadi.  Birinchi
    kanalda topilgan yo'lni shablonga aylantirib, qolganlarini bir urinishda
    tekshiramiz — aks holda har kanal uchun o'nlab variantni qayta sinardik.
    """
    parts = urlparse(url)
    path = parts.path + (f"?{parts.query}" if parts.query else "")
    # Kanal raqami yo'lda ikki xil ko'rinishda uchraydi: `102`/`c1`/`01`
    # (o'rnida) yoki `channel=1` (parametrda).
    for pattern, replacement in (
        (rf"channel={channel}\b", "channel={ch}"),
        (rf"/Streaming/Channels/{channel}(\d\d)", r"/Streaming/Channels/{ch}\1"),
        (rf"/c{channel}/", "/c{ch}/"),
        (rf"_0{channel}_", "_0{ch}_"),
    ):
        new_path, count = re.subn(pattern, replacement, path, count=1)
        if count:
            return new_path
    # Kanal raqami umuman yo'q (masalan Tapo `/stream2`) — shablon
    # o'zgarmaydi va barcha kanallar bir xil manzilni ko'rsatadi.
    return path


def apply_template(
    template: str, host: str, port: int, username: str, password: str, channel: int
) -> str:
    clean_host = re.sub(r"^rtsps?://", "", host.strip(), flags=re.I).split("/")[0]
    auth = f"{quote(username, safe='')}:{quote(password, safe='')}@" if username else ""
    return f"rtsp://{auth}{clean_host}:{int(port)}{template.format(ch=channel)}"


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

    # `rtsp_transport;tcp` — UDP do'kon Wi-Fi'sida kadr yo'qotadi va tasvir
    # "sinadi".  `stimeout` — soket I/O kutish chegarasi (mikrosoniyada):
    # OpenCV'ning `CAP_PROP_OPEN_TIMEOUT_MSEC` xossasi FFMPEG backendida
    # e'tiborsiz qolarkan va javob bermaydigan IP'da ulanish 30 soniya
    # osilib turardi.
    #
    # `timeout` **ataylab ishlatilmaydi**: RTSP demuxer uchun uning ma'nosi
    # boshqa ("kiruvchi ulanishni kutish", `listen` rejimini nazarda
    # tutadi), ya'ni u mijoz ulanishini butunlay buzishi mumkin.
    #
    # Muhit o'zgaruvchisi chaqiruvdan keyin **tiklanadi**: `retail.service`
    # alohida jarayon bo'lsa ham, supervisor unga `dict(os.environ)` ni
    # uzatadi.  Sinov qoldirgan qiymat zanjirga o'tib, barcha kamerani
    # ochilmaydigan qilib qo'ygan edi — aynan shu xato.
    previous = os.environ.get("OPENCV_FFMPEG_CAPTURE_OPTIONS")
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
        f"rtsp_transport;tcp|stimeout;{int(timeout_sec * 1_000_000)}"
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
        # Muhitni tiklaymiz — pastdagi izohga qarang.
        if previous is None:
            os.environ.pop("OPENCV_FFMPEG_CAPTURE_OPTIONS", None)
        else:
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = previous
