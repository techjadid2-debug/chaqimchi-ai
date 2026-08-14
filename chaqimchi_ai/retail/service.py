"""Do'kon analitikasi — alohida xizmat sifatida.

Nega alohida jarayon:

* **Xato ajratilgan.**  Detektor yoki ffmpeg yiqilsa yuz tanish va API
  ishlashda davom etadi; teskarisi ham.  Ikkalasi bitta jarayonda bo'lsa
  bittasining xotira sizishi ikkinchisini ham o'ldirardi.
* **Kameralar odatda boshqacha.**  Eshik va kassa — analitika, kirish eshigi —
  yuz tanish.  Bir kamera ikkalasiga kerak bo'lsa oqim ikki marta ochiladi;
  bu narx to'langan bilib to'lanadi.
* **Qayta ishga tushirish arzon.**  Qoida o'zgarganda faqat shu xizmat
  qayta yuklanadi.

Hodisalar **outbox**ga yoziladi (`data/outbox.db`, WAL rejimi) va shu retail
xizmatidagi mustaqil sync worker HTTPS orqali qayta urinishli yuklaydi.
Telegram xabarini
ham cloud yuboradi (`cloud/notify.py`), shuning uchun `telegram_alert` bu
yerda alohida integratsiya emas: hodisa outboxga tushadi, qolganini cloud
qiladi.

Ishga tushirish:

    python -m chaqimchi_ai.retail.service --config config/config.yaml

Qurilmada `--config` berilmaydi: yo'l `CHAQIMCHI_CONFIG` da turadi va yuz
tanish xizmati bilan **bitta** fayl bo'ladi — kamera ikki joyda ta'riflanmasin.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import yaml

from chaqimchi_ai.cloud_sync import CloudEventSync
from chaqimchi_ai.event_models import EdgeEvent
from chaqimchi_ai.outbox import EventOutbox
from chaqimchi_ai.retail.broker import FrameBroker
from chaqimchi_ai.retail.budget import InferenceBudget
from chaqimchi_ai.retail.claims import Priority
from chaqimchi_ai.retail.inventory import (
    CameraPlan,
    describe,
    merge_cameras,
    read_sotqin_cache,
)
from chaqimchi_ai.retail.pipeline import RetailPipeline
from chaqimchi_ai.retail.ringbuffer import RingBuffer
from chaqimchi_ai.retail.rules import RuleEngine, Schedule
from chaqimchi_ai.retail.runner import CameraSource, RetailRunner
from chaqimchi_ai.retail.tamper import TamperDetector
from chaqimchi_ai.retail.vision_review import VisionReviewer
from chaqimchi_ai.scene_analytics import PersonDetector, SceneAnalyzer, build_person_detector
from chaqimchi_ai.settings import AppSettings, SceneSettings, default_config_path

logger = logging.getLogger(__name__)

PRIORITIES: Dict[str, Priority] = {
    "security": Priority.SECURITY,
    "retail": Priority.RETAIL,
    "background": Priority.BACKGROUND,
}


def load_rules(path: Optional[Path]) -> RuleEngine:
    """Qoidalarni YAML yoki JSON dan o'qiydi.

    Fayl **bor, lekin buzuq** bo'lsa xato beriladi va xizmat ishga tushmaydi.
    Jimgina bo'sh qoidalar bilan davom etish yomonroq bo'lardi: sotuvchi
    qoidani yozgan deb o'ylab yuradi, tizim esa hech qachon ogohlantirmaydi.
    """
    if path is None:
        return RuleEngine()
    if not path.is_file():
        raise FileNotFoundError(f"Qoidalar fayli topilmadi: {path}")
    text = path.read_text(encoding="utf-8")
    payload = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    return RuleEngine.from_config(payload or {})


class OutboxSink:
    """Qoida buyurgan harakatni bajaradi: hodisani outboxga yozadi.

    `cloud_sync` va `telegram_alert` ikkalasi ham shu yerda tugaydi — farqi
    cloud tomonda: `warning`/`critical` hodisalar uchun u Telegramga yozadi.
    Edge tomonda ikkinchi Telegram mijozini saqlash shovqin va takror xabar
    demakdir.
    """

    def __init__(self, outbox: EventOutbox) -> None:
        self.outbox = outbox
        self.written = 0

    def __call__(self, action: str, event: EdgeEvent) -> None:
        if action == "ignore":
            return
        self.outbox.enqueue(event)
        self.written += 1

    def clip_ready(self, event: EdgeEvent, path: Path) -> None:
        """Klip tayyor bo'lgach hodisa yangilangan holda qayta yoziladi.

        Hodisa oldin yuborilgan bo'lsa ham outbox uni idempotent batch qilib
        qayta yuboradi va klipni alohida yuklaydi. Tez alert klip tayyor
        bo'lishini kutib qolmaydi.
        """
        logger.info("[%s] klip tayyor: %s", event.camera_id, path)
        event.clip_path = str(path)
        self.outbox.enqueue(event)


def prune_event_media(
    root: Path,
    *,
    retention_sec: int,
    max_bytes: int,
    suffixes: frozenset[str],
    now: Optional[float] = None,
) -> Tuple[int, int]:
    """Yuklangan/yetim event mediasini muddat va kvota bo'yicha tozalaydi."""
    if not root.is_dir():
        return 0, 0
    current = time.time() if now is None else float(now)
    files = []
    for path in root.iterdir():
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        files.append((path, stat.st_mtime, stat.st_size))

    removed = 0
    freed = 0
    kept = []
    for path, modified, size in files:
        if modified < current - retention_sec:
            try:
                path.unlink()
            except OSError:
                logger.warning("Eski klip o'chirilmadi: %s", path)
                kept.append((path, modified, size))
            else:
                removed += 1
                freed += size
        else:
            kept.append((path, modified, size))

    total = sum(size for _path, _modified, size in kept)
    for path, _modified, size in sorted(kept, key=lambda item: item[1]):
        if total <= max_bytes:
            break
        try:
            path.unlink()
        except OSError:
            logger.warning("Kvotadagi klip o'chirilmadi: %s", path)
            continue
        total -= size
        removed += 1
        freed += size
    return removed, freed


