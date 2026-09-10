"""Tun: IR o'tishi, yopiq do'kondagi harakat, «tun» belgisi, tungi qoidalar.

Kamera, model va ffmpeg kerak emas — `test_retail_pipeline.py` dagi soxta
bo'laklar.  Har test bitta savolga javob beradi: tunda zanjir yolg'on
gapirmaydimi va haqiqiy narsani o'tkazib yubormaydimi.
"""

from __future__ import annotations

from datetime import time as dt_time
from pathlib import Path
from typing import Any, List, Optional

import numpy as np

from enes.event_models import EdgeEvent
from enes.retail import nightmode
from enes.retail.broker import FrameBroker
from enes.retail.budget import InferenceBudget
from enes.retail.pipeline import (
    NIGHT_MOTION_RATIO,
    NIGHT_MOTION_SEC,
    RetailPipeline,
)
from enes.retail.rules import RuleEngine, Schedule
from enes.retail.tamper import TamperDetector
from enes.scene_analytics import MotionGate
from tests.test_retail_pipeline import FRAME, Clock, FakeAnalyzer, Recorder

WORKDAY = Schedule.parse("09:00", "21:00")


class FakeNight:
    """Rejim almashuvi qo'lda beriladi."""

    def __init__(self, mode: str = nightmode.DAY) -> None:
        self.mode = mode
        self.queued: Optional[tuple] = None

    def switch(self, new: str) -> None:
        self.queued = (self.mode, new)
        self.mode = new

    def update(self, _frame, *, now: float):
        change, self.queued = self.queued, None
        return change


class SpyTamper:
    def __init__(self) -> None:
        self.relearns = 0
        self.frames = 0
        self.alerted = False

    def update(self, _frame, *, now: float):
        self.frames += 1
        return None

    def relearn(self) -> None:
        self.relearns += 1


def build(tmp_path: Path, *, hour: int, events: Optional[List[EdgeEvent]] = None, night: Any = None, tamper: Any = None, rules: Optional[RuleEngine] = None):
    broker = FrameBroker(InferenceBudget(target_fps=30.0, min_fps=1.0, max_fps=60.0))
    analyzer = FakeAnalyzer(events or [])
    analyzer.motion.resets = 0
    analyzer.motion.reset = lambda: setattr(analyzer.motion, "resets", analyzer.motion.resets + 1)
    recorder = Recorder()
    pipeline = RetailPipeline(
        broker,
        rules or RuleEngine(),
        on_action=recorder,
        clock=Clock(),
        local_time=lambda: dt_time(hour=hour),
        business_hours=WORKDAY,
        after_hours_debounce_sec=300.0,
    )
    pipeline.add_camera("zal-01", analyzer, tamper=tamper, night=night, now=0.0)  # type: ignore[arg-type]
    return pipeline, analyzer, recorder


def kinds(recorder: Recorder) -> List[str]:
    return [event.event_type for _action, event in recorder.actions]


# ── IR o'tishi ───────────────────────────────────────────────────────────


def test_switching_to_ir_relearns_the_tamper_baseline_and_the_background(tmp_path: Path) -> None:
    """Kunduz→IR: buzilish detektori va fon modeli qaytadan — hodisa YO'Q."""
    night = FakeNight()
    tamper = SpyTamper()
    pipeline, analyzer, recorder = build(tmp_path, hour=22, night=night, tamper=tamper)

    pipeline.offer("zal-01", FRAME, now=1.0)
    assert tamper.relearns == 0

    night.switch(nightmode.IR)
    pipeline.offer("zal-01", FRAME, now=2.0)

    assert tamper.relearns == 1
    assert analyzer.motion.resets == 1
    assert analyzer.size_boost == 1.0
    assert kinds(recorder) == [], "IR o'tishi hodisa emas"
    assert pipeline.stats()["night"] == {"motion_alerts": 0, "relearns": 1, "modes": {"zal-01": "ir"}}


def test_a_blind_camera_raises_the_size_floor_and_feeds_a_brightened_frame(tmp_path: Path) -> None:
    """IR'siz kamera tunda: ramka chegarasi 1.5×, detektorga yoritilgan kadr."""
    night = FakeNight()
    pipeline, analyzer, recorder = build(tmp_path, hour=12, night=night)
    seen: List[Any] = []
    analyzer.analyze = lambda frame, *, now: (seen.append(frame), [])[1]  # type: ignore[assignment]

    dark = np.full((16, 16, 3), 12, dtype=np.uint8)
    night.switch(nightmode.DARK)
    pipeline.offer("zal-01", dark, now=1.0)
    pipeline.step(now=1.0)

    assert analyzer.size_boost == 1.5
    assert seen and seen[-1].mean() > dark.mean(), "detektorga yoritilgan nusxa"
    assert pipeline._cameras["zal-01"].last_frame is dark, "rasm/klip uchun ASL kadr"

    night.switch(nightmode.DAY)
    pipeline.offer("zal-01", dark, now=2.0)
    assert analyzer.size_boost == 1.0


def test_the_real_tamper_detector_accepts_the_ir_frame_after_relearn() -> None:
    """Haqiqiy detektor: qayta o'rganishdan keyin oq-qora kadr me'yor, DARK chiqmaydi."""
    from tests.test_retail_tamper import feed, live, scene, warm

    detector = TamperDetector(min_duration_sec=10.0)
    warm(detector, scene())
    ir = (scene().astype(np.float32) * 0.3).astype(np.uint8)  # keskin qorong'ilashdi
    detector.relearn()
    assert detector.update(live(ir), now=10.0) is None
    assert feed(detector, ir, start=10.2, stop=40.0) is None
    assert detector.stats()["relearns"] == 1


