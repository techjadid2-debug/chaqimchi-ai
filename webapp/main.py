"""
Chaqimchi AI — Pro Server Edition.

Bir nechta RTSP kameralarini fon rejimida tahlil qiladi va voqealarni SQL bazasiga saqlaydi.
Mini PC (Server) uchun moslashtirilgan.

Bu fayl faqat ilovani yig'adi: marshrutlar `webapp/routers/` da, uzoq yashovchi
komponentlar `AppContainer` da (`app.state.container`).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from chaqimchi_ai import __version__, telegram_bot
from chaqimchi_ai.antispoof import build_checker
from chaqimchi_ai.camera_manager import CameraManager
from chaqimchi_ai.cloud_sync import CloudEventSync
from chaqimchi_ai.event_models import EdgeEvent
from chaqimchi_ai.licensing.client import EdgeLicenseClient
from chaqimchi_ai.licensing.enforce import filter_cameras
from chaqimchi_ai.retention import retention_loop
from chaqimchi_ai.runtime.container import AppContainer
from chaqimchi_ai.scene_analytics import build_scene_analyzer
from chaqimchi_ai.settings import SceneSettings
from webapp.errors import register_error_handlers
from webapp.routers import auth, backup, calibrate, events, persons, system, vision

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"


def _apply_remote_scene_config(
    container: AppContainer, payload: Dict, *, persist: bool = True
) -> None:
    revision = int(payload.get("revision", 0))
    if revision <= container.remote_config_revision:
        return
    remote = payload.get("config") or {}
    current = container.settings.scene.model_dump()
    for key in ("occupancy_limit", "loitering_sec", "zones"):
        if key in remote:
            current[key] = remote[key]
    scene = SceneSettings.model_validate(current)
    container.settings.scene = scene
    container.remote_config_revision = revision
    if container.camera_manager:
        for camera_id, analyzer in container.camera_manager.scene_analyzers.items():
            analyzer.settings = scene
            analyzer.zones = [zone for zone in scene.zones if zone.camera_id == camera_id]
    if persist:
        cache = container.base_dir / "data" / "remote_scene_config.json"
        cache.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, cache)


def _load_remote_scene_cache(container: AppContainer) -> None:
    cache = container.base_dir / "data" / "remote_scene_config.json"
    if not cache.is_file():
        return
    try:
        payload = json.loads(cache.read_text(encoding="utf-8"))
        _apply_remote_scene_config(container, payload, persist=False)
    except (OSError, ValueError, TypeError):
        logger.warning("Remote scene config cache yaroqsiz", exc_info=True)


# ── Litsenziya ───────────────────────────────────────────────────────────


async def _resolve_license_client(container: AppContainer) -> EdgeLicenseClient:
    lic = container.settings.license
    client = EdgeLicenseClient(
        lic.cloud_url,
        lic.site_id or "",
        lic.device_token or "",
        container.base_dir / "data" / "license_cache.json",
        offline_grace_days=lic.offline_grace_days,
    )
    if lic.pairing_code and not lic.device_token:
        claimed = await client.claim_device(lic.pairing_code, label="edge-server")
        client.site_id = claimed["site_id"]
        client.device_token = claimed["device_token"]
        logger.warning(
            "Juftlash muvaffaqiyatli. config.yaml ga yozing: site_id=%s device_token=<token>",
            claimed["site_id"],
        )
    return client


async def _license_heartbeat_loop(container: AppContainer) -> None:
    while True:
        try:
            cfg = container.settings
            if not cfg.license.enabled or container.license_client is None:
                break
            active = len(container.camera_manager.cameras) if container.camera_manager else 0
            container.license_state = await container.license_client.refresh(
                active_cameras=active
            )
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("License heartbeat: %s", e)
        await asyncio.sleep(container.settings.license.heartbeat_interval_sec)


# ── Kameralar va voqea callback'i ────────────────────────────────────────


def _make_on_face_match(container: AppContainer):
    """Kamera callback'ini konteynerga bog'lab qaytaradi.

    Faza 2 da bu butunlay `bus.publish(FaceMatched(...))` ga aylanadi va
    quyidagi to'rtta yon ta'sir mustaqil obunachilarga bo'linadi.
    """

    async def on_face_match(
        camera_id: str,
        person_meta: Dict,
        face_data: Dict,
        image_path: Optional[str] = None,
    ) -> None:
        event = EdgeEvent(
            event_type="employee_seen",
            camera_id=camera_id,
            person_id=str(person_meta["id"]),
            person_name=person_meta["name"],
            score=float(person_meta["score"]),
            model_version=container.settings.face.model_version,
            snapshot_path=image_path,
            track_id=face_data.get("track_id"),
        )
        container.events.log_edge_event(event)
        if container.settings.cloud_sync.enabled:
            container.outbox.enqueue(event)

        payload = {
            "type": "event",
            "camera_id": camera_id,
            "person_name": person_meta["name"],
            "score": person_meta["score"],
            "timestamp": time.strftime("%H:%M:%S"),
            "snapshot_url": f"/api/snapshots/{Path(image_path).name}" if image_path else None,
            "track_id": face_data.get("track_id"),
        }
        # Nusxa bo'yicha yuriladi: yuborish paytida ro'yxat o'zgarishi mumkin.
        for client in list(container.ws_clients):
            try:
                await client.send_json(payload)
            except Exception:
                logger.debug("WebSocket mijoziga yuborib bo‘lmadi", exc_info=True)
                try:
                    container.ws_clients.remove(client)
                except ValueError:
                    pass

        cfg = container.settings
        if cfg.telegram.enabled:
            task = asyncio.create_task(
                telegram_bot.send_alert(
                    name=person_meta["name"],
                    score=person_meta["score"],
                    interval=cfg.telegram.alert_interval_sec,
                )
            )
            # Havolani ushlab turish: aks holda task GC bo'lib ketishi va
            # xatosi hech qachon ko'rinmasligi mumkin.
            container.background_tasks.add(task)
            task.add_done_callback(container.background_tasks.discard)

    return on_face_match


def _make_on_scene_event(container: AppContainer):
    async def on_scene_event(event: EdgeEvent) -> None:
        container.events.log_edge_event(event)
        if container.settings.cloud_sync.enabled:
            container.outbox.enqueue(event)
        payload = {
            "type": "event",
            **event.cloud_payload(),
            "snapshot_url": (
                f"/api/snapshots/{Path(event.snapshot_path).name}"
                if event.snapshot_path
                else None
            ),
        }
        for client in list(container.ws_clients):
            try:
                await client.send_json(payload)
            except Exception:
                try:
                    container.ws_clients.remove(client)
                except ValueError:
                    pass

        if container.settings.telegram.enabled and event.severity in {"warning", "critical"}:
            task = asyncio.create_task(telegram_bot.send_event_alert(event.cloud_payload()))
            container.background_tasks.add(task)
            task.add_done_callback(container.background_tasks.discard)

    return on_scene_event


async def _start_cameras(container: AppContainer) -> None:
    cfg = container.settings
    cameras = cfg.cameras
    if container.license_state is not None:
        cameras = filter_cameras(cameras, container.license_state.max_cameras)
        if not container.license_state.telegram_allowed:
            cfg.telegram.enabled = False

    antispoof_checker = None
    if cfg.antispoof.enabled:
        antispoof_checker = build_checker(
            backend=cfg.antispoof.backend,
            model_path=(
                container.base_dir / cfg.antispoof.model_path
                if cfg.antispoof.model_path
                else None
            ),
            min_score=cfg.antispoof.min_score,
            min_blur_variance=cfg.antispoof.min_blur_variance,
            live_index=cfg.antispoof.live_index,
        )

    scene_analyzers = {
        cam.id: build_scene_analyzer(cam.id, cfg.scene, container.base_dir)
        for cam in cameras
        if cam.enabled and cfg.scene.enabled
    }
    container.camera_manager = CameraManager(
        container.engine,
        container.db,
        compare_threshold=cfg.face.compare_threshold,
        match_debounce_sec=cfg.events.match_debounce_sec,
        save_snapshots=cfg.events.save_snapshots,
        snapshots_dir=container.base_dir / cfg.paths.snapshots_dir,
        enable_tracking=cfg.tracking.enabled,
        tracking_iou=cfg.tracking.iou_threshold,
        tracking_max_missed=cfg.tracking.max_missed_frames,
        frame_skip=cfg.camera.frame_skip,
        antispoof_enabled=cfg.antispoof.enabled,
        antispoof_min_blur=cfg.antispoof.min_blur_variance,
        antispoof_checker=antispoof_checker,
        scene_analyzers={key: value for key, value in scene_analyzers.items() if value},
        on_event=_make_on_scene_event(container),
    )
    on_match = _make_on_face_match(container)
    for cam in cameras:
        if cam.enabled:
            await container.camera_manager.add_camera(cam.id, cam.source, on_match=on_match)


# ── Ilova ────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    container: AppContainer = app.state.container
    cfg = container.settings

    production_errors = cfg.production_errors()
    if production_errors:
        raise RuntimeError(
            "Production konfiguratsiyasi xavfsiz emas: " + "; ".join(production_errors)
        )

    container.warmup()
    _load_remote_scene_cache(container)

    if cfg.telegram.enabled:
        await telegram_bot.init_bot(cfg.telegram.token, cfg.telegram.chat_id)

    if cfg.license.enabled:
        container.license_client = await _resolve_license_client(container)
        try:
            container.license_state = await container.license_client.refresh(active_cameras=0)
        except Exception as e:
            logger.warning("Litsenziya serveriga ulanib bo‘lmadi: %s", e)
            container.license_state = container.license_client.load_cache()

        if container.license_state and container.license_state.is_operational:
            await _start_cameras(container)
            container.license_task = asyncio.create_task(_license_heartbeat_loop(container))
        else:
            logger.error("Litsenziya faol emas — kameralar ishga tushirilmadi.")
    else:
        await _start_cameras(container)

    # Arxiv tozalash kameralardan mustaqil: obuna to'xtatilgan bo'lsa ham
    # eski biometrik kadrlar muddatidan ortiq saqlanib qolmasligi kerak.
    container.retention_task = asyncio.create_task(retention_loop(container))

    if cfg.cloud_sync.enabled:
        def health_payload():
            thermal = Path("/sys/class/thermal/thermal_zone0/temp")
            try:
                temperature = float(thermal.read_text().strip()) / 1000
            except (OSError, ValueError):
                temperature = None
            disk = shutil.disk_usage(container.base_dir / "data")
            queue = container.outbox.stats()
            return {
                "cameras_active": len(container.camera_manager.cameras)
                if container.camera_manager
                else 0,
                "temperature_c": temperature,
                "disk_free_bytes": disk.free,
                "outbox_pending": queue["pending"],
                "outbox_bytes": queue["bytes"],
                "app_version": __version__,
                "model_version": cfg.face.model_version,
            }

        container.cloud_sync = CloudEventSync(
            cfg.cloud_sync,
            container.outbox,
            health_provider=health_payload,
            config_applier=lambda payload: _apply_remote_scene_config(container, payload),
        )
        container.cloud_sync_task = asyncio.create_task(container.cloud_sync.run())

    try:
        yield
    finally:
        await container.aclose()


def create_app(container: Optional[AppContainer] = None) -> FastAPI:
    """Ilovani yig'ish.

    Args:
        container: Testlar uchun tayyor konteyner. Berilmasa `config.yaml`
            asosida yangi konteyner quriladi (og'ir komponentlar dangasa).
    """
    resolved_container = container or AppContainer(BASE_DIR)
    production = resolved_container.settings.environment == "production"
    app = FastAPI(
        title="Chaqimchi AI — Server Edition",
        lifespan=lifespan,
        docs_url=None if production else "/docs",
        redoc_url=None if production else "/redoc",
        openapi_url=None if production else "/openapi.json",
    )
    app.state.container = resolved_container

    origins = app.state.container.settings.server.cors_origins
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(origins),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    register_error_handlers(app)

    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR)), name="assets")
    app.include_router(system.router)
    app.include_router(auth.router)
    app.include_router(persons.router)
    app.include_router(events.router)
    app.include_router(calibrate.router)
    app.include_router(backup.router)
    app.include_router(vision.router)
    return app


app = create_app()
