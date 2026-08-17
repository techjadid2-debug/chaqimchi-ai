"""ONVIF orqali kameradan **haqiqiy** oqim manzilini so'rash.

Nega kerak.  Ilgari ONVIF faqat qurilmani *topish* uchun ishlatilardi:
WS-Discovery IP manzilni qaytarardi, RTSP yo'li esa `KNOWN_PATHS`
ro'yxatidan **taxmin** qilinardi.  Ro'yxatda bo'lmagan kamerada bu
"tasvir kelmadi" bilan tugardi va mijozda tuzatishning imkoni yo'q edi —
u yo'lni qayerdan bilsin?

ONVIF standartining butun mazmuni shu savolga javob berishda:

    GetProfiles   → kamerada qanday oqimlar bor (kodek, o'lcham, FPS)
    GetStreamUri  → o'sha oqimning **aniq** RTSP manzili

Ya'ni taxmin qilish shart emas — kameraning o'zidan so'raladi.  Shu bilan
birga `GetDeviceInformation` ishlab chiqaruvchi nomini beradi, ya'ni
"brendni avtomatik aniqlash" ham shu yerdan chiqadi.

Kutubxona qo'shilmadi (`onvif-zeep` va uning `zeep`/`lxml` bog'liqliklari
Windows to'plamini ~20 MB kattalashtirardi va embeddable Python'da
o'rnatilishi ishonchsiz).  Bizga ONVIF'ning uch chaqiruvi kerak, ular esa
oddiy SOAP POST — mana shu fayl.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote, urlparse, urlunparse
from xml.etree import ElementTree

import httpx

logger = logging.getLogger(__name__)

#: Bitta SOAP chaqiruvi uchun kutish.  Kamera javob bermasa keyingi
#: usulga o'tamiz — mijozni kutdirib qo'yishdan ko'ra taxminiy yo'lni
#: sinagan yaxshiroq.
TIMEOUT_SEC = 6.0

#: Javobning maksimal hajmi.  Tarmoqdagi qurilma ishonchli manba emas:
#: cheksiz javob xotirani yeb qo'yishi mumkin.  Eng katta `GetProfiles`
#: javobi ~50 KB, ya'ni bu chegara keng.
MAX_RESPONSE_BYTES = 1_000_000

#: Qurilma xizmati ko'pincha shu yo'llarda turadi.  WS-Discovery XAddr
#: bergan bo'lsa u ishlatiladi, aks holda shular sinaladi.
DEVICE_SERVICE_PATHS: Tuple[str, ...] = (
    "/onvif/device_service",
    "/onvif/device",
    "/onvif/Device",
    "/device_service",
)

_SOAP_ENV = "http://www.w3.org/2003/05/soap-envelope"
_WSSE = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
_WSU = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
_PASSWORD_DIGEST = (
    "http://docs.oasis-open.org/wss/2004/01/"
    "oasis-200401-wss-username-token-profile-1.0#PasswordDigest"
)
_BASE64_BINARY = (
    "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary"
)


@dataclass(frozen=True)
class StreamProfile:
    """Kameradagi bitta oqim — ONVIF `Profile` ning bizga kerak qismi."""

    token: str
    name: str
    #: "H264", "H265", "JPEG" — bo'sh bo'lishi ham mumkin.
    encoding: str = ""
    width: int = 0
    height: int = 0
    fps: float = 0.0
    #: `GetStreamUri` bergan manzil (parolsiz).
    uri: str = ""

    @property
    def pixels(self) -> int:
        return self.width * self.height

    @property
    def is_substream(self) -> bool:
        """Yengil oqimmi.

        Tahlil uchun aynan shunisi kerak: 640×360 H.264 oddiy ofis
        kompyuterida ham dekodlanadi, 1080p esa protsessorni yeb qo'yadi.
        """
        return 0 < self.pixels <= 640 * 480


@dataclass
class DeviceInfo:
    manufacturer: str = ""
    model: str = ""
    firmware: str = ""
    serial: str = ""

    @property
    def brand(self) -> str:
        """Panelda ko'rsatiladigan qisqa nom."""
        parts = [p for p in (self.manufacturer.strip(), self.model.strip()) if p]
        return " ".join(parts)


