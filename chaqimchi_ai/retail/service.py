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
from chaqimchi_ai.retail.pressure import SystemPressure
from chaqimchi_ai.retail.ringbuffer import RingBuffer
from chaqimchi_ai.retail.rules import RuleEngine, Schedule
from chaqimchi_ai.retail.runner import CameraSource, RetailRunner
from chaqimchi_ai.retail.tamper import TamperDetector
from chaqimchi_ai.scene_analytics import PersonDetector, SceneAnalyzer, build_person_detector
from chaqimchi_ai.settings import AppSettings, SceneSettings, default_config_path

logger = logging.getLogger(__name__)

PRIORITIES: Dict[str, Priority] = {
    "security": Priority.SECURITY,
    "retail": Priority.RETAIL,
    "background": Priority.BACKGROUND,
}

#: Qurilma sog'ligi haqidagi hodisalar hech qanday paketga bog'lanmaydi.
#: Mijoz qaysi funksiyani sotib olganidan qat'i nazar, kamerasi
#: ishlamayotganini bilishi shart.
HEALTH_EVENTS = frozenset({"camera_offline", "camera_recovered", "stream_frozen"})


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
    for key in ("occupancy_limit", "loitering_sec", "queue_limit"):
        if key in remote and remote[key] is not None:
            scene_payload[key] = remote[key]
    # Geometriya faqat cloud'da HAQIQATAN chizilgan bo'lsa olinadi.
    # Ilgari shart `key in remote` edi — cloud `get_site_config()` esa har
    # doim bo'sh `"lines": []` qaytaradi, ya'ni ulanish bilanoq sehrgarda
    # chizilgan chiziq runtime'da o'chib, kirish-chiqish sanash jimgina
    # to'xtardi (config.yaml va panel esa chiziq bor deb ko'rsatib
    # turardi).  `cloud_config.apply()` xuddi shu sababdan `if lines or
    # zones:` bilan ishlaydi — bu yerda ham o'sha qoida.
    for key in ("zones", "lines"):
        if remote.get(key):
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
    # Davomat: cloud yoqqan bo'lsa VA kamera davomat ro'yxatida bo'lsa.
    # Eski cloud `face_captured`ni tanimaydi va butun batchni rad etadi —
    # shu filtr yoqilmagan saytda hodisa chiqishining oldini oladi.
    attendance_on = bool((cache.get("attendance") or {}).get("enabled"))
    attendance_cameras = {
        str(camera_id)
        for camera_id in (cache.get("config") or {}).get("attendance_camera_ids") or []
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
        if event.event_type == "face_captured":
            return attendance_on and str(event.camera_id) in attendance_cameras
        # Kamera sog'ligi litsenziyalanadigan funksiya emas.  Mijoz qaysi
        # paketni olganidan qat'i nazar, kamerasi o'chganini bilishi kerak —
        # aks holda u ishlamayotgan tizim uchun pul to'lab yuraveradi.
        if event.event_type in HEALTH_EVENTS:
            return True
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
        raise RuntimeError("Kamera topilmadi: cloud inventari ham, retail.cameras ham bo'sh")
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
    broker = FrameBroker(
        InferenceBudget(target_fps=cfg.target_fps, min_fps=cfg.min_fps, max_fps=cfg.max_fps)
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
        # Bu argumentsiz `budget.py` dagi `pressure >= 0.85` tarmog'i o'lik
        # kod bo'lib turadi: byudjet faqat latency bo'yicha sozlanadi va
        # qurilma qizib ketganini kech biladi.
        pressure=SystemPressure(),
    )

    buffer_dir = _resolve(base_dir, cfg.buffer_dir)
    recording = [camera for camera in cameras if camera.record_url]
    # Disk kvotasi umumiy: 40 GB ni yozayotgan kameralar teng bo'lishadi.
    # Bo'lmasa har kamera to'liq kvotani o'ziniki deb bilib, 8 kamerada
    # 320 GB talab qilardi — 128 GB disk esa oldin to'lardi.
    per_camera = cfg.buffer_max_bytes // max(1, len(recording))

    # Davomat kameralari (cloud belgilagan, ko'pi bilan 2 ta): faqat shularda
    # yuz kadri chiqadi — qolganlari uchun qo'shimcha ish yo'q.
    cache = read_sotqin_cache(sotqin_cache_path(settings, base_dir))
    attendance_enabled = bool((cache.get("attendance") or {}).get("enabled"))
    attendance_cameras = {
        str(camera_id)
        for camera_id in (cache.get("config") or {}).get("attendance_camera_ids") or []
    }

    # Demografiya (jins/yosh): bitta umumiy estimator, faqat kirish
    # chizig'i bor kameralarga beriladi.  Bosim oshsa analyzer o'zi
    # o'chiradi (byudjetdagi pressure orqali).
    from chaqimchi_ai.retail.demography import build_demography_estimator

    demography = build_demography_estimator(settings, base_dir)
    entrance_cameras = {line.camera_id for line in settings.scene.lines}

    def read_pressure() -> float:
        return broker.budget.pressure

    for camera in cameras:
        analyzer = SceneAnalyzer(
            camera.camera_id,
            detector,
            settings.scene,
            attendance=attendance_enabled and camera.camera_id in attendance_cameras,
            demography=demography if camera.camera_id in entrance_cameras else None,
            pressure=read_pressure,
        )
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
        "tahlil=%d hodisa=%d klip=%d | kafolat buzilishi=%d p95=%.0f ms target=%.1f FPS bosim=%.2f",
        stats["analyzed"],
        stats["events"],
        stats["clips"]["written"],
        broker["floor_violations"],
        broker["budget"]["p95_latency_ms"],
        broker["budget"]["target_fps"],
        broker["budget"]["pressure"],
    )
    # Bosim yuqori bo'lsa qaysi manba sababchi ekani aytiladi: "bosim 0.9"
    # nima qilishni aytmaydi, "xotira 0.9" esa aytadi.
    breakdown = stats.get("pressure")
    if breakdown and broker["budget"]["pressure"] >= 0.7:
        logger.warning(
            "Qurilma bosim ostida: CPU=%.2f xotira=%.2f harorat=%.2f",
            breakdown.get("cpu", 0.0),
            breakdown.get("memory", 0.0),
            breakdown.get("temperature", 0.0),
        )


