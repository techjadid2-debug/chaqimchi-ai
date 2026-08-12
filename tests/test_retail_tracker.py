"""Harakatni bashorat qiluvchi tracker.

Asosiy talab: normal tezlikda yurgan odam bitta ID ni saqlab qolsin.  Aks
holda kirish/chiqish kam sanaladi va konversiya hisoboti xato chiqadi.
"""

from __future__ import annotations

import pytest

from chaqimchi_ai.face_tracker import FaceTracker
from chaqimchi_ai.retail.tracker import MotionTracker


def box(x: float, *, width: float = 60.0, height: float = 160.0, y: float = 100.0):
    return {"bbox": [x, y, x + width, y + height], "score": 0.9}


def ids_while_walking(tracker, *, start: float, step: float, frames: int):
    seen = []
    for index in range(frames):
        result = tracker.update([box(start + index * step)])
        seen.append(result[0]["track_id"])
    return seen


# ── Asosiy muammo ────────────────────────────────────────────────────────


def test_normal_walking_speed_keeps_one_id() -> None:
    """640×360 da 5 FPS: odam ~60 px keng, kadrlar orasida ~45 px siljiydi."""
    tracker = MotionTracker()
    assert len(set(ids_while_walking(tracker, start=50.0, step=45.0, frames=8))) == 1


def test_old_tracker_fails_on_the_same_input() -> None:
    """Nima uchun yangi tracker kerakligini qayd etadi."""
    old = FaceTracker(iou_threshold=0.25, max_missed_frames=10)
    seen = []
    for index in range(8):
        seen.append(old.update([box(50.0 + index * 45.0)])[0]["track_id"])
    assert len(set(seen)) > 1  # har kadrda yangi ID


def test_very_fast_movement_still_breaks_and_that_is_honest() -> None:
    """Bashorat mo'jiza emas: tezlik keskin o'zgarsa track baribir uziladi.

    Birinchi kadrda tezlik hali noma'lum, shuning uchun juda katta sakrash
    bog'lanmaydi.  Bu halol chegara — sotuvda "har qanday tezlikda ishlaydi"
    deb aytilmasin.
    """
    tracker = MotionTracker()
    tracker.update([box(50.0)])
    result = tracker.update([box(400.0)])  # bir kadrda 350 px
    assert result[0]["track_id"] != 1


# ── Bashorat va pana ─────────────────────────────────────────────────────


def test_track_survives_a_short_occlusion() -> None:
    tracker = MotionTracker()
    for index in range(4):
        tracker.update([box(50.0 + index * 40.0)])
    first_id = tracker.update([box(50.0 + 4 * 40.0)])[0]["track_id"]

    # Ikki kadr davomida odam ustun ortida — deteksiya yo'q.
    tracker.update([])
    tracker.update([])

    # Yana paydo bo'ldi, harakatini davom ettirgan joyda.
    again = tracker.update([box(50.0 + 7 * 40.0)])[0]["track_id"]
    assert again == first_id


def test_track_is_dropped_after_a_long_absence() -> None:
    tracker = MotionTracker(max_missed_frames=3)
    first = tracker.update([box(50.0)])[0]["track_id"]
    for _ in range(4):
        tracker.update([])
    assert tracker.active == 0
    assert tracker.update([box(50.0)])[0]["track_id"] != first


def test_prediction_stops_after_a_few_missed_frames() -> None:
    """Uzoq ko'rinmagan ramka kadrdan uchib chiqib begonaga yopishmasin."""
    tracker = MotionTracker(max_missed_frames=20, max_velocity_frames=2)
    for index in range(5):
        tracker.update([box(50.0 + index * 40.0)])
    for _ in range(10):
        tracker.update([])

    # Bashorat to'xtagani uchun ramka joyida qolgan; boshqa joydan chiqqan
    # odam eski ID ni o'g'irlab ketmaydi.
    assert tracker.update([box(900.0)])[0]["track_id"] not in {1}


# ── Ko'p odam ────────────────────────────────────────────────────────────


def test_two_people_walking_apart_keep_separate_ids() -> None:
    tracker = MotionTracker()
    left_ids, right_ids = [], []
    for index in range(6):
        result = tracker.update([box(300.0 - index * 30.0), box(500.0 + index * 30.0)])
        by_x = sorted(result, key=lambda item: item["bbox"][0])
        left_ids.append(by_x[0]["track_id"])
        right_ids.append(by_x[1]["track_id"])
    assert len(set(left_ids)) == 1
    assert len(set(right_ids)) == 1
    assert left_ids[0] != right_ids[0]


def test_each_detection_gets_exactly_one_track() -> None:
    tracker = MotionTracker()
    result = tracker.update([box(100.0), box(300.0), box(500.0)])
    assert len({item["track_id"] for item in result}) == 3


def test_detections_are_annotated_in_place_like_the_old_tracker() -> None:
    tracker = MotionTracker()
    detections = [box(100.0)]
    returned = tracker.update(detections)
    assert returned is detections
    assert "track_id" in detections[0]


# ── Konfiguratsiya ───────────────────────────────────────────────────────


def test_invalid_configuration_is_rejected() -> None:
    with pytest.raises(ValueError):
        MotionTracker(iou_threshold=0.0)
    with pytest.raises(ValueError):
        MotionTracker(max_missed_frames=0)
    with pytest.raises(ValueError):
        MotionTracker(velocity_smoothing=1.5)


def test_stationary_person_keeps_the_same_id() -> None:
    tracker = MotionTracker()
    seen = [tracker.update([box(200.0)])[0]["track_id"] for _ in range(20)]
    assert len(set(seen)) == 1
