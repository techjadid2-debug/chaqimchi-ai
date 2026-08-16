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

import logging
import os
import re
import sqlite3
import threading
import time
import webbrowser
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from chaqimchi_ai.local import camera_probe, cloud_link, config_store, paths
from chaqimchi_ai.local.supervisor import RetailSupervisor

logger = logging.getLogger(__name__)

PORT = int(os.environ.get("CHAQIMCHI_LOCAL_PORT", "8760"))
STATIC_DIR = Path(__file__).resolve().parent / "static"

#: Do'kon profili: ko'pi bilan 4 kamera qabul qilingan (`docs/DOKON_MVP.md`).
#: Sehrgar bundan ortig'ini taklif qilmaydi — o'lchanmagan sig'imni va'da
#: qilish keyin "sekin ishlaydi" degan shikoyatga aylanadi.
MAX_CAMERAS = 4

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
        match = next(
            (item for item in config_store.cameras() if item.get("id") == camera_id), None
        )
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

    config_store.save_camera(
        camera_id=camera_id,
        stream_url=body.rtsp_url.strip(),
        label=body.label.strip(),
        record_url=(body.record_url or "").strip() or None,
        priority=body.priority,
    )
    return {"ok": True, "camera_id": camera_id, **config_store.summary()}


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
    return {**cloud_link.status(), "pending_events": cloud_link.pending_events()}


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


# ── Xizmat boshqaruvi ────────────────────────────────────────────────────


@app.get("/api/status")
async def status() -> Dict[str, Any]:
    return {**supervisor.status(), **config_store.summary()}


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


def _read_events(limit: int = 500) -> List[Dict[str, Any]]:
    """Hodisalarni outbox'dan o'qiydi.

    Outbox — zanjir yozadigan yagona joy, ya'ni panel ham, kelajakdagi
    Telegram yuboruvchi ham bitta manbadan oladi.  Faqat o'qiymiz va hech
    narsani o'chirmaymiz: o'chirish cloudga yuborilgandan keyin bo'ladi.
    """
    db = paths.outbox_path()
    if not db.is_file():
        return []
    try:
        # `ro` rejim: panel hech qanday holatda navbatga tegmasin.
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2.0)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT payload FROM outbox ORDER BY created_at DESC LIMIT ?", (int(limit),)
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
    events = _read_events()
    today = datetime.now().astimezone().date()
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
            for event in _read_events(limit)
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
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(paths.logs_dir() / "local.log", encoding="utf-8"),
        ],
    )
    import uvicorn

    url = f"http://127.0.0.1:{PORT}"
    print("=" * 62)
    print("  Chaqimchi AI — do'kon nazorati")
    print(f"  Boshqaruv paneli: {url}")
    print(f"  Sozlamalar: {paths.data_dir()}")
    print("=" * 62)

    _auto_pair_if_handed_off()
    _autostart_if_ready()
    if os.environ.get("CHAQIMCHI_LOCAL_NO_BROWSER", "").lower() not in {"1", "true", "yes"}:
        _open_browser(url)

    try:
        uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
    finally:
        supervisor.stop()


if __name__ == "__main__":
    main()
