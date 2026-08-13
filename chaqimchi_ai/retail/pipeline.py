"""Retail zanjiri — kadrdan hodisagacha, hodisadan harakatgacha.

Bo'laklar alohida yozilgan va alohida sinalgan, lekin qurilmada ular bitta
zanjir bo'lishi kerak:

    kamera → harakat filtri → FrameBroker → detektor + analiz → qoida → harakat
                                    ↑                                      │
                              InferenceBudget ←── o'lchangan latency ──────┘

Bu modul o'sha zanjir va boshqa hech narsa.  Ichida na kamera ochish, na
ffmpeg ishga tushirish bor — ular chaqiruvchining ishi.  Shu sabab butun
mantiq apparatsiz, soatga bog'lanmagan holda sinaladi.

Uchta qaror shu yerda qotirilgan:

1. **Harakat filtri `offer()` da**, `analyze()` da emas.  Fon modeli (MOG2)
   har kadrni ko'rishi kerak; faqat tanlangan kadrlarni ko'rsa fonni noto'g'ri
   o'rganadi va harakat bor joyda ham "harakat yo'q" deb turaveradi.
2. **`complete()` har doim chaqiriladi** (`finally`).  Aks holda detektor
   xato bergan kamera abadiy "tahlil qilinmoqda" holatida qolib, boshqa hech
   qachon navbat olmaydi — bitta xato butun kamerani o'chirib qo'yardi.
3. **Klip kechiktiriladi.**  Hodisa 14:30:00 da bo'lsa klip [14:29:50,
   14:30:20] oralig'i, ya'ni oxirgi 20 soniya hali yozilmagan.  Darhol
   kesilsa aynan "keyin nima bo'ldi" degan qism yo'qoladi.  Hodisaning o'zi
   kutmaydi — u allaqachon yuborilgan, klip keyinroq qo'shiladi.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from datetime import time as clock_time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from chaqimchi_ai.event_models import EdgeEvent
from chaqimchi_ai.retail.broker import FrameBroker
from chaqimchi_ai.retail.claims import Priority
from chaqimchi_ai.retail.ringbuffer import RingBuffer
from chaqimchi_ai.retail.rules import Decision, RuleEngine
from chaqimchi_ai.scene_analytics import SceneAnalyzer

logger = logging.getLogger(__name__)

#: Harakat ulushi shu qiymatga yetganda kamera to'liq og'irlik oladi.  0.10 —
#: kadrning o'ndan biri o'zgargan, ya'ni kamera oldidan odam o'tgan.  Undan
#: yuqorisi (yorug'lik o'zgarishi, shamolda tebrangan bayroq) qo'shimcha ulush
#: bermaydi: shovqin muhim hodisadan ustun turmasligi kerak.
MOTION_SATURATION = 0.10

#: `latency_sec` musbat bo'lishi shart (byudjet buni talab qiladi).  Soat
#: o'lchov farqini ko'rsatmasa ham kamera bo'shatilishi kerak.
MIN_LATENCY_SEC = 1e-6

#: Kesilmagan klip so'rovlari cheklovi.  ffmpeg buzilib qolsa navbat cheksiz
#: o'smasin — eng eskisi tashlanadi va `dropped` da ko'rinadi.
MAX_PENDING_CLIPS = 200


@dataclass
class _Camera:
    analyzer: SceneAnalyzer
    clips: Optional[RingBuffer] = None
    offered: int = 0
    gated: int = 0
    analyzed: int = 0
    errors: int = 0


@dataclass(frozen=True)
class _PendingClip:
    event: EdgeEvent
    camera_id: str
    moment: float
    ready_at: float


@dataclass(frozen=True)
class Analysis:
    """Bitta tahlilning natijasi — kuzatuv va test uchun."""

    camera_id: str
    events: List[EdgeEvent]
    decisions: List[Decision]
    latency_sec: float
    rescued: bool
    failed: bool = False


@dataclass
class _Totals:
    offered: int = 0
    gated: int = 0
    analyzed: int = 0
    errors: int = 0
    events: int = 0
    suppressed: int = 0
    action_errors: int = 0
    actions: Dict[str, int] = field(default_factory=dict)
    clips_written: int = 0
    clips_missing: int = 0
    clips_dropped: int = 0
    clips_unavailable: int = 0


class RetailPipeline:
    """Broker, analiz, qoida va klipni bir-biriga ulaydi.

    Uchta halqa bor va ular **ajratilgan**:

    * `offer()` — har kamera oqimidan kelgan kadr uchun (tez, faqat filtr);
    * `step()` — inferens halqasi, `burst / target_fps` dan tez aylanishi
      kerak (30 FPS uchun ~66 ms);
    * `flush_clips()` — sekin halqa, ffmpeg shu yerda ishlaydi.

    `flush_clips()` ni inferens halqasidan chaqirmang: `-c copy` bo'lsa ham
    ffmpeg yuzlab millisekund oladi va o'sha vaqt byudjetdan yeyiladi.

    **Qulf shu yerda.**  Broker va byudjet sof mantiq — ular qulfsiz va shunday
    qolishi kerak (test va o'qish uchun).  Lekin amalda `offer()` har kameraning
    o'z oqimidan, `step()` inferens oqimidan, `flush_clips()` esa uchinchisidan
    chaqiriladi, ya'ni broker holatiga uch tomondan tegiladi.  Qulf faqat
    holatga tegadigan qisqa joylarni yopadi; tahlil, ffmpeg va `on_action`
    qulfdan **tashqarida** ishlaydi — aks holda bitta sekin Telegram so'rovi
    butun tizimni to'xtatib qo'yardi.
    """

    def __init__(
        self,
        broker: FrameBroker,
        rules: RuleEngine,
        *,
        on_action: Callable[[str, EdgeEvent], None],
        on_clip: Optional[Callable[[EdgeEvent, Path], None]] = None,
        clip_dir: Optional[Path] = None,
        pre_sec: float = 10.0,
        post_sec: float = 20.0,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
        local_time: Optional[Callable[[], clock_time]] = None,
    ) -> None:
        if pre_sec < 0 or post_sec < 0:
            raise ValueError("pre_sec va post_sec manfiy bo'lmasin")
        self.broker = broker
        self.rules = rules
        self.on_action = on_action
        self.on_clip = on_clip
        self.clip_dir = Path(clip_dir) if clip_dir is not None else None
        self.pre_sec = float(pre_sec)
        self.post_sec = float(post_sec)
        #: `clock` — model qancha ishlaganini o'lchaydi (monoton bo'lishi shart).
        self._clock = clock
        #: `wall_clock` — klip qidiriladigan haqiqiy vaqt; segment fayllari
        #: UTC nomi bilan yoziladi, shuning uchun bu monoton soat emas.
        self._wall_clock = wall_clock
        #: Qoida jadvallari do'konning **mahalliy** vaqtiga qaraydi ("09:00 dan
        #: 21:00 gacha") — qurilma do'kon bilan bir zonada turadi.
        self._local_time = local_time or (lambda: datetime.now().time())
        self._cameras: Dict[str, _Camera] = {}
        self._pending: List[_PendingClip] = []
        self._totals = _Totals()
        self._lock = threading.Lock()

    # ── Ro'yxat ──────────────────────────────────────────────────────────

    def add_camera(
        self,
        camera_id: str,
        analyzer: SceneAnalyzer,
        *,
        priority: Priority = Priority.RETAIL,
        floor_fps: Optional[float] = None,
        clips: Optional[RingBuffer] = None,
        now: float = 0.0,
    ) -> None:
        """Kamerani zanjirga qo'shadi va brokerga ro'yxatdan o'tkazadi.

        `clips` berilmasa shu kameraning `save_clip` qoidalari bajarilmaydi —
        hodisa baribir yuboriladi, faqat videosiz.
        """
        with self._lock:
            self._cameras[camera_id] = _Camera(analyzer=analyzer, clips=clips)
            self.broker.register(camera_id, priority=priority, floor_fps=floor_fps, now=now)

    # ── Kadr qabul qilish ────────────────────────────────────────────────

    def offer(self, camera_id: str, frame: Any, *, now: float) -> bool:
        """Kameradan kelgan xom kadr.  Harakat bo'lmasa shu yerda to'xtaydi.

        `False` — kadr tahlilga tushmadi: yo harakat yo'q, yo oldingi kadr
        hali navbatda turgan edi (uni almashtirdik).  Ikkalasi ham normal.

        Filtr analizator ichidagi bilan **aynan bitta** obyekt: fon modeli
        har kadrni ko'rgani uchun to'g'ri o'rganadi.
        """
        camera = self._require(camera_id)
        # Filtr qulfdan tashqarida: u har kadr uchun ishlaydi va uni qulf
        # ichiga olish 8 kameraning oqimini navbatga tizib qo'yardi.  Xavfsiz,
        # chunki har kameraning fon modeliga faqat o'z oqimi tegadi.
        gate = camera.analyzer.motion
        ratio = gate.motion_ratio(frame)
        with self._lock:
            camera.offered += 1
            self._totals.offered += 1
            if ratio < gate.min_area_ratio:
                camera.gated += 1
                self._totals.gated += 1
                return False
            score = min(1.0, ratio / MOTION_SATURATION)
            return self.broker.submit(camera_id, frame, motion_score=score, now=now)

    # ── Inferens halqasi ─────────────────────────────────────────────────

    def step(self, *, now: float) -> Optional[Analysis]:
        """Bitta tahlil qadami.  Navbat yoki byudjet bo'sh bo'lsa `None`."""
        with self._lock:
            claim = self.broker.acquire(now)
            if claim is None:
                return None
            camera = self._require(claim.camera_id)

        # Tahlil qulfdan tashqarida — eng uzun ish shu va u boshqa kameralarning
        # kadr yuborishini to'sib qo'ymasligi kerak.
        started = self._clock()
        events: List[EdgeEvent] = []
        failed = False
        try:
            events = camera.analyzer.analyze(claim.frame, now=now)
        except Exception:
            failed = True
            logger.exception("[%s] tahlil xatosi", claim.camera_id)
        finally:
            latency = max(self._clock() - started, MIN_LATENCY_SEC)
            with self._lock:
                camera.analyzed += 1
                self._totals.analyzed += 1
                if failed:
                    camera.errors += 1
                    self._totals.errors += 1
                self._totals.events += len(events)
                # Kamera har qanday holatda bo'shatilishi kerak — xato bo'lsa ham.
                self.broker.complete(claim.camera_id, latency_sec=latency, now=now)

        decisions: List[Decision] = []
        if events:
            local_time = self._local_time()
            with self._lock:
                # Qoida dvigatelida cooldown holati bor — u ham qulf ostida.
                decisions = self.rules.decisions(events, now=now, local_time=local_time)
                self._totals.suppressed += len(events) - len(decisions)
            for decision in decisions:
                self._dispatch(decision, camera_id=claim.camera_id)
        return Analysis(
            camera_id=claim.camera_id,
            events=events,
            decisions=decisions,
            latency_sec=latency,
            rescued=claim.rescued,
            failed=failed,
        )

    def _dispatch(self, decision: Decision, *, camera_id: str) -> None:
        for action in decision.actions:
            with self._lock:
                self._totals.actions[action] = self._totals.actions.get(action, 0) + 1
            if action == "save_clip":
                self._queue_clip(decision.event, camera_id=camera_id)
                continue
            try:
                self.on_action(action, decision.event)
            except Exception:
                # Telegram javob bermasligi tahlilni to'xtatmasin: qolgan
                # harakatlar va keyingi kadrlar ishlashda davom etadi.
                with self._lock:
                    self._totals.action_errors += 1
                logger.exception("[%s] '%s' harakati bajarilmadi", camera_id, action)

    # ── Klip ─────────────────────────────────────────────────────────────

    def _queue_clip(self, event: EdgeEvent, *, camera_id: str) -> None:
        moment = self._wall_clock()
        with self._lock:
            camera = self._cameras[camera_id]
            if camera.clips is None or self.clip_dir is None:
                self._totals.clips_unavailable += 1
                return
            self._pending.append(
                _PendingClip(
                    event=event,
                    camera_id=camera_id,
                    moment=moment,
                    ready_at=moment + self.post_sec,
                )
            )
            if len(self._pending) > MAX_PENDING_CLIPS:
                self._pending.pop(0)
                self._totals.clips_dropped += 1

    def flush_clips(self, *, wall_now: Optional[float] = None) -> List[Path]:
        """Yozilib bo'lgan kliplarni kesadi.  **Sekin halqadan chaqirilsin.**

        Klip tayyor bo'lganda hodisaning `metadata.clip_path` maydoni
        to'ldiriladi va `on_clip` chaqiriladi — cloud hodisani allaqachon
        olgan, endi unga video qo'shiladi.
        """
        wall_now = self._wall_clock() if wall_now is None else float(wall_now)
        with self._lock:
            ready = [item for item in self._pending if item.ready_at <= wall_now]
            if not ready:
                return []
            self._pending = [item for item in self._pending if item.ready_at > wall_now]
            buffers = {item.camera_id: self._cameras[item.camera_id].clips for item in ready}

        # ffmpeg qulfdan tashqarida: kesish yuzlab millisekund oladi va bu
        # vaqtda inferens halqasi to'xtab turmasligi kerak.
        written: List[Path] = []
        for item in ready:
            buffer = buffers.get(item.camera_id)
            if buffer is None:  # kamerada ring buffer yo'q
                with self._lock:
                    self._totals.clips_unavailable += 1
                continue
            output = Path(self.clip_dir or ".") / f"{item.camera_id}-{item.event.event_id}.mp4"
            try:
                path = buffer.extract(
                    item.moment,
                    output=output,
                    pre_sec=self.pre_sec,
                    post_sec=self.post_sec,
                )
            except Exception:
                path = None
                logger.exception("[%s] klip kesilmadi", item.camera_id)
            if path is None:
                with self._lock:
                    self._totals.clips_missing += 1
                continue
            with self._lock:
                self._totals.clips_written += 1
            item.event.metadata["clip_path"] = str(path)
            written.append(path)
            if self.on_clip is not None:
                try:
                    self.on_clip(item.event, path)
                except Exception:
                    with self._lock:
                        self._totals.action_errors += 1
                    logger.exception("[%s] klip xabari yuborilmadi", item.camera_id)
        return written

    # ── Holat ────────────────────────────────────────────────────────────

    def _require(self, camera_id: str) -> _Camera:
        camera = self._cameras.get(camera_id)
        if camera is None:
            raise KeyError(f"Kamera zanjirga qo'shilmagan: {camera_id}")
        return camera

    @property
    def pending_clips(self) -> int:
        with self._lock:
            return len(self._pending)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return self._stats()

    def _stats(self) -> Dict[str, Any]:
        return {
            "broker": self.broker.stats(),
            "offered": self._totals.offered,
            "gated": self._totals.gated,
            "analyzed": self._totals.analyzed,
            "errors": self._totals.errors,
            "events": self._totals.events,
            "suppressed": self._totals.suppressed,
            "actions": dict(sorted(self._totals.actions.items())),
            "action_errors": self._totals.action_errors,
            "clips": {
                "pending": len(self._pending),
                "written": self._totals.clips_written,
                "missing": self._totals.clips_missing,
                "dropped": self._totals.clips_dropped,
                "unavailable": self._totals.clips_unavailable,
            },
            "cameras": {
                camera_id: {
                    "offered": camera.offered,
                    "gated": camera.gated,
                    "analyzed": camera.analyzed,
                    "errors": camera.errors,
                }
                for camera_id, camera in sorted(self._cameras.items())
            },
        }
