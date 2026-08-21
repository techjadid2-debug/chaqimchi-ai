"""Retail zanjiri: kadr → filtr → navbat → tahlil → qoida → harakat → klip.

Kamera ham, model ham, ffmpeg ham kerak emas.  Analizator va ring buffer
almashtiriladi, vaqt esa tashqaridan beriladi — natija takrorlanadigan.
"""

from __future__ import annotations

from datetime import time as dt_time
from pathlib import Path
from typing import Any, List, Optional, Tuple

import numpy as np
import pytest

from chaqimchi_ai.event_models import EdgeEvent
from chaqimchi_ai.retail.broker import FrameBroker
from chaqimchi_ai.retail.budget import InferenceBudget
from chaqimchi_ai.retail.claims import Priority
from chaqimchi_ai.retail.pipeline import MOTION_SATURATION, RetailPipeline
from chaqimchi_ai.retail.rules import Rule, RuleEngine, Schedule
from chaqimchi_ai.retail.tamper import TamperAlert
from chaqimchi_ai.scene_analytics import SceneAnalyzer
from chaqimchi_ai.settings import SceneSettings

FRAME = np.zeros((8, 8, 3), dtype=np.uint8)
WALL = 1_800_000_000.0  # klip vaqti uchun "haqiqiy" soat


# ── Soxta bo'laklar ──────────────────────────────────────────────────────


class FakeGate:
    """`MotionGate` o'rniga: harakat ulushi qo'lda beriladi."""

    def __init__(self, min_area_ratio: float = 0.01) -> None:
        self.min_area_ratio = min_area_ratio
        self.ratio = 1.0
        self.calls = 0

    def motion_ratio(self, _frame) -> float:
        self.calls += 1
        return self.ratio


class FakeAnalyzer:
    """Berilgan hodisalarni qaytaradi yoki xato beradi."""

    def __init__(self, events: Optional[List[EdgeEvent]] = None) -> None:
        self.motion = FakeGate()
        self.events = events or []
        self.raises = False
        self.calls = 0

    def analyze(self, _frame, *, now: float) -> List[EdgeEvent]:
        self.calls += 1
        if self.raises:
            raise RuntimeError("model yiqildi")
        return list(self.events)


class FakeBuffer:
    """`RingBuffer` o'rniga: qaysi lahza so'ralganini yozib boradi."""

    def __init__(self, *, found: bool = True) -> None:
        self.found = found
        self.requests: List[Tuple[float, float, float]] = []

    def extract(self, moment: float, *, output: Path, pre_sec: float, post_sec: float):
        self.requests.append((moment, pre_sec, post_sec))
        if not self.found:
            return None
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"klip")
        return output


class Recorder:
    """Bajarilgan harakatlar ro'yxati."""

    def __init__(self) -> None:
        self.actions: List[Tuple[str, EdgeEvent]] = []
        self.clips: List[Tuple[EdgeEvent, Path]] = []
        self.raises = False

    def __call__(self, action: str, event: EdgeEvent) -> None:
        if self.raises:
            raise RuntimeError("telegram javob bermadi")
        self.actions.append((action, event))

    def clip(self, event: EdgeEvent, path: Path) -> None:
        self.clips.append((event, path))

    @property
    def names(self) -> List[str]:
        return [action for action, _event in self.actions]


class Clock:
    """Har chaqiruvda belgilangan qadamga siljiydigan soat."""

    def __init__(self, step: float = 0.02) -> None:
        self.value = 0.0
        self.step = step

    def __call__(self) -> float:
        self.value += self.step
        return self.value