def prune_event_clips(
    root: Path, *, retention_sec: int, max_bytes: int, now: Optional[float] = None
) -> Tuple[int, int]:
    return prune_event_media(
        root,
        retention_sec=retention_sec,
        max_bytes=max_bytes,
        suffixes=frozenset({".mp4"}),
        now=now,
    )


def build_reviewer(
    settings: AppSettings, base_dir: Path, sink: Callable[[str, EdgeEvent], None]
) -> Optional[VisionReviewer]:
    """Ko'rish agenti yoqilgan bo'lsa ko'rikchini yig'adi, aks holda `None`.

    `vision.enabled: false` (standart) bo'lsa `anthropic` kutubxonasi ham
    import qilinmaydi va bir tiyin sarflanmaydi.  Kalit topilmasa xizmat
    yiqilmaydi — analitika AI'siz ishlashda davom etadi, faqat ogohlantirish
    izohsiz qoladi.
    """
    cfg = settings.vision
    if not cfg.enabled:
        return None
    from chaqimchi_ai.vision_agent import UsageStore, VisionAgent, VisionConfig

    agent = VisionAgent(
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
        # Sarf hisobi yuz tanish xizmati bilan **bitta** fayl: ikkalasi ham
        # shu bazaga yozadi, ya'ni kunlik limit umumiy bo'ladi.
        UsageStore(_resolve(base_dir, settings.paths.vision_db)),
    )
    logger.info(
        "Ko'rish agenti yoqilgan: %s, kamera boshiga %d soniyada bir marta, "
        "kuniga %d tagacha",
        cfg.model,
        cfg.min_interval_sec,
        cfg.max_calls_per_day,
    )
    return VisionReviewer(agent, sink)


