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

Hodisalar mavjud **outbox**ga yoziladi (`data/outbox.db`, WAL rejimi) va uni
allaqachon bor cloud sync yuklaydi.  Ya'ni bu xizmatga internet, token yoki
qayta urinish mantig'i kerak emas — u faqat diskka yozadi.  Telegram xabarini
ham cloud yuboradi (`cloud/notify.py`), shuning uchun `telegram_alert` bu
yerda alohida integratsiya emas: hodisa outboxga tushadi, qolganini cloud
qiladi.

Ishga tushirish:

    python -m chaqimchi_ai.retail.service --config config/config.yaml
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

import yaml

from chaqimchi_ai.event_models import EdgeEvent
from chaqimchi_ai.outbox import EventOutbox
from chaqimchi_ai.retail.broker import FrameBroker
from chaqimchi_ai.retail.budget import InferenceBudget
from chaqimchi_ai.retail.claims import Priority
from chaqimchi_ai.retail.pipeline import RetailPipeline
from chaqimchi_ai.retail.ringbuffer import RingBuffer
from chaqimchi_ai.retail.rules import RuleEngine
from chaqimchi_ai.retail.runner import CameraSource, RetailRunner
from chaqimchi_ai.scene_analytics import PersonDetector, SceneAnalyzer, build_person_detector
from chaqimchi_ai.settings import AppSettings

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

        `enqueue` `INSERT OR IGNORE` ishlatadi, ya'ni hodisa allaqachon
        yuborilgan bo'lsa bu qator e'tiborsiz qoladi — klip yo'li faqat hali
        yuborilmagan hodisaga qo'shiladi.  Bu ataylab: hodisani klip uchun
        ushlab turishdan ko'ra klipsiz, lekin **o'z vaqtida** yuborish afzal.
        """
        logger.info("[%s] klip tayyor: %s", event.camera_id, path)
        self.outbox.enqueue(event)


def _resolve(base_dir: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base_dir / path


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
    cfg = settings.retail
    if not cfg.enabled:
        raise RuntimeError("retail.enabled: false — xizmat ishga tushmaydi")
    if not cfg.cameras:
        raise RuntimeError("retail.cameras bo'sh — kamera ro'yxati kerak")

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
        InferenceBudget(
            target_fps=cfg.target_fps, min_fps=cfg.min_fps, max_fps=cfg.max_fps
        )
    )
    rules_path = _resolve(base_dir, cfg.rules_path) if cfg.rules_path else None
    pipeline = RetailPipeline(
        broker,
        load_rules(rules_path),
        on_action=sink,
        on_clip=sink.clip_ready,
        clip_dir=_resolve(base_dir, cfg.clip_dir),
        pre_sec=cfg.pre_sec,
        post_sec=cfg.post_sec,
    )
    runner = RetailRunner(
        pipeline,
        housekeeping_sec=cfg.housekeeping_sec,
        on_stats=_log_stats if on_stats is None else on_stats,
    )

    buffer_dir = _resolve(base_dir, cfg.buffer_dir)
    recording = [camera for camera in cfg.cameras if camera.record_url]
    # Disk kvotasi umumiy: 40 GB ni yozayotgan kameralar teng bo'lishadi.
    # Bo'lmasa har kamera to'liq kvotani o'ziniki deb bilib, 8 kamerada
    # 320 GB talab qilardi — 128 GB disk esa oldin to'lardi.
    per_camera = cfg.buffer_max_bytes // max(1, len(recording))

    for camera in cfg.cameras:
        analyzer = SceneAnalyzer(camera.id, detector, settings.scene)
        clips = (
            RingBuffer(
                camera.id,
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
                camera_id=camera.id,
                stream_url=camera.stream_url,
                priority=PRIORITIES[camera.priority],
                record_url=camera.record_url,
                sample_fps=camera.sample_fps,
                floor_fps=camera.floor_fps,
            ),
            analyzer,
            clips=clips,
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


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Chaqimchi Retail AI xizmati")
    parser.add_argument("--config", default="config/config.yaml", help="config.yaml yo'li")
    parser.add_argument("--base-dir", default=".", help="loyiha ildizi")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    base_dir = Path(args.base_dir).resolve()
    settings = AppSettings.load(_resolve(base_dir, args.config), base_dir=base_dir)

    runner = build_runner(settings, base_dir)
    runner.start()

    stopped = threading.Event()

    def _handle(signum, _frame) -> None:
        logger.info("Signal %s — to'xtatilmoqda", signum)
        stopped.set()

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)
    try:
        stopped.wait()
    finally:
        runner.stop()
    logger.info("Retail xizmati to'xtadi")
    return 0


if __name__ == "__main__":  # pragma: no cover - qo'lda ishga tushirish
    raise SystemExit(main())
