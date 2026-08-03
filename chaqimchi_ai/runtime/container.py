"""AppContainer — barcha uzoq yashovchi komponentlarning yagona egasi.

Bungacha `webapp/main.py` da sakkizta modul-global va ular uchun qo'lda yozilgan
`global X; if X is None:` singleton'lari bor edi. Ular uch muammoni tug'dirgan:

1. `app.dependency_overrides` ishlamagan — handlerlar `get_db()` ni to'g'ridan-to'g'ri
   chaqirgan, `Depends()` orqali emas. Shu sababli testlar marshrutlarga
   umuman murojaat qila olmagan (`tests/test_webapp_routes.py` faqat yo'l
   ro'yxatini tekshiradi).
2. Thread-safe emas — birinchi chaqiruv threadpool'da poyga holatiga tushardi.
3. Testlar orasida holat oqib ketardi (global'lar hech qachon tozalanmasdi).

Konteyner shu uchtasini ham hal qiladi: bitta obyekt, `app.state.container` da
yashaydi, testda tayyor (soxta) komponentlar bilan qurish mumkin.

Komponentlar **dangasa** quriladi — `FaceEngine` ONNX modelini 3-8 soniya va
~400 MB bilan yuklaydi, shuning uchun uni faqat rostdan kerak bo'lganda quramiz.
Testlar hech qachon qurmasligi uchun `engine_or_none` bor.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, List, Optional, Set

from chaqimchi_ai.audit import AuditLog
from chaqimchi_ai.database import FaceDatabase
from chaqimchi_ai.events import EventLog
from chaqimchi_ai.roi import RoiConfig
from chaqimchi_ai.settings import AppSettings, load_app_settings

if TYPE_CHECKING:  # pragma: no cover
    from chaqimchi_ai.camera_manager import CameraManager
    from chaqimchi_ai.face_engine import FaceEngine
    from chaqimchi_ai.licensing.client import EdgeLicenseClient
    from chaqimchi_ai.licensing.models import LicenseState
    from chaqimchi_ai.vision_agent import VisionAgent

logger = logging.getLogger(__name__)


class AppContainer:
    """Uzoq yashovchi komponentlar egasi.

    Args:
        base_dir: Loyiha ildizi — barcha nisbiy yo'llar shundan hisoblanadi.
        settings: Tayyor sozlamalar. Berilmasa `config.yaml` dan yuklanadi.
        engine / db / events / audit: Testlar uchun oldindan qurilgan
            komponentlar. Berilgani dangasa qurishni chetlab o'tadi.
    """

    def __init__(
        self,
        base_dir: Path,
        *,
        settings: Optional[AppSettings] = None,
        engine: Optional["FaceEngine"] = None,
        db: Optional[FaceDatabase] = None,
        events: Optional[EventLog] = None,
        audit: Optional[AuditLog] = None,
    ) -> None:
        self.base_dir = Path(base_dir)

        self._settings = settings
        self._engine = engine
        self._db = db
        self._events = events
        self._audit = audit
        self._vision: Optional["VisionAgent"] = None

        # Lifespan tomonidan boshqariladigan holat.
        self.camera_manager: Optional["CameraManager"] = None
        self.license_state: Optional["LicenseState"] = None
        self.license_client: Optional["EdgeLicenseClient"] = None
        self.license_task: Optional[Any] = None
        self.retention_task: Optional[Any] = None
        #: Oxirgi arxiv tozalash natijasi (`chaqimchi_ai.retention.PurgeResult`).
        self.last_purge: Optional[Any] = None
        self.ws_clients: List[Any] = []
        # Fon vazifalariga kuchli havola. `asyncio.create_task` natijasi
        # saqlanmasa, task o'rtada GC bo'lib ketishi va xatosi hech qachon
        # ko'rinmasligi mumkin.
        self.background_tasks: Set[Any] = set()

    # ── Sozlamalar ────────────────────────────────────────────────────────

    @property
    def settings(self) -> AppSettings:
        if self._settings is None:
            self._settings = load_app_settings(self.base_dir)
        return self._settings

    # ── Yuz yadrosi ───────────────────────────────────────────────────────

    @property
    def engine(self) -> "FaceEngine":
        """ONNX modelini yuklaydi (3-8s). Faqat rostdan kerak bo'lganda chaqiring."""
        if self._engine is None:
            # Import shu yerda: `face_engine` insightface'ni tortadi, uni
            # modul darajasida import qilish testlarni sekinlashtiradi.
            from chaqimchi_ai.face_engine import FaceEngine

            cfg = self.settings
            roi = cfg.roi
            self._engine = FaceEngine(
                model_name=cfg.face.model_name,
                det_size=cfg.face.det_size,
                preprocess_max_side=cfg.face.preprocess_max_side,
                roi=RoiConfig(
                    enabled=roi.enabled,
                    normalized=roi.normalized,
                    x1=roi.x1,
                    y1=roi.y1,
                    x2=roi.x2,
                    y2=roi.y2,
                ),
            )
        return self._engine

    @property
    def engine_or_none(self) -> Optional["FaceEngine"]:
        """Qurilgan bo'lsa qaytaradi, aks holda None — **qurmaydi**.

        `/health` va `/ready` shuni ishlatadi: ular "hali yuklanmoqda" javobini
        berishi kerak, model yuklashni boshlab yubormasligi kerak.
        """
        return self._engine

    # ── Ma'lumot omborlari ────────────────────────────────────────────────

    @property
    def db(self) -> FaceDatabase:
        if self._db is None:
            cfg = self.settings
            self._db = FaceDatabase(
                self.base_dir / cfg.paths.db_path,
                encrypt_embeddings=cfg.storage.encrypt_embeddings,
                vector_backend=cfg.storage.vector_backend,
            )
        return self._db

    @property
    def db_or_none(self) -> Optional[FaceDatabase]:
        return self._db

    @property
    def events(self) -> EventLog:
        if self._events is None:
            self._events = EventLog(self.base_dir / self.settings.paths.events_db)
        return self._events

    @property
    def audit(self) -> AuditLog:
        if self._audit is None:
            self._audit = AuditLog(self.base_dir / self.settings.paths.audit_db)
        return self._audit

    @property
    def vision(self) -> Optional["VisionAgent"]:
        """Ko'rish agenti — `vision.enabled` bo'lsa quriladi, aks holda None."""
        cfg = self.settings.vision
        if not cfg.enabled:
            return None
        if self._vision is None:
            from chaqimchi_ai.vision_agent import UsageStore, VisionAgent, VisionConfig

            self._vision = VisionAgent(
                VisionConfig(
                    enabled=cfg.enabled,
                    model=cfg.model,
                    max_side=cfg.max_side,
                    jpeg_quality=cfg.jpeg_quality,
                    min_interval_sec=cfg.min_interval_sec,
                    max_calls_per_day=cfg.max_calls_per_day,
                    max_calls_per_month=cfg.max_calls_per_month,
                    effort=cfg.effort,
                    max_tokens=cfg.max_tokens,
                    timeout_sec=cfg.timeout_sec,
                    telegram_alerts=cfg.telegram_alerts,
                ),
                UsageStore(self.base_dir / self.settings.paths.vision_db),
            )
        return self._vision

    # ── Hayotiy sikl ──────────────────────────────────────────────────────

    def warmup(self) -> None:
        """Og'ir komponentlarni oldindan qurish (lifespan boshida)."""
        self.engine  # noqa: B018 — dangasa qurishni majburlash
        self.db  # noqa: B018
        self.events  # noqa: B018
        self.audit  # noqa: B018

    async def aclose(self) -> None:
        """Barcha resurslarni yopish. Xato bo'lsa ham qolganini yopishda davom etadi."""
        if self.license_task is not None:
            self.license_task.cancel()
            self.license_task = None

        if self.retention_task is not None:
            self.retention_task.cancel()
            self.retention_task = None

        if self.camera_manager is not None:
            try:
                await self.camera_manager.stop_all()
            except Exception:
                logger.warning("Kameralarni to'xtatishda xato", exc_info=True)
            self.camera_manager = None

        # Telegram klienti — hozir modul-global; Faza 1 da konteynerga ko'chadi.
        try:
            from chaqimchi_ai import telegram_bot

            await telegram_bot.close_bot()
        except Exception:
            logger.debug("Telegram klientini yopishda xato", exc_info=True)

        self.ws_clients.clear()
