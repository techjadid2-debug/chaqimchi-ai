import numpy as np
import pytest

from chaqimchi_ai.similarity import cosine_compare_arrays


def test_cosine_self_is_one():
    v = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    idx, scores, matched = cosine_compare_arrays(v, [v], threshold=0.4)
    assert len(scores) == 1
    assert scores[0] == pytest.approx(1.0, abs=1e-4)
    assert bool(matched[0]) is True


def test_cosine_orthogonal_low():
    a = np.array([1.0, 0.0], dtype=np.float32)
    b = np.array([0.0, 1.0], dtype=np.float32)
    _, scores, matched = cosine_compare_arrays(a, [b], threshold=0.99)
    assert scores[0] == pytest.approx(0.0, abs=1e-5)
    assert bool(matched[0]) is False


def test_empty_targets():
    v = np.ones((4,), dtype=np.float32)
    idx, scores, matched = cosine_compare_arrays(v, [], threshold=0.4)
    assert idx.size == 0 and scores.size == 0 and matched.size == 0


def test_dim_mismatch_raises():
    a = np.ones((3,), dtype=np.float32)
    b = np.ones((4,), dtype=np.float32)
    with pytest.raises(ValueError):
        cosine_compare_arrays(a, [b], threshold=0.4)
