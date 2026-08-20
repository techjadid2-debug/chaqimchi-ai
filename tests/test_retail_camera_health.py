"""Kamera o'chganini kim biladi?

Bungacha kamera holati faqat `runner.stats()` ichida yashardi va hech qachon
hodisaga aylanmasdi. Ya'ni kamera kabeli uzilsa yoki NVR o'chsa, do'kon egasi
buni faqat hisobotdagi bo'shliqdan — bir necha kundan keyin — bilardi.
Cloud tomondagi ogohlantirish esa butun **qurilma** 24 soat jim turgandagina
ishlardi, bitta kamera uchun emas.

Kamera, ffmpeg va soat kerak emas: hammasi injektsiya qilinadi.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional, Tuple

import numpy as np

from chaqimchi_ai.event_models import EdgeEvent
from chaqimchi_ai.retail.broker import FrameBroker
from chaqimchi_ai.retail.budget import InferenceBudget
from chaqimchi_ai.retail.pipeline import RetailPipeline
from chaqimchi_ai.retail.rules import Rule, RuleEngine
from chaqimchi_ai.retail.runner import OFFLINE_AFTER_FAILURES, CameraSource, RetailRunner

FRAME = np.zeros((8, 8, 3), dtype=np.uint8)


class FakeGate:
    min_area_ratio = 0.01

    @staticmethod
    def motion_ratio(_frame) -> float:
        return 1.0


class FakeAnalyzer:
    def __init__(self) -> None:
        self.motion = FakeGate()

    @staticmethod
    def analyze(_frame, *, now: float) -> List[EdgeEvent]:
        return []


class Recorder:
    def __init__(self) -> None:
        self.actions: List[Tuple[str, EdgeEvent]] = []

    def __call__(self, action: str, event: EdgeEvent) -> None:
        self.actions.append((action, event))

    @property
    def events(self) -> List[EdgeEvent]:
        return [event for _action, event in self.actions]

    def of_type(self, event_type: str) -> List[EdgeEvent]:
        return [event for event in self.events if event.event_type == event_type]


class DeadCapture:
    """Ochiladi, lekin kadr bermaydi — kabel uzilgan kameradek."""

    def __init__(self, *, opens: bool = True) -> None:
        self.opens = opens
        self.released = False

    def isOpened(self) -> bool:  # noqa: N802 — OpenCV API nomi
        return self.opens

    @staticmethod
    def grab() -> bool:
        return False

    def release(self) -> None:
        self.released = True


class LiveCapture:
    """Ishlab turgan kamera.  `alive` ni `False` qilsak oqim uziladi."""

    def __init__(self) -> None:
        self.released = False
        self.alive = True

    def isOpened(self) -> bool:  # noqa: N802 — OpenCV API nomi
        return self.alive

    def grab(self) -> bool:
        return self.alive

    @staticmethod
    def retrieve():
        return True, FRAME

    def release(self) -> None:
        self.released = True


def build(
    tmp_path: Path, *, rules: Optional[RuleEngine] = None
) -> Tuple[RetailRunner, Recorder, Any]:
    """Runner + pipeline; kamera fabrikasi testda almashtiriladi."""
    recorder = Recorder()
    pipeline = RetailPipeline(
        FrameBroker(InferenceBudget(target_fps=30.0, min_fps=1.0, max_fps=60.0)),
        rules or RuleEngine(),
        on_action=recorder,
        clip_dir=tmp_path / "clips",
        clock=lambda: 0.0,
        wall_clock=lambda: 0.0,
        local_time=lambda: None,
    )
    factory = {"capture": None}
    runner = RetailRunner(
        pipeline,
        capture_factory=lambda _url: factory["capture"],
        spawn=lambda *a, **k: None,
        clock=lambda: 0.0,
    )
    runner.add_camera(
        CameraSource(camera_id="camera-01", stream_url="rtsp://nvr/1"),
        FakeAnalyzer(),  # type: ignore[arg-type]
        now=0.0,
    )
    return runner, recorder, factory


# ── Kamera o'chdi ────────────────────────────────────────────────────────


def test_a_single_failure_is_not_an_outage(tmp_path: Path) -> None:
    """Bitta tarmoq uzilishi yoki NVR qayta yuklanishi xabar bermasin."""
    runner, recorder, factory = build(tmp_path)
    factory["capture"] = None  # ochilmadi

    runner.capture_once("camera-01", now=1.0)

    assert recorder.events == []


def test_repeated_failures_become_an_event(tmp_path: Path) -> None:
    runner, recorder, factory = build(tmp_path)
    factory["capture"] = None

    # Har urinish orasida backoff kutiladi (2, 4, 8 soniya).
    moment = 1.0
    for _ in range(OFFLINE_AFTER_FAILURES):
        runner.capture_once("camera-01", now=moment)
        moment += 60.0

    offline = recorder.of_type("camera_offline")
    assert len(offline) == 1
    assert offline[0].camera_id == "camera-01"
    assert offline[0].severity == "warning"
    assert offline[0].metadata["attempts"] == OFFLINE_AFTER_FAILURES


def test_the_outage_is_announced_once_not_every_retry(tmp_path: Path) -> None:
    """Kamera kechqurun o'chirilgan bo'lsa telefon tun bo'yi jiringlamasin."""
    runner, recorder, factory = build(tmp_path)
    factory["capture"] = None

    moment = 1.0
    for _ in range(20):
        runner.capture_once("camera-01", now=moment)
        moment += 60.0

    assert len(recorder.of_type("camera_offline")) == 1


