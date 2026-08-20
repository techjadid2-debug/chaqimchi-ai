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


# ── Demografiya (jins/yosh) — kirish kesishmasida ────────────────────────


class FakeDemography:
    def __init__(self, result=None):
        self.result = result or {"jins": "ayol", "yosh": 27}
        self.calls = 0

    def estimate(self, frame, bbox):
        self.calls += 1
        return self.result


def _entrance_analyzer(demography, pressure=None):
    settings = SceneSettings.model_validate({"enabled": True, "burst_fps": 30, **DOOR})
    detector = ScriptedDetector()
    analyzer = SceneAnalyzer("cam-1", detector, settings, demography=demography, pressure=pressure)
    analyzer.motion.has_motion = lambda _frame: True
    return analyzer, detector


def _in_crossing(analyzer, detector, *, now: float = 1.0):
    events = walk(analyzer, detector, start=0.30, stop=0.70, step=0.04, now=now)
    crossed = [e for e in events if e.event_type == "line_crossed"]
    return crossed[0] if crossed else None


def test_demography_rides_the_in_crossing_metadata() -> None:
    """Natija alohida hodisa emas — o'sha line_crossed metadatasida.

    Yangi hodisa turi eski cloudda butun batchni 422 qilardi.
    """
    fake = FakeDemography({"jins": "erkak", "yosh": 41})
    analyzer, detector = _entrance_analyzer(fake)

    crossing = _in_crossing(analyzer, detector)

    assert crossing is not None
    if crossing.direction == "in":
        assert crossing.metadata["demografiya"] == {"jins": "erkak", "yosh": 41}
        assert fake.calls == 1
    else:
        assert "demografiya" not in crossing.metadata, "chiqishda baholanmaydi"


def test_camera_without_estimator_stays_untouched() -> None:
    analyzer, detector = _entrance_analyzer(None)

    crossing = _in_crossing(analyzer, detector)

    assert crossing is not None and "demografiya" not in crossing.metadata


def test_high_pressure_skips_demography() -> None:
    """Bosim 0.85+ — xavfsizlik va sanash ustuvor, demografiya kutadi."""
    fake = FakeDemography()
    analyzer, detector = _entrance_analyzer(fake, pressure=lambda: 0.9)

    crossing = _in_crossing(analyzer, detector)

    assert crossing is not None
    assert "demografiya" not in crossing.metadata
    assert fake.calls == 0, "og'ir paytda model umuman chaqirilmasin"


def test_failed_estimates_are_capped_per_track() -> None:
    """Yuz topilmayotgan trek uchun cheksiz urinish bo'lmasin."""

    class NoFace(FakeDemography):
        def estimate(self, frame, bbox):
            self.calls += 1
            return None

    fake = NoFace()
    analyzer, detector = _entrance_analyzer(fake)

    # Bir trek ikki marta kirdi-chiqdi qildi (4 kesishma) — urinish 2 ta.
    _in_crossing(analyzer, detector, now=1.0)
    walk(analyzer, detector, start=0.70, stop=0.30, step=0.04, now=30.0)
    _in_crossing(analyzer, detector, now=60.0)

    assert fake.calls <= 2


def test_estimator_crash_never_breaks_analysis() -> None:
    class Boom(FakeDemography):
        def estimate(self, frame, bbox):
            raise RuntimeError("model yiqildi")

    analyzer, detector = _entrance_analyzer(Boom())

    crossing = _in_crossing(analyzer, detector)

    assert crossing is not None, "tahlil davom etadi"
    assert "demografiya" not in crossing.metadata


# ── Kassa nazorati ───────────────────────────────────────────────────────
#
# Eng muhim qoida: bo'sh kassaning O'ZI signal emas.  Mijoz yo'q paytda
# kassa bo'sh bo'lishi normal va bu haqda xabar berish — shovqin.
# Signal ikkalasi birga bo'lganda: kadrda odamlar bor, kassada esa yo'q.

#: Kassa zonasi kadrning chap yarmida — o'ng yarim "savdo zali" bo'lib
#: qoladi va u yerdagi odam kassaga kirmaydi.
CHECKOUT = {
    "queue_limit": 3,
    "occupancy_limit": 9999,
    "loitering_sec": 86400,
    "checkout_idle_sec": 60,
    "zones": [
        {
            "name": "kassa",
            "camera_id": "cam-1",
            "queue": True,
            "polygon": [[0.0, 0.0], [0.5, 0.0], [0.5, 1.0], [0.0, 1.0]],
        }
    ],
}


def _checkout_events(analyzer, now: float, kind: str):
    return [e for e in analyzer.process(FRAME, now=now) if e.event_type == kind]