def build(
    tmp_path: Path,
    *,
    events: Optional[List[EdgeEvent]] = None,
    rules: Optional[RuleEngine] = None,
    clips: Any = "default",
    wall: Optional[List[float]] = None,
    snapshots: bool = False,
) -> Tuple[RetailPipeline, FakeAnalyzer, Recorder, Any]:
    broker = FrameBroker(InferenceBudget(target_fps=30.0, min_fps=1.0, max_fps=60.0))
    analyzer = FakeAnalyzer(events)
    recorder = Recorder()
    buffer = FakeBuffer() if clips == "default" else clips
    wall_values = list(wall or [])
    pipeline = RetailPipeline(
        broker,
        rules or RuleEngine(),
        on_action=recorder,
        on_clip=recorder.clip,
        clip_dir=tmp_path / "clips",
        snapshot_dir=tmp_path / "snapshots" if snapshots else None,
        snapshot_writer=lambda path, _frame: (
            path.parent.mkdir(parents=True, exist_ok=True),
            path.write_bytes(b"jpeg"),
            True,
        )[2],
        pre_sec=10.0,
        post_sec=20.0,
        clock=Clock(),
        wall_clock=(lambda: wall_values.pop(0)) if wall_values else (lambda: WALL),
        local_time=lambda: None,
    )
    pipeline.add_camera("kassa-01", analyzer, clips=buffer, now=0.0)  # type: ignore[arg-type]
    return pipeline, analyzer, recorder, buffer


def line_crossed() -> EdgeEvent:
    return EdgeEvent(event_type="line_crossed", camera_id="kassa-01", direction="in")


def loitering() -> EdgeEvent:
    return EdgeEvent(event_type="loitering", camera_id="kassa-01", severity="warning")


def run(pipeline: RetailPipeline, *, now: float = 1.0, frame=FRAME) -> Any:
    pipeline.offer("kassa-01", frame, now=now)
    return pipeline.step(now=now)


# ── Harakat filtri ───────────────────────────────────────────────────────


def test_still_frame_never_reaches_the_budget(tmp_path: Path) -> None:
    """Filtrning butun ma'nosi shu: bo'sh kadr uchun model ishlamasin."""
    pipeline, analyzer, _recorder, _buffer = build(tmp_path)
    analyzer.motion.ratio = 0.0

    assert pipeline.offer("kassa-01", FRAME, now=1.0) is False
    assert pipeline.step(now=1.0) is None
    assert analyzer.calls == 0
    assert pipeline.stats()["gated"] == 1


def test_motion_amount_becomes_the_camera_share(tmp_path: Path) -> None:
    """Ko'p harakatli kamera byudjetdan ko'proq ulush oladi."""
    pipeline, analyzer, _recorder, _buffer = build(tmp_path)
    seen: List[float] = []
    original = pipeline.broker.submit
    pipeline.broker.submit = lambda *args, **kwargs: (  # type: ignore[method-assign]
        seen.append(kwargs["motion_score"]),
        original(*args, **kwargs),
    )[1]

    analyzer.motion.ratio = MOTION_SATURATION / 2
    pipeline.offer("kassa-01", FRAME, now=1.0)
    analyzer.motion.ratio = MOTION_SATURATION * 5
    pipeline.offer("kassa-01", FRAME, now=1.1)

    # Yarim to'yinganlik — yarim ball; to'yinganlikdan yuqorisi 1.0 da to'xtaydi,
    # aks holda yorug'lik o'zgarishi butun byudjetni tortib olardi.
    assert seen == [0.5, 1.0]


def test_the_gate_sees_every_frame(tmp_path: Path) -> None:
    """Fon modeli har kadrni ko'rmasa fonni noto'g'ri o'rganadi."""
    pipeline, analyzer, _recorder, _buffer = build(tmp_path)
    analyzer.motion.ratio = 0.0

    for index in range(5):
        pipeline.offer("kassa-01", FRAME, now=1.0 + index)

    assert analyzer.motion.calls == 5


def test_unknown_camera_is_rejected(tmp_path: Path) -> None:
    pipeline, _analyzer, _recorder, _buffer = build(tmp_path)
    with pytest.raises(KeyError):
        pipeline.offer("yo-q-kamera", FRAME, now=1.0)


# ── Hodisadan harakatgacha ───────────────────────────────────────────────


def test_event_reaches_the_action(tmp_path: Path) -> None:
    pipeline, _analyzer, recorder, _buffer = build(tmp_path, events=[line_crossed()])

    result = run(pipeline)

    assert result is not None and result.failed is False
    assert recorder.names == ["cloud_sync"]  # qoida yo'q → standart yo'l
    assert recorder.actions[0][1].event_type == "line_crossed"


def test_a_rule_can_suppress_an_event(tmp_path: Path) -> None:
    rules = RuleEngine([Rule(name="xodimlar", event_type="line_crossed", suppress=True)])
    pipeline, _analyzer, recorder, _buffer = build(tmp_path, events=[line_crossed()], rules=rules)

    run(pipeline)

    assert recorder.actions == []
    assert pipeline.stats()["suppressed"] == 1