def test_a_stream_that_stops_delivering_frames_counts_as_an_outage(tmp_path: Path) -> None:
    """Ulanish ochiq, lekin `grab()` `False` qaytaradi — kabel uzilgan."""
    runner, recorder, factory = build(tmp_path)
    factory["capture"] = DeadCapture()

    moment = 1.0
    for _ in range(OFFLINE_AFTER_FAILURES):
        factory["capture"] = DeadCapture()
        runner.capture_once("camera-01", now=moment)
        moment += 60.0

    assert len(recorder.of_type("camera_offline")) == 1


# ── Kamera tiklandi ──────────────────────────────────────────────────────


def test_recovery_reports_how_long_the_camera_was_down(tmp_path: Path) -> None:
    runner, recorder, factory = build(tmp_path)
    factory["capture"] = None

    moment = 1.0
    for _ in range(OFFLINE_AFTER_FAILURES):
        runner.capture_once("camera-01", now=moment)
        moment += 60.0
    offline_at = recorder.of_type("camera_offline")[0]
    assert offline_at is not None

    factory["capture"] = LiveCapture()
    runner.capture_once("camera-01", now=moment + 300.0)

    recovered = recorder.of_type("camera_recovered")
    assert len(recovered) == 1
    assert recovered[0].severity == "info"
    # Uzilish 3-urinishda e'lon qilingan (moment=121), tiklanish moment=481.
    assert recovered[0].metadata["downtime_sec"] > 0


def test_a_camera_that_never_went_offline_does_not_report_recovery(tmp_path: Path) -> None:
    """Har qayta ulanish "tiklandi" bo'lsa, RTSP ning normal uzilishi ham
    xabar qilinardi."""
    runner, recorder, factory = build(tmp_path)
    factory["capture"] = LiveCapture()

    runner.capture_once("camera-01", now=1.0)

    assert recorder.of_type("camera_recovered") == []


def test_the_cycle_can_repeat(tmp_path: Path) -> None:
    runner, recorder, factory = build(tmp_path)

    for _round in range(2):
        moment = 1.0 + _round * 10_000
        # Kamera uzildi: mavjud ulanish ham o'ldi, yangisi ham ochilmayapti.
        runner._streams["camera-01"].capture = None
        factory["capture"] = None
        for _ in range(OFFLINE_AFTER_FAILURES):
            runner.capture_once("camera-01", now=moment)
            moment += 60.0
        factory["capture"] = LiveCapture()
        runner.capture_once("camera-01", now=moment)

    assert len(recorder.of_type("camera_offline")) == 2
    assert len(recorder.of_type("camera_recovered")) == 2


def test_stats_show_the_outage(tmp_path: Path) -> None:
    runner, _recorder, factory = build(tmp_path)
    factory["capture"] = None

    assert runner.stats()["streams"]["camera-01"]["offline"] is False

    moment = 1.0
    for _ in range(OFFLINE_AFTER_FAILURES):
        runner.capture_once("camera-01", now=moment)
        moment += 60.0

    assert runner.stats()["streams"]["camera-01"]["offline"] is True


# ── Qoida dvigatelidan o'tish ────────────────────────────────────────────


def test_health_events_obey_the_rules_file(tmp_path: Path) -> None:
    """Hodisa to'g'ridan-to'g'ri outboxga yozilmaydi.

    Aks holda cooldown ham, `telegram_alert` ham, jadval ham ishlamasdi va
    kamera sog'ligini `config/rules.yaml` bilan boshqarib bo'lmasdi.
    """
    rules = RuleEngine(
        [
            Rule(
                name="Kamera javob bermayapti",
                event_type="camera_offline",
                severity="critical",
                actions=("cloud_sync", "telegram_alert"),
            )
        ]
    )
    runner, recorder, factory = build(tmp_path, rules=rules)
    factory["capture"] = None

    moment = 1.0
    for _ in range(OFFLINE_AFTER_FAILURES):
        runner.capture_once("camera-01", now=moment)
        moment += 60.0

    assert recorder.actions[0][0] == "cloud_sync"
    assert recorder.actions[1][0] == "telegram_alert"
    # Qoida severity'ni ko'tara oldi.
    assert recorder.events[0].severity == "critical"


