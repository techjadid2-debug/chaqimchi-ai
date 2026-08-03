from chaqimchi_ai.licensing.enforce import filter_cameras
from chaqimchi_ai.settings import CameraItem


def test_filter_cameras_limits_enabled() -> None:
    cams = [
        CameraItem(id="a", source=0, enabled=True),
        CameraItem(id="b", source=1, enabled=True),
        CameraItem(id="c", source=2, enabled=True),
    ]
    out = filter_cameras(cams, max_cameras=2)
    enabled = [c for c in out if c.enabled]
    assert len(enabled) == 2