def test_rule_actions_replace_the_default(tmp_path: Path) -> None:
    rules = RuleEngine(
        [
            Rule(
                name="kirish",
                event_type="line_crossed",
                actions=("telegram_alert", "cloud_sync"),
            )
        ]
    )
    pipeline, _analyzer, recorder, _buffer = build(tmp_path, events=[line_crossed()], rules=rules)

    run(pipeline)

    assert recorder.names == ["telegram_alert", "cloud_sync"]


def test_telegram_choice_travels_inside_the_event(tmp_path: Path) -> None:
    """Qoidaning Telegram tanlovi hodisaning o'zida cloudga boradi.

    `metadata.alert` bayrog'i — `cloud/notify.py wants_telegram()` uchun
    yakuniy so'z.  Usiz `telegram_alert` harakati dekorativ edi: cloud
    faqat severity'ga qarab yuborar edi.
    """
    rules = RuleEngine(
        [
            Rule(
                name="alertli", event_type="line_crossed", actions=("telegram_alert", "cloud_sync")
            ),
            Rule(name="jim", event_type="loitering", actions=("cloud_sync",)),
        ]
    )
    pipeline, _analyzer, recorder, _buffer = build(
        tmp_path, events=[line_crossed(), loitering()], rules=rules
    )

    run(pipeline)

    by_type = {event.event_type: event for _name, event in recorder.actions}
    assert by_type["line_crossed"].metadata.get("alert") is True
    assert by_type["loitering"].metadata.get("alert") is False


# ── Xatolar zanjirni to'xtatmasligi ──────────────────────────────────────


def test_detector_failure_does_not_freeze_the_camera(tmp_path: Path) -> None:
    """Eng xavflisi: xato bo'lgan kamera abadiy "band" bo'lib qolishi.

    `complete()` chaqirilmasa `in_flight` qaytmaydi va kamera boshqa hech
    qachon navbat olmaydi — bitta xato butun kamerani o'chirib qo'yardi.
    """
    pipeline, analyzer, _recorder, _buffer = build(tmp_path, events=[line_crossed()])
    analyzer.raises = True

    first = run(pipeline, now=1.0)
    analyzer.raises = False
    second = run(pipeline, now=2.0)

    assert first is not None and first.failed is True
    assert second is not None and second.failed is False
    assert len(second.events) == 1
    assert pipeline.stats()["errors"] == 1


def test_a_failed_action_does_not_stop_the_rest(tmp_path: Path) -> None:
    pipeline, _analyzer, recorder, _buffer = build(tmp_path, events=[line_crossed()])
    recorder.raises = True

    run(pipeline, now=1.0)
    recorder.raises = False
    run(pipeline, now=2.0)

    assert pipeline.stats()["action_errors"] == 1
    assert recorder.names == ["cloud_sync"]  # ikkinchisi o'tdi


def test_measured_latency_feeds_the_budget(tmp_path: Path) -> None:
    pipeline, _analyzer, _recorder, _buffer = build(tmp_path, events=[line_crossed()])

    result = run(pipeline)

    assert result is not None and result.latency_sec > 0
    assert pipeline.stats()["broker"]["budget"]["samples"] == 1


def test_idle_loop_returns_nothing(tmp_path: Path) -> None:
    pipeline, _analyzer, _recorder, _buffer = build(tmp_path)
    assert pipeline.step(now=1.0) is None


# ── Klip ─────────────────────────────────────────────────────────────────


CLIP_RULES = RuleEngine(
    [Rule(name="klip", event_type="line_crossed", actions=("save_clip", "cloud_sync"))]
)


def test_clip_waits_until_the_footage_after_the_event_exists(tmp_path: Path) -> None:
    """Hodisa lahzasida oxirgi 20 soniya hali yozilmagan.

    Darhol kesilsa aynan "keyin nima bo'ldi" degan qism yo'qoladi.
    """
    pipeline, _analyzer, _recorder, buffer = build(
        tmp_path, events=[line_crossed()], rules=CLIP_RULES
    )

    run(pipeline)

    assert pipeline.pending_clips == 1
    assert pipeline.flush_clips(wall_now=WALL + 19.0) == []  # hali erta
    assert buffer.requests == []

    written = pipeline.flush_clips(wall_now=WALL + 20.0)

    assert len(written) == 1
    assert buffer.requests == [(WALL, 10.0, 20.0)]
    assert pipeline.pending_clips == 0


