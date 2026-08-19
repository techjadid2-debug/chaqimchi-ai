"""Lokal Chaqimchi AI — sozlash ustasi va do'kon paneli.

Ishga tushirish:

    python -m chaqimchi_ai.local.app          # → http://127.0.0.1:8760

`127.0.0.1` ataylab: bu do'kon kompyuteridagi shaxsiy panel, tarmoqqa
ochilishi shart emas.  Shuning uchun Windows firewall qoidasi ham kerak
emas — eski o'rnatuvchi 8750 portni butun tarmoq uchun ochib qo'yardi.

Portning cloud (8750) dan farqli bo'lishi ham ataylab: bir kompyuterda
ikkalasini ishlatib ko'rish kerak bo'lsa, ular urishmaydi.
"""

from __future__ import annotations

import functools
import json
import logging
import os
import re
import sqlite3
import threading
import time
import webbrowser
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from chaqimchi_ai import __version__
from chaqimchi_ai.limits import NVR_SCAN_CHANNELS, SHOP_MAX_CAMERAS
from chaqimchi_ai.local import (
    camera_probe,
    cloud_config,
    cloud_link,
    config_store,
    onvif_client,
    paths,
)
from chaqimchi_ai.local.supervisor import RetailSupervisor

logger = logging.getLogger(__name__)

PORT = int(os.environ.get("CHAQIMCHI_LOCAL_PORT", "8760"))
STATIC_DIR = Path(__file__).resolve().parent / "static"

#: Do'kon profili: ko'pi bilan 4 kamera qabul qilingan (`docs/DOKON_MVP.md`).
#: Sehrgar bundan ortig'ini taklif qilmaydi — o'lchanmagan sig'imni va'da
#: qilish keyin "sekin ishlaydi" degan shikoyatga aylanadi.
#: Qiymat yagona manbadan: `chaqimchi_ai/limits.py`.
MAX_CAMERAS = SHOP_MAX_CAMERAS

supervisor = RetailSupervisor()

app = FastAPI(title="Chaqimchi AI — lokal", docs_url=None, redoc_url=None)

if STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR)), name="assets")


# ── Sahifalar ────────────────────────────────────────────────────────────


def _page(name: str) -> FileResponse:
    page = STATIC_DIR / name
    if not page.is_file():
        raise HTTPException(404, "Sahifa topilmadi")
    return FileResponse(page)


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    """Sozlash tugallangan bo'lsa panel, aks holda sehrgar.

    Mijoz yorliqni bosganda "qayerga borishim kerak?" degan savol
    bo'lmasligi kerak — dastur o'zi to'g'ri joyni ochadi.
    """
    return _page("panel.html" if config_store.is_ready() else "setup.html")


@app.get("/setup", include_in_schema=False)
async def setup_page() -> FileResponse:
    return _page("setup.html")


@app.get("/panel", include_in_schema=False)
async def panel_page() -> FileResponse:
    return _page("panel.html")


@app.get("/health", include_in_schema=False)
async def health() -> Dict[str, Any]:
    return {"ok": True, "service": "chaqimchi-local"}


# ── Sozlama ──────────────────────────────────────────────────────────────


@app.get("/api/setup/summary")
async def setup_summary() -> Dict[str, Any]:
    return {**config_store.summary(), "max_cameras": MAX_CAMERAS}


@app.get("/api/setup/hardware")
async def hardware_capacity() -> Dict[str, Any]:
    """Bu kompyuter nechta kamerani ko'taradi.

    Sehrgar buni kamera qo'shishdan **oldin** ko'rsatadi: zaif mashinaga
    to'rtta kamera qo'shilsa hisobot jimgina to'liqsiz bo'lardi va buni
    hech kim sezmasdi.
    """
    import anyio

    from chaqimchi_ai.local import hardware

    capacity = await anyio.to_thread.run_sync(
        functools.partial(hardware.measure, str(paths.data_dir()))
    )
    return {"ok": True, **capacity.as_dict()}


@app.post("/api/setup/scan")
async def scan_network() -> Dict[str, Any]:
    """Lokal tarmoqdagi kamera va NVR larni qidiradi.

    Bu yerda xato **yutilmaydi**.  Ilgari cloud'dagi shu nomli endpoint
    mavjud bo'lmagan funksiyani chaqirardi va `except` hamma narsani yutib,
    doim bo'sh ro'yxat qaytarardi — natijada "kameralarni avtomatik topadi"
    degan va'da hech qachon ishlamagan, testlar esa yashil turgan.
    """
    from chaqimchi_ai.discovery import discover_cameras_all

    devices = await discover_cameras_all(timeout_sec=3.0)
    return {
        "ok": True,
        "count": len(devices),
        "devices": [
            {
                "ip": device["ip"],
                "vendor": device.get("vendor_hint") or "IP kamera / NVR",
                "has_onvif": bool(device.get("has_onvif")),
                "has_rtsp": bool(device.get("has_rtsp")),
                "rtsp_port": device.get("rtsp_port", 554),
                # ONVIF so'rovi aynan topilgan portga borsin: ilgari bu
                # ma'lumot yo'qolib, so'rov doim 80-portga ketardi.
                "onvif_port": device.get("onvif_port", 0),
                "xaddrs": device.get("xaddrs", ""),
                "suggested_urls": device.get("suggested_urls", []),
            }
            for device in devices
        ],
    }