@dataclass
class OnvifResult:
    ok: bool = False
    device: DeviceInfo = field(default_factory=DeviceInfo)
    profiles: List[StreamProfile] = field(default_factory=list)
    error: str = ""
    hint: str = ""


# ── SOAP qurilishi ───────────────────────────────────────────────────────


def _security_header(username: str, password: str) -> str:
    """WS-Security UsernameToken (PasswordDigest).

    ONVIF shu usulni talab qiladi: parol ochiq ketmaydi, o'rniga
    `SHA1(nonce + vaqt + parol)` yuboriladi.  `Created` maydoni tufayli
    eski so'rovni qayta ishlatib bo'lmaydi — shuning uchun kamera soati
    juda adashgan bo'lsa autentifikatsiya rad etiladi (buni xato
    matnida aytamiz).
    """
    if not username:
        return ""
    nonce = os.urandom(16)
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    digest = hashlib.sha1(  # noqa: S324 — algoritmni ONVIF standarti belgilaydi
        nonce + created.encode("utf-8") + password.encode("utf-8")
    ).digest()
    return (
        f'<s:Header><Security s:mustUnderstand="1" xmlns="{_WSSE}">'
        "<UsernameToken>"
        f"<Username>{_escape(username)}</Username>"
        f'<Password Type="{_PASSWORD_DIGEST}">'
        f"{base64.b64encode(digest).decode()}</Password>"
        f'<Nonce EncodingType="{_BASE64_BINARY}">'
        f"{base64.b64encode(nonce).decode()}</Nonce>"
        f'<Created xmlns="{_WSU}">{created}</Created>'
        "</UsernameToken></Security></s:Header>"
    )


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def _envelope(body: str, username: str, password: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<s:Envelope xmlns:s="{_SOAP_ENV}">'
        f"{_security_header(username, password)}"
        f"<s:Body>{body}</s:Body></s:Envelope>"
    )


def _call(
    url: str, body: str, *, username: str = "", password: str = "", timeout: float = TIMEOUT_SEC
) -> Optional[ElementTree.Element]:
    """Bitta SOAP so'rovi.  Muvaffaqiyatsizlikda `None`.

    401 kelsa HTTP Digest bilan qayta urinamiz: ONVIF profili
    WS-Security'ni talab qilsa ham, ayrim kameralar (ayniqsa arzon
    xitoy modellari) faqat HTTP Digest'ni tushunadi.
    """
    payload = _envelope(body, username, password).encode("utf-8")
    headers = {"Content-Type": "application/soap+xml; charset=utf-8"}
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.post(url, content=payload, headers=headers)
            if response.status_code == 401 and username:
                response = client.post(
                    url,
                    content=payload,
                    headers=headers,
                    auth=httpx.DigestAuth(username, password),
                )
            if response.status_code >= 400:
                logger.info("ONVIF %s → HTTP %s", url, response.status_code)
                return None
            return _parse(response.content)
    except (httpx.HTTPError, OSError) as exc:
        logger.info("ONVIF so'rov muvaffaqiyatsiz (%s): %s", url, exc)
        return None


def _parse(raw: bytes) -> Optional[ElementTree.Element]:
    """XML javobini xavfsiz o'qiydi.

    Kamera — tarmoqdagi ishonchsiz qurilma.  Ikki himoya: hajm chegarasi
    va DOCTYPE/ENTITY ni rad etish (ular bilan kichik javob xotirada
    gigabaytga yoyilishi mumkin — "billion laughs" hujumi).
    """
    if len(raw) > MAX_RESPONSE_BYTES:
        logger.warning("ONVIF javobi juda katta (%d bayt) — rad etildi", len(raw))
        return None
    head = raw[:4096].lower()
    if b"<!doctype" in head or b"<!entity" in head:
        logger.warning("ONVIF javobida DOCTYPE bor — rad etildi")
        return None
    try:
        return ElementTree.fromstring(raw)  # noqa: S314 — DOCTYPE yuqorida rad etilgan
    except ElementTree.ParseError as exc:
        logger.info("ONVIF javobi XML emas: %s", exc)
        return None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find(root: ElementTree.Element, name: str) -> Optional[ElementTree.Element]:
    """Nom bo'shlig'iga qaramay birinchi mos elementni topadi.

    Har ishlab chiqaruvchi o'z prefiksini ishlatadi (`tds:`, `trt:`,
    `tt:`, ba'zilari umuman prefiksi:z), shuning uchun qat'iy nom
    bo'shlig'i bilan qidirish real kameralarda ishlamaydi.
    """
    for element in root.iter():
        if _local(element.tag) == name:
            return element
    return None