def test_the_event_is_sent_immediately_not_after_the_clip(tmp_path: Path) -> None:
    """Ogohlantirish 20 soniya kutmaydi — klip keyinroq qo'shiladi."""
    pipeline, _analyzer, recorder, _buffer = build(
        tmp_path, events=[line_crossed()], rules=CLIP_RULES
    )

    run(pipeline)

    assert recorder.names == ["cloud_sync"]
    assert recorder.clips == []


def test_ready_clip_is_attached_to_its_event(tmp_path: Path) -> None:
    pipeline, _analyzer, recorder, _buffer = build(
        tmp_path, events=[line_crossed()], rules=CLIP_RULES
    )

    run(pipeline)
    pipeline.flush_clips(wall_now=WALL + 30.0)

    event, path = recorder.clips[0]
    assert path.is_file()
    assert event.clip_path == str(path)
    assert "clip_path" not in event.cloud_payload()
    assert pipeline.stats()["clips"]["written"] == 1


def test_security_event_has_private_snapshot_before_cloud_action(tmp_path: Path) -> None:
    event = EdgeEvent(
        event_type="camera_tampered",
        severity="critical",
        camera_id="kassa-01",
    )
    pipeline, _analyzer, recorder, _buffer = build(tmp_path, events=[event], snapshots=True)

    run(pipeline)

    sent = recorder.actions[0][1]
    assert sent.snapshot_path is not None
    assert Path(sent.snapshot_path).read_bytes() == b"jpeg"
    assert sent.cloud_payload()["has_snapshot"] is True
    assert "snapshot_path" not in sent.cloud_payload()
    assert pipeline.stats()["snapshots"] == {"written": 1, "missing": 0}


def test_loitering_does_not_burn_the_snapshot_budget(tmp_path: Path) -> None:
    """Uzoq turish uchun rasm OLINMAYDI — hodisaning o'zi esa ketaveradi.

    Jonli o'lchov (2026-08-21, bitta do'kon, 7.4 soat): 321 hodisadan 300
    tasi loitering edi va 29 MB rasmning 28.9 MB'i shundan chiqqan.  Do'kon
    kunlik 500 talik snapshot chegarasining 302 tasini yeb qo'ygan — ya'ni
    kechqurun haqiqiy o'g'rilik hodisasiga rasm ilinmay qolardi.

    Hodisaning o'zi saqlanishi SHART: issiqlik xaritasi va "eng ko'p
    turilgan joy" hisoboti unga tayanadi.
    """
    event = EdgeEvent(
        event_type="loitering",
        severity="warning",
        camera_id="kassa-01",
    )
    pipeline, _analyzer, recorder, _buffer = build(tmp_path, events=[event], snapshots=True)

    run(pipeline)

    sent = recorder.actions[0][1]
    assert sent.event_type == "loitering"  # hodisa ketdi
    assert sent.snapshot_path is None  # lekin rasmsiz
    assert sent.cloud_payload()["has_snapshot"] is False
    # "missing" ham 0: rasm YOZILMADI, ya'ni urinib ko'rib yiqilgani emas.
    assert pipeline.stats()["snapshots"] == {"written": 0, "missing": 0}


def test_normal_zone_event_does_not_capture_a_security_snapshot(tmp_path: Path) -> None:
    event = EdgeEvent(
        event_type="zone_entered",
        camera_id="kassa-01",
        zone="savdo-zali",
        metadata={"restricted": False},
    )
    pipeline, _analyzer, recorder, _buffer = build(tmp_path, events=[event], snapshots=True)

    run(pipeline)

    sent = recorder.actions[0][1]
    assert sent.snapshot_path is None
    assert pipeline.stats()["snapshots"] == {"written": 0, "missing": 0}


