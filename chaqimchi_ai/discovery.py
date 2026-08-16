"""Lokal tarmoqdagi IP kameralar va NVR larni avtomatik aniqlash (Auto-discovery) moduli.

ONVIF WS-Discovery (UDP Multicast) va standart RTSP/HTTP port skanerlash
orqali do'kondagi kameralarni tezda topadi va substream oqimlarini taklif qiladi.
"""

from __future__ import annotations

import asyncio
import logging
import re
import socket
import time
import urllib.parse
import uuid
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ONVIF WS-Discovery multicast manzili va porti
WS_DISCOVERY_IP = "239.255.255.250"
WS_DISCOVERY_PORT = 3702

#: Probe paketining andozasi.
#:
#: Ikki narsa ataylab shunday:
#:
#: 1. `MessageID` **har safar yangi** bo'ladi.  Ilgari u qattiq yozilgan
#:    qiymat edi va ko'p kamera takrorlangan MessageID ni "shu so'rovga
#:    allaqachon javob berdim" deb tashlab yuborardi — natijada qidiruv
#:    faqat birinchi marta ishlab, keyin doim bo'sh qaytardi.
#: 2. `Types` filtri **bo'sh** qoldiriladi.  Ilgari `tds:Device` yozilgan
#:    edi, kameralar esa o'zini `dn:NetworkVideoTransmitter` deb e'lon
#:    qiladi va bunday filtrga javob bermaydi.  Filtrsiz Probe ONVIF
#:    standartida "hammasi mos" degani.
WS_PROBE_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<Envelope xmlns="http://www.w3.org/2003/05/soap-envelope"
          xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing">
  <Header>
    <wsa:MessageID>uuid:{message_id}</wsa:MessageID>
    <wsa:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</wsa:To>
    <wsa:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</wsa:Action>
  </Header>
  <Body>
    <Probe xmlns="http://schemas.xmlsoap.org/ws/2005/04/discovery"
           xmlns:dn="http://www.onvif.org/ver10/network/wsdl">{types}</Probe>
  </Body>