class RtspTemplateBody(BaseModel):
    brand: str = Field(pattern="^(hikvision|dahua|uniview)$")
    host: str = Field(min_length=3, max_length=120)
    port: int = Field(default=554, ge=1, le=65535)
    username: str = Field(default="", max_length=64)
    password: str = Field(default="", max_length=128)
    channel: int = Field(default=1, ge=1, le=64)


@app.post("/api/setup/rtsp-template")
async def rtsp_template(body: RtspTemplateBody) -> Dict[str, Any]:
    """Brend bo'yicha RTSP manzilini yig'adi — mijoz uni yodlashi shart emas."""
    try:
        url = camera_probe.build_rtsp(
            brand=body.brand,
            host=body.host,
            port=body.port,
            username=body.username,
            password=body.password,
            channel=body.channel,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"ok": True, "rtsp_url": url, "safe_url": camera_probe.redact(url)}


class CameraTestBody(BaseModel):
    rtsp_url: str = Field(min_length=7, max_length=500)


@app.post("/api/setup/test-camera")
async def test_camera(body: CameraTestBody) -> JSONResponse:
    """Kameradan haqiqiy kadr olishga urinadi.

    Rasm sehrgarda ko'rsatiladi — bu mijozning "ishladi" degan yagona
    ishonchli isboti.  Kadr `/api/setup/preview` orqali alohida olinadi,
    chunki JSON ichida base64 rasm sahifani sekinlashtirardi.
    """
    url = body.rtsp_url.strip()
    if not url.lower().startswith(("rtsp://", "rtsps://", "http://", "https://")):
        raise HTTPException(422, "Manzil rtsp:// bilan boshlanishi kerak")
    import anyio

    result = await anyio.to_thread.run_sync(camera_probe.grab_frame, url)
    if not result.ok:
        return JSONResponse(
            status_code=200,
            content={
                "ok": False,
                "error": result.error,
                "hint": result.hint,
                "safe_url": camera_probe.redact(url),
            },
        )
    _PREVIEW_CACHE.put(url, result.jpeg or b"")
    return JSONResponse(
        content={
            "ok": True,
            "width": result.width,
            "height": result.height,
            "safe_url": camera_probe.redact(url),
        }
    )


class _PreviewCache:
    """Oxirgi olingan kadrlarni xotirada saqlaydi.

    Nega diskka emas: kadrda do'kon ichi va odamlar bor.  Sozlash tugagach
    u kerak emas, diskda esa qolib ketardi.  Xotirada bo'lsa dastur
    yopilishi bilan o'chadi.
    """

    #: Bir vaqtda ko'pi bilan shuncha kadr — 4 kamera + zapas.
    LIMIT = 8

    def __init__(self) -> None:
        self._items: Dict[str, bytes] = {}
        self._lock = threading.Lock()

    def put(self, key: str, value: bytes) -> None:
        with self._lock:
            if len(self._items) >= self.LIMIT:
                self._items.pop(next(iter(self._items)), None)
            self._items[key] = value

    def get(self, key: str) -> Optional[bytes]:
        with self._lock:
            return self._items.get(key)


_PREVIEW_CACHE = _PreviewCache()


@app.get("/api/setup/preview")
async def preview(camera_id: str = "", rtsp_url: str = "") -> Response:
    """Chiziq chizish uchun kadr.

    `camera_id` berilsa saqlangan kamera manzili ishlatiladi — RTSP parolini
    brauzer manzil qatoriga chiqarmaslik uchun.
    """
    url = rtsp_url.strip()
    if camera_id:
        match = next((item for item in config_store.cameras() if item.get("id") == camera_id), None)
        if match is None:
            raise HTTPException(404, "Kamera topilmadi")
        url = str(match.get("stream_url") or "")
    if not url:
        raise HTTPException(422, "Kamera manzili berilmagan")

    cached = _PREVIEW_CACHE.get(url)
    if cached is None:
        import anyio

        result = await anyio.to_thread.run_sync(camera_probe.grab_frame, url)
        if not result.ok or not result.jpeg:
            raise HTTPException(503, result.error or "Kadr olinmadi")
        cached = result.jpeg
        _PREVIEW_CACHE.put(url, cached)
    return Response(
        cached,
        media_type="image/jpeg",
        # Kadr do'kon ichini ko'rsatadi — brauzer keshiga tushmasin.
        headers={"Cache-Control": "no-store"},
    )


class ScanChannelsBody(BaseModel):
    brand: str = Field(default="auto", pattern="^(auto|hikvision|dahua|uniview)$")
    host: str = Field(min_length=3, max_length=120)
    port: int = Field(default=554, ge=1, le=65535)
    username: str = Field(default="", max_length=64)
    password: str = Field(default="", max_length=128)


class AutoFindBody(BaseModel):
    host: str = Field(min_length=3, max_length=120)
    port: int = Field(default=554, ge=1, le=65535)
    username: str = Field(default="", max_length=64)
    password: str = Field(default="", max_length=128)
    channel: int = Field(default=1, ge=1, le=64)