def test_camera_without_a_buffer_still_reports_the_event(tmp_path: Path) -> None:
    """Klip yo'q — hodisa baribir ketadi.  Klipsiz hodisa hodisasizdan yaxshi."""
    pipeline, _analyzer, recorder, _buffer = build(
        tmp_path, events=[line_crossed()], rules=CLIP_RULES, clips=None
    )

    run(pipeline)

    assert recorder.names == ["cloud_sync"]
    assert pipeline.stats()["clips"]["unavailable"] == 1
    assert pipeline.pending_clips == 0


def test_missing_footage_is_counted_not_raised(tmp_path: Path) -> None:
    pipeline, _analyzer, _recorder, _buffer = build(
        tmp_path, events=[line_crossed()], rules=CLIP_RULES, clips=FakeBuffer(found=False)
    )

    run(pipeline)
    assert pipeline.flush_clips(wall_now=WALL + 30.0) == []
    assert pipeline.stats()["clips"]["missing"] == 1


def test_broken_ffmpeg_does_not_grow_the_queue_forever(tmp_path: Path) -> None:
    from chaqimchi_ai.retail import pipeline as module

    pipeline, _analyzer, _recorder, _buffer = build(
        tmp_path, events=[line_crossed()], rules=CLIP_RULES
    )

    for index in range(module.MAX_PENDING_CLIPS + 5):
        run(pipeline, now=1.0 + index)

    assert pipeline.pending_clips == module.MAX_PENDING_CLIPS
    assert pipeline.stats()["clips"]["dropped"] == 5


# ── Ikki kamera bitta byudjetda ──────────────────────────────────────────


def test_security_camera_wins_the_contested_budget(tmp_path: Path) -> None:
    """Byudjet yetmasa xavfsizlik kamerasi oldinda bo'ladi."""
    broker = FrameBroker(InferenceBudget(target_fps=1.0, min_fps=1.0, max_fps=2.0))
    recorder = Recorder()
    pipeline = RetailPipeline(
        broker, RuleEngine(), on_action=recorder, clock=Clock(), local_time=lambda: None
    )
    pipeline.add_camera("ombor", FakeAnalyzer(), priority=Priority.SECURITY, now=0.0)  # type: ignore[arg-type]
    pipeline.add_camera("kassa", FakeAnalyzer(), priority=Priority.RETAIL, now=0.0)  # type: ignore[arg-type]

    pipeline.offer("ombor", FRAME, now=10.0)
    pipeline.offer("kassa", FRAME, now=10.0)
    result = pipeline.step(now=10.0)

    assert result is not None and result.camera_id == "ombor"


# ── Kamera buzilishi ─────────────────────────────────────────────────────


class FakeTamper:
    """Belgilangan kadrda bir marta ogohlantiradi."""

    def __init__(self, *, at: int = 1) -> None:
        self.at = at
        self.calls = 0
        self.alerted = False

    def update(self, _frame, *, now: float):
        self.calls += 1
        if self.calls != self.at:
            return None
        self.alerted = True
        return TamperAlert(reason="qorong'i", score=0.97, duration_sec=12.0)


def test_a_covered_camera_reports_even_without_motion(tmp_path: Path) -> None:
    """Butun tekshiruvning sababi shu: yopilgan kamerada harakat yo'q.

    Filtr ichida turganda buzilish hech qachon sezilmasdi — tizim
    "hammasi joyida" deb ko'rsatib turaverardi.
    """
    pipeline, analyzer, recorder, _buffer = build(tmp_path)
    tamper = FakeTamper()
    pipeline.add_camera("yopiq-01", analyzer, tamper=tamper, now=0.0)  # type: ignore[arg-type]
    analyzer.motion.ratio = 0.0  # harakat umuman yo'q

    assert pipeline.offer("yopiq-01", FRAME, now=1.0) is False  # kadr tahlilga ketmadi

    assert recorder.names == ["cloud_sync"]
    event = recorder.actions[0][1]
    assert event.event_type == "camera_tampered"
    assert event.severity == "critical"
    assert event.metadata["reason"] == "qorong'i"
    assert pipeline.stats()["tamper_alerts"] == 1


def test_tamper_event_obeys_the_rules(tmp_path: Path) -> None:
    rules = RuleEngine(
        [Rule(name="buzilish", event_type="camera_tampered", actions=("telegram_alert",))]
    )
    pipeline, analyzer, recorder, _buffer = build(tmp_path, rules=rules)
    pipeline.add_camera("yopiq-01", analyzer, tamper=FakeTamper(), now=0.0)  # type: ignore[arg-type]

    pipeline.offer("yopiq-01", FRAME, now=1.0)

    assert recorder.names == ["telegram_alert"]


