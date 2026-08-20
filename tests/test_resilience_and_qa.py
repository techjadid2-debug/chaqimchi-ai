"""Barqarorlik (Resilience) va Statik Tracker testlari."""

from chaqimchi_ai.retail.tracker import MotionTracker


def test_motion_tracker_detects_static_objects():
    tracker = MotionTracker(iou_threshold=0.2, max_missed_frames=10)

    # 1-kadr: obyekt paydo bo'ldi
    dets = tracker.update([{"bbox": [100.0, 100.0, 150.0, 200.0], "score": 0.9}])
    assert len(dets) == 1
    track_id = dets[0]["track_id"]
    assert not tracker.is_static(track_id, min_hits=5)

    # 10 marta deyarli joyidan qimirlamagan holda update qilish (masalan vitrina manekeni)
    for _ in range(10):
        dets = tracker.update([{"bbox": [100.2, 100.1, 150.1, 200.2], "score": 0.9}])
        assert len(dets) == 1

    # Endi 5 tadan ko'p hit bo'ldi va harakat 1 px dan kam -> statik deb hisoblanadi
    assert tracker.is_static(track_id, min_hits=5, max_net_movement=5.0)


def test_motion_tracker_moving_object_is_not_static():
    tracker = MotionTracker(iou_threshold=0.2, max_missed_frames=10)

    # Odam oldinga qarab harakatlanmoqda
    x = 100.0
    for i in range(10):
        dets = tracker.update(
            [{"bbox": [x + i * 15.0, 100.0, x + i * 15.0 + 50.0, 200.0], "score": 0.9}]
        )

    track_id = dets[0]["track_id"]
    # 10 ta hit bo'lsa ham, 150 px siljigan -> statik EMAS
    assert not tracker.is_static(track_id, min_hits=5, max_net_movement=5.0)


# Eslatma: `purge_emergency_if_disk_low` testi olib tashlandi — funksiya
# `chaqimchi_ai/retention.py` bilan birga arxivlangan (hech qaysi xizmat
# uni chaqirmasdi; disk himoyasi edge'da `outbox.prune`, cloudda esa
# media kvotasi orqali ishlaydi).