@app.post("/api/setup/auto-find")
async def auto_find(body: AutoFindBody) -> Dict[str, Any]:
    """Brendni bilmasdan ishlaydigan RTSP formatini o'zi topadi.

    Mijoz NVR brendini ko'pincha bilmaydi yoki noto'g'ri tanlaydi.
    Ilgari bitta noto'g'ri format sinalib, "tasvir kelmadi" degan
    foydasiz xato chiqardi.  Endi ma'lum formatlar ketma-ket sinaladi
    va topilgani mijozga nomi bilan ko'rsatiladi.
    """
    import anyio

    name, url, result = await anyio.to_thread.run_sync(
        functools.partial(
            camera_probe.find_working_url,
            body.host,
            port=body.port,
            username=body.username,
            password=body.password,
            channel=body.channel,
        )
    )
    if url is None:
        return {
            "ok": False,
            "error": result.error,
            "hint": result.hint,
        }
    _PREVIEW_CACHE.put(url, result.jpeg or b"")
    return {
        "ok": True,
        "format": name,
        "rtsp_url": url,
        "safe_url": camera_probe.redact(url),
        "width": result.width,
        "height": result.height,
    }


#: NVR kanal skaneri holati.  Lokal sehrgarda bitta foydalanuvchi bo'ladi —
#: bitta job yetarli.  Ilgari skaner sinxron edi: yomon holatda o'nlab
#: daqiqa "osilib" turardi va mijoz nima bo'layotganini ko'rmasdi.
_SCAN_JOB: Dict[str, Any] = {"running": False, "channels": [], "hint": "", "current": 0}
_SCAN_JOB_TASK: Optional[Any] = None

#: Butun skanerga umumiy chegara — undan keyin topilganlari bilan to'xtaydi.
SCAN_CHANNELS_DEADLINE_SEC = 90.0


def _channel_from_uri(uri: str) -> int:
    """RTSP manzilidan kanal raqamini taxmin qiladi (topilmasa 0).

    Hikvision: /Channels/302 → 3-kanal; Dahua: channel=3; boshqalar:
    yo'ldagi birinchi kichik son.
    """
    match = re.search(r"[Cc]hannels?[/=](\d+)", uri)
    if match:
        value = int(match.group(1))
        return value // 100 if value >= 100 else value
    match = re.search(r"/c(\d+)/", uri)
    if match:
        return int(match.group(1))
    return 0


def _scan_via_onvif(body: ScanChannelsBody, deadline: float) -> List[Dict[str, Any]]:
    """NVR kanallarini ONVIF profillaridan oladi (taxminsiz yo'l).

    NVR har kanalni alohida profil qilib e'lon qiladi — bitta `describe`
    barcha kanallarning aniq RTSP manzilini beradi.  Yo'l-taxminlash
    endi faqat ONVIF ishlamagan holat uchun zaxira.
    """
    clean_host = body.host.strip().split("/")[0].split(":")[0]
    answer = onvif_client.describe(
        clean_host, username=body.username, password=body.password, port=0
    )
    if not answer.ok or not answer.profiles:
        return []

    # Kanal bo'yicha guruhlab, har kanaldan eng yengil (substream) oqim.
    by_channel: Dict[int, List[Any]] = {}
    unknown = 0
    for profile in answer.profiles:
        if not profile.uri:
            continue
        channel = _channel_from_uri(profile.uri)
        if channel == 0:
            unknown += 1
            channel = -unknown  # vaqtinchalik nomer; keyin tartib beriladi
        by_channel.setdefault(channel, []).append(profile)

    found: List[Dict[str, Any]] = []
    ordered = sorted(by_channel.items(), key=lambda item: (item[0] < 0, abs(item[0])))
    for index, (channel, profiles) in enumerate(ordered[:NVR_SCAN_CHANNELS], start=1):
        if time.monotonic() > deadline:
            break
        number = channel if channel > 0 else index
        _SCAN_JOB["current"] = number
        best = onvif_client.pick_best_profile(profiles)
        if best is None or not best.uri:
            continue
        url = onvif_client.with_credentials(best.uri, body.username, body.password, host=clean_host)
        result = camera_probe.grab_frame(url, timeout_sec=camera_probe.SCAN_TIMEOUT_SEC)
        if result.ok:
            _PREVIEW_CACHE.put(url, result.jpeg or b"")
            found.append(
                {
                    "channel": number,
                    "rtsp_url": url,
                    "safe_url": camera_probe.redact(url),
                    "width": result.width,
                    "height": result.height,
                }
            )
    return found


def _scan_via_templates(body: ScanChannelsBody, deadline: float) -> List[Dict[str, Any]]:
    """Zaxira yo'l: ma'lum RTSP yo'llarini kanalma-kanal sinash.

    Muhim chegara: shablon **ko'pi bilan 2 kanalda** qidiriladi.  Ilgari
    birinchi kanal bo'sh bo'lsa har kanal uchun to'liq qidiruv qaytadan
    yurar va skaner o'nlab daqiqa cho'zilardi.
    """
    found: List[Dict[str, Any]] = []
    working_path: Optional[str] = None
    template_attempts = 0

    for channel in range(1, NVR_SCAN_CHANNELS + 1):
        if time.monotonic() > deadline:
            break
        _SCAN_JOB["current"] = channel
        url: Optional[str] = None
        result = None

        if body.brand == "auto" and working_path is None:
            if template_attempts >= 2:
                break  # ikki kanalda ham format topilmadi — NVR javob bermayapti
            template_attempts += 1
            _name, url, result = camera_probe.find_working_url(
                body.host,
                port=body.port,
                username=body.username,
                password=body.password,
                channel=channel,
            )
            if url:
                working_path = camera_probe.path_template(url, channel)
        else:
            try:
                url = (
                    camera_probe.apply_template(
                        working_path, body.host, body.port, body.username, body.password, channel
                    )
                    if working_path
                    else camera_probe.build_rtsp(
                        brand=body.brand,
                        host=body.host,
                        port=body.port,
                        username=body.username,
                        password=body.password,
                        channel=channel,
                    )
                )
            except ValueError:
                break
            result = camera_probe.grab_frame(url, timeout_sec=camera_probe.SCAN_TIMEOUT_SEC)

        if url and result is not None and result.ok:
            _PREVIEW_CACHE.put(url, result.jpeg or b"")
            found.append(
                {
                    "channel": channel,
                    "rtsp_url": url,
                    "safe_url": camera_probe.redact(url),
                    "width": result.width,
                    "height": result.height,
                }
            )
    return found