def test_an_empty_shop_never_reports_an_empty_checkout() -> None:
    """Do'konda odam yo'q — bo'sh kassa kutilgan holat.

    Bu tekshiruv bo'lmasa kechqurun yopilgandan keyin hisob ketaverib,
    ertalab birinchi mijoz kelishi bilan darrov signal chiqib ketardi.
    """
    analyzer, detector = analyzer_for(**CHECKOUT)
    detector.people = []
    # 1.0 dan boshlanadi: `process` birinchi kadrni tezlik chegarasi
    # sabab o'tkazib yuboradi (`_last_analysis` noldan boshlanadi).
    for tick in range(1, 300, 20):
        assert _checkout_events(analyzer, float(tick), "checkout_unattended") == []


def test_customers_in_view_but_nobody_at_the_checkout() -> None:
    analyzer, detector = analyzer_for(**CHECKOUT)
    # Savdo zalida (o'ng yarim) ikki mijoz, kassada hech kim yo'q.
    detector.people = [(0.7, 0.5), (0.8, 0.5)]

    assert _checkout_events(analyzer, 1.0, "checkout_unattended") == []
    assert _checkout_events(analyzer, 59.0, "checkout_unattended") == []

    alerts = _checkout_events(analyzer, 62.0, "checkout_unattended")
    assert len(alerts) == 1
    assert alerts[0].zone == "kassa"
    assert alerts[0].severity == "warning"
    assert alerts[0].metadata["people_in_view"] == 2

    # Latch: holat o'zgarmaguncha qayta chiqmaydi.
    assert _checkout_events(analyzer, 200.0, "checkout_unattended") == []


def test_the_alert_rearms_once_the_checkout_is_used_again() -> None:
    analyzer, detector = analyzer_for(**CHECKOUT)
    detector.people = [(0.7, 0.5)]
    analyzer.process(FRAME, now=1.0)
    assert _checkout_events(analyzer, 62.0, "checkout_unattended")

    # Kassaga odam keldi — hisob noldan boshlanadi.
    detector.people = [(0.2, 0.5), (0.7, 0.5)]
    analyzer.process(FRAME, now=70.0)

    detector.people = [(0.7, 0.5)]
    analyzer.process(FRAME, now=80.0)
    assert _checkout_events(analyzer, 100.0, "checkout_unattended") == []
    assert len(_checkout_events(analyzer, 145.0, "checkout_unattended")) == 1


TWO_TILLS = {
    "queue_limit": 3,
    "occupancy_limit": 9999,
    "loitering_sec": 86400,
    "checkout_idle_sec": 3600,  # bo'sh kassa signali bu testga xalaqit bermasin
    "zones": [
        {
            "name": "kassa-1",
            "camera_id": "cam-1",
            "queue": True,
            "polygon": [[0.0, 0.0], [0.5, 0.0], [0.5, 1.0], [0.0, 1.0]],
        },
        {
            "name": "kassa-2",
            "camera_id": "cam-1",
            "queue": True,
            "polygon": [[0.5, 0.0], [1.0, 0.0], [1.0, 1.0], [0.5, 1.0]],
        },
    ],
}


def test_a_long_queue_next_to_an_empty_till_asks_to_open_it() -> None:
    analyzer, detector = analyzer_for(**TWO_TILLS)
    detector.people = [(0.1, 0.5), (0.2, 0.5), (0.3, 0.5)]

    alerts = _checkout_events(analyzer, 1.0, "checkout_second_till")
    assert len(alerts) == 1
    assert alerts[0].zone == "kassa-1"
    assert alerts[0].queue_length == 3
    assert alerts[0].metadata["bosh_kassalar"] == ["kassa-2"]

    # Latch — navbat turaversa takrorlanmaydi.
    assert _checkout_events(analyzer, 2.0, "checkout_second_till") == []


def test_no_second_till_advice_when_both_are_busy() -> None:
    """Ikkinchi kassa allaqachon ishlayapti — maslahat o'rinsiz."""
    analyzer, detector = analyzer_for(**TWO_TILLS)
    detector.people = [(0.1, 0.5), (0.2, 0.5), (0.3, 0.5), (0.7, 0.5)]

    assert _checkout_events(analyzer, 1.0, "checkout_second_till") == []


def test_a_single_till_shop_never_gets_the_advice() -> None:
    """Ochadigan ikkinchi kassa yo'q — bu xabar mijozni g'ashiga tegadi."""
    analyzer, detector = analyzer_for(**CHECKOUT)
    detector.people = [(0.1, 0.5), (0.2, 0.5), (0.3, 0.5)]

    assert _checkout_events(analyzer, 1.0, "checkout_second_till") == []