def test_a_camera_without_the_check_stays_silent(tmp_path: Path) -> None:
    pipeline, _analyzer, recorder, _buffer = build(tmp_path)

    pipeline.offer("kassa-01", FRAME, now=1.0)

    assert recorder.actions == []
    assert pipeline.stats()["tamper_alerts"] == 0


# ── Ish vaqtidan tashqari ────────────────────────────────────────────────

WORKDAY = Schedule.parse("09:00", "21:00")


def person() -> EdgeEvent:
    return EdgeEvent(event_type="person_detected", camera_id="kassa-01", track_id=7)


def build_hours(tmp_path: Path, *, hour: int, **kwargs):
    broker = FrameBroker(InferenceBudget(target_fps=30.0, min_fps=1.0, max_fps=60.0))
    analyzer = FakeAnalyzer([person()])
    recorder = Recorder()
    pipeline = RetailPipeline(
        broker,
        RuleEngine(),
        on_action=recorder,
        clock=Clock(),
        local_time=lambda: dt_time(hour=hour),
        business_hours=WORKDAY,
        **kwargs,
    )
    pipeline.add_camera("kassa-01", analyzer, now=0.0)  # type: ignore[arg-type]
    return pipeline, recorder


def test_a_person_at_night_becomes_an_alert(tmp_path: Path) -> None:
    """Kunduzi kadrdagi odam — mijoz, kechasi — ogohlantirish."""
    pipeline, recorder = build_hours(tmp_path, hour=23)

    run(pipeline)

    kinds = [event.event_type for _action, event in recorder.actions]
    assert "after_hours_presence" in kinds
    alert = next(
        event for _a, event in recorder.actions if event.event_type == "after_hours_presence"
    )
    assert alert.severity == "warning"
    assert alert.track_id == 7
    assert alert.metadata["local_time"] == "23:00"


def test_a_person_during_opening_hours_is_just_a_customer(tmp_path: Path) -> None:
    pipeline, recorder = build_hours(tmp_path, hour=12)

    run(pipeline)

    kinds = [event.event_type for _action, event in recorder.actions]
    assert kinds == ["person_detected"]


def test_the_night_alert_is_not_repeated_for_every_frame(tmp_path: Path) -> None:
    """Kechasi turgan odam har kadrda yangi ogohlantirish bermasin."""
    pipeline, recorder = build_hours(tmp_path, hour=23, after_hours_debounce_sec=300.0)

    run(pipeline, now=1.0)
    run(pipeline, now=100.0)
    run(pipeline, now=400.0)

    alerts = [e for _a, e in recorder.actions if e.event_type == "after_hours_presence"]
    assert len(alerts) == 2  # 1.0 va 400.0; 100.0 tormozlangan


def test_without_business_hours_the_event_never_appears(tmp_path: Path) -> None:
    pipeline, _analyzer, recorder, _buffer = build(tmp_path, events=[person()])

    run(pipeline)

    kinds = [event.event_type for _action, event in recorder.actions]
    assert kinds == ["person_detected"]


# ── Haqiqiy `SceneAnalyzer` bilan ─────────────────────────────────────────


class ScriptedDetector:
    """Berilgan markazlar bo'yicha odam qaytaradi (0..1 koordinatada)."""

    def __init__(self) -> None:
        self.people: List[Tuple[float, float]] = []

    def detect(self, _frame):
        return [
            {"bbox": [x * 100 - 5.0, y * 100 - 20.0, x * 100 + 5.0, y * 100], "score": 0.9}
            for x, y in self.people
        ]


