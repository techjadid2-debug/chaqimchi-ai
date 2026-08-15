"""2-Bosqich: Barqarorlik (Resilience), Disk Favqulodda FIFO Tozalash va Statik Tracker testlari."""

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from chaqimchi_ai.retail.tracker import MotionTracker
from chaqimchi_ai.retention import purge_emergency_if_disk_low


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


def test_purge_emergency_if_disk_low(tmp_path: Path):
    media_dir = tmp_path / "media"
    media_dir.mkdir()

    # 3 ta eski fayl yaratamiz
    f1 = media_dir / "old1.mp4"
    f1.write_bytes(b"x" * 1024)
    time.sleep(0.01)
    f2 = media_dir / "old2.jpg"
    f2.write_bytes(b"y" * 2048)
    time.sleep(0.01)
    f3 = media_dir / "new.jpg"
    f3.write_bytes(b"z" * 4096)

    # Diskda joy kamligini mock qilamiz (masalan 1 GB qolgan, minimum 2 GB kerak)
    mock_usage = MagicMock(free=1 * 1024 * 1024 * 1024, total=100 * 1024 * 1024 * 1024)
    with patch("shutil.disk_usage", return_value=mock_usage):
        deleted_count, freed_bytes = purge_emergency_if_disk_low(
            [media_dir],
            min_free_bytes=2 * 1024 * 1024 * 1024,
            target_free_bytes=3 * 1024 * 1024 * 1024,
        )
        assert deleted_count == 3
        assert freed_bytes == 1024 + 2048 + 4096
        assert not f1.exists()
        assert not f2.exists()
        assert not f3.exists()
