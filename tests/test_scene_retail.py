"""SceneAnalyzer'ning retail hodisalari: kirish/chiqish, dwell, navbat.

Testlar detektorni almashtirib, odamni kadrda **qo'lda yurgizadi** — shunda
kamera ham, model ham kerak bo'lmaydi va natija takrorlanadigan bo'ladi.
"""

from __future__ import annotations

from typing import List, Tuple

import numpy as np

from chaqimchi_ai.scene_analytics import SceneAnalyzer
from chaqimchi_ai.settings import SceneSettings

FRAME = np.zeros((100, 100, 3), dtype=np.uint8)


class ScriptedDetector:
    """Berilgan markaz nuqtalari bo'yicha bbox qaytaradi (0..1 koordinatada)."""

    def __init__(self) -> None:
        self.people: List[Tuple[float, float]] = []

    def detect(self, frame):
        boxes = []
        for x, y in self.people:
            # `SceneAnalyzer` markazni ((x1+x2)/2, y2) dan oladi, ya'ni oyoq nuqtasi.
            cx, bottom = x * 100, y * 100
            boxes.append({"bbox": [cx - 5.0, bottom - 20.0, cx + 5.0, bottom], "score": 0.9})
        return boxes


def analyzer_for(**scene) -> tuple[SceneAnalyzer, ScriptedDetector]:
    settings = SceneSettings.model_validate({"enabled": True, "burst_fps": 30, **scene})
    detector = ScriptedDetector()
    analyzer = SceneAnalyzer("cam-1", detector, settings)
    analyzer.motion.has_motion = lambda _frame: True
    return analyzer, detector


# ── Kirish/chiqish ───────────────────────────────────────────────────────

DOOR = {"lines": [{"name": "eshik", "camera_id": "cam-1", "start": [0.5, 0.0], "end": [0.5, 1.0]}]}


def walk(analyzer, detector, *, start: float, stop: float, step: float, now: float = 1.0):
    """Odamni gorizontal yurgizadi va yig'ilgan hodisalarni qaytaradi."""
    events = []
    position = start
    direction = 1 if stop >= start else -1
    while (position - stop) * direction <= 1e-9:
        detector.people = [(round(position, 4), 0.5)]
        events.extend(analyzer.process(FRAME, now=now))
        position += step * direction
        now += 0.2
    return events


def test_walking_through_the_door_emits_line_crossed_with_direction() -> None:
    analyzer, detector = analyzer_for(**DOOR)

    events = walk(analyzer, detector, start=0.30, stop=0.70, step=0.04)
    crossed = [e for e in events if e.event_type == "line_crossed"]

    assert len(crossed) == 1
    assert crossed[0].line == "eshik"
    assert crossed[0].direction in {"in", "out"}
    assert crossed[0].track_id is not None


def test_walking_back_produces_the_opposite_direction() -> None:
    analyzer, detector = analyzer_for(**DOOR)

    first = [
        e
        for e in walk(analyzer, detector, start=0.30, stop=0.70, step=0.04)
        if e.event_type == "line_crossed"
    ][0]
    second = [
        e
        for e in walk(analyzer, detector, start=0.70, stop=0.30, step=0.04, now=20.0)
        if e.event_type == "line_crossed"
    ][0]

    assert {first.direction, second.direction} == {"in", "out"}


def test_fast_walking_still_counts_the_crossing() -> None:
    """Normal tezlikda yurgan odam ham sanalishi shart.

    Eski IoU tracker bu holatda track ID ni yo'qotardi va kirish sanalmasdi
    (`retail/tracker.py` dagi hisob).  `MotionTracker` harakatni bashorat
    qilgani uchun ID saqlanadi.
    """
    analyzer, detector = analyzer_for(**DOOR)

    events = walk(analyzer, detector, start=0.30, stop=0.70, step=0.10)

    crossed = [e for e in events if e.event_type == "line_crossed"]
    assert len(crossed) == 1


def test_moving_without_crossing_emits_nothing() -> None:
    analyzer, detector = analyzer_for(**DOOR)
    events = walk(analyzer, detector, start=0.20, stop=0.40, step=0.04)
    assert [e for e in events if e.event_type == "line_crossed"] == []


def test_lines_of_other_cameras_are_ignored() -> None:
    analyzer, detector = analyzer_for(
        lines=[{"name": "boshqa", "camera_id": "cam-2", "start": [0.5, 0.0], "end": [0.5, 1.0]}]
    )
    events = walk(analyzer, detector, start=0.30, stop=0.70, step=0.04)
    assert [e for e in events if e.event_type == "line_crossed"] == []


# ── Dwell ────────────────────────────────────────────────────────────────


