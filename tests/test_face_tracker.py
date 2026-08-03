from chaqimchi_ai.face_tracker import FaceTracker, bbox_iou


def test_bbox_iou_full_overlap() -> None:
    b = [10.0, 10.0, 50.0, 50.0]
    assert bbox_iou(b, b) == 1.0


def test_tracker_keeps_id_when_bbox_moves_slightly() -> None:
    t = FaceTracker(iou_threshold=0.3, max_missed_frames=5)
    f1 = [{"bbox": [0.0, 0.0, 100.0, 100.0]}]
    t.update(f1)
    tid = f1[0]["track_id"]

    f2 = [{"bbox": [5.0, 5.0, 105.0, 105.0]}]
    t.update(f2)
    assert f2[0]["track_id"] == tid


def test_tracker_new_id_after_miss_frames() -> None:
    t = FaceTracker(iou_threshold=0.5, max_missed_frames=2)
    f1 = [{"bbox": [0.0, 0.0, 50.0, 50.0]}]
    t.update(f1)
    old = f1[0]["track_id"]

    t.update([])
    t.update([])
    f2 = [{"bbox": [200.0, 200.0, 250.0, 250.0]}]
    t.update(f2)
    assert f2[0]["track_id"] != old