def _find_all(root: ElementTree.Element, name: str) -> List[ElementTree.Element]:
    return [element for element in root.iter() if _local(element.tag) == name]


def _text(root: Optional[ElementTree.Element], name: str) -> str:
    if root is None:
        return ""
    found = _find(root, name)
    return (found.text or "").strip() if found is not None else ""


# ── ONVIF chaqiruvlari ───────────────────────────────────────────────────


def get_device_information(
    service_url: str, username: str = "", password: str = ""
) -> Optional[DeviceInfo]:
    """Ishlab chiqaruvchi, model, proshivka.

    Aynan shu chaqiruv "brendni avtomatik aniqlash" ni haqiqiy qiladi:
    ilgari panelda barcha qurilma "IP kamera / NVR" deb ko'rinardi.
    """
    root = _call(
        service_url,
        '<GetDeviceInformation xmlns="http://www.onvif.org/ver10/device/wsdl"/>',
        username=username,
        password=password,
    )
    if root is None:
        return None
    info = DeviceInfo(
        manufacturer=_text(root, "Manufacturer"),
        model=_text(root, "Model"),
        firmware=_text(root, "FirmwareVersion"),
        serial=_text(root, "SerialNumber"),
    )
    return info if (info.manufacturer or info.model) else None


def get_media_service(service_url: str, username: str = "", password: str = "") -> str:
    """Media xizmatining manzili.

    Ko'pchilik kamerada u qurilma xizmati bilan bir xil manzilda javob
    beradi, lekin qismi (masalan Dahua NVR) alohida yo'l talab qiladi —
    shuning uchun so'rab olamiz, taxmin qilmaymiz.
    """
    root = _call(
        service_url,
        '<GetCapabilities xmlns="http://www.onvif.org/ver10/device/wsdl">'
        "<Category>Media</Category></GetCapabilities>",
        username=username,
        password=password,
    )
    if root is not None:
        media = _find(root, "Media")
        xaddr = _text(media, "XAddr") if media is not None else ""
        if xaddr:
            # Kamera ichki manzilini qaytarishi mumkin (NAT yoki ikki
            # tarmoqli NVR).  Biz **ulanа olgan** hostni saqlab qolamiz,
            # aks holda keyingi so'rov yetib bormaydi.
            return _rehost(xaddr, service_url)
    return service_url


def _rehost(url: str, reference: str) -> str:
    """`url` ning host qismini `reference` nikiga almashtiradi."""
    try:
        target, ref = urlparse(url), urlparse(reference)
    except ValueError:
        return reference
    if not target.hostname or not ref.hostname:
        return reference
    if target.hostname == ref.hostname:
        return url
    netloc = ref.hostname
    if target.port and target.port not in (80, 443):
        netloc = f"{ref.hostname}:{target.port}"
    elif ref.port:
        netloc = f"{ref.hostname}:{ref.port}"
    return urlunparse((target.scheme, netloc, target.path, "", target.query, ""))


def get_profiles(media_url: str, username: str = "", password: str = "") -> List[StreamProfile]:
    """Kameradagi oqimlar ro'yxati: kodek, o'lcham, FPS."""
    root = _call(
        media_url,
        '<GetProfiles xmlns="http://www.onvif.org/ver10/media/wsdl"/>',
        username=username,
        password=password,
    )
    if root is None:
        return []

    profiles: List[StreamProfile] = []
    for node in _find_all(root, "Profiles"):
        token = node.attrib.get("token") or node.attrib.get("Token") or ""
        if not token:
            continue
        encoder = _find(node, "VideoEncoderConfiguration")
        resolution = _find(encoder, "Resolution") if encoder is not None else None
        profiles.append(
            StreamProfile(
                token=token,
                name=_text(node, "Name") or token,
                encoding=_text(encoder, "Encoding").upper() if encoder is not None else "",
                width=_int(_text(resolution, "Width")) if resolution is not None else 0,
                height=_int(_text(resolution, "Height")) if resolution is not None else 0,
                fps=_float(_text(encoder, "FrameRateLimit")) if encoder is not None else 0.0,
            )
        )
    return profiles


