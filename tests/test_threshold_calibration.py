import numpy as np

from chaqimchi_ai.threshold_calibration import calibrate_from_gallery


def _orthonormal_rows(n: int, dim: int = 512) -> np.ndarray:
    base = np.eye(dim, dtype=np.float32)[:n]
    return base


def test_calibrate_insufficient_gallery() -> None:
    report = calibrate_from_gallery(
        np.empty((1, 512), dtype=np.float32),
        current_threshold=0.4,
    )
    assert report.gallery_size == 1
    assert report.suggested_threshold == 0.4


def test_calibrate_suggests_above_cross_scores() -> None:
    emb = _orthonormal_rows(3)
    report = calibrate_from_gallery(emb, current_threshold=0.4, margin=0.02)
    assert report.gallery_size == 3
    assert len(report.negative_scores) == 6
    assert report.suggested_threshold > max(report.negative_scores)
