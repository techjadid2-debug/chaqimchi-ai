"""Kirish/chiqish chizig'i va zonada turish vaqti.

Bu ikkalasi konversiya hisobining asosi: "nechta odam kirdi" noto'g'ri
bo'lsa, "savdo konversiyasi" ham noto'g'ri chiqadi.
"""

from __future__ import annotations

import pytest

from chaqimchi_ai.retail.lines import (
    CountingLine,
    DwellTracker,
    LineCounter,
    segments_intersect,
)


def door(**overrides) -> CountingLine:
    defaults = dict(name="eshik", camera_id="kirish", start=(0.5, 0.0), end=(0.5, 1.0))
    defaults.update(overrides)
    return CountingLine(**defaults)  # type: ignore[arg-type]


# ── Geometriya ───────────────────────────────────────────────────────────


def test_segments_intersect_only_when_they_really_cross() -> None:
    # Kesishadi
    assert segments_intersect((0, 0), (1, 1), (0, 1), (1, 0)) is True
    # Parallel
    assert segments_intersect((0, 0), (1, 0), (0, 1), (1, 1)) is False
    # Cheksiz chiziqda kesishardi, lekin kesmalar yetmaydi — eshik yonidan
    # o'tgan odam "kirdi" bo'lmasligi kerak.
    assert segments_intersect((0, 0), (0.2, 0.2), (0.8, 0), (0.8, 1)) is False


def test_line_rejects_invalid_geometry() -> None:
    with pytest.raises(ValueError, match="0..1"):
        door(start=(1.5, 0.0))
    with pytest.raises(ValueError, match="nol"):
        door(start=(0.5, 0.5), end=(0.5, 0.5))


# ── Kirish/chiqish ───────────────────────────────────────────────────────


def test_crossing_left_to_right_is_counted_once_with_direction() -> None:
    counter = LineCounter([door()])

    assert counter.update(1, (0.3, 0.5)) == []  # birinchi nuqta — taqqoslashga baza yo'q
    crossings = counter.update(1, (0.7, 0.5))

    assert len(crossings) == 1
    assert crossings[0].line == "eshik"
    assert crossings[0].track_id == 1
    direction = crossings[0].direction
    # Yana harakat qilsa qayta sanalmaydi.
    assert counter.update(1, (0.9, 0.5)) == []
    # Orqaga qaytsa teskari yo'nalish.
    back = counter.update(1, (0.2, 0.5))
    assert len(back) == 1
    assert back[0].direction != direction


def test_swap_direction_flips_in_and_out() -> None:
    normal = LineCounter([door()])
    swapped = LineCounter([door(swap_direction=True)])

    normal.update(1, (0.3, 0.5))
    swapped.update(1, (0.3, 0.5))

    assert normal.update(1, (0.7, 0.5))[0].direction != swapped.update(1, (0.7, 0.5))[0].direction


def test_standing_on_the_line_does_not_count_repeatedly() -> None:
    counter = LineCounter([door()])
    counter.update(1, (0.5, 0.4))
    # Chiziq ustida turibdi va biroz qimirlaydi.
    total = sum(len(counter.update(1, (0.5, 0.4 + step * 0.01))) for step in range(1, 20))
    assert total == 0


def test_walking_alongside_the_line_is_not_a_crossing() -> None:
    counter = LineCounter([door()])
    counter.update(1, (0.3, 0.1))
    assert counter.update(1, (0.3, 0.9)) == []


def test_one_movement_can_cross_two_lines() -> None:
    counter = LineCounter(
        [
            door(name="tashqi", start=(0.3, 0.0), end=(0.3, 1.0)),
            door(name="ichki", start=(0.6, 0.0), end=(0.6, 1.0)),
        ]
    )
    counter.update(7, (0.1, 0.5))
    crossings = counter.update(7, (0.9, 0.5))
    assert sorted(item.line for item in crossings) == ["ichki", "tashqi"]


def test_forgotten_tracks_do_not_leak_memory() -> None:
    counter = LineCounter([door()])
    for track_id in range(50):
        counter.update(track_id, (0.3, 0.5))
    assert counter.tracked == 50

    counter.retain([1, 2, 3])
    assert counter.tracked == 3
    counter.forget(1)
    assert counter.tracked == 2


def test_new_track_id_after_occlusion_is_not_double_counted() -> None:
    """Tracker ID almashtirsa, yangi track o'z birinchi nuqtasidan boshlaydi."""
    counter = LineCounter([door()])
    counter.update(1, (0.3, 0.5))
    counter.update(1, (0.7, 0.5))  # kirdi
    # Odam qayta paydo bo'ldi, lekin boshqa ID bilan — chiziqning narigi tomonida.
    assert counter.update(2, (0.8, 0.5)) == []


# ── Dwell ────────────────────────────────────────────────────────────────


def test_dwell_alerts_once_after_the_threshold() -> None:
    tracker = DwellTracker({"tokcha-3": 60.0})

    assert tracker.update(1, ["tokcha-3"], now=0.0) == []
    assert tracker.update(1, ["tokcha-3"], now=59.0) == []

    alerts = tracker.update(1, ["tokcha-3"], now=61.0)
    assert len(alerts) == 1
    assert alerts[0].zone == "tokcha-3"
    assert alerts[0].dwell_sec == pytest.approx(61.0)

    # Turishda davom etsa qayta ogohlantirmaydi.
    assert tracker.update(1, ["tokcha-3"], now=200.0) == []


def test_leaving_and_returning_restarts_the_clock() -> None:
    tracker = DwellTracker({"tokcha-3": 60.0})
    tracker.update(1, ["tokcha-3"], now=0.0)
    tracker.update(1, ["tokcha-3"], now=61.0)  # ogohlantirdi

    tracker.update(1, [], now=70.0)  # chiqdi
    tracker.update(1, ["tokcha-3"], now=80.0)  # qaytdi

    assert tracker.update(1, ["tokcha-3"], now=130.0) == []  # 50 s — hali yetmadi
    assert len(tracker.update(1, ["tokcha-3"], now=141.0)) == 1


def test_zones_without_a_threshold_are_ignored() -> None:
    tracker = DwellTracker({"tokcha-3": 10.0})
    tracker.update(1, ["yo'lak"], now=0.0)
    assert tracker.update(1, ["yo'lak"], now=1000.0) == []


def test_each_track_and_zone_is_counted_separately() -> None:
    tracker = DwellTracker({"kassa": 30.0, "tokcha": 30.0})
    tracker.update(1, ["kassa", "tokcha"], now=0.0)
    tracker.update(2, ["kassa"], now=20.0)

    alerts = tracker.update(1, ["kassa", "tokcha"], now=31.0)
    assert sorted(item.zone for item in alerts) == ["kassa", "tokcha"]
    assert tracker.update(2, ["kassa"], now=31.0) == []  # 2-track hali 11 s


def test_dwell_state_is_released_with_the_track() -> None:
    tracker = DwellTracker({"kassa": 30.0})
    tracker.update(1, ["kassa"], now=0.0)
    assert tracker.dwell_of(1, "kassa", now=10.0) == pytest.approx(10.0)

    tracker.retain([2])
    assert tracker.dwell_of(1, "kassa", now=10.0) is None


def test_dwell_rejects_useless_threshold() -> None:
    with pytest.raises(ValueError):
        DwellTracker({"kassa": 0.0})