def _int(value: str) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _float(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def get_stream_uri(media_url: str, token: str, username: str = "", password: str = "") -> str:
    """Oqimning aniq RTSP manzili.  **Taxmin qilinmaydi** — so'raladi."""
    root = _call(
        media_url,
        '<GetStreamUri xmlns="http://www.onvif.org/ver10/media/wsdl">'
        '<StreamSetup xmlns:tt="http://www.onvif.org/ver10/schema">'
        "<tt:Stream>RTP-Unicast</tt:Stream>"
        "<tt:Transport><tt:Protocol>RTSP</tt:Protocol></tt:Transport>"
        "</StreamSetup>"
        f"<ProfileToken>{_escape(token)}</ProfileToken>"
        "</GetStreamUri>",
        username=username,
        password=password,
    )
    return _text(root, "Uri") if root is not None else ""


# ── Yuqori darajadagi yordamchi ──────────────────────────────────────────


def with_credentials(url: str, username: str, password: str, *, host: str = "") -> str:
    """RTSP manziliga login-parolni qo'shadi (va kerak bo'lsa hostni tuzatadi).

    Ikki haqiqiy muammo hal qilinadi:

    1. `GetStreamUri` manzilni **parolsiz** qaytaradi — OpenCV esa uni
       shundayligicha ochib bo'lmaydi, 401 oladi.
    2. Kamera ba'zan o'zining **ichki** manzilini yozadi (`192.168.1.10`),
       biz esa unga boshqa manzil orqali ulanganmiz.  U holda manzil
       ishlamaydi va sabab mutlaqo tushunarsiz bo'lardi.
    """
    try:
        parts = urlparse(url)
    except ValueError:
        return url
    if not parts.hostname:
        return url
    hostname = host or parts.hostname
    netloc = f"{hostname}:{parts.port}" if parts.port else hostname
    if username:
        netloc = f"{quote(username, safe='')}:{quote(password, safe='')}@{netloc}"
    return urlunparse((parts.scheme, netloc, parts.path, "", parts.query, ""))


def pick_best_profile(profiles: List[StreamProfile]) -> Optional[StreamProfile]:
    """Tahlil uchun eng mos oqimni tanlaydi.

    Tartib ataylab shunday:

    1. **H.264 substream** — ideal: yengil dekodlash, kichik kadr.
    2. H.264 (har qanday o'lcham) — ishlaydi, protsessorga og'irroq.
    3. Qolgani (H.265/MJPEG) — oxirgi chora; ishlamasligi mumkin va
       mijozga bu haqda ogohlantirish beriladi.

    H.265 ataylab oxirida: to'plamdagi OpenCV uni har doim ham
    dekodlamaydi, dekodlagan taqdirda ham eski protsessorda tahlilga
    joy qolmaydi.
    """
    if not profiles:
        return None
    with_uri = [p for p in profiles if p.uri] or profiles

    def rank(profile: StreamProfile) -> Tuple[int, int]:
        h264 = profile.encoding in ("H264", "H.264", "AVC")
        if h264 and profile.is_substream:
            group = 0
        elif h264:
            group = 1
        elif profile.encoding in ("JPEG", "MJPEG"):
            group = 2
        else:
            group = 3
        # Guruh ichida kichikroq kadr afzal.
        return (group, profile.pixels or 10**9)

    return sorted(with_uri, key=rank)[0]


def compatibility_note(profile: StreamProfile) -> Tuple[str, str]:
    """Oqim mos keladimi — mijoz tilida.  `(ogohlantirish, maslahat)`.

    Ikkalasi bo'sh bo'lsa — muammo yo'q.  Bu tekshiruv **kamera
    qo'shilgunga qadar** ishlaydi: aks holda mijoz hisobot bo'sh
    chiqqanda, bir necha kundan keyin bilardi.
    """
    if profile.encoding in ("H265", "H.265", "HEVC"):
        return (
            "Bu oqim H.265 (HEVC) formatida.",
            "Dastur H.264 bilan ishonchli ishlaydi. NVR menyusida shu kamera "
            "uchun substream'ni H.264 ga o'zgartiring: "
            "Configuration → Video → Sub Stream → Encoding: H.264.",
        )
    if profile.encoding in ("JPEG", "MJPEG"):
        return (
            "Bu oqim MJPEG formatida.",
            "MJPEG tarmoqni ko'p band qiladi. Iloji bo'lsa H.264 substream'ni "
            "yoqing — tasvir sifati bir xil, yuk esa bir necha barobar kam.",
        )
    if profile.pixels > 1280 * 720:
        return (
            f"Bu oqim katta o'lchamda ({profile.width}×{profile.height}).",
            "Tahlil uchun substream (640×360) yetarli va kompyuterni ancha "
            "kam band qiladi. NVR'da substream'ni yoqing.",
        )
    return ("", "")


def describe(
    host: str,
    *,
    username: str = "",
    password: str = "",
    xaddr: str = "",
    port: int = 80,
) -> OnvifResult:
    """Kamerani ONVIF orqali to'liq so'rab chiqadi.

    Bitta chaqiruvda: brend, oqimlar ro'yxati va har birining RTSP
    manzili.  Sehrgar shu natijadan foydalanadi — yo'l taxmin qilish
    endi faqat **zaxira** yo'l.
    """
    candidates: List[str] = []
    if xaddr:
        candidates.append(_rehost(xaddr, f"http://{host}:{port}/"))
    candidates.extend(f"http://{host}:{port}{path}" for path in DEVICE_SERVICE_PATHS)
    if port != 80:
        candidates.extend(f"http://{host}{path}" for path in DEVICE_SERVICE_PATHS)

    seen: set[str] = set()
    for service_url in candidates:
        if service_url in seen:
            continue
        seen.add(service_url)

        info = get_device_information(service_url, username, password)
        if info is None:
            continue

        media_url = get_media_service(service_url, username, password)
        profiles = get_profiles(media_url, username, password)
        if not profiles:
            return OnvifResult(
                ok=False,
                device=info,
                error="Kamera javob berdi, lekin oqimlar ro'yxatini bermadi.",
                hint="Kamera menyusida ONVIF uchun foydalanuvchiga "
                "«Media» huquqi berilganini tekshiring.",
            )

        filled = [
            StreamProfile(
                token=profile.token,
                name=profile.name,
                encoding=profile.encoding,
                width=profile.width,
                height=profile.height,
                fps=profile.fps,
                uri=get_stream_uri(media_url, profile.token, username, password),
            )
            for profile in profiles
        ]
        logger.info(
            "ONVIF: %s — %d ta oqim (%s)",
            info.brand or host,
            len(filled),
            ", ".join(f"{p.encoding} {p.width}x{p.height}" for p in filled) or "noma'lum",
        )
        return OnvifResult(ok=True, device=info, profiles=filled)

    return OnvifResult(
        ok=False,
        error="Kamera ONVIF so'roviga javob bermadi.",
        hint="Kamera menyusida ONVIF yoqilganini va login-parol to'g'ri "
        "ekanini tekshiring. Ba'zi kameralarda ONVIF uchun alohida "
        "foydalanuvchi yaratish kerak.",
    )


# ── ONVIF'siz brend aniqlash ─────────────────────────────────────────────
#
# ONVIF o'chirilgan yoki parol noma'lum bo'lsa ham brendni bilish mumkin:
# qurilmaning o'zi har javobda o'zini tanitadi.  Bu bepul ma'lumot ilgari
# umuman ishlatilmasdi va panelda hamma narsa "IP kamera / NVR" edi.

#: Javob matnidagi belgi → brend nomi.  Tartib muhim: aniqrog'i oldinda.
FINGERPRINTS: Tuple[Tuple[str, str], ...] = (
    ("hikvision", "Hikvision"),
    ("hilook", "HiLook"),
    ("app-webs", "Hikvision"),  # Hikvision veb-serveri
    ("ip camera(", "Hikvision"),  # RTSP realm="IP Camera(12345)"
    ("dahua", "Dahua"),
    ("imou", "IMOU"),
    ("lechange", "IMOU"),
    ("uniview", "Uniview"),
    ("unv", "Uniview"),
    ("tp-link", "TP-Link"),
    ("tapo", "TP-Link Tapo"),
    ("vigi", "TP-Link VIGI"),
    ("hipcam", "Xiongmai"),
    ("xiongmai", "Xiongmai"),
    ("besder", "Besder"),
    ("axis", "Axis"),
    ("bosch", "Bosch"),
    ("reolink", "Reolink"),
    ("ezviz", "EZVIZ"),
    ("h264dvrrtspserver", "Xiongmai / DVR"),
)


def brand_from_banner(text: str) -> str:
    """Javob matnidan brendni taxmin qiladi.

    Manba ikkita bo'ladi: RTSP `DESCRIBE` javobining `Server:` sarlavhasi
    va 401 dagi `WWW-Authenticate: Digest realm="..."`.  Hikvision o'z
    realm'ida `IP Camera(...)` yozadi, Dahua `Server: Dahua Rtsp Server`
    beradi — ya'ni parolni bilmasdan ham brend ma'lum bo'ladi.
    """
    if not text:
        return ""
    lowered = text.lower()
    for needle, brand in FINGERPRINTS:
        if needle in lowered:
            return brand
    return ""


def brand_from_http(host: str, port: int = 80, timeout: float = 2.0) -> str:
    """Veb-interfeys sarlavhalaridan brendni taxmin qiladi."""
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            response = client.get(f"http://{host}:{port}/")
    except (httpx.HTTPError, OSError):
        return ""
    haystack = " ".join(
        [
            response.headers.get("server", ""),
            response.headers.get("www-authenticate", ""),
            response.text[:2000] if "text" in response.headers.get("content-type", "") else "",
        ]
    )
    return brand_from_banner(haystack)


def brand_hint(host: str, *, rtsp_banner: str = "", http_port: int = 80) -> str:
    """Brendni bor manbalardan aniqlaydi.  Topilmasa bo'sh satr."""
    return brand_from_banner(rtsp_banner) or brand_from_http(host, http_port)


#: Brend nomidan `KNOWN_PATHS` ichidagi yo'l shabloniga ko'prik.
#: Brend ma'lum bo'lsa o'sha brendning yo'li **birinchi** sinaladi —
#: o'nta variantni ketma-ket sinash o'rniga bitta urinishda topiladi.
#: Qiymatlar ikkala ro'yxatdagi nomlarga mos kelishi kerak:
#: `discovery.COMMON_RTSP_TEMPLATES` ("XM Substream") va
#: `camera_probe.KNOWN_PATHS` ("Xiongmai / Besder") — shuning uchun
#: bir brend uchun bir necha kalit.
BRAND_PATH_ORDER: Dict[str, Tuple[str, ...]] = {
    "Hikvision": ("Hikvision",),
    "HiLook": ("Hikvision",),
    "EZVIZ": ("Hikvision",),
    "Dahua": ("Dahua",),
    "IMOU": ("Dahua",),
    "Uniview": ("Uniview",),
    "TP-Link": ("TP-Link", "Tapo"),
    "TP-Link Tapo": ("TP-Link", "Tapo"),
    "TP-Link VIGI": ("TP-Link", "Tapo"),
    "Xiongmai": ("Xiongmai", "XM "),
    "Besder": ("Xiongmai", "XM "),
    "Xiongmai / DVR": ("Xiongmai", "XM "),
    "Reolink": ("Xiongmai", "XM "),
}


def path_order_for(brand: str) -> Tuple[str, ...]:
    """Brend nomiga mos yo'l guruhlarini qaytaradi (ustuvorlik uchun)."""
    if not brand:
        return ()
    for name, order in BRAND_PATH_ORDER.items():
        if name.lower() in brand.lower():
            return order
    # `GetDeviceInformation` to'liq nom beradi ("Hangzhou Hikvision…"),
    # shuning uchun belgilar bo'yicha ham qaraymiz.
    detected = brand_from_banner(brand)
    return BRAND_PATH_ORDER.get(detected, ()) if detected else ()


def normalise_brand(raw: str) -> str:
    """Uzun rasmiy nomni qisqartiradi.

    `GetDeviceInformation` ko'pincha "Hangzhou Hikvision Digital
    Technology Co.,Ltd." qaytaradi — panelda bu bir qatorga sig'maydi va
    mijozga hech narsa aytmaydi.
    """
    cleaned = re.sub(r"\s+", " ", (raw or "")).strip(" .,")
    if not cleaned:
        return ""
    short = brand_from_banner(cleaned)
    return short or cleaned[:40]
