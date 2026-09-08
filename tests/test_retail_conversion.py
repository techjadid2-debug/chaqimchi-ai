"""Avtomatik konversiya maxraji — qurilmadagi `SeenCounter`.

Capture rate = kirgan ÷ yaqinlashgan.  Bu testlar maxraj (yaqinlashgan)
noto'g'ri shishmasligini qo'riqlaydi: bir kadrlik xato deteksiya odam
deb sanalmaydi, bir odam oyna ichida bir marta sanaladi.
"""

from __future__ import annotations

import pytest

from enes.retail.conversion import SeenCounter


def test_a_one_frame_flicker_is_not_a_person() -> None:
    """Bitta kadrda ko'ringan quti — xato deteksiya, sanalmaydi."""
    counter = SeenCounter(min_frames=2)
    counter.mark(1)
    assert counter.flush() == 0


def test_a_track_seen_enough_frames_counts_once() -> None:
    counter = SeenCounter(min_frames=2)
    counter.mark(1)
    counter.mark(1)
    counter.mark(1)  # uchinchi ko'rinish sanoqni oshirmaydi
    assert counter.flush() == 1


def test_distinct_tracks_are_counted_separately() -> None:
    counter = SeenCounter(min_frames=1)
    counter.mark(1)
    counter.mark(2)
    counter.mark(3)
    assert counter.flush() == 3


def test_flush_starts_the_next_window_from_zero() -> None:
    counter = SeenCounter(min_frames=1)
    counter.mark(1)
    assert counter.flush() == 1
    assert counter.flush() == 0


def test_a_returning_track_after_flush_counts_as_a_new_visit() -> None:
    """Chiqib qaytgan odam ikki tashrif — line_crossed re-entry bilan bir xil."""
    counter = SeenCounter(min_frames=1)
    counter.mark(7)
    counter.flush()
    counter.mark(7)
    assert counter.flush() == 1


def test_half_counted_tracks_do_not_leak_into_the_next_window() -> None:
    """Chegaraga yetmagan track keyingi oynaga oqib o'tmasin."""
    counter = SeenCounter(min_frames=2)
    counter.mark(1)  # bitta kadr — hali sanalmagan
    assert counter.flush() == 0
    counter.mark(1)  # yangi oynada yana bitta kadr — hali yetarli emas
    assert counter.flush() == 0


def test_min_frames_must_be_positive() -> None:
    with pytest.raises(ValueError):
        SeenCounter(min_frames=0)
