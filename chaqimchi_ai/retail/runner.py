"""Zanjirni qurilmada aylantiruvchi halqalar.

`RetailPipeline` "nima qilish kerak"ni biladi, bu modul esa uni **aylantiradi**:
kameradan kadr o'qiydi, inferens halqasini yuritadi va ffmpeg ishlarini alohida
oqimda bajaradi.

    har kamera: grab → (vaqti kelsa) retrieve → offer()      ← oqim/kamera
    inferens:   step()                                        ← bitta oqim
    uy ishlari: flush_clips(), prune(), stats                 ← bitta oqim

Uchta narsa ataylab shunday:

1. **`grab()` va `retrieve()` ajratilgan.**  `grab()` kadrni oladi, lekin
   dekodlamaydi; `retrieve()` esa dekodlaydi.  Kamera 15 FPS bersa ham bizga
   sekundiga 5 ta kadr yetadi — qolgan 10 tasi dekodlanmasdan tashlanadi.
   Har kadrni dekodlash 8 kamerada N100 ning katta qismini yeb qo'yardi.
2. **Uzilish kutilgan holat.**  RTSP uziladi (tarmoq, kamera qayta yuklandi,
   NVR band).  Har kamera o'z backoff'i bilan qayta ulanadi va boshqa
   kameralarga xalaqit bermaydi.
3. **ffmpeg alohida oqimda.**  Klip kesish va segment tozalash sekin ish;
   inferens halqasida turса byudjet o'sha vaqtni yo'qotardi.

Bu modul ham apparatsiz sinaladi: `capture_factory`, `spawn`, soat va uyqu
tashqaridan beriladi.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from chaqimchi_ai.event_models import EdgeEvent
from chaqimchi_ai.retail.claims import Priority
from chaqimchi_ai.retail.pipeline import RetailPipeline
from chaqimchi_ai.retail.ringbuffer import RingBuffer
from chaqimchi_ai.retail.tamper import TamperDetector
from chaqimchi_ai.scene_analytics import SceneAnalyzer

logger = logging.getLogger(__name__)

#: Qayta ulanish orasidagi eng uzun kutish.  Kamera kechqurun o'chirilgan
#: bo'lsa har soniyada urinib log to'ldirmaslik kerak, lekin ertalab
#: yoqilganda ham yarim daqiqadan ko'p kutmasin.
MAX_BACKOFF_SEC = 30.0

#: Kamera yopiq turganda oqim shuncha uxlaydi — bo'sh aylanish CPU yemasin.
CLOSED_SLEEP_SEC = 0.2

#: Shuncha ketma-ket muvaffaqiyatsiz urinishdan keyin kamera "o'chgan"
#: deb e'lon qilinadi.  Backoff 2, 4, 8 soniya bo'lgani uchun bu ~14
#: soniya: bitta tarmoq uzilishi yoki NVR qayta yuklanishi shovqin
#: bermaydi, lekin haqiqiy uzilish ikki daqiqada emas, yarim daqiqada
#: bilinadi.
OFFLINE_AFTER_FAILURES = 3


def open_stream(url: str) -> Any:
    """Standart RTSP ochish yo'li.

    `rtsp_transport=tcp` — UDP paket yo'qotishi buzuq kadr beradi.
    `BUFFERSIZE=1` — drayver kadr to'plab qo'ymasin: bizga eng yangisi kerak,
    navbatdagi eskirgani emas.
    """
    import cv2

    os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
    capture = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    try:
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:  # pragma: no cover - backend qo'llab-quvvatlamasligi mumkin
        pass
    return capture


@dataclass(frozen=True)
class CameraSource:
    """Bitta kameraning manzillari va roli.

    `stream_url` — **substream** (640×360 atrofida): tahlil shundan ketadi.
    `record_url` — **main stream**: klip uchun xom holda yoziladi.  Berilmasa
    ring buffer yozilmaydi va bu kamerada klip bo'lmaydi.
    """

    camera_id: str
    stream_url: str
    priority: Priority = Priority.RETAIL
    record_url: Optional[str] = None
    #: Sekundiga shuncha kadr dekodlanadi.  Qolgani `grab()` bilan tashlanadi.
    sample_fps: float = 5.0
    floor_fps: Optional[float] = None

    def __post_init__(self) -> None:
        if self.sample_fps <= 0:
            raise ValueError(f"{self.camera_id}: sample_fps musbat bo'lishi kerak")


@dataclass
class _Stream:
    source: CameraSource
    clips: Optional[RingBuffer] = None
    capture: Any = None
    recorder: Any = None
    last_sample: float = float("-inf")
    failures: int = 0
    retry_at: float = 0.0
    recorder_retry_at: float = 0.0
    frames: int = 0
    reconnects: int = 0
    recorder_starts: int = 0
    #: Kamera qachondan beri javob bermayapti.  `None` — hodisa hali
    #: e'lon qilinmagan (yo ishlayapti, yo urinishlar soni yetmagan).
    offline_since: Optional[float] = None

    @property
    def interval(self) -> float:
        return 1.0 / self.source.sample_fps


class RetailRunner:
    def __init__(
        self,
        pipeline: RetailPipeline,
        *,
        capture_factory: Callable[[str], Any] = open_stream,
        spawn: Callable[..., Any] = subprocess.Popen,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        housekeeping_sec: float = 30.0,
        idle_sleep_sec: float = 0.01,
        pressure: Optional[Callable[[], float]] = None,
        on_stats: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        if housekeeping_sec <= 0:
            raise ValueError("housekeeping_sec musbat bo'lishi kerak")
        self.pipeline = pipeline
        self.capture_factory = capture_factory
        self.spawn = spawn
        self.housekeeping_sec = float(housekeeping_sec)
        #: Ish yo'q bo'lganda inferens halqasi shuncha uxlaydi.  Byudjet
        #: `burst / target_fps` dan tez chaqirilishini talab qiladi (30 FPS,
        #: `burst=2` → 66 ms), shuning uchun bu undan ancha kichik.
        self.idle_sleep_sec = float(idle_sleep_sec)
        self._clock = clock
        self._sleep = sleep
        self._pressure = pressure
        self._on_stats = on_stats
        self._streams: Dict[str, _Stream] = {}
        self._threads: List[threading.Thread] = []
        self._stop = threading.Event()
        self._running = False

    # ── Ro'yxat ──────────────────────────────────────────────────────────

    def add_camera(
        self,
        source: CameraSource,
        analyzer: SceneAnalyzer,
        *,
        clips: Optional[RingBuffer] = None,
        tamper: Optional[TamperDetector] = None,
        now: Optional[float] = None,
    ) -> None:
        if self._running:
            raise RuntimeError("Kamera ishlab turgan runner'ga qo'shilmaydi")
        self._streams[source.camera_id] = _Stream(source=source, clips=clips)
        self.pipeline.add_camera(
            source.camera_id,
            analyzer,
            priority=source.priority,
            floor_fps=source.floor_fps,
            clips=clips,
            tamper=tamper,
            now=self._clock() if now is None else now,
        )

    # ── Bitta qadam (halqalarning ichi) ──────────────────────────────────

    def capture_once(self, camera_id: str, *, now: Optional[float] = None) -> bool:
        """Bitta kadr qadamining hammasi.  Kadr tahlilga yuborilsa `True`.

        Halqadan ajratilgani — sinash uchun: oqimlarsiz ham har holat
        (uzilish, qayta ulanish, kadr tashlash) tekshiriladi.
        """
        now = self._clock() if now is None else now
        stream = self._streams[camera_id]
        self._supervise_recorder(stream, now)

        if stream.capture is None:
            if now < stream.retry_at:
                return False
            capture = self.capture_factory(stream.source.stream_url)
            if capture is None or not capture.isOpened():
                self._release(capture)
                self._backoff(stream, now, "ochilmadi")
                return False
            stream.capture = capture
            stream.reconnects += 1
            # `failures` bu yerda **nolga tushmaydi**.  Ochilish oqim sog'lom
            # degani emas: NVR TCP ulanishni qabul qilib, keyin hech qanday
            # kadr bermasligi mumkin.  Shunday kamera har siklda qayta
            # ochilib, hisobni nolga tushirib yuborardi va hech qachon
            # "o'chgan" deb e'lon qilinmasdi.

        capture = stream.capture
        # `grab()` dekodlamaydi — oqimni yangi holatda ushlab turishning eng
        # arzon yo'li.
        if not capture.grab():
            self._backoff(stream, now, "oqim uzildi")
            return False
        # Kadr keldi — mana shu oqim tirikligining yagona haqiqiy isboti.
        stream.failures = 0
        self._recovered(stream, now)
        if now - stream.last_sample < stream.interval:
            return False

        ok, frame = capture.retrieve()
        if not ok or frame is None:
            self._backoff(stream, now, "kadr dekodlanmadi")
            return False

        stream.last_sample = now
        stream.frames += 1
        self.pipeline.offer(camera_id, frame, now=now)
        return True

    def inference_once(self, *, now: Optional[float] = None) -> bool:
        """Byudjet ruxsat bergan bitta tahlil.  Ish bo'lmasa `False`."""
        return self.pipeline.step(now=self._clock() if now is None else now) is not None

    def housekeeping_once(self) -> None:
        """Sekin ishlar: klip kesish, eski segmentlarni o'chirish, metrikalar."""
        if self._pressure is not None:
            try:
                self.pipeline.broker.budget.set_pressure(self._pressure())
            except Exception:
                logger.exception("Yuk signali o'qilmadi")
        try:
            self.pipeline.flush_clips()
        except Exception:
            logger.exception("Klip kesishda xato")
        for stream in self._streams.values():
            if stream.clips is None:
                continue
            try:
                stream.clips.prune()
            except Exception:
                logger.exception("[%s] segment tozalashda xato", stream.source.camera_id)
        if self._on_stats is not None:
            try:
                self._on_stats(self.stats())
            except Exception:
                logger.exception("Metrika yuborilmadi")

    # ── Ichki ────────────────────────────────────────────────────────────

    def _backoff(self, stream: _Stream, now: float, reason: str) -> None:
        self._release(stream.capture)
        stream.capture = None
        stream.failures += 1
        wait = min(MAX_BACKOFF_SEC, float(2**min(stream.failures, 5)))
        stream.retry_at = now + wait
        logger.warning(
            "[%s] %s — %.0f soniyadan keyin qayta urinamiz",
            stream.source.camera_id,
            reason,
            wait,
        )
        # Uzilish hodisaga aylanadi.  Bungacha kamera holati faqat
        # `stats()` ichida yashardi va do'kon egasi kamera o'chganini
        # hisobotdagi bo'shliqdan — bir necha kundan keyin — bilardi.
        if stream.offline_since is None and stream.failures >= OFFLINE_AFTER_FAILURES:
            stream.offline_since = now
            self._emit(
                EdgeEvent(
                    event_type="camera_offline",
                    severity="warning",
                    camera_id=stream.source.camera_id,
                    metadata={"reason": reason, "attempts": stream.failures},
                ),
                now=now,
            )

    def _recovered(self, stream: _Stream, now: float) -> None:
        if stream.offline_since is None:
            return
        downtime = round(max(0.0, now - stream.offline_since), 1)
        stream.offline_since = None
        logger.info("[%s] kamera tiklandi (%.0f soniya)", stream.source.camera_id, downtime)
        self._emit(
            EdgeEvent(
                event_type="camera_recovered",
                severity="info",
                camera_id=stream.source.camera_id,
                metadata={"downtime_sec": downtime},
            ),
            now=now,
        )

    def _emit(self, event: EdgeEvent, *, now: float) -> None:
        """Sog'liq hodisasini zanjirga uzatadi.

        Outboxga to'g'ridan-to'g'ri yozish mumkin edi, lekin u holda qoida
        dvigateli chetlab o'tilardi — cooldown ham, `telegram_alert` ham
        ishlamasdi.  Xato bo'lsa kadr halqasi to'xtamaydi: kamera o'qishdan
        muhimroq narsa yo'q.
        """
        try:
            self.pipeline.emit_system_event(event, now=now)
        except Exception:
            logger.exception("[%s] sog'liq hodisasi yuborilmadi", event.camera_id)

    @staticmethod
    def _release(capture: Any) -> None:
        if capture is None:
            return
        try:
            capture.release()
        except Exception:  # pragma: no cover - backend'ga xos
            logger.debug("Kamera yopilmadi", exc_info=True)

    def _supervise_recorder(self, stream: _Stream, now: float) -> None:
        """Ring buffer yozuvchi ffmpeg tirikligini tekshiradi.

        Jarayon o'lsa klip yozilmay qoladi va buni hech kim sezmaydi — hodisa
        bo'lganda "video yo'q" deb chiqadi.  Shuning uchun har kadr qadamida
        arzon `poll()` qilinadi.
        """
        source = stream.source
        if stream.clips is None or not source.record_url:
            return
        if stream.recorder is not None and stream.recorder.poll() is None:
            return
        if stream.recorder is not None:
            logger.warning("[%s] segment yozuvchi to'xtagan", source.camera_id)
            stream.recorder = None
        if now < stream.recorder_retry_at:
            return
        try:
            stream.recorder = self.spawn(
                stream.clips.record_command(source.record_url),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            stream.recorder_starts += 1
        except Exception:
            logger.exception("[%s] segment yozuvchi ishga tushmadi", source.camera_id)
        stream.recorder_retry_at = now + 5.0

    # ── Halqalar ─────────────────────────────────────────────────────────

    def _capture_loop(self, camera_id: str) -> None:
        stream = self._streams[camera_id]
        while not self._stop.is_set():
            try:
                self.capture_once(camera_id)
            except Exception:
                logger.exception("[%s] kadr halqasida xato", camera_id)
                self._stop.wait(1.0)
                continue
            if stream.capture is None:
                # Kamera yopiq — `grab()` bizni sekinlatmaydi, o'zimiz kutamiz.
                self._stop.wait(CLOSED_SLEEP_SEC)

    def _inference_loop(self) -> None:
        while not self._stop.is_set():
            try:
                if not self.inference_once():
                    self._sleep(self.idle_sleep_sec)
            except Exception:
                logger.exception("Inferens halqasida xato")
                self._stop.wait(1.0)

    def _housekeeping_loop(self) -> None:
        while not self._stop.wait(self.housekeeping_sec):
            self.housekeeping_once()

    # ── Boshqaruv ────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        if not self._streams:
            raise RuntimeError("Kamera qo'shilmagan")
        self._stop.clear()
        self._running = True
        self._threads = [
            threading.Thread(
                target=self._capture_loop, args=(camera_id,), name=f"retail-{camera_id}", daemon=True
            )
            for camera_id in self._streams
        ]
        self._threads.append(
            threading.Thread(target=self._inference_loop, name="retail-inference", daemon=True)
        )
        self._threads.append(
            threading.Thread(target=self._housekeeping_loop, name="retail-uy", daemon=True)
        )
        for thread in self._threads:
            thread.start()
        logger.info("Retail runner ishga tushdi: %d kamera", len(self._streams))

    def stop(self, *, timeout: float = 5.0) -> None:
        """To'xtatadi va resurslarni bo'shatadi.  Qayta chaqirish xavfsiz."""
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=timeout)
        self._threads = []
        self._running = False
        for stream in self._streams.values():
            self._release(stream.capture)
            stream.capture = None
            if stream.recorder is not None:
                self._terminate(stream.recorder)
                stream.recorder = None

    @staticmethod
    def _terminate(process: Any) -> None:
        try:
            process.terminate()
            process.wait(timeout=5)
        except Exception:
            logger.debug("Yozuvchi jarayon to'xtamadi", exc_info=True)

    @property
    def running(self) -> bool:
        return self._running

    def stats(self) -> Dict[str, Any]:
        data = self.pipeline.stats()
        data["streams"] = {
            camera_id: {
                "frames": stream.frames,
                "connected": stream.capture is not None,
                "reconnects": stream.reconnects,
                "failures": stream.failures,
                "offline": stream.offline_since is not None,
                "recorder": stream.recorder is not None,
                "recorder_starts": stream.recorder_starts,
            }
            for camera_id, stream in sorted(self._streams.items())
        }
        return data