def _resolve(base_dir: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base_dir / path


def sotqin_cache_path(settings: AppSettings, base_dir: Path) -> Path:
    """Sotqin cloud config keshining yo'li.

    Uch manba, shu tartibda: konfig, muhit o'zgaruvchisi (agent ham shundan
    o'qiydi), standart yo'l.
    """
    if settings.retail.sotqin_config_path:
        return _resolve(base_dir, settings.retail.sotqin_config_path)
    return Path(
        os.environ.get(
            "CHAQIMCHI_SOTQIN_CONFIG_CACHE",
            "/opt/chaqimchi/shared/data/sotqin-config.json",
        )
    )


def plan_cameras(settings: AppSettings, base_dir: Path) -> Tuple[List[CameraPlan], Any]:
    """Zanjirga tushadigan kameralar va cloud config revisiyasi.

    Manba cloud inventari: o'rnatuvchi kamerani panelda qo'shsa, u shu yerga
    tushadi.  Lokal konfig faqat qo'shimcha sozlamani beradi (klip manbasi,
    prioritet, kadr tezligi).
    """
    cfg = settings.retail
    if cfg.cameras_source == "config":
        return merge_cameras([], cfg.cameras), None
    cache = read_sotqin_cache(sotqin_cache_path(settings, base_dir))
    return merge_cameras(cache["cameras"], cfg.cameras), cache["revision"]


def apply_remote_site_settings(settings: AppSettings, base_dir: Path) -> None:
    """Cloud onboardingdagi line/zone/soatlarni retail zanjiriga qo'llaydi."""
    if settings.retail.cameras_source == "config":
        return
    cache = read_sotqin_cache(sotqin_cache_path(settings, base_dir))
    remote = cache.get("config") or {}
    scene_payload = settings.scene.model_dump()
    for key in ("occupancy_limit", "loitering_sec", "queue_limit", "zones", "lines"):
        if key in remote:
            scene_payload[key] = remote[key]
    settings.scene = SceneSettings.model_validate(scene_payload)
    if remote.get("open_from") and remote.get("open_to"):
        settings.retail.open_from = str(remote["open_from"])
        settings.retail.open_to = str(remote["open_to"])


def retail_event_filter(settings: AppSettings, base_dir: Path) -> Callable[[EdgeEvent], bool]:
    """Cloud shartnomasida yoqilmagan paket event/klip/alert chiqarmaydi."""
    if settings.retail.cameras_source == "config":
        return lambda _event: True
    cache = read_sotqin_cache(sotqin_cache_path(settings, base_dir))
    if cache.get("revision") is None:
        # Mustaqil/dev konfiguratsiya: cloud shartnomasi yo'q, lokal qoidalar
        # yagona manba. Haqiqiy paired config revision bilan keladi.
        return lambda _event: True
    enabled = {
        str(item.get("code"))
        for item in cache.get("cloud_features") or []
        if isinstance(item, dict) and item.get("code")
    }
    traffic = {"line_crossed", "occupancy_exceeded", "dwell_exceeded"}
    queue = {"queue_threshold_exceeded"}
    security = {
        "zone_entered",
        "loitering",
        "after_hours_presence",
        "camera_tampered",
    }

    def allowed(event: EdgeEvent) -> bool:
        if event.event_type == "person_detected":
            return False
        if event.event_type in traffic:
            return "person_count" in enabled
        if event.event_type in queue:
            return "queue_length" in enabled
        if event.event_type in security:
            return "store_security" in enabled
        return False

    return allowed


def build_runner(
    settings: AppSettings,
    base_dir: Path,
    *,
    detector: Optional[PersonDetector] = None,
    outbox: Optional[EventOutbox] = None,
    on_stats: Optional[Any] = None,
) -> RetailRunner:
    """Konfigdan to'liq ishga tayyor runner yig'adi.

    `detector` va `outbox` tashqaridan berilishi mumkin — sinovda model fayli
    va cloud kerak bo'lmasin.
    """
    apply_remote_site_settings(settings, base_dir)
    cfg = settings.retail
    if not cfg.enabled:
        raise RuntimeError("retail.enabled: false — xizmat ishga tushmaydi")
    cameras, revision = plan_cameras(settings, base_dir)
    if not cameras:
        raise RuntimeError(
            "Kamera topilmadi: cloud inventari ham, retail.cameras ham bo'sh"
        )
    logger.info("%s (config revision: %s)", describe(cameras), revision)

    if detector is None:
        # Bitta model, hamma kamera uchun: xotira ham, iGPU compile vaqti ham
        # bir marta sarflanadi.
        detector = build_person_detector(settings.scene, base_dir)
    if outbox is None:
        sync = settings.cloud_sync
        outbox = EventOutbox(
            base_dir / "data" / "outbox.db",
            max_bytes=sync.queue_max_bytes,
            retention_days=sync.queue_days,
        )

    sink = OutboxSink(outbox)
    reviewer = build_reviewer(settings, base_dir, sink)
    broker = FrameBroker(
        InferenceBudget(
            target_fps=cfg.target_fps, min_fps=cfg.min_fps, max_fps=cfg.max_fps
        )
    )
    rules_path = _resolve(base_dir, cfg.rules_path) if cfg.rules_path else None
    business_hours = (
        Schedule.parse(cfg.open_from, cfg.open_to) if cfg.open_from and cfg.open_to else None
    )
    rules = load_rules(rules_path)
    if business_hours is not None and "ish-vaqti" in rules.schedules:
        # Owner paneldagi ish vaqti queue qoidasiga ham tegishli. YAML dagi
        # 09:00–21:00 faqat onboarding hali to'ldirilmagan paytdagi default.
        rules.schedules["ish-vaqti"] = business_hours
    clip_dir = _resolve(base_dir, cfg.clip_dir)
    snapshot_dir = _resolve(base_dir, settings.paths.snapshots_dir)
    pipeline = RetailPipeline(
        broker,
        rules,
        on_action=sink,
        on_clip=sink.clip_ready,
        on_review=None if reviewer is None else reviewer.submit,
        clip_dir=clip_dir,
        snapshot_dir=snapshot_dir,
        pre_sec=cfg.pre_sec,
        post_sec=cfg.post_sec,
        business_hours=business_hours,
        after_hours_debounce_sec=cfg.after_hours_debounce_sec,
        event_filter=retail_event_filter(settings, base_dir),
    )
    stats_callback = _log_stats if on_stats is None else on_stats

    def report_stats(stats: Dict[str, Any]) -> None:
        removed, freed = prune_event_clips(
            clip_dir,
            retention_sec=cfg.buffer_retention_sec,
            max_bytes=settings.cloud_sync.queue_max_bytes,
        )
        if removed:
            logger.info("Eski event kliplari tozalandi: %d fayl, %.1f MB", removed, freed / 2**20)
        snapshot_removed, snapshot_freed = prune_event_media(
            snapshot_dir,
            retention_sec=cfg.buffer_retention_sec,
            max_bytes=max(1, settings.cloud_sync.queue_max_bytes // 4),
            suffixes=frozenset({".jpg", ".jpeg"}),
        )
        if snapshot_removed:
            logger.info(
                "Eski event rasmlari tozalandi: %d fayl, %.1f MB",
                snapshot_removed,
                snapshot_freed / 2**20,
            )
        stats_callback(stats)

    runner = RetailRunner(
        pipeline,
        housekeeping_sec=cfg.housekeeping_sec,
        on_stats=report_stats,
        reviewer=reviewer,
    )

    buffer_dir = _resolve(base_dir, cfg.buffer_dir)
    recording = [camera for camera in cameras if camera.record_url]
    # Disk kvotasi umumiy: 40 GB ni yozayotgan kameralar teng bo'lishadi.
    # Bo'lmasa har kamera to'liq kvotani o'ziniki deb bilib, 8 kamerada
    # 320 GB talab qilardi — 128 GB disk esa oldin to'lardi.
    per_camera = cfg.buffer_max_bytes // max(1, len(recording))

    for camera in cameras:
        analyzer = SceneAnalyzer(camera.camera_id, detector, settings.scene)
        clips = (
            RingBuffer(
                camera.camera_id,
                buffer_dir,
                segment_sec=cfg.segment_sec,
                retention_sec=cfg.buffer_retention_sec,
                max_bytes=per_camera,
            )
            if camera.record_url
            else None
        )
        runner.add_camera(
            CameraSource(
                camera_id=camera.camera_id,
                stream_url=camera.stream_url,
                priority=PRIORITIES[camera.priority],
                record_url=camera.record_url,
                sample_fps=camera.sample_fps,
                floor_fps=camera.floor_fps,
            ),
            analyzer,
            clips=clips,
            tamper=(
                TamperDetector(min_duration_sec=cfg.tamper_min_duration_sec)
                if cfg.tamper_enabled
                else None
            ),
        )
    return runner


def _log_stats(stats: Dict[str, Any]) -> None:
    """Ishga tushirishda kuzatiladigan asosiy raqamlar.

    `floor_violations` — qurilma yetishmayapti (kamera kafolatlangan
    tezlikdan sekin ko'rilyapti).  `p95_latency_ms` — model sekinlashgan.
    """
    broker = stats["broker"]
    logger.info(
        "tahlil=%d hodisa=%d klip=%d | kafolat buzilishi=%d p95=%.0f ms target=%.1f FPS",
        stats["analyzed"],
        stats["events"],
        stats["clips"]["written"],
        broker["floor_violations"],
        broker["budget"]["p95_latency_ms"],
        broker["budget"]["target_fps"],
    )
    vision = stats.get("vision")
    if vision:
        # Xarajat alohida qatorda: bu yagona **pul yeydigan** raqam va uni
        # log ichida qidirib yurmaslik kerak.
        logger.info(
            "AI ko'rigi: %d ta xulosa, $%.4f | o'tkazib yuborilgan: oraliq=%d "
            "limit=%d navbat=%d xato=%d",
            vision["completed"],
            vision["cost_usd"],
            vision["throttled"],
            vision["over_budget"],
            vision["dropped"],
            vision["failed"],
        )


def _watcher(
    settings: AppSettings, base_dir: Path, stopped: threading.Event
) -> Callable[[Dict[str, Any]], None]:
    """Metrikani yozadi va cloud config o'zgarganini kuzatadi.

    Kamera cloud panelida qo'shilganda xizmat o'zini to'xtatadi, systemd esa
    uni qayta ishga tushiradi (`Restart=always`).  Kamerani ishlab turgan
    zanjirga qo'shish ancha murakkab bo'lardi: broker, byudjet va ring buffer
    holati o'zgarishi kerak.  Qayta ishga tushish bir necha soniya oladi va
    natijasi aniq — yarim qo'llangan config'dan yaxshi.
    """
    cache = sotqin_cache_path(settings, base_dir)
    try:
        revision = read_sotqin_cache(cache)["revision"]
    except ValueError:
        revision = None

    def observe(stats: Dict[str, Any]) -> None:
        _log_stats(stats)
        if not settings.retail.restart_on_config_change:
            return
        try:
            current = read_sotqin_cache(cache)["revision"]
        except ValueError:
            logger.exception("Sotqin config keshi o'qilmadi — eski ro'yxat qoladi")
            return
        if current != revision:
            logger.warning(
                "Cloud config o'zgardi (%s → %s) — xizmat qayta ishga tushadi",
                revision,
                current,
            )
            stopped.set()

    return observe


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Chaqimchi Retail AI xizmati")
    parser.add_argument(
        "--config", default=None, help="config yo'li (standart: $CHAQIMCHI_CONFIG)"
    )
    parser.add_argument("--base-dir", default=".", help="loyiha ildizi")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    base_dir = Path(args.base_dir).resolve()
    # Qurilmada konfig yo'li `CHAQIMCHI_CONFIG` da turadi (sotqin.env) — xizmat
    # yuz tanish bilan **bitta** faylni o'qishi kerak, aks holda kamera ikki
    # joyda ta'riflanardi.
    config_path = _resolve(base_dir, args.config) if args.config else default_config_path(base_dir)
    logger.info("Konfig: %s", config_path)
    settings = AppSettings.load(config_path, base_dir=base_dir)

    stopped = threading.Event()
    sync_cfg = settings.cloud_sync
    outbox = EventOutbox(
        base_dir / "data" / "outbox.db",
        max_bytes=sync_cfg.queue_max_bytes,
        retention_days=sync_cfg.queue_days,
    )
    runner = build_runner(
        settings,
        base_dir,
        outbox=outbox,
        on_stats=_watcher(settings, base_dir, stopped),
    )
    runner.start()
    sync_thread: Optional[threading.Thread] = None
    if sync_cfg.enabled:
        sync = CloudEventSync(sync_cfg, outbox)
        sync_thread = threading.Thread(
            target=lambda: asyncio.run(sync.run(stop_requested=stopped.is_set)),
            name="retail-cloud-sync",
            daemon=True,
        )
        sync_thread.start()

    def _handle(signum, _frame) -> None:
        logger.info("Signal %s — to'xtatilmoqda", signum)
        stopped.set()

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)
    try:
        stopped.wait()
    finally:
        stopped.set()
        runner.stop()
        if sync_thread is not None:
            sync_thread.join(timeout=sync_cfg.interval_sec + 5)
    logger.info("Retail xizmati to'xtadi")
    return 0


if __name__ == "__main__":  # pragma: no cover - qo'lda ishga tushirish
    raise SystemExit(main())