def test_a_broken_event_sink_does_not_stop_the_capture_loop(tmp_path: Path) -> None:
    """Kamera o'qishdan muhimroq narsa yo'q: xabar yuborilmasa ham
    zanjir ishlashda davom etadi."""
    runner, _recorder, factory = build(tmp_path)

    def explode(_action: str, _event: EdgeEvent) -> None:
        raise RuntimeError("outbox yiqildi")

    runner.pipeline.on_action = explode
    factory["capture"] = None

    moment = 1.0
    for _ in range(OFFLINE_AFTER_FAILURES + 2):
        assert runner.capture_once("camera-01", now=moment) is False
        moment += 60.0


# ── Litsenziya darvozasi ─────────────────────────────────────────────────


def test_health_events_are_never_gated_by_the_licence(tmp_path: Path) -> None:
    """Bu oson o'tkazib yuboriladigan joy.

    `retail_event_filter()` noma'lum turlar uchun `False` qaytaradi, ya'ni
    yangi hodisa turi jimgina yutilib ketardi.  Sog'liq esa sotiladigan
    funksiya emas: mijoz qaysi paketni olganidan qat'i nazar, kamerasi
    ishlamayotganini bilishi kerak.
    """
    import json

    from chaqimchi_ai.retail.service import retail_event_filter
    from chaqimchi_ai.settings import AppSettings

    cache = tmp_path / "sotqin-config.json"
    cache.write_text(
        # Hech qanday funksiya sotib olinmagan.
        json.dumps({"revision": 7, "cloud_features": [], "cameras": []}),
        encoding="utf-8",
    )
    settings = AppSettings.model_validate(
        {"retail": {"enabled": True, "cameras_source": "auto", "sotqin_config_path": str(cache)}}
    )
    allowed = retail_event_filter(settings, tmp_path)

    for event_type in ("camera_offline", "camera_recovered", "stream_frozen"):
        assert allowed(EdgeEvent(event_type=event_type, camera_id="camera-01")) is True, event_type
    # Sotiladigan funksiyalar esa hali ham yopiq.
    assert allowed(EdgeEvent(event_type="line_crossed", camera_id="camera-01")) is False


# ── Qotib qolgan oqim ────────────────────────────────────────────────────


class FrozenTamper:
    """`TamperDetector` o'rniga: belgilangan kadrda qotish haqida aytadi."""

    def __init__(self) -> None:
        self.calls = 0
        self.alerted = False

    def update(self, _frame, *, now: float):
        from chaqimchi_ai.retail.tamper import FREEZE, FROZEN, TamperAlert

        self.calls += 1
        if self.calls != 2:
            return None
        return TamperAlert(reason=FROZEN, score=1.0, duration_sec=25.0, kind=FREEZE)


def test_a_frozen_stream_is_a_different_event_than_a_covered_camera(tmp_path: Path) -> None:
    """Qotgan oqimni "kamera yopilgan" deb aytish o'rnatuvchini noto'g'ri
    joyga — linzani artishga — yuboradi; aslida NVR qayta yuklanishi kerak."""
    recorder = Recorder()
    pipeline = RetailPipeline(
        FrameBroker(InferenceBudget(target_fps=30.0, min_fps=1.0, max_fps=60.0)),
        RuleEngine(),
        on_action=recorder,
        clip_dir=tmp_path / "clips",
        clock=lambda: 0.0,
        wall_clock=lambda: 0.0,
        local_time=lambda: None,
    )
    pipeline.add_camera("camera-01", FakeAnalyzer(), tamper=FrozenTamper(), now=0.0)  # type: ignore[arg-type]

    pipeline.offer("camera-01", FRAME, now=1.0)
    pipeline.offer("camera-01", FRAME, now=2.0)

    frozen = recorder.of_type("stream_frozen")
    assert len(frozen) == 1
    assert frozen[0].severity == "critical"
    assert frozen[0].metadata["duration_sec"] == 25.0
    assert recorder.of_type("camera_tampered") == []
    stats = pipeline.stats()
    assert stats["freezes"] == 1
    assert stats["tamper_alerts"] == 0