def _run_channel_scan(body: ScanChannelsBody) -> None:
    """Skaner ishchisi (alohida thread'da) — natijani _SCAN_JOB ga yozadi."""
    deadline = time.monotonic() + SCAN_CHANNELS_DEADLINE_SEC
    try:
        found = []
        if body.username:
            # ONVIF parol talab qiladi — parolsiz to'g'ri zaxira yo'lga.
            found = _scan_via_onvif(body, deadline)
        if not found:
            found = _scan_via_templates(body, deadline)
        _SCAN_JOB["channels"] = found
        _SCAN_JOB["hint"] = (
            ""
            if found
            else "Birorta kanaldan tasvir kelmadi. IP, login va parolni tekshiring "
            "yoki NVR'da RTSP yoqilganiga ishonch hosil qiling."
        )
    except Exception:
        logger.exception("NVR kanal skaneri xato bilan tugadi")
        _SCAN_JOB["hint"] = "Skanerda kutilmagan xato — qaytadan urinib ko'ring."
    finally:
        _SCAN_JOB["running"] = False
        _SCAN_JOB["current"] = 0


@app.post("/api/setup/scan-channels")
async def scan_channels(body: ScanChannelsBody) -> Dict[str, Any]:
    """NVR kanallarini skanerlashni **boshlaydi** (natija status orqali).

    Nega kerak: do'konda odatda bitta NVR va unda 4 kamera bo'ladi —
    mijoz login-parolni bir marta kiritadi.  Skaner fonda ishlaydi:
    ilgari so'rov sinxron edi va yomon holatda brauzer daqiqalab osilib
    turardi.

    Kanallar ketma-ket sinaladi: NVR bir vaqtda ko'p ulanishni ko'tara
    olmaydi va parallel so'rovlar ishlaydigan kamerani ham "javob
    bermadi" qilib ko'rsatardi.
    """
    import anyio

    global _SCAN_JOB_TASK
    if _SCAN_JOB["running"]:
        return {"ok": True, "started": False, "running": True}
    _SCAN_JOB.update({"running": True, "channels": [], "hint": "", "current": 0})

    async def _worker() -> None:
        await anyio.to_thread.run_sync(functools.partial(_run_channel_scan, body))

    import asyncio

    _SCAN_JOB_TASK = asyncio.create_task(_worker())
    return {"ok": True, "started": True, "running": True}


@app.get("/api/setup/scan-channels/status")
async def scan_channels_status() -> Dict[str, Any]:
    """Skaner jarayoni: sehrgar har soniyada so'rab progress ko'rsatadi."""
    return {
        "ok": True,
        "running": bool(_SCAN_JOB["running"]),
        "current_channel": int(_SCAN_JOB["current"]),
        "total": NVR_SCAN_CHANNELS,
        "found": len(_SCAN_JOB["channels"]),
        "channels": list(_SCAN_JOB["channels"]),
        "hint": str(_SCAN_JOB["hint"]),
    }


class OnvifBody(BaseModel):
    host: str = Field(min_length=3, max_length=120)
    username: str = Field(default="", max_length=64)
    password: str = Field(default="", max_length=128)
    #: ONVIF veb-xizmati porti (RTSP porti emas).  0 — avtomatik:
    #: 80/8899/8000 dan ochig'i sinaladi (ilgari doim 80 ketardi va
    #: 8899-portdagi NVRlar "javob bermadi" bo'lib ko'rinardi).
    port: int = Field(default=0, ge=0, le=65535)
    #: WS-Discovery bergan aniq manzil — bo'lsa u birinchi sinaladi.
    xaddr: str = Field(default="", max_length=300)