def test_a_real_walk_through_the_door_produces_an_action(tmp_path: Path) -> None:
    """Kontrakt tekshiruvi: haqiqiy `SceneAnalyzer` zanjirga tushadi."""
    settings = SceneSettings.model_validate(
        {
            "enabled": True,
            "burst_fps": 30,
            "lines": [
                {"name": "eshik", "camera_id": "eshik-01", "start": [0.5, 0.0], "end": [0.5, 1.0]}
            ],
        }
    )
    detector = ScriptedDetector()
    analyzer = SceneAnalyzer("eshik-01", detector, settings)
    broker = FrameBroker(InferenceBudget(target_fps=30.0, min_fps=1.0, max_fps=60.0))
    recorder = Recorder()
    pipeline = RetailPipeline(
        broker, RuleEngine(), on_action=recorder, clock=Clock(), local_time=lambda: None
    )
    pipeline.add_camera("eshik-01", analyzer, now=0.0)

    # Shovqinli kadr — MOG2 uchun haqiqiy harakat.
    rng = np.random.default_rng(7)
    now = 1.0
    for position in [0.30, 0.38, 0.46, 0.54, 0.62, 0.70]:
        detector.people = [(position, 0.5)]
        frame = rng.integers(0, 255, size=(120, 120, 3), dtype=np.uint8)
        pipeline.offer("eshik-01", frame, now=now)
        pipeline.step(now=now)
        now += 0.2

    crossings = [event for _action, event in recorder.actions if event.event_type == "line_crossed"]
    assert len(crossings) == 1
    assert crossings[0].direction in {"in", "out"}


# ── `ai_review` — cloud uchun ajratilgan nom ─────────────────────────────


def test_ai_review_action_is_accepted_but_does_nothing(tmp_path: Path) -> None:
    """Eski mijoz konfigi yiqilmasin: `ai_review` qabul qilinadi, lekin
    edge'da bajarilmaydi va outboxga hodisa yozmaydi.  AI ko'rigi cloudga
    ko'chirildi (talablar hujjati §6)."""
    rules = RuleEngine(
        [
            Rule(
                name="Kamera buzilishi",
                event_type="camera_tampered",
                actions=("cloud_sync", "ai_review"),
            )
        ]
    )
    pipeline, analyzer, recorder, _buffer = build(tmp_path, rules=rules)
    pipeline.add_camera("yopiq-01", analyzer, tamper=FakeTamper(), now=0.0)  # type: ignore[arg-type]

    pipeline.offer("yopiq-01", FRAME, now=1.0)

    # `cloud_sync` bajarildi, `ai_review` esa hisoblandi-yu, hech nima qilmadi.
    assert recorder.names == ["cloud_sync"]
    assert pipeline.stats()["actions"]["ai_review"] == 1


# ── Davomat: yuz kadri crop ──────────────────────────────────────────────


def face_captured() -> EdgeEvent:
    return EdgeEvent(
        event_type="face_captured",
        camera_id="kassa-01",
        metadata={"bbox": [40, 20, 80, 120]},
    )


def test_face_capture_ships_an_upper_body_crop_not_the_full_frame(tmp_path: Path) -> None:
    """Kadrda boshqa odamlar ham bor — cloudga faqat ramka yuqori qismi ketadi."""
    pipeline, _analyzer, recorder, _buffer = build(
        tmp_path, events=[face_captured()], snapshots=True
    )
    captured = {}

    def writer(path: Path, frame) -> bool:
        captured["shape"] = frame.shape
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"jpeg")
        return True

    pipeline.snapshot_writer = writer
    big_frame = np.zeros((200, 200, 3), dtype=np.uint8)

    run(pipeline, frame=big_frame)

    event = recorder.actions[0][1]
    assert event.snapshot_path and event.snapshot_path.endswith("-face.jpg")
    height, width, _ = captured["shape"]
    assert height == 35, "bbox balandligining ~35% qismi (100 * 0.35)"
    assert width == 48, "bbox eni + 10% chekka (40 + 2*4)"


def test_face_capture_without_a_frame_is_sent_without_media(tmp_path: Path) -> None:
    """Kadr topilmasa hodisa matn bo'lib ketaveradi — oqim to'xtamaydi."""
    pipeline, _analyzer, recorder, _buffer = build(
        tmp_path, events=[face_captured()], snapshots=True
    )
    # offer/step'siz to'g'ridan-to'g'ri dispatch — last_frame hali yo'q.
    from chaqimchi_ai.retail.rules import Decision

    pipeline._dispatch(
        Decision(event=face_captured(), actions=("cloud_sync",), rule_name=None),
        camera_id="kassa-01",
    )

    assert recorder.actions[0][1].snapshot_path is None
