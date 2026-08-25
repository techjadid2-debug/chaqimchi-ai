"""Durable Vision Agent worker entrypoint.

FastAPI API tez javob berishi uchun Gemini, snapshot o'qish va audio
transkripsiya alohida compose processida bajariladi.

DIQQAT: bu jarayon `cloud.main`ni IMPORT QILMAYDI.  Avval qilardi — 313 KB
modul, 227 route va StaticFiles mountlari import-effekt sifatida yuklanib,
`lifespan` esa ishlamagani uchun production tekshiruvlarining birortasi
workerga tegmasdi: noto'g'ri env bilan worker "sog'lom" ko'rinib, jimgina
o'zining shaxsiy SQLite'iga yozib o'tirardi.  Endi kerakli narsalar
bevosita quriladi va production talablari shu yerda ham tekshiriladi.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
import time
from pathlib import Path

from cloud import vision_agent
from cloud.event_store import EventStore, event_store_from_env
from cloud.snapshots import snapshot_store_from_env
from cloud.store import CloudStore

logger = logging.getLogger("vision-worker")

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("CHAQIMCHI_CLOUD_DB", str(BASE_DIR / "data" / "cloud" / "cloud.db")))
HEARTBEAT_MARKER = Path("/tmp/vision-worker.heartbeat")


def _production() -> bool:
    return os.environ.get("CHAQIMCHI_ENV", "development").strip().lower() == "production"


def validate_environment() -> None:
    """API `lifespan`idagi asosiy production talablari worker uchun ham.

    Muvaffaqiyatsizlikda ANIQ xato bilan darhol chiqiladi — compose
    `restart: unless-stopped` bilan bu log'da ko'rinadi.  Jim davom etish
    esa "sog'lom ko'ringan, hech narsa qilmaydigan" worker degani edi.
    """
    problems = []
    if _production():
        if not os.environ.get("DATABASE_URL", "").strip():
            problems.append("DATABASE_URL yo'q — worker prod'da SQLite'ga tushib qolardi")
        if not os.environ.get("CHAQIMCHI_S3_ENDPOINT", "").strip():
            problems.append("CHAQIMCHI_S3_ENDPOINT yo'q — media o'qib bo'lmaydi")
    if not vision_agent.configured():
        # Bu xato emas — kalit hali sozlanmagan bo'lishi mumkin.  Lekin
        # worker buni har startda aniq aytadi, jim qolmaydi.
        logger.warning(
            "Gemini sozlanmagan (CHAQIMCHI_GEMINI_API_KEY / CHAQIMCHI_GEMINI_VISION_MODEL) — "
            "joblar metadata-javob rejimida ishlaydi"
        )
    if problems:
        for problem in problems:
            logger.error("Vision worker ishga tushmadi: %s", problem)
        sys.exit(2)


def _build_stores() -> tuple[EventStore, CloudStore]:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    event_store = (
        event_store_from_env(BASE_DIR)
        if database_url
        else EventStore(sqlite_path=DB_PATH.parent / "events.db")
    )
    # migrate=False: cloud.db'ning yagona yozuvchisi va migratori API.
    cloud_store = CloudStore(DB_PATH, migrate=False)
    return event_store, cloud_store


def _touch_heartbeat() -> None:
    """Compose healthcheck o'qiydigan marker.

    `worker_loop`ning O'ZI chaqiradi — ya'ni marker faqat sikl haqiqatan
    aylanayotganda yangilanadi.  Avvalgi alohida heartbeat-task sikl o'lib
    qolganda ham tiklayverar, healthcheck yolg'on "sog'lom" ko'rsatardi.
    """
    try:
        HEARTBEAT_MARKER.write_text(str(time.time()), encoding="ascii")
    except OSError:
        pass


async def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    validate_environment()
    event_store, cloud_store = _build_stores()
    snapshots = snapshot_store_from_env(BASE_DIR)

    async def media_get(key: str) -> bytes:
        return await asyncio.to_thread(snapshots.get, key)

    async def media_delete(key: str) -> None:
        await asyncio.to_thread(snapshots.delete, key)

    async def media_put(key: str, data: bytes, mime: str) -> None:
        await asyncio.to_thread(snapshots.put, key, data, content_type=mime)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for item in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(item, stop.set)
        except NotImplementedError:  # pragma: no cover - Windows local runner
            pass
    await vision_agent.worker_loop(
        event_store,
        cameras_for_site=cloud_store.list_cameras,
        media_get=media_get,
        media_delete=media_delete,
        media_put=media_put,
        stop=stop,
        heartbeat=_touch_heartbeat,
    )


if __name__ == "__main__":
    asyncio.run(run())