@app.post("/api/setup/onvif")
async def onvif_probe(body: OnvifBody) -> Dict[str, Any]:
    """Kameradan ONVIF orqali oqim manzilini **so'raydi**.

    Farqi shu: `scan-channels` ma'lum yo'llarni birma-bir *taxmin*
    qiladi, bu esa kameraning o'zidan aniq manzilni oladi.  Ro'yxatda
    bo'lmagan yoki nostandart sozlangan kamera faqat shu yo'l bilan
    ishlaydi.

    Ustiga ustak, javobda kodek ham keladi — ya'ni H.265 muammosini
    mijoz kamerani qo'shishdan **oldin** biladi, hisobot bo'sh chiqqanda
    emas.
    """
    import anyio

    result = await anyio.to_thread.run_sync(
        functools.partial(
            onvif_client.describe,
            body.host.strip(),
            username=body.username,
            password=body.password,
            xaddr=body.xaddr.strip(),
            port=body.port,
        )
    )

    if not result.ok:
        return {
            "ok": False,
            "error": result.error,
            "hint": result.hint,
            "brand": onvif_client.normalise_brand(result.device.brand),
        }

    best = onvif_client.pick_best_profile(result.profiles)
    streams = []
    for profile in result.profiles:
        warning, advice = onvif_client.compatibility_note(profile)
        url = onvif_client.with_credentials(
            profile.uri, body.username, body.password, host=body.host.strip()
        )
        streams.append(
            {
                "token": profile.token,
                "name": profile.name,
                "encoding": profile.encoding or "noma'lum",
                "width": profile.width,
                "height": profile.height,
                "fps": profile.fps,
                "rtsp_url": url,
                "safe_url": camera_probe.redact(url),
                "recommended": bool(best and profile.token == best.token),
                "warning": warning,
                "advice": advice,
            }
        )

    return {
        "ok": True,
        "brand": onvif_client.normalise_brand(result.device.brand),
        "model": result.device.model,
        "firmware": result.device.firmware,
        "streams": streams,
        "count": len(streams),
    }


class CameraSaveBody(BaseModel):
    camera_id: str = Field(default="", max_length=32)
    label: str = Field(default="", max_length=64)
    rtsp_url: str = Field(min_length=7, max_length=500)
    record_url: Optional[str] = Field(default=None, max_length=500)
    priority: str = Field(default="retail", pattern="^(security|retail|background)$")


@app.get("/api/setup/cameras")
async def list_cameras() -> Dict[str, Any]:
    """Saqlangan kameralar.  RTSP paroli hech qachon qaytarilmaydi."""
    return {
        "cameras": [
            {
                "camera_id": item.get("id"),
                "label": item.get("label") or item.get("id"),
                "safe_url": camera_probe.redact(str(item.get("stream_url") or "")),
                "priority": item.get("priority", "retail"),
            }
            for item in config_store.cameras()
        ],
        "max_cameras": MAX_CAMERAS,
    }


@app.post("/api/setup/cameras")
async def save_camera(body: CameraSaveBody) -> Dict[str, Any]:
    existing = config_store.cameras()
    camera_id = body.camera_id.strip() or _next_camera_id(existing)
    if not re.fullmatch(r"[a-z0-9\-]{3,32}", camera_id):
        raise HTTPException(422, "Kamera ID faqat lotin harfi, raqam va chiziqchadan iborat")
    is_new = all(item.get("id") != camera_id for item in existing)
    if is_new and len(existing) >= MAX_CAMERAS:
        raise HTTPException(422, f"Ko'pi bilan {MAX_CAMERAS} kamera qo'shish mumkin")

    # Klip yozish uchun asosiy oqim: mijoz bermagan bo'lsa substream
    # manzilidan o'zimiz chiqaramiz va tezgina tekshiramiz.  Bungacha
    # `record_url` hech qachon to'ldirilmasdi — kliplar Windows'da umuman
    # ishlamaganining sabablaridan biri shu edi.
    record_url = (body.record_url or "").strip() or None
    if record_url is None:
        record_url = _verified_record_url(body.rtsp_url.strip())

    config_store.save_camera(
        camera_id=camera_id,
        stream_url=body.rtsp_url.strip(),
        label=body.label.strip(),
        record_url=record_url,
        priority=body.priority,
    )
    return {
        "ok": True,
        "camera_id": camera_id,
        "record_url_found": bool(record_url),
        **config_store.summary(),
    }


def _verified_record_url(stream_url: str) -> Optional[str]:
    """Asosiy oqim taklifini tekshirib qaytaradi; ishlamasa None.

    401 ham qabul qilinadi: yo'l mavjud, faqat digest autentifikatsiya
    kerak — ffmpeg uni o'zi bajaradi.  404/454 esa "bunday yo'l yo'q".
    """
    suggested = camera_probe.suggest_record_url(stream_url)
    if not suggested:
        return None
    try:
        code, _response = camera_probe.rtsp_describe(suggested, timeout_sec=4.0)
    except OSError:
        return None
    return suggested if code in (200, 401) else None


def _next_camera_id(existing: List[Dict[str, Any]]) -> str:
    used = {str(item.get("id")) for item in existing}
    for index in range(1, MAX_CAMERAS + 1):
        candidate = f"camera-{index:02d}"
        if candidate not in used:
            return candidate
    raise HTTPException(422, f"Ko'pi bilan {MAX_CAMERAS} kamera qo'shish mumkin")


@app.delete("/api/setup/cameras/{camera_id}")
async def delete_camera(camera_id: str) -> Dict[str, Any]:
    config_store.delete_camera(camera_id)
    return {"ok": True, **config_store.summary()}


class GeometryBody(BaseModel):
    lines: List[Dict[str, Any]] = Field(default_factory=list)
    zones: List[Dict[str, Any]] = Field(default_factory=list)


@app.get("/api/setup/geometry")
async def get_geometry() -> Dict[str, Any]:
    return config_store.geometry()


@app.put("/api/setup/geometry")
async def put_geometry(body: GeometryBody) -> Dict[str, Any]:
    """Chiziq va zonalarni saqlaydi.

    Saqlashdan oldin `AppSettings` bilan tekshiriladi: noto'g'ri koordinata
    yoki bo'sh nom bilan yozib qo'yilsa, zanjir keyingi ishga tushishda
    yiqilardi va mijoz sababini bilmasdi.
    """
    config_store.save_geometry(body.lines, body.zones)
    try:
        config_store.load_settings()
    except Exception as exc:  # noqa: BLE001 — pydantic xatosi mijozga ko'rsatiladi
        raise HTTPException(422, f"Chiziq/zona saqlanmadi: {exc}") from exc
    return {"ok": True, **config_store.summary()}


