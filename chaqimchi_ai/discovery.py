"""Lokal tarmoqdagi IP kameralar va NVR larni avtomatik aniqlash (Auto-discovery) moduli.

ONVIF WS-Discovery (UDP Multicast) va standart RTSP/HTTP port skanerlash
orqali do'kondagi kameralarni tezda topadi va substream oqimlarini taklif qiladi.
"""

from __future__ import annotations

import asyncio
import logging
import re
import socket
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ONVIF WS-Discovery multicast manzili va porti
WS_DISCOVERY_IP = "239.255.255.250"
WS_DISCOVERY_PORT = 3702

WS_PROBE_XML = """<?xml version="1.0" encoding="utf-8"?>
<Envelope xmlns:tds="http://www.onvif.org/ver10/device/wsdl"
          xmlns="http://www.w3.org/2003/05/soap-envelope">
  <Header>
    <wsa:MessageID xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing">
      uuid:d29944a7-9662-4214-b513-2d6840f39645
    </wsa:MessageID>
    <wsa:To xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing">
      urn:schemas-xmlsoap-org:ws:2005:04:discovery
    </wsa:To>
    <wsa:Action xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing">
      http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe
    </wsa:Action>
  </Header>
  <Body>
    <Probe xmlns="http://schemas.xmlsoap.org/ws/2005/04/discovery">
      <Types>tds:Device</Types>
    </Probe>
  </Body>
</Envelope>"""

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


async def scan_local_network_for_cameras(max_concurrent: int = 40) -> List[Dict[str, Any]]:
    """Lokal tarmoqni (C-class /24) skanerlab, kamera xizmatlari ochiq qurilmalarni topadi."""
    local_ip, candidate_ips = get_local_ip_range()
    if not candidate_ips:
        logger.info("Lokal tarmoq diapazoni topilmadi (IP: %s)", local_ip)
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


def onvif_ws_discovery(timeout_sec: float = 2.0) -> List[Dict[str, Any]]:
    """Sinxron UDP multicast orqali ONVIF WS-Discovery so'rovini yuboradi va javoblarni yig'adi."""
    discovered = []
    seen_xaddrs = set()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.settimeout(timeout_sec)
    # TTL multicast
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    except Exception:
        pass

    try:
        sock.sendto(WS_PROBE_XML.encode("utf-8"), (WS_DISCOVERY_IP, WS_DISCOVERY_PORT))

        while True:
            try:
                data, addr = sock.recvfrom(65535)
                text = data.decode("utf-8", errors="ignore")

                # XAddrs qidirish (<d:XAddrs>http://192.168.1.100:80/onvif/device_service</d:XAddrs>)
                xaddrs_match = re.search(r"XAddrs>([^<]+)<", text, re.IGNORECASE)
                scopes_match = re.search(r"Scopes>([^<]+)<", text, re.IGNORECASE)

                xaddrs = xaddrs_match.group(1).strip() if xaddrs_match else ""
                scopes = scopes_match.group(1).strip() if scopes_match else ""

                device_ip = addr[0]
                if xaddrs:
                    first_url = xaddrs.split()[0]
                    parsed = urllib.parse.urlparse(first_url)
                    if parsed.hostname:
                        device_ip = parsed.hostname

                if device_ip not in seen_xaddrs:
                    seen_xaddrs.add(device_ip)
                    # Scopes ichidan model/brand qidirish
                    vendor = "ONVIF Device"
                    for item in scopes.split():
                        if "hardware/" in item:
                            vendor = urllib.parse.unquote(item.split("hardware/")[-1])
                        elif "name/" in item:
                            vendor = urllib.parse.unquote(item.split("name/")[-1])

                    discovered.append(
                        {
                            "ip": device_ip,
                            "xaddrs": xaddrs,
                            "vendor_hint": vendor,
                            "has_onvif": True,
                            "has_rtsp": True,
                            "rtsp_port": 554,
                        }
                    )
            except (socket.timeout, TimeoutError):
                break
            except Exception as e:
                logger.debug("WS-Discovery paketida xatolik: %s", e)
                break
    except Exception as exc:
        logger.warning("WS-Discovery xatoligi: %s", exc)
    finally:
        sock.close()

    return discovered


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

    # Har bir topilgan qurilma uchun tavsiya etilgan RTSP substream URL lari shablonini tuzish
    result_list = []
    for ip, info in combined.items():
        templates = []
        for tmpl in COMMON_RTSP_TEMPLATES:
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