def retail_status_path(settings: AppSettings, base_dir: Path) -> Path:
    """Zanjir holati yoziladigan fayl.

    Sotqin agenti bilan aloqa uchun eng sodda kanal: ikkalasi ham alohida
    jarayon, lekin bitta diskda.  Soket yoki IPC qo'shish faqat ishlamay
    qolishi mumkin bo'lgan yana bitta narsa bo'lardi.
    """
    if settings.retail.status_path:
        return _resolve(base_dir, settings.retail.status_path)
    return Path(
        os.environ.get(
            "CHAQIMCHI_RETAIL_STATUS",
            "/opt/chaqimchi/shared/data/retail-status.json",
        )
    )


def write_status(path: Path, stats: Dict[str, Any], *, now: Optional[float] = None) -> None:
    """Kameralarning haqiqiy ulanish holatini diskka yozadi.

    Nima uchun kerak: agent `cameras_active` ni `ffprobe` natijasidan
    olardi, ya'ni "RTSP manzil javob beryaptimi" degan savolga javob
    berardi.  Lekin kamera ffprobe uchun ochiq bo'lib, retail zanjiri
    bir soat backoff'da turishi mumkin — 72 soatlik soak testi esa aynan
    shu farqni sezmasdan "4 kamera ishlayapti" deb sertifikatlab qo'yardi.
    """
    streams = stats.get("streams") or {}
    payload = {
        "updated_at": time.time() if now is None else float(now),
        "cameras_configured": len(streams),
        "cameras_active": sum(
            1 for item in streams.values() if item.get("connected") and not item.get("offline")
        ),
        "cameras": {
            camera_id: {
                "connected": bool(item.get("connected")),
                "offline": bool(item.get("offline")),
                "frames": int(item.get("frames") or 0),
                "reconnects": int(item.get("reconnects") or 0),
            }
            for camera_id, item in streams.items()
        },
        "analyzed": stats.get("analyzed", 0),
        "events": stats.get("events", 0),
        # Tarif faollashtirilmagani sabab tashlangan hodisalar — panel buni
        # ko'rsatishi shart: "hodisa bor, lekin cloudga bormayapti".
        "plan_filtered": stats.get("plan_filtered", 0),
        "pressure": stats.get("pressure") or {},
    }
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        # `mkdir` ham `try` ichida: yo'l band bo'lsa (fayl turgan bo'lsa)
        # u ham xato beradi, va holat fayli yozilmagani uchun butun
        # zanjirni to'xtatish noto'g'ri bo'lardi.
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
        os.replace(temporary, path)
    except OSError:
        logger.warning("Holat fayli yozilmadi: %s", path)
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            # Yo'lning o'zi yaroqsiz bo'lsa tozalash ham imkonsiz.
            pass


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
    status = retail_status_path(settings, base_dir)
    try:
        revision = read_sotqin_cache(cache)["revision"]
    except ValueError:
        revision = None

    def observe(stats: Dict[str, Any]) -> None:
        _log_stats(stats)
        write_status(status, stats)
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