class SettingsBody(BaseModel):
    open_from: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    open_to: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    occupancy_limit: int = Field(default=config_store.DEFAULT_OCCUPANCY_LIMIT, ge=1, le=10000)
    queue_limit: int = Field(default=config_store.DEFAULT_QUEUE_LIMIT, ge=1, le=1000)
    loitering_sec: int = Field(default=config_store.DEFAULT_LOITERING_SEC, ge=5, le=86400)


@app.put("/api/setup/settings")
async def put_settings(body: SettingsBody) -> Dict[str, Any]:
    if bool(body.open_from) != bool(body.open_to):
        raise HTTPException(422, "Ochilish va yopilish vaqtini birga kiriting")
    config_store.save_store_hours(body.open_from, body.open_to)
    config_store.save_limits(
        occupancy_limit=body.occupancy_limit,
        queue_limit=body.queue_limit,
        loitering_sec=body.loitering_sec,
    )
    return {"ok": True, **config_store.summary()}


class TelegramBody(BaseModel):
    token: str = Field(default="", max_length=120)
    chat_id: str = Field(default="", max_length=64)


@app.put("/api/setup/telegram")
async def put_telegram(body: TelegramBody) -> Dict[str, Any]:
    config_store.save_telegram(body.token.strip() or None, body.chat_id.strip() or None)
    return {"ok": True, **config_store.summary()}


# ── Cloudga ulanish ──────────────────────────────────────────────────────


