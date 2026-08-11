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
