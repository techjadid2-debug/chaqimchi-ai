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
import os
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
from chaqimchi_ai.retail.rules import Decision, RuleEngine, Schedule
from chaqimchi_ai.retail.tamper import FREEZE, TAMPER, TamperDetector
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

SECURITY_MEDIA_EVENTS = frozenset(
    {"camera_tampered", "after_hours_presence", "zone_entered", "loitering"}
)


def write_jpeg(path: Path, frame: Any) -> bool:
    """Kadrni atomik JPEG qilib yozadi; partial rasm hech qachon ko'rinmaydi."""
    import cv2

    ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(encoded.tobytes())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return True


@dataclass
class _Camera:
    analyzer: SceneAnalyzer
    clips: Optional[RingBuffer] = None
    tamper: Optional[TamperDetector] = None
    offered: int = 0
    gated: int = 0
    analyzed: int = 0
    errors: int = 0
    tamper_alerts: int = 0
    freezes: int = 0
    #: Oxirgi "ish vaqtidan tashqari" hodisasi — takror oqimini to'sish uchun.
    after_hours_at: float = float("-inf")
    #: Oxirgi ko'rilgan kadr — `ai_review` harakati shuni AI ga yuboradi.
    #: Faqat havola saqlanadi (nusxa emas): kadr allaqachon xotirada va uni
    #: har kadrda ko'chirish 8 kamerada behuda ish bo'lardi.
    last_frame: Any = None


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
    #: Cloud shartnomasida yoqilmagan paket sabab tashlab yuborilganlar.
    #: `suppressed` dan alohida: u — qoidalarning ongli qarori, bu esa
    #: "tarif faollashtirilmagan" belgisi va panelda ogohlantirish bo'lib
    #: chiqishi kerak (ilgari jimgina yutilardi).
    plan_filtered: int = 0
    action_errors: int = 0
    actions: Dict[str, int] = field(default_factory=dict)
    clips_written: int = 0
    clips_missing: int = 0
    clips_dropped: int = 0
    clips_unavailable: int = 0
    tamper_alerts: int = 0
    freezes: int = 0
    after_hours: int = 0
    snapshots_written: int = 0
    snapshots_missing: int = 0


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
        snapshot_dir: Optional[Path] = None,
        snapshot_writer: Callable[[Path, Any], bool] = write_jpeg,
        pre_sec: float = 10.0,
        post_sec: float = 20.0,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
        local_time: Optional[Callable[[], clock_time]] = None,
        business_hours: Optional[Schedule] = None,
        after_hours_debounce_sec: float = 300.0,
        event_filter: Optional[Callable[[EdgeEvent], bool]] = None,
    ) -> None:
        if pre_sec < 0 or post_sec < 0:
            raise ValueError("pre_sec va post_sec manfiy bo'lmasin")
        self.broker = broker
        self.rules = rules
        self.on_action = on_action
        self.on_clip = on_clip
        self.clip_dir = Path(clip_dir) if clip_dir is not None else None
        self.snapshot_dir = Path(snapshot_dir) if snapshot_dir is not None else None
        self.snapshot_writer = snapshot_writer
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
        #: Do'kon ish vaqti.  Berilsa, tashqarisida ko'ringan odam uchun
        #: `after_hours_presence` chiqadi.  Berilmasa bu hodisa umuman yo'q.
        self.business_hours = business_hours
        self.after_hours_debounce_sec = float(after_hours_debounce_sec)
        self.event_filter = event_filter or (lambda _event: True)
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
        tamper: Optional[TamperDetector] = None,
        now: float = 0.0,
    ) -> None:
        """Kamerani zanjirga qo'shadi va brokerga ro'yxatdan o'tkazadi.

        `clips` berilmasa shu kameraning `save_clip` qoidalari bajarilmaydi —
        hodisa baribir yuboriladi, faqat videosiz.  `tamper` berilmasa kamera
        yopilganini hech kim sezmaydi.
        """
        with self._lock:
            self._cameras[camera_id] = _Camera(analyzer=analyzer, clips=clips, tamper=tamper)
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
        # Qulfsiz: havolani almashtirish GIL ostida atomar, ya'ni o'quvchi
        # oqim eski yoki yangi kadrni oladi — ikkalasi ham butun kadr.  Har
        # kadr uchun qulf olish 8 kamerani navbatga tizib qo'yardi.
        camera.last_frame = frame
        # Kamera buzilishi **filtrdan oldin** tekshiriladi: yopilgan kamerada
        # harakat yo'q, ya'ni filtr uni o'tkazmasdi va buzilish hech qachon
        # sezilmasdi.
        if camera.tamper is not None:
            alert = camera.tamper.update(frame, now=now)
            if alert is not None:
                self._report_tamper(camera_id, alert, now=now)

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

        # Tahlilga tushgan kadr — AI ko'radigan ham aynan shu bo'lishi kerak,
        # oqimdagi keyingi tasodifiy kadr emas.
        camera.last_frame = claim.frame

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
                # Kamera har qanday holatda bo'shatilishi kerak — xato bo'lsa ham.
                self.broker.complete(claim.camera_id, latency_sec=latency, now=now)

        decisions: List[Decision] = []
        if events:
            after_hours = self._after_hours_event(events, claim.camera_id, now=now)
            if after_hours is not None:
                events.append(after_hours)
            decisions = self._report(events, camera_id=claim.camera_id, now=now)
        return Analysis(
            camera_id=claim.camera_id,
            events=events,
            decisions=decisions,
            latency_sec=latency,
            rescued=claim.rescued,
            failed=failed,
        )

    # ── Hodisadan harakatgacha ───────────────────────────────────────────

    def _report(self, events: List[EdgeEvent], *, camera_id: str, now: float) -> List[Decision]:
        """Hodisalarni qoidadan o'tkazib, harakatlarni bajaradi.

        Ikki manbadan chaqiriladi: inferens halqasi (tahlil natijasi) va kadr
        halqasi (kamera buzilishi).  Ikkalasi ham bir xil yo'ldan o'tishi
        kerak, aks holda buzilish hodisasiga qoida yozib bo'lmasdi.
        """
        original_count = len(events)
        events = [event for event in events if self.event_filter(event)]
        local_time = self._local_time()
        with self._lock:
            self._totals.events += original_count
            self._totals.plan_filtered += original_count - len(events)
            # Qoida dvigatelida cooldown holati bor — u ham qulf ostida.
            decisions = self.rules.decisions(events, now=now, local_time=local_time)
            self._totals.suppressed += len(events) - len(decisions)
        for decision in decisions:
            self._dispatch(decision, camera_id=camera_id)
        return decisions

    def _report_tamper(self, camera_id: str, alert: Any, *, now: float) -> None:
        """Buzilish yoki qotib qolgan oqim.

        Ikkalasi ham bir xil o'lchovdan chiqadi, lekin hodisa turi boshqa:
        qotgan oqimni "kamera yopilgan" deb aytish o'rnatuvchini noto'g'ri
        joyga — linzani artishga — yuboradi, aslida esa NVR qayta
        yuklanishi kerak.
        """
        frozen = getattr(alert, "kind", TAMPER) == FREEZE
        logger.warning(
            "[%s] %s: %s (%.0f soniya)",
            camera_id,
            "oqim qotib qoldi" if frozen else "kamera buzilgan",
            alert.reason,
            alert.duration_sec,
        )
        with self._lock:
            if frozen:
                self._cameras[camera_id].freezes += 1
                self._totals.freezes += 1
            else:
                self._cameras[camera_id].tamper_alerts += 1
                self._totals.tamper_alerts += 1
        self._report(
            [
                EdgeEvent(
                    event_type="stream_frozen" if frozen else "camera_tampered",
                    severity="critical",
                    camera_id=camera_id,
                    score=alert.score,
                    metadata={"reason": alert.reason, "duration_sec": alert.duration_sec},
                )
            ],
            camera_id=camera_id,
            now=now,
        )

    def emit_system_event(self, event: EdgeEvent, *, now: float) -> None:
        """Zanjirdan tashqarida tug'ilgan hodisa (kamera uzilishi, tiklanishi).

        `runner` uni to'g'ridan-to'g'ri outboxga yozishi ham mumkin edi, lekin
        u holda qoida dvigateli chetlab o'tilardi: cooldown, jadval va
        `telegram_alert` ishlamasdi.  Shu yo'ldan o'tgani uchun kamera
        sog'ligi hodisalari ham `config/rules.yaml` bilan boshqariladi.
        """
        self._report([event], camera_id=event.camera_id, now=now)

    def _after_hours_event(
        self, events: List[EdgeEvent], camera_id: str, *, now: float
    ) -> Optional[EdgeEvent]:
        """Ish vaqtidan tashqari ko'ringan odam.

        Alohida hodisa turi kerak, chunki bu boshqa savol: kunduzi kadrdagi
        odam — mijoz, kechasi esa **ogohlantirish**.  Mijozga ham "Odam
        aniqlandi" emas, "Ish vaqtidan tashqari harakat" deb ko'rsatiladi.
        """
        if self.business_hours is None:
            return None
        local_time = self._local_time()
        if local_time is None or self.business_hours.contains(local_time):
            return None
        people = [event for event in events if event.event_type == "person_detected"]
        if not people:
            return None
        with self._lock:
            camera = self._cameras[camera_id]
            if now - camera.after_hours_at < self.after_hours_debounce_sec:
                return None
            camera.after_hours_at = now
            self._totals.after_hours += 1
        return EdgeEvent(
            event_type="after_hours_presence",
            severity="warning",
            camera_id=camera_id,
            track_id=people[0].track_id,
            occupancy=len(people),
            metadata={"local_time": local_time.strftime("%H:%M")},
        )

    def _dispatch(self, decision: Decision, *, camera_id: str) -> None:
        self._attach_face_crop(decision.event, camera_id=camera_id)
        self._attach_security_snapshot(decision.event, camera_id=camera_id)
        # Qoida Telegram so'raganmi — hodisaning o'zida yozib qo'yiladi.
        # Bungacha `telegram_alert` harakati dekorativ edi: cloud faqat
        # severity'ga qarab yuborar, ya'ni qoidalardagi tanlov va
        # sovutishlar hech narsani boshqarmasdi.  Endi cloud/notify.py shu
        # bayroqqa bo'ysunadi (eski versiya hodisalarida bayroq bo'lmaydi —
        # u holda severity fallback ishlaydi).
        if decision.event.metadata is None:
            decision.event.metadata = {}
        decision.event.metadata["alert"] = "telegram_alert" in decision.actions
        for action in decision.actions:
            with self._lock:
                self._totals.actions[action] = self._totals.actions.get(action, 0) + 1
            if action == "save_clip":
                self._queue_clip(decision.event, camera_id=camera_id)
                continue
            if action == "ai_review":
                # Cloud tomonidagi AI ko'rigi uchun ajratilgan nom.  Edge'da
                # bajarilmaydi, lekin qoidalar faylida uchrasa xato bermasin —
                # mijozning eski konfigi validatsiyadan o'tsin.
                continue
            try:
                self.on_action(action, decision.event)
            except Exception:
                # Telegram javob bermasligi tahlilni to'xtatmasin: qolgan
                # harakatlar va keyingi kadrlar ishlashda davom etadi.
                with self._lock:
                    self._totals.action_errors += 1
                logger.exception("[%s] '%s' harakati bajarilmadi", camera_id, action)

    def drain_heatmaps(self) -> Dict[str, Any]:
        """Har kameraning yig'ilgan issiqlik to'rini olib bo'shatadi."""
        result: Dict[str, Any] = {}
        for camera_id, camera in self._cameras.items():
            grid = getattr(camera.analyzer, "heatmap", None)
            if grid is None:
                continue
            cells, frames, points = grid.drain()
            if points:
                result[camera_id] = {"grid": cells, "frames": frames}
        return result

    def latest_frame(self, camera_id: str) -> Optional[Any]:
        """Kameraning oxirgi tahlil qilingan kadri (jonli ko'rish uchun).

        Yangi RTSP ulanish YO'Q — kadr allaqachon xotirada turadi, uni
        faqat JPEG qilib berish qoladi.
        """
        camera = self._cameras.get(camera_id)
        return camera.last_frame if camera is not None else None

    def _attach_face_crop(self, event: EdgeEvent, *, camera_id: str) -> None:
        """`face_captured` uchun odam ramkasining yuqori qismini kesib oladi.

        To'liq kadr yuborilmaydi — maxfiylik (kadrda boshqa odamlar bor)
        va hajm: crop odatda 20-60 KB, to'liq kadr esa yarim megabayt.
        Yuzni topish/tanish bu yerda YO'Q — hammasi cloudda.
        """
        if event.event_type != "face_captured" or self.snapshot_dir is None:
            return
        bbox = (event.metadata or {}).get("bbox")
        camera = self._cameras.get(camera_id)
        frame = camera.last_frame if camera is not None else None
        if frame is None or not bbox or len(bbox) != 4:
            with self._lock:
                self._totals.snapshots_missing += 1
            return
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = (int(value) for value in bbox)
        # Yuqori ~35% + yon tomonlarga 10% chekka: bosh ramka chetiga tegib
        # turganda ham yuz kesilib qolmasin.
        margin = int((x2 - x1) * 0.10)
        top = max(0, y1)
        bottom = min(height, y1 + max(1, int((y2 - y1) * 0.35)))
        left = max(0, x1 - margin)
        right = min(width, x2 + margin)
        if bottom - top < 16 or right - left < 16:
            with self._lock:
                self._totals.snapshots_missing += 1
            return
        path = self.snapshot_dir / f"{camera_id}-{event.event_id}-face.jpg"
        try:
            written = self.snapshot_writer(path, frame[top:bottom, left:right])
        except Exception:
            written = False
            logger.exception("[%s] yuz kadri yozilmadi", camera_id)
        with self._lock:
            if written:
                event.snapshot_path = str(path)
                self._totals.snapshots_written += 1
            else:
                self._totals.snapshots_missing += 1

    def _attach_security_snapshot(self, event: EdgeEvent, *, camera_id: str) -> None:
        # Oddiy zona kirishi retail analitikasi, xavfsizlik hodisasi emas.
        # Snapshot faqat aniq `restricted` zona uchun olinadi.
        if event.event_type == "zone_entered" and not event.metadata.get("restricted"):
            return
        if (
            event.event_type not in SECURITY_MEDIA_EVENTS
            or self.snapshot_dir is None
            or event.snapshot_path
        ):
            return
        camera = self._cameras.get(camera_id)
        frame = camera.last_frame if camera is not None else None
        if frame is None:
            with self._lock:
                self._totals.snapshots_missing += 1
            return
        path = self.snapshot_dir / f"{camera_id}-{event.event_id}.jpg"
        try:
            written = self.snapshot_writer(path, frame)
        except Exception:
            written = False
            logger.exception("[%s] xavfsizlik snapshoti yozilmadi", camera_id)
        with self._lock:
            if written:
                event.snapshot_path = str(path)
                self._totals.snapshots_written += 1
            else:
                self._totals.snapshots_missing += 1

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

        Klip tayyor bo'lganda hodisaning edge-only `clip_path` maydoni
        to'ldiriladi va `on_clip` chaqiriladi. Lokal yo'l cloud payloadiga
        kirmaydi; sync videoni alohida endpointga uzatadi.
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
            item.event.clip_path = str(path)
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
            "plan_filtered": self._totals.plan_filtered,
            "tamper_alerts": self._totals.tamper_alerts,
            "freezes": self._totals.freezes,
            "after_hours": self._totals.after_hours,
            "actions": dict(sorted(self._totals.actions.items())),
            "action_errors": self._totals.action_errors,
            "snapshots": {
                "written": self._totals.snapshots_written,
                "missing": self._totals.snapshots_missing,
            },
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
                    "tamper_alerts": camera.tamper_alerts,
                    "freezes": camera.freezes,
                    "tampered": camera.tamper is not None and camera.tamper.alerted,
                }
                for camera_id, camera in sorted(self._cameras.items())
            },
        }