class PairBody(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    cloud_url: str = Field(min_length=3, max_length=200)


@app.get("/api/setup/cloud-status")
async def cloud_status() -> Dict[str, Any]:
    return {
        **cloud_link.status(),
        **cloud_config.status(),
        "pending_events": cloud_link.pending_events(),
    }


@app.post("/api/setup/pair")
async def pair(body: PairBody) -> Dict[str, Any]:
    """Pairing kod bilan cloudga ulaydi.

    Ulangandan keyin zanjir **qayta ishga tushiriladi**: `cloud_sync`
    sozlamasi faqat startda o'qiladi, ya'ni qayta ishga tushirmasak
    hodisalar hamon lokal navbatda qolib ketardi va mijoz "ulandi" degan
    yozuvni ko'rib turib, panelida hech nima ko'rmasdi.
    """
    import anyio

    try:
        site = await anyio.to_thread.run_sync(cloud_link.claim, body.code, body.cloud_url)
    except cloud_link.PairingError as exc:
        raise HTTPException(422, str(exc)) from exc

    if supervisor.status()["running"]:
        supervisor.restart()

    return {
        "ok": True,
        "site_id": site.site_id,
        "owner_url": f"{site.cloud_url}/owner",
        **cloud_link.status(),
    }


@app.post("/api/setup/unpair")
async def unpair() -> Dict[str, Any]:
    cloud_link.unlink()
    if supervisor.status()["running"]:
        supervisor.restart()
    return {"ok": True, **cloud_link.status()}


@app.post("/api/setup/pull-config")
async def pull_config() -> Dict[str, Any]:
    """Cloudda kiritilgan kamera va chiziqlarni darhol olib tushadi.

    Fon sinxronizatsiyasi buni har daqiqada o'zi qiladi; bu tugma
    o'rnatuvchi uchun — u cloudda sozlab bo'lgach kutib turmaydi.
    """
    import anyio

    applied = await anyio.to_thread.run_sync(cloud_config.sync_once)
    if applied is None:
        return {"ok": True, "applied": False, "message": "Cloudda yangi sozlama yo'q"}
    return {"ok": True, "applied": True, **applied, **config_store.summary()}


# ── Xizmat boshqaruvi ────────────────────────────────────────────────────


@app.get("/api/status")
async def status() -> Dict[str, Any]:
    return {
        **supervisor.status(),
        **config_store.summary(),
        # Har funksiya holati va sababi — panelda "yashil chiroq yolg'oni"
        # o'rniga aniq ro'yxat ko'rinadi.
        "features": config_store.feature_status(),
    }


@app.post("/api/service/start")
async def service_start() -> Dict[str, Any]:
    return supervisor.start()


@app.post("/api/service/stop")
async def service_stop() -> Dict[str, Any]:
    return supervisor.stop()


@app.post("/api/service/restart")
async def service_restart() -> Dict[str, Any]:
    return supervisor.restart()


@app.get("/api/service/log")
async def service_log() -> Dict[str, Any]:
    return {"lines": supervisor.log_tail()}


# ── Hisobot ──────────────────────────────────────────────────────────────


#: Bir kunlik hodisalar uchun ortig'i bilan yetadi (gavjum do'kon kuniga
#: ming atrofida yozadi).  Chegara faqat xotira uchun — buzuq baza panelni
#: yiqitmasin.
_REPORT_ROW_CAP = 20_000


def _read_events(since: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Hodisalarni outbox'dan o'qiydi.

    Outbox — zanjir yozadigan yagona joy, ya'ni panel ham, Telegram
    yuboruvchi ham bitta manbadan oladi.  Panel faqat o'qiydi; cloudga
    yuborilgan yozuvlar ham shu yerda qoladi (`outbox.acknowledge` ularni
    o'chirmaydi, "yuborildi" deb belgilaydi).

    `since` — shu vaqtdan keyingi yozuvlar.  Ilgari eng yangi 500 tasi
    olinib, **keyin** bugungi kunga filtrlanardi: gavjum do'konda ertalabki
    kirishlar ro'yxat oxiridan tushib qolardi va panel kam ko'rsatardi.
    """
    db = paths.outbox_path()
    if not db.is_file():
        return []
    try:
        # `ro` rejim: panel hech qanday holatda navbatga tegmasin.
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2.0)
        conn.row_factory = sqlite3.Row
        try:
            if since is None:
                rows = conn.execute(
                    "SELECT payload FROM outbox ORDER BY created_at DESC LIMIT ?",
                    (_REPORT_ROW_CAP,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT payload FROM outbox WHERE created_at >= ? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (since.astimezone(timezone.utc).isoformat(), _REPORT_ROW_CAP),
                ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        logger.info("Hodisalar o'qilmadi: %s", exc)
        return []

    import json

    events: List[Dict[str, Any]] = []
    for row in rows:
        try:
            events.append(json.loads(row["payload"]))
        except ValueError:
            continue
    return events


@app.get("/api/report")
async def report() -> Dict[str, Any]:
    """Bugungi qisqacha hisobot — mijoz birinchi navbatda shuni ko'radi.

    "Bugun" — do'konning **mahalliy** kuni, UTC emas.  Toshkent UTC+5
    bo'lgani uchun ertalabki savdo UTC bo'yicha kechagi kunga tushib qolardi
    va do'kon egasi ochilishdan keyin ham nol ko'rardi.
    """
    now_local = datetime.now().astimezone()
    today = now_local.date()
    # Kun boshidan bir soat oldin: `created_at` (navbatga qo'yilgan vaqt) va
    # `occurred_at` (hodisa vaqti) biroz farq qilishi mumkin.
    day_start = datetime.combine(
        today, datetime.min.time(), tzinfo=now_local.tzinfo
    ) - timedelta(hours=1)
    events = _read_events(since=day_start)
    entered = exited = 0
    hourly = Counter()
    alerts: List[Dict[str, Any]] = []

    for event in events:
        occurred = str(event.get("occurred_at") or "")
        try:
            moment = datetime.fromisoformat(occurred.replace("Z", "+00:00"))
        except ValueError:
            continue
        # Zanjir vaqtni UTC da yozadi; taqqoslash mahalliy vaqtda bo'ladi.
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        moment = moment.astimezone()
        if moment.date() != today:
            continue
        kind = event.get("event_type")
        if kind == "line_crossed":
            if event.get("direction") == "in":
                entered += 1
                hourly[moment.hour] += 1
            elif event.get("direction") == "out":
                exited += 1
        elif event.get("severity") in {"warning", "critical"}:
            alerts.append(
                {
                    "type": kind,
                    "camera_id": event.get("camera_id"),
                    "occurred_at": occurred,
                    "zone": event.get("zone"),
                }
            )

    busiest = max(hourly.items(), key=lambda item: item[1], default=None)
    return {
        "date": today.isoformat(),
        "entered": entered,
        "exited": exited,
        "inside_estimate": max(0, entered - exited),
        "busiest_hour": {"hour": busiest[0], "entered": busiest[1]} if busiest else None,
        "hourly": [{"hour": hour, "entered": hourly.get(hour, 0)} for hour in range(24)],
        "alerts": alerts[:20],
        "alert_count": len(alerts),
        "events_total": len(events),
    }


@app.get("/api/events")
async def events(limit: int = 50) -> Dict[str, Any]:
    limit = max(1, min(int(limit), 200))
    return {
        "events": [
            {
                "event_type": event.get("event_type"),
                "severity": event.get("severity"),
                "camera_id": event.get("camera_id"),
                "occurred_at": event.get("occurred_at"),
                "zone": event.get("zone"),
                "direction": event.get("direction"),
                "queue_length": event.get("queue_length"),
            }
            # Eng yangisi birinchi — `_read_events` shu tartibda qaytaradi.
            for event in _read_events()[:limit]
        ]
    }


# ── Ishga tushirish ──────────────────────────────────────────────────────


def _open_browser(url: str, delay_sec: float = 1.5) -> None:
    """Server ko'tarilgach brauzerni ochadi.

    Kechikish kerak: darhol ochilsa brauzer ulanolmay "sahifa topilmadi"
    ko'rsatadi va mijoz dastur ishlamadi deb o'ylaydi.
    """

    def _later() -> None:
        time.sleep(delay_sec)
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001 — brauzersiz serverda ham ishlashi kerak
            logger.info("Brauzer ochilmadi — qo'lda oching: %s", url)

    threading.Thread(target=_later, daemon=True).start()


def _auto_pair_if_handed_off() -> None:
    """O'rnatuvchi kod qoldirgan bo'lsa cloudga o'zi ulanadi.

    Bu sehrgarning 5-qadamini mijoz uchun butunlay yo'q qiladi: u
    faqat o'rnatadi, qolgani o'zi bo'ladi.  Xato bo'lsa jimgina
    o'tkaziladi — sehrgar kodni odatdagidek so'raydi.
    """
    try:
        cloud_link.auto_pair()
    except Exception:  # noqa: BLE001 — ulanish dasturni to'xtatmasligi kerak
        logger.exception("Avtomatik ulanishda kutilmagan xato")


def _write_alive(phase: str) -> None:
    """Updater rollback qarori uchun tiriklik izi.

    `starting` — `main()` boshlandi; `running` — panel ishlab turibdi
    (sikl har daqiqa yangilab turadi).  Yangilashdan keyin `running`
    yozilmasa, updater dastur ishga tusha olmagan deb biladi va oldingi
    versiyaga qaytaradi (`chaqimchi_ai/local/updater.py`).
    """
    try:
        paths.alive_marker_path().write_text(
            json.dumps(
                {
                    "version": __version__,
                    "phase": phase,
                    "at": datetime.now(timezone.utc).isoformat(),
                }
            ),
            encoding="utf-8",
        )
    except OSError:  # noqa: PERF203 — disk to'la bo'lsa ham panel ishlayversin
        logger.warning("Tiriklik izi yozilmadi: %s", paths.alive_marker_path())


def _start_config_sync() -> None:
    """Cloud sozlamasini fonda kuzatib boradi.

    O'rnatuvchi cloud panelida kamera qo'shsa yoki chiziqni o'zgartirsa,
    do'kondagi kompyuterga borish shart emas: o'zgarish bir daqiqada
    tushadi.

    Ip `daemon`: dastur yopilganda uni alohida to'xtatish shart emas.
    """

    def _loop() -> None:
        while True:
            _write_alive("running")
            try:
                # Heartbeat birinchi: cloud qurilma tirikligini va qaysi
                # versiyada ekanini bilishi kerak, hatto zanjir
                # to'xtagan bo'lsa ham.
                cloud_config.send_heartbeat(supervisor.status())
                cloud_config.upload_heatmaps()

                applied = cloud_config.sync_once()
                if applied and applied.get("cameras"):
                    # Kamera ro'yxati o'zgardi — zanjir uni faqat startda
                    # o'qiydi, shuning uchun qayta ishga tushiramiz.
                    if supervisor.status()["running"]:
                        supervisor.restart()
                    else:
                        _autostart_if_ready()
            except Exception:  # noqa: BLE001 — sinxronizatsiya dasturni to'xtatmasin
                logger.exception("Cloud sozlamasini olishda kutilmagan xato")
            time.sleep(cloud_config.POLL_INTERVAL_SEC)

    def _media_loop() -> None:
        # Jonli ko'rish: zanjir yozgan kadrlarni har 2-3 soniyada cloudga
        # yuboradi.  So'rov yo'q payt sikl bitta fayl-stat bilan tugaydi.
        while True:
            try:
                cloud_config.upload_media_frames()
            except Exception:  # noqa: BLE001 — jonli kadr dasturni to'xtatmasin
                logger.exception("Jonli kadr yuborishda kutilmagan xato")
            time.sleep(cloud_config.LIVE_UPLOAD_INTERVAL_SEC)

    threading.Thread(target=_loop, name="cloud-config-sync", daemon=True).start()
    threading.Thread(target=_media_loop, name="live-frame-upload", daemon=True).start()


def _autostart_if_ready() -> None:
    """Sozlangan bo'lsa AI zanjirini o'zi ko'taradi.

    Do'kon kompyuteri qayta yuklanganda mijoz hech qanday tugma bosmasligi
    kerak — aks holda nazorat jimgina to'xtab qolardi va buni faqat bir
    haftadan keyin, hisobot bo'sh chiqqanda sezishardi.
    """
    if config_store.is_ready() and config_store.model_available():
        logger.info("Sozlama tayyor — AI zanjiri avtomatik ishga tushmoqda")
        supervisor.start()


def main() -> None:
    from logging.handlers import RotatingFileHandler

    # Rotatsiyasiz log 24/7 ishlaydigan do'kon kompyuterida `C:` diskini
    # to'ldirishning eng ehtimolli yo'li edi (ayniqsa kamera uzilib
    # qayta ulanaverganda).  5 MB × 3 — bir necha haftalik tarix, yetadi.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            RotatingFileHandler(
                paths.logs_dir() / "local.log",
                maxBytes=5 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            ),
        ],
    )
    import uvicorn

    # Updater uchun: dastur hech bo'lmasa shu nuqtagacha yetib keldi.
    _write_alive("starting")

    url = f"http://127.0.0.1:{PORT}"
    print("=" * 62)
    print("  Chaqimchi AI — do'kon nazorati")
    print(f"  Boshqaruv paneli: {url}")
    print(f"  Sozlamalar: {paths.data_dir()}")
    print("=" * 62)

    _auto_pair_if_handed_off()
    # Cloudda sozlangan bo'lsa, zanjir ishga tushishidan **oldin** olib
    # tushamiz — aks holda birinchi daqiqada kamerasiz ishga tushib,
    # keyin qayta start bo'lardi.
    try:
        cloud_config.sync_once()
        cloud_config.send_heartbeat(supervisor.status())
    except Exception:  # noqa: BLE001
        logger.exception("Boshlang'ich cloud sozlamasi olinmadi")
    _autostart_if_ready()
    _start_config_sync()
    if os.environ.get("CHAQIMCHI_LOCAL_NO_BROWSER", "").lower() not in {"1", "true", "yes"}:
        _open_browser(url)

    try:
        uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
    finally:
        supervisor.stop()


if __name__ == "__main__":
    main()
