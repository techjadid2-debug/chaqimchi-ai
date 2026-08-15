"""Sotqin R1 — NVR/IP kameralar bilan Chaqimchi Cloud orasidagi gateway.

Bu servis AI inferens bajarmaydi. U qurilma identifikatsiyasi, heartbeat,
cloud konfiguratsiyasi va ishonchli yangilanish uchun yengil control plane'dir.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import shutil
import sqlite3
import tempfile
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from chaqimchi_ai import __version__
from chaqimchi_ai.sotqin_media import SotqinMediaRuntime
from chaqimchi_ai.sotqin_profile import (
    BUFFER_MAX_BYTES,
    BUFFER_RETENTION_DAYS,
    HARDWARE_MODEL,
    HARDWARE_PROFILE,
    HARDWARE_REVISION,
    MAX_CAMERAS,
    MIN_FREE_BYTES,
    PRODUCT_NAME,
    product_payload,
)

logger = logging.getLogger(__name__)


def _read_first(paths: tuple[Path, ...]) -> Optional[str]:
    for path in paths:
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if value and value.lower() not in {"none", "unknown", "default string"}:
            return value
    return None


def detected_serial() -> str:
    return (
        os.environ.get("CHAQIMCHI_SOTQIN_SERIAL", "").strip()
        or _read_first(
            (
                Path("/sys/class/dmi/id/product_serial"),
                Path("/sys/class/dmi/id/board_serial"),
                Path("/etc/machine-id"),
            )
        )
        or platform.node()
        or "sotqin-unassigned"
    )


class SotqinAgent:
    def __init__(self) -> None:
        self.cloud_url = os.environ.get("CHAQIMCHI_CLOUD_URL", "").strip().rstrip("/")
        self.site_id = os.environ.get("CHAQIMCHI_SITE_ID", "").strip()
        self.device_id = os.environ.get("CHAQIMCHI_DEVICE_ID", "").strip()
        self.device_token = os.environ.get("CHAQIMCHI_DEVICE_TOKEN", "").strip()
        self.hardware_model = os.environ.get(
            "CHAQIMCHI_SOTQIN_MODEL", HARDWARE_MODEL
        ).strip()
        self.hardware_revision = os.environ.get(
            "CHAQIMCHI_SOTQIN_REVISION", HARDWARE_REVISION
        ).strip()
        self.serial_number = detected_serial()
        raw_interval = os.environ.get("CHAQIMCHI_SOTQIN_HEARTBEAT_SEC", "60").strip()
        try:
            self.interval = max(30, int(raw_interval))
        except ValueError:
            self.interval = 60
        raw_probe_interval = os.environ.get("CHAQIMCHI_CAMERA_PROBE_SEC", "300").strip()
        try:
            self.probe_interval = max(60, int(raw_probe_interval))
        except ValueError:
            self.probe_interval = 300
        self.last_probe_at = 0.0
        self.monotonic = time.monotonic
        self.config_path = Path(
            os.environ.get(
                "CHAQIMCHI_SOTQIN_CONFIG_CACHE",
                "/opt/chaqimchi/shared/data/sotqin-config.json",
            )
        )
        data_root = Path("/opt/chaqimchi/shared/data")
        self.outbox_paths = (
            Path(os.environ.get("CHAQIMCHI_RETAIL_OUTBOX", str(data_root / "outbox.db"))),
            Path(
                os.environ.get(
                    "CHAQIMCHI_ATTENDANCE_OUTBOX",
                    str(data_root / "attendance-outbox.db"),
                )
            ),
        )
        self.client: Optional[httpx.AsyncClient] = None
        self.task: Optional[asyncio.Task] = None
        self.last_ok: Optional[str] = None
        self.last_error: Optional[str] = None
        self.remote_config_revision = 0
        self.config_status = "pending"
        self.media = SotqinMediaRuntime()

    @property
    def configured(self) -> bool:
        return bool(self.cloud_url and self.site_id and self.device_id and self.device_token)

    @property
    def headers(self) -> Dict[str, str]:
        return {
            "X-Site-Id": self.site_id,
            "X-Device-Id": self.device_id,
            "X-Device-Token": self.device_token,
        }

    def health_payload(self) -> Dict[str, Any]:
        thermal = Path("/sys/class/thermal/thermal_zone0/temp")
        try:
            temperature = float(thermal.read_text(encoding="utf-8").strip()) / 1000
        except (OSError, ValueError):
            temperature = None
        data_root = Path("/opt/chaqimchi/shared/data")
        if not data_root.exists():
            data_root = Path.cwd()
        disk = shutil.disk_usage(data_root)
        queue = self._outbox_health()
        return {
            "cameras_active": self.media.health()["online"],
            "temperature_c": temperature,
            "disk_free_bytes": disk.free,
            "outbox_pending": queue["pending"],
            "outbox_bytes": queue["bytes"],
            "outbox_critical_pending": queue["critical_pending"],
            "app_version": __version__,
            "model_version": None,
            "product_name": PRODUCT_NAME,
            "hardware_model": self.hardware_model,
            "hardware_revision": self.hardware_revision,
            "serial_number": self.serial_number,
            "config_revision": self.remote_config_revision,
        }

    def _outbox_health(self) -> Dict[str, int]:
        totals = {"pending": 0, "bytes": 0, "critical_pending": 0}
        for path in self.outbox_paths:
            if not path.is_file():
                continue
            try:
                with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2) as conn:
                    columns = {
                        str(row[1]) for row in conn.execute("PRAGMA table_info(outbox)")
                    }
                    size_parts = ["length(payload)"]
                    if "snapshot_size" in columns:
                        size_parts.append("snapshot_size")
                    if "clip_size" in columns:
                        size_parts.append("clip_size")
                    critical = (
                        "COALESCE(SUM(CASE WHEN priority>=30 THEN 1 ELSE 0 END),0)"
                        if "priority" in columns
                        else "0"
                    )
                    row = conn.execute(
                        "SELECT COUNT(*),"
                        f"COALESCE(SUM({'+'.join(size_parts)}),0),"
                        f"{critical} FROM outbox"
                    ).fetchone()
            except (OSError, sqlite3.Error):
                continue
            totals["pending"] += int(row[0])
            totals["bytes"] += int(row[1])
            totals["critical_pending"] += int(row[2])
        return totals

    def validate_config(self, payload: Dict[str, Any]) -> None:
        revision = payload.get("revision")
        product = payload.get("product", {})
        features = payload.get("cloud_features", [])
        if not isinstance(revision, int) or revision < 0:
            raise ValueError("Config revision noto'g'ri")
        if product.get("name") != PRODUCT_NAME:
            raise ValueError("Config Sotqin mahsuloti uchun emas")
        if int(product.get("max_cameras", 0)) > MAX_CAMERAS:
            raise ValueError(f"Sotqin R1 {MAX_CAMERAS} kameradan ortiq config'ni qabul qilmaydi")
        buffer_policy = payload.get("buffer_policy", {})
        if buffer_policy:
            if int(buffer_policy.get("max_bytes", 0)) > BUFFER_MAX_BYTES:
                raise ValueError("Sotqin 8/128 uchun buffer 40 GB dan oshmasligi kerak")
            if int(buffer_policy.get("max_days", 0)) > BUFFER_RETENTION_DAYS:
                raise ValueError("Sotqin 8/128 uchun buffer 3 kundan oshmasligi kerak")
        if not isinstance(features, list):
            raise ValueError("cloud_features ro'yxat bo'lishi kerak")
        for feature in features:
            if not isinstance(feature, dict) or not feature.get("code"):
                raise ValueError("Cloud AI funksiya config'i noto'g'ri")
            if feature.get("queue_kind") not in {"realtime", "batch"}:
                raise ValueError("Funksiya navbati realtime yoki batch bo'lishi kerak")
        self.media.apply_config(payload)

    def persist_config(self, payload: Dict[str, Any]) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self.config_path.parent,
            prefix=f".{self.config_path.name}.",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, self.config_path)

    async def report_config(self, revision: int, status: str, error: str = "") -> None:
        if self.client is None:
            raise RuntimeError("HTTP client tayyor emas")
        response = await self.client.post(
            f"{self.cloud_url}/api/v1/sotqin/config/ack",
            headers=self.headers,
            json={"revision": revision, "status": status, "error": error or None},
        )
        response.raise_for_status()

    async def apply_config(self, payload: Dict[str, Any]) -> None:
        revision = int(payload.get("revision", 0))
        try:
            self.validate_config(payload)
            self.persist_config(payload)
        except Exception as exc:
            self.config_status = "rejected"
            try:
                await self.report_config(revision, "rejected", str(exc)[:500])
            except Exception:
                pass
            raise
        self.remote_config_revision = revision
        self.config_status = "ack_pending"
        await self.report_config(revision, "applied")
        self.config_status = "applied"

    async def report_camera_probes(self) -> None:
        if self.client is None:
            raise RuntimeError("HTTP client tayyor emas")
        probes = await asyncio.to_thread(self.media.probe_all)
        if not probes:
            return
        response = await self.client.post(
            f"{self.cloud_url}/api/v1/sotqin/camera-probes", headers=self.headers, json=probes
        )
        response.raise_for_status()

    async def maybe_report_camera_probes(self, *, force: bool = False) -> None:
        now = self.monotonic()
        if not force and now - self.last_probe_at < self.probe_interval:
            return
        await self.report_camera_probes()
        self.last_probe_at = now

    async def upload_previews(self, camera_ids: Any) -> int:
        """O'rnatuvchi so'ragan kameralardan bittadan kadr yuboradi.

        Bitta kamera yiqilsa qolganlari yuborilaveradi — o'rnatuvchi to'rt
        kameradan uchtasini ko'rib, to'rtinchisi ishlamayotganini bilsin.
        """
        if self.client is None or not isinstance(camera_ids, list):
            return 0
        sent = 0
        for raw in camera_ids[:MAX_CAMERAS]:
            camera = self.media.camera(str(raw))
            if camera is None or not camera.get("enabled"):
                continue
            try:
                image = await asyncio.to_thread(self.media.grab_preview, camera)
            except Exception:
                logger.exception("[%s] kadr olinmadi", camera["camera_id"])
                continue
            if not image:
                logger.warning("[%s] kadr olinmadi (RTSP javob bermadi)", camera["camera_id"])
                continue
            try:
                response = await self.client.put(
                    f"{self.cloud_url}/api/v1/sotqin/cameras/{camera['camera_id']}/preview",
                    headers={**self.headers, "Content-Type": "image/jpeg"},
                    content=image,
                )
                response.raise_for_status()
                sent += 1
            except Exception:
                logger.exception("[%s] kadr yuborilmadi", camera["camera_id"])
        return sent

    async def heartbeat_once(self) -> None:
        if not self.configured:
            raise RuntimeError("Sotqin pairing qilinmagan")
        if self.client is None:
            self.client = httpx.AsyncClient(timeout=20)
        response = await self.client.post(
            f"{self.cloud_url}/api/v1/sotqin/heartbeat",
            headers=self.headers,
            json=self.health_payload(),
        )
        response.raise_for_status()
        # Cloud heartbeat javobida config revision'ini aytadi. O'zgarmagan
        # bo'lsa og'ir `/config` so'rovi umuman qilinmaydi — kuniga 1440 ta
        # emas, faqat rostdan o'zgargan paytda.
        try:
            heartbeat = response.json()
        except ValueError:
            heartbeat = {}
        await self.upload_previews(heartbeat.get("preview_requested"))
        if (
            heartbeat.get("config_changed") is False
            and self.config_status == "applied"
            and int(heartbeat.get("config_revision", -1)) == self.remote_config_revision
        ):
            await self.maybe_report_camera_probes()
            self.last_ok = datetime.now(timezone.utc).isoformat()
            self.last_error = None
            return
        config_response = await self.client.get(
            f"{self.cloud_url}/api/v1/sotqin/config",
            headers=self.headers,
        )
        config_response.raise_for_status()
        payload = config_response.json()
        revision = int(payload.get("revision", 0))
        if revision != self.remote_config_revision or self.config_status != "applied":
            await self.apply_config(payload)
            await self.maybe_report_camera_probes(force=True)
        else:
            await self.maybe_report_camera_probes()
        self.last_ok = datetime.now(timezone.utc).isoformat()
        self.last_error = None

    async def run(self) -> None:
        while True:
            try:
                await self.heartbeat_once()
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001 - offline holat normal
                self.last_error = str(exc)[:300]
            await asyncio.sleep(self.interval)

    def start(self) -> None:
        if self.task is None:
            self.task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        if self.task is not None:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None
        if self.client is not None:
            await self.client.aclose()
            self.client = None


control = SotqinAgent()


@asynccontextmanager
async def lifespan(_: FastAPI):
    control.start()
    try:
        yield
    finally:
        await control.stop()


app = FastAPI(
    title="Chaqimchi Sotqin R1",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.get("/health")
async def health() -> JSONResponse:
    status = 200 if control.configured else 503
    return JSONResponse(
        status_code=status,
        content={
            "ok": control.configured,
            "product": PRODUCT_NAME,
            "hardware_profile": HARDWARE_PROFILE,
            "hardware": product_payload(),
            "hardware_model": control.hardware_model,
            "serial_number": control.serial_number,
            "mode": "control-only",
            "version": __version__,
            "paired": control.configured,
            "cloud_connected": bool(control.last_ok),
            "last_error": control.last_error,
            "remote_config_revision": control.remote_config_revision,
            "config_status": control.config_status,
            "device_health": control.health_payload(),
            "ai_model": "cloud-only",
            "buffer_policy": {
                "max_bytes": BUFFER_MAX_BYTES,
                "max_days": BUFFER_RETENTION_DAYS,
                "min_free_bytes": MIN_FREE_BYTES,
            },
        },
    )


@app.get("/ready")
async def ready() -> JSONResponse:
    return await health()


@app.get("/preflight")
async def preflight() -> JSONResponse:
    """O'rnatuvchi uchun tekshiruv ro'yxati.

    `/health` "men tirikman" deydi; bu esa "obyektni topshirsa bo'ladimi"
    degan savolga javob beradi va har muammo uchun nima qilish kerakligini
    aytadi.

    Asosiy yo'l — skript (`sotqin_preflight.py`), chunki u xizmat
    ishlamayotganda ham ishlaydi.  Bu marshrut faqat qulaylik uchun, shuning
    uchun import muvaffaqiyatsiz bo'lsa ham xizmat yiqilmaydi.
    """
    try:
        from scripts.sotqin_preflight import Preflight
    except ImportError:
        return JSONResponse(
            status_code=501,
            content={
                "ready": False,
                "detail": "Tekshiruvni buyruq satridan ishga tushiring",
                "command": (
                    "/opt/chaqimchi/venv/bin/python "
                    "/opt/chaqimchi/current/scripts/sotqin_preflight.py"
                ),
            },
        )
    payload = await asyncio.to_thread(Preflight().payload)
    return JSONResponse(status_code=200 if payload["ready"] else 503, content=payload)