</Envelope>"""

#: Yuboriladigan filtrlar.  Filtrsizga javob bermaydigan qaysar
#: qurilmalar uchun aniq tur ham yuboriladi — ikkalasi arzon.
PROBE_TYPES: Tuple[str, ...] = (
    "",
    "<Types>dn:NetworkVideoTransmitter</Types>",
)

#: Bitta filtr necha marta yuboriladi.  WS-Discovery UDP ustida ishlaydi,
#: ya'ni paket yo'qolishi **odatiy hol** — ayniqsa do'kon kommutatorida.
#: Standartning o'zi ham takroriy yuborishni tavsiya qiladi.
PROBE_REPEATS = 2

# Ko'p uchraydigan kamera brendlarining standart RTSP substream yo'llari
COMMON_RTSP_TEMPLATES = [
    # Hikvision / HiLook
    {"name": "Hikvision Substream", "path": "/Streaming/Channels/102"},
    {"name": "Hikvision Substream (Ch2)", "path": "/Streaming/Channels/202"},
    {"name": "Hikvision Mainstream", "path": "/Streaming/Channels/101"},
    # Dahua / IMOU
    {"name": "Dahua Substream", "path": "/cam/realmonitor?channel=1&subtype=1"},
    {"name": "Dahua Mainstream", "path": "/cam/realmonitor?channel=1&subtype=0"},
    # Uniview (UNV)
    {"name": "Uniview Substream", "path": "/unicast/c1/s1/live"},
    {"name": "Uniview Mainstream", "path": "/unicast/c1/s0/live"},
    # Xiongmai / XM / Besder / H.264 DVR
    {"name": "XM Substream", "path": "/h264Preview_01_sub"},
    {"name": "XM Mainstream", "path": "/h264Preview_01_main"},
    # TP-Link Tapo / Vigi
    {"name": "Tapo Substream", "path": "/stream2"},
    {"name": "Tapo Mainstream", "path": "/stream1"},
    # Standart umumiy RTSP
    {"name": "Generic Live 1", "path": "/live/ch0_1"},
    {"name": "Generic Live 0", "path": "/live/ch0_0"},
    {"name": "Generic RTSP", "path": "/live/av0"},
    {"name": "Generic Stream", "path": "/onvif1"},
]


def get_local_ip_range() -> Tuple[str, List[str]]:
    """Qurilmaning lokal IP manzili va tarmoq prefiksini aniqlaydi."""
    local_ip = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    if local_ip.startswith("127.") or local_ip == "0.0.0.0":
        return local_ip, []

    parts = local_ip.split(".")
    if len(parts) != 4:
        return local_ip, []

    subnet_prefix = f"{parts[0]}.{parts[1]}.{parts[2]}"
    candidate_ips = [
        f"{subnet_prefix}.{i}" for i in range(1, 255) if f"{subnet_prefix}.{i}" != local_ip
    ]
    return local_ip, candidate_ips


async def _probe_tcp_port(ip: str, port: int, timeout: float = 0.5) -> bool:
    """Berilgan IP va port ochiqligini tekshiradi."""
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout=timeout)
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False


async def probe_ip_camera_services(ip: str) -> Optional[Dict[str, Any]]:
    """Bitta IP manzilda RTSP yoki ONVIF xizmatlari mavjudligini aniqlaydi."""
    # Odatdagi kamera portlari: 554 (RTSP), 8554 (RTSP alt), 80 (HTTP/ONVIF), 8000 (Hikvision SDK), 8899 (ONVIF)
    rtsp_open = await _probe_tcp_port(ip, 554, timeout=0.4)
    if not rtsp_open:
        rtsp_open = await _probe_tcp_port(ip, 8554, timeout=0.3)

    onvif_open = (
        await _probe_tcp_port(ip, 80, timeout=0.3)
        or await _probe_tcp_port(ip, 8899, timeout=0.3)
        or await _probe_tcp_port(ip, 8000, timeout=0.3)
    )

    if rtsp_open or onvif_open:
        return {
            "ip": ip,
            "rtsp_port": 554 if rtsp_open else 8554,
            "has_rtsp": rtsp_open,
            "has_onvif": onvif_open,
            "vendor_hint": "IP Camera / NVR",
        }
    return None


async def scan_local_network_for_cameras(max_concurrent: int = 64) -> List[Dict[str, Any]]:
    """Lokal tarmoqlarni (/24) skanerlab, kamera xizmatlari ochiq qurilmalarni topadi.

    **Barcha** interfeys tekshiriladi: NVR ko'pincha internetdan alohida
    kabelda turadi va faqat standart yo'nalishni skanerlash uni
    ko'rmasdan qolardi.
    """
    candidate_ips: List[str] = []
    own = set(local_ipv4_addresses())
    # Ikkitadan ortiq tarmoqni skanerlash mijozni uzoq kutdiradi va
    # amalda uchramaydi.
    for local_ip in list(own)[:2]:
        parts = local_ip.split(".")
        if len(parts) != 4:
            continue
        prefix = f"{parts[0]}.{parts[1]}.{parts[2]}"
        candidate_ips.extend(
            f"{prefix}.{i}" for i in range(1, 255) if f"{prefix}.{i}" not in own
        )

    if not candidate_ips:
        logger.info("Lokal tarmoq diapazoni topilmadi")
        return []

    semaphore = asyncio.Semaphore(max_concurrent)

    async def _check(ip: str):
        async with semaphore:
            return await probe_ip_camera_services(ip)

    tasks = [_check(ip) for ip in candidate_ips]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    found = []
    for res in results:
        if isinstance(res, dict) and res is not None:
            found.append(res)

    logger.info("Lokal tarmoqda %d ta potentsial kamera topildi", len(found))
    return sorted(found, key=lambda x: [int(p) for p in x["ip"].split(".") if p.isdigit()] or [0])


def local_ipv4_addresses() -> List[str]:
    """Kompyuterning barcha IPv4 manzillari.

    Nega kerak: do'kon kompyuterida ko'pincha **ikkita** tarmoq bo'ladi —
    internet uchun Wi-Fi va NVR uchun alohida kabel.  Multicast paket
    faqat bitta interfeysdan chiqadi, standart yo'nalish esa odatda
    internetga qaraydi.  Ya'ni NVR turgan tarmoqqa so'rov **umuman
    yetib bormasdi** va "hech narsa topilmadi" chiqardi.
    """
    addresses: List[str] = []

    # Standart yo'nalishdagi manzil (odatda internetga qaragani).
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80))
        addresses.append(probe.getsockname()[0])
        probe.close()
    except OSError:
        pass

    # Qolgan interfeyslar.
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addresses.append(info[4][0])
    except (OSError, socket.gaierror):
        pass

    unique = []
    for address in addresses:
        if address not in unique and not address.startswith(("127.", "169.254.")):
            unique.append(address)
    return unique


def _probe_packets() -> List[bytes]:
    """Yuboriladigan Probe paketlari — har birida yangi MessageID."""
    packets = []
    for types in PROBE_TYPES:
        for _ in range(PROBE_REPEATS):
            packets.append(
                WS_PROBE_TEMPLATE.format(message_id=uuid.uuid4(), types=types).encode("utf-8")
            )
    return packets


def _parse_probe_match(text: str, sender_ip: str) -> Optional[Dict[str, Any]]:
    """ProbeMatch javobidan IP, manzil va brendni ajratadi."""
    xaddrs_match = re.search(r"XAddrs>([^<]+)<", text, re.IGNORECASE)
    scopes_match = re.search(r"Scopes>([^<]+)<", text, re.IGNORECASE)
    if not xaddrs_match and "probematch" not in text.lower():
        return None

    xaddrs = xaddrs_match.group(1).strip() if xaddrs_match else ""
    scopes = scopes_match.group(1).strip() if scopes_match else ""

    device_ip = sender_ip
    if xaddrs:
        parsed = urllib.parse.urlparse(xaddrs.split()[0])
        if parsed.hostname:
            device_ip = parsed.hostname

    return {
        "ip": device_ip,
        "xaddrs": xaddrs,
        "vendor_hint": vendor_from_scopes(scopes),
        "has_onvif": True,
        "has_rtsp": True,
        "rtsp_port": 554,
    }


def vendor_from_scopes(scopes: str) -> str:
    """ONVIF `Scopes` satridan qurilma nomini ajratadi.

    Scope'lar `onvif://www.onvif.org/name/HIKVISION` ko'rinishida keladi.
    Ilgari ro'yxat bo'ylab yurilib, **oxirgi** mos scope g'olib chiqardi —
    ya'ni foydali `hardware/DS-2CD2043` ni keyingi `location/…` bosib
    ketishi mumkin edi.  Endi tartib aniq: nom, keyin model.
    """
    found: Dict[str, str] = {}
    for item in scopes.split():
        for key in ("name", "hardware"):
            marker = f"/{key}/"
            if marker in item:
                value = urllib.parse.unquote(item.split(marker, 1)[-1]).strip()
                if value and key not in found:
                    found[key] = value
    parts = [found.get("name", ""), found.get("hardware", "")]
    label = " ".join(part for part in parts if part).strip()
    return label or "ONVIF qurilma"


def onvif_ws_discovery(timeout_sec: float = 2.0) -> List[Dict[str, Any]]:
    """WS-Discovery: barcha tarmoq interfeyslariga Probe yuboradi."""
    interfaces = local_ipv4_addresses() or [""]
    discovered: Dict[str, Dict[str, Any]] = {}

    for source_ip in interfaces:
        for device in _discover_on_interface(source_ip, timeout_sec):
            discovered.setdefault(device["ip"], device)

    logger.info("WS-Discovery: %d ta ONVIF qurilma topildi", len(discovered))
    return list(discovered.values())


def _discover_on_interface(source_ip: str, timeout_sec: float) -> List[Dict[str, Any]]:
    """Bitta interfeysdan Probe yuborib javoblarni yig'adi."""
    found: List[Dict[str, Any]] = []
    seen: set = set()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        except OSError:
            pass
        if source_ip:
            # Paket aynan shu interfeysdan chiqishini majburlaymiz.
            try:
                sock.setsockopt(
                    socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(source_ip)
                )
                sock.bind((source_ip, 0))
            except OSError as exc:
                logger.debug("Interfeys %s ishlatilmadi: %s", source_ip, exc)
                return []

        for packet in _probe_packets():
            try:
                sock.sendto(packet, (WS_DISCOVERY_IP, WS_DISCOVERY_PORT))
            except OSError as exc:
                logger.debug("Probe yuborilmadi (%s): %s", source_ip or "default", exc)
                return []

        deadline = time.monotonic() + timeout_sec
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            sock.settimeout(remaining)
            try:
                data, addr = sock.recvfrom(65535)
            except (socket.timeout, TimeoutError):
                break
            except OSError as exc:
                logger.debug("WS-Discovery o'qishda xato: %s", exc)
                break

            # Bitta buzuq paket butun qidiruvni to'xtatmasligi kerak:
            # ilgari shu yerdagi `break` tufayli bitta g'alati javob
            # qolgan barcha kamerani ko'rinmas qilib qo'yardi.
            try:
                device = _parse_probe_match(data.decode("utf-8", errors="ignore"), addr[0])
            except Exception as exc:  # noqa: BLE001 — javob ishonchsiz manbadan
                logger.debug("ProbeMatch o'qilmadi: %s", exc)
                continue

            if device and device["ip"] not in seen:
                seen.add(device["ip"])
                found.append(device)
    finally:
        sock.close()

    return found