def test_standing_in_a_zone_emits_dwell_once() -> None:
    analyzer, detector = analyzer_for(
        loitering_sec=86400,  # loitering aralashmasin
        zones=[
            {
                "name": "tokcha-3",
                "camera_id": "cam-1",
                "polygon": [[0.0, 0.0], [0.5, 0.0], [0.5, 1.0], [0.0, 1.0]],
                "dwell_sec": 60,
            }
        ],
    )
    detector.people = [(0.2, 0.5)]

    assert [e for e in analyzer.process(FRAME, now=1.0) if e.event_type == "dwell_exceeded"] == []
    assert [e for e in analyzer.process(FRAME, now=59.0) if e.event_type == "dwell_exceeded"] == []

    alerts = [e for e in analyzer.process(FRAME, now=61.0) if e.event_type == "dwell_exceeded"]
    assert len(alerts) == 1
    assert alerts[0].zone == "tokcha-3"
    assert alerts[0].dwell_sec >= 60.0

    # Turishda davom etsa takrorlamaydi.
    assert [e for e in analyzer.process(FRAME, now=200.0) if e.event_type == "dwell_exceeded"] == []


def test_zone_without_dwell_setting_never_alerts() -> None:
    analyzer, detector = analyzer_for(
        loitering_sec=86400,
        zones=[
            {
                "name": "yo'lak",
                "camera_id": "cam-1",
                "polygon": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
            }
        ],
    )
    detector.people = [(0.5, 0.5)]
    analyzer.process(FRAME, now=0.0)
    assert [
        e for e in analyzer.process(FRAME, now=9999.0) if e.event_type == "dwell_exceeded"
    ] == []


# ── Navbat ───────────────────────────────────────────────────────────────

QUEUE_ZONE = {
    "queue_limit": 3,
    "occupancy_limit": 9999,
    "loitering_sec": 86400,
    "zones": [
        {
            "name": "kassa",
            "camera_id": "cam-1",
            "queue": True,
            "polygon": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
        }
    ],
}


def test_queue_alert_fires_at_the_limit_and_latches() -> None:
    analyzer, detector = analyzer_for(**QUEUE_ZONE)

    detector.people = [(0.2, 0.5), (0.4, 0.5)]
    assert [
        e for e in analyzer.process(FRAME, now=1.0) if e.event_type == "queue_threshold_exceeded"
    ] == []

    detector.people = [(0.2, 0.5), (0.4, 0.5), (0.6, 0.5)]
    alerts = [
        e for e in analyzer.process(FRAME, now=2.0) if e.event_type == "queue_threshold_exceeded"
    ]
    assert len(alerts) == 1
    assert alerts[0].queue_length == 3
    assert alerts[0].zone == "kassa"
    assert alerts[0].severity == "warning"

    # Navbat turaversa qayta ogohlantirmaydi — mijoz xabardan charchamasin.
    assert [
        e for e in analyzer.process(FRAME, now=3.0) if e.event_type == "queue_threshold_exceeded"
    ] == []


def test_queue_alert_rearms_after_the_queue_clears() -> None:
    analyzer, detector = analyzer_for(**QUEUE_ZONE)
    detector.people = [(0.2, 0.5), (0.4, 0.5), (0.6, 0.5)]
    analyzer.process(FRAME, now=1.0)

    detector.people = [(0.2, 0.5)]  # navbat tarqadi
    analyzer.process(FRAME, now=2.0)

    detector.people = [(0.2, 0.5), (0.4, 0.5), (0.6, 0.5), (0.8, 0.5)]
    alerts = [
        e for e in analyzer.process(FRAME, now=3.0) if e.event_type == "queue_threshold_exceeded"
    ]
    assert len(alerts) == 1


def test_zone_without_queue_flag_never_reports_a_queue() -> None:
    analyzer, detector = analyzer_for(
        queue_limit=2,
        occupancy_limit=9999,
        loitering_sec=86400,
        zones=[
            {
                "name": "zal",
                "camera_id": "cam-1",
                "polygon": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
            }
        ],
    )
    detector.people = [(0.2, 0.5), (0.4, 0.5), (0.6, 0.5)]
    events = analyzer.process(FRAME, now=1.0)
    assert [e for e in events if e.event_type == "queue_threshold_exceeded"] == []


# ── Xotira ───────────────────────────────────────────────────────────────


def test_track_state_is_released_so_memory_does_not_grow_all_day() -> None:
    """8/128 qurilmada kun bo'yi o'sadigan lug'at xotirani yeydi."""
    analyzer, detector = analyzer_for(**DOOR)

    for index in range(40):
        detector.people = [(0.2 + (index % 3) * 0.1, 0.1 + index * 0.02)]
        analyzer.process(FRAME, now=float(index))

    assert analyzer.lines.tracked > 1
    # Tracklar eskirgandan keyin (>120 s) holat tozalanadi.
    detector.people = []
    analyzer.process(FRAME, now=1000.0)
    assert analyzer.lines.tracked == 0