def test_motion_gate_reset_starts_a_new_warmup() -> None:
    gate = MotionGate()
    frame = np.zeros((90, 160, 3), dtype=np.uint8)
    for _ in range(12):
        gate.motion_ratio(frame)
    assert gate.motion_ratio(frame) < 1.0
    gate.reset()
    assert gate.motion_ratio(frame) == 1.0, "isinish qaytadan — hamma narsa harakat"


# ── Yopiq do'kondagi harakat ─────────────────────────────────────────────


def offer_motion(pipeline: RetailPipeline, analyzer: FakeAnalyzer, ratio: float, *, start: float, stop: float, step: float = 0.2) -> None:
    analyzer.motion.ratio = ratio
    moment = start
    while moment < stop:
        pipeline.offer("zal-01", FRAME, now=moment)
        moment += step


def test_sustained_motion_in_the_closed_store_becomes_an_event(tmp_path: Path) -> None:
    pipeline, analyzer, recorder = build(tmp_path, hour=23)

    offer_motion(pipeline, analyzer, NIGHT_MOTION_RATIO, start=0.0, stop=NIGHT_MOTION_SEC + 1.0)

    events = [e for _a, e in recorder.actions if e.event_type == "night_motion"]
    assert len(events) == 1
    assert events[0].severity == "warning"
    assert events[0].metadata["night"] is True
    assert events[0].metadata["local_time"] == "23:00"
    assert pipeline.stats()["night"]["motion_alerts"] == 1


def test_a_brief_flash_is_not_night_motion(tmp_path: Path) -> None:
    """Mashina chirog'i derazadan — 3 soniyadan qisqa, hodisa emas."""
    pipeline, analyzer, recorder = build(tmp_path, hour=23)

    offer_motion(pipeline, analyzer, 0.5, start=0.0, stop=1.0)
    offer_motion(pipeline, analyzer, 0.0, start=1.0, stop=2.0)
    offer_motion(pipeline, analyzer, 0.5, start=2.0, stop=3.0)

    assert "night_motion" not in kinds(recorder)


def test_motion_during_opening_hours_is_not_night_motion(tmp_path: Path) -> None:
    pipeline, analyzer, recorder = build(tmp_path, hour=12)
    offer_motion(pipeline, analyzer, 0.5, start=0.0, stop=10.0)
    assert "night_motion" not in kinds(recorder)


def test_night_motion_is_not_repeated_within_the_debounce(tmp_path: Path) -> None:
    pipeline, analyzer, recorder = build(tmp_path, hour=23)
    offer_motion(pipeline, analyzer, 0.5, start=0.0, stop=100.0, step=1.0)
    assert kinds(recorder).count("night_motion") == 1
    offer_motion(pipeline, analyzer, 0.5, start=300.0, stop=310.0, step=1.0)
    assert kinds(recorder).count("night_motion") == 2


def test_a_recognised_person_suppresses_the_motion_event(tmp_path: Path) -> None:
    """Odam tanilgan bo'lsa `after_hours_presence` chiqadi — ikkinchi xabar yo'q."""
    person = EdgeEvent(event_type="person_detected", camera_id="zal-01", track_id=3)
    pipeline, analyzer, recorder = build(tmp_path, hour=23, events=[person])

    pipeline.offer("zal-01", FRAME, now=0.0)
    pipeline.step(now=0.0)
    assert "after_hours_presence" in kinds(recorder)

    analyzer.events = []
    offer_motion(pipeline, analyzer, 0.5, start=1.0, stop=10.0)
    assert "night_motion" not in kinds(recorder)

    # 60 soniyadan keyin odam ko'rinmaydi — harakat yana o'z hodisasini beradi.
    offer_motion(pipeline, analyzer, 0.5, start=70.0, stop=80.0)
    assert "night_motion" in kinds(recorder)


# ── «Tun» belgisi ────────────────────────────────────────────────────────


def test_every_event_outside_hours_carries_the_night_flag(tmp_path: Path) -> None:
    def crossing() -> EdgeEvent:
        return EdgeEvent(event_type="line_crossed", camera_id="zal-01", direction="in")

    pipeline, analyzer, recorder = build(tmp_path, hour=2, events=[crossing()])
    pipeline.offer("zal-01", FRAME, now=0.0)
    pipeline.step(now=0.0)
    night_flags = [e.metadata.get("night") for _a, e in recorder.actions if e.event_type == "line_crossed"]
    assert night_flags == [True]

    pipeline, analyzer, recorder = build(tmp_path, hour=12, events=[crossing()])
    pipeline.offer("zal-01", FRAME, now=0.0)
    pipeline.step(now=0.0)
    assert all(not (e.metadata or {}).get("night") for _a, e in recorder.actions)


# ── Qoidalar fayli ───────────────────────────────────────────────────────


def test_the_shipped_rules_treat_a_night_tamper_faster_than_a_day_one() -> None:
    """`config/rules.yaml`: tungi qoida kunduzgidan OLDIN turadi va ustun keladi."""
    from enes.retail.service import load_rules

    root = Path(__file__).resolve().parents[1]
    engine = load_rules(root / "config" / "rules.yaml")
    tamper = EdgeEvent(event_type="camera_tampered", camera_id="zal-01", severity="critical")

    night = engine.evaluate(tamper, now=0.0, local_time=dt_time(23, 0))
    day = engine.evaluate(tamper, now=1000.0, local_time=dt_time(12, 0))
    assert night.rule_name == "Tunda kamera buzilishi"
    assert day.rule_name == "Kamera buzilishi"

    motion = EdgeEvent(event_type="night_motion", camera_id="zal-01", severity="warning")
    decision = engine.evaluate(motion, now=2000.0, local_time=dt_time(23, 0))
    assert decision.rule_name == "Tunda harakat"
    assert "telegram_alert" in decision.actions and "save_clip" in decision.actions
