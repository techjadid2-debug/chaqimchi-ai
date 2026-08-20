import numpy as np

from chaqimchi_ai.scene_analytics import SceneAnalyzer
from chaqimchi_ai.settings import SceneSettings


class FakeDetector:
    def detect(self, frame):
        return [{"bbox": [20.0, 20.0, 80.0, 90.0], "score": 0.9}]


def test_scene_analyzer_emits_four_core_event_types() -> None:
    settings = SceneSettings.model_validate(
        {
            "enabled": True,
            "burst_fps": 5,
            "loitering_sec": 5,
            "occupancy_limit": 1,
            "event_debounce_sec": 1,
            "zones": [
                {
                    "name": "ombor",
                    "camera_id": "cam-1",
                    "restricted": True,
                    "polygon": [[0, 0], [1, 0], [1, 1], [0, 1]],
                }
            ],
        }
    )
    analyzer = SceneAnalyzer("cam-1", FakeDetector(), settings)
    analyzer.motion.has_motion = lambda _frame: True
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    first = analyzer.process(frame, now=10)
    assert {event.event_type for event in first} == {
        "person_detected",
        "zone_entered",
        "occupancy_exceeded",
    }
    assert next(e for e in first if e.event_type == "zone_entered").severity == "warning"

    later = analyzer.process(frame, now=16)
    assert "loitering" in {event.event_type for event in later}


def test_scene_analyzer_motion_gate_skips_detector() -> None:
    class ExplodingDetector:
        def detect(self, frame):
            raise AssertionError("detector chaqirilmasligi kerak")

    analyzer = SceneAnalyzer("cam", ExplodingDetector(), SceneSettings())
    analyzer.motion.has_motion = lambda _frame: False
    assert analyzer.process(np.zeros((10, 10, 3), dtype=np.uint8), now=1) == []


# ── Davomat: yuz kadri produseri ─────────────────────────────────────────
#
# Qurilma yuzni tanimaydi — faqat yaqin kelgan odamdan `face_captured`
# chiqaradi.  Moslash cloudda (cloud/faces.py, tests/test_cloud_faces.py).


def face_events(events):
    return [event for event in events if event.event_type == "face_captured"]


def _attendance_analyzer(bbox):
    class Detector:
        def detect(self, frame):
            return [{"bbox": list(bbox), "score": 0.9}]

    analyzer = SceneAnalyzer(
        "cam-1", Detector(), SceneSettings(event_debounce_sec=1), attendance=True
    )
    analyzer.motion.has_motion = lambda _frame: True
    return analyzer


def test_attendance_camera_emits_a_face_capture() -> None:
    analyzer = _attendance_analyzer([20.0, 10.0, 80.0, 90.0])  # bo'yi 80% — yaqin
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    events = face_events(analyzer.analyze(frame, now=10))

    assert len(events) == 1
    assert events[0].camera_id == "cam-1"
    assert events[0].metadata["bbox"] == [20.0, 10.0, 80.0, 90.0]


def test_ordinary_cameras_never_emit_face_captures() -> None:
    class Detector:
        def detect(self, frame):
            return [{"bbox": [20.0, 10.0, 80.0, 90.0], "score": 0.9}]

    analyzer = SceneAnalyzer("cam-1", Detector(), SceneSettings(event_debounce_sec=1))
    analyzer.motion.has_motion = lambda _frame: True

    events = face_events(analyzer.analyze(np.zeros((100, 100, 3), dtype=np.uint8), now=10))

    assert events == []


def test_far_away_person_is_skipped() -> None:
    """Kichik ramka = mayda yuz — cloud bekorga ishlamasin."""
    analyzer = _attendance_analyzer([20.0, 40.0, 40.0, 60.0])  # bo'yi 20% < 28%

    events = face_events(analyzer.analyze(np.zeros((100, 100, 3), dtype=np.uint8), now=10))

    assert events == []


def test_one_track_sends_at_most_two_captures_with_a_pause() -> None:
    """Eshik oldida turgan odam oqimni to'ldirmasin: 2 ta kadr, orasi 60 s."""
    analyzer = _attendance_analyzer([20.0, 10.0, 80.0, 90.0])
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    assert len(face_events(analyzer.analyze(frame, now=10))) == 1
    assert face_events(analyzer.analyze(frame, now=30)) == [], "60 s o'tmadi"
    assert len(face_events(analyzer.analyze(frame, now=75))) == 1
    assert face_events(analyzer.analyze(frame, now=200)) == [], "limit 2 ta"