async def discover_cameras_all(timeout_sec: float = 3.0) -> List[Dict[str, Any]]:
    """Ham WS-Discovery, ham lokal tarmoq port skanerlashni birlashtirib eng to'liq ro'yxatni qaytaradi."""
    # 1. WS-Discovery (Thread pool orqali)
    onvif_devices = await asyncio.to_thread(onvif_ws_discovery, min(timeout_sec, 2.0))

    # 2. Subnet port scan
    scanned_devices = await scan_local_network_for_cameras()

    # Birlashtirish (IP bo'yicha de-duplication)
    combined: Dict[str, Dict[str, Any]] = {}

    for d in scanned_devices:
        combined[d["ip"]] = d

    for d in onvif_devices:
        ip = d["ip"]
        if ip in combined:
            combined[ip].update(d)
        else:
            combined[ip] = d

    # 3. Brendni aniqlash — parolsiz, qurilmaning o'z javoblaridan.
    await asyncio.gather(
        *(asyncio.to_thread(_identify_brand, info) for info in combined.values()),
        return_exceptions=True,
    )

    # Har bir topilgan qurilma uchun tavsiya etilgan RTSP substream URL lari shablonini tuzish
    result_list = []
    for ip, info in combined.items():
        templates = []
        for tmpl in _templates_for(info.get("brand", "")):
            templates.append(
                {
                    "name": tmpl["name"],
                    "url": f"rtsp://{ip}:{info.get('rtsp_port', 554)}{tmpl['path']}",
                    "path": tmpl["path"],
                }
            )
        info["suggested_urls"] = templates
        result_list.append(info)

    return sorted(
        result_list, key=lambda x: [int(p) for p in x["ip"].split(".") if p.isdigit()] or [0]
    )