#: Jonli kadr yozish qadami (soniya) va o'lchami.
LIVE_FRAME_INTERVAL_SEC = 2.0
LIVE_FRAME_WIDTH = 640
LIVE_FRAME_JPEG_QUALITY = 70

#: Issiqlik to'ri qancha tez-tez diskka tushadi.
HEATMAP_FLUSH_INTERVAL_SEC = 600.0


def _heatmap_flush_loop(pipeline: RetailPipeline, base_dir: Path, stopped: threading.Event) -> None:
    """Har 10 daqiqada yig'ilgan to'rlarni faylga yozadi.

    Yuborishni lokal ilova qiladi (cloud hisob ma'lumotlari unda) — biz
    faqat `data/heatmap/` ga yozamiz; 200 kelganda ilova o'chiradi.
    """
    from datetime import datetime, timezone

    from chaqimchi_ai.retail.heatmap import write_heatmap_file

    directory = base_dir / "heatmap"
    while not stopped.wait(HEATMAP_FLUSH_INTERVAL_SEC):
        try:
            drained = pipeline.drain_heatmaps()
            if not drained:
                continue
            bucket = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
            for camera_id, item in drained.items():
                write_heatmap_file(directory, camera_id, bucket, item["grid"], int(item["frames"]))
        except Exception:
            logger.exception("Issiqlik to'ri yozilmadi")


def _live_frame_loop(pipeline: RetailPipeline, base_dir: Path, stopped: threading.Event) -> None:
    """Jonli ko'rish kadrlarini diskka yozib turadi.

    Lokal ilova heartbeat javobidan `live-request.json` yozadi; biz shu
    yerda so'ralgan kameralarning **oxirgi tahlil kadri**ni (yangi RTSP
    ulanishsiz) 640px JPEG qilib `live/` ga qo'yamiz; ilova esa uni
    cloudga yuboradi.  So'rov yo'q payt sikl deyarli bepul (bitta stat).
    """
    import json as json_module
    from datetime import datetime, timezone

    import cv2

    request_path = base_dir / "live-request.json"
    out_dir = base_dir / "live"

    while not stopped.wait(LIVE_FRAME_INTERVAL_SEC):
        if not request_path.is_file():
            continue
        try:
            raw = json_module.loads(request_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if not isinstance(raw, dict):
            continue
        now = datetime.now(timezone.utc)
        for camera_id, item in raw.items():
            try:
                until = datetime.fromisoformat(str((item or {}).get("until")))
            except (TypeError, ValueError):
                continue
            if until.tzinfo is None:
                until = until.replace(tzinfo=timezone.utc)
            if until <= now:
                continue
            frame = pipeline.latest_frame(str(camera_id))
            if frame is None:
                continue
            height, width = frame.shape[:2]
            if width > LIVE_FRAME_WIDTH:
                scale = LIVE_FRAME_WIDTH / width
                frame = cv2.resize(frame, (LIVE_FRAME_WIDTH, max(1, round(height * scale))))
            ok, encoded = cv2.imencode(
                ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), LIVE_FRAME_JPEG_QUALITY]
            )
            if not ok:
                continue
            out_dir.mkdir(parents=True, exist_ok=True)
            target = out_dir / f"{camera_id}.jpg"
            temporary = target.with_name(f".{target.name}.tmp")
            try:
                temporary.write_bytes(encoded.tobytes())
                os.replace(temporary, target)
            except OSError:
                temporary.unlink(missing_ok=True)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Chaqimchi Retail AI xizmati")
    parser.add_argument("--config", default=None, help="config yo'li (standart: $CHAQIMCHI_CONFIG)")
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
    threading.Thread(
        target=_live_frame_loop,
        args=(runner.pipeline, base_dir, stopped),
        name="live-frames",
        daemon=True,
    ).start()
    threading.Thread(
        target=_heatmap_flush_loop,
        args=(runner.pipeline, base_dir, stopped),
        name="heatmap-flush",
        daemon=True,
    ).start()
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