def _identify_brand(info: Dict[str, Any]) -> None:
    """Qurilmaning brendini aniqlab `info` ga yozadi (joyida o'zgartiradi).

    Ilgari panelda har bir topilgan qurilma "IP kamera / NVR" deb
    ko'rinardi — ya'ni ro'yxat mijozga hech narsa aytmasdi va u qaysi
    biri kamerayu qaysi biri printer ekanini bilmasdi.

    Uch manba ketma-ket sinaladi (birinchi topilgani yetarli):
    RTSP salomlashuvi → ONVIF scope nomi → veb-interfeys sarlavhasi.
    Hech biri parol talab qilmaydi.
    """
    from chaqimchi_ai.local import camera_probe, onvif_client

    ip = info["ip"]
    brand = ""

    if info.get("has_rtsp"):
        # Parolsiz `DESCRIBE` 401 qaytaradi, lekin javob ichida
        # `Server:` va `realm="…"` bo'ladi — brend aynan shu yerda.
        _, raw = camera_probe.rtsp_describe(
            f"rtsp://{ip}:{info.get('rtsp_port', 554)}/", timeout_sec=2.0
        )
        brand = onvif_client.brand_from_banner(raw)

    if not brand:
        brand = onvif_client.brand_from_banner(info.get("vendor_hint", ""))

    if not brand and info.get("has_onvif"):
        brand = onvif_client.brand_from_http(ip)

    info["brand"] = brand
    if brand:
        info["vendor_hint"] = brand
    elif not info.get("vendor_hint") or info["vendor_hint"] == "IP Camera / NVR":
        info["vendor_hint"] = "IP kamera / NVR"


def _templates_for(brand: str) -> List[Dict[str, str]]:
    """Yo'l shablonlarini brend bo'yicha tartiblaydi.

    Brend ma'lum bo'lsa uning yo'llari birinchi sinaladi: o'nta variantni
    ketma-ket sinash o'rniga birinchisidayoq topiladi va mijoz bir daqiqa
    emas, bir necha soniya kutadi.
    """
    from chaqimchi_ai.local import onvif_client

    order = onvif_client.path_order_for(brand)
    if not order:
        return list(COMMON_RTSP_TEMPLATES)
    preferred = [
        tmpl
        for tmpl in COMMON_RTSP_TEMPLATES
        if any(key.lower() in tmpl["name"].lower() for key in order)
    ]
    rest = [tmpl for tmpl in COMMON_RTSP_TEMPLATES if tmpl not in preferred]
    return preferred + rest
