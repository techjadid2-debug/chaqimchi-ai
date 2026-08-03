import numpy as np

from chaqimchi_ai.image_util import resize_bgr_max_side


def test_resize_noop_when_small():
    img = np.zeros((100, 80, 3), dtype=np.uint8)
    out = resize_bgr_max_side(img, max_side=640)
    assert out.shape == img.shape


def test_resize_scales_long_side():
    img = np.zeros((1000, 500, 3), dtype=np.uint8)
    out = resize_bgr_max_side(img, max_side=500)
    h, w = out.shape[:2]
    assert max(h, w) == 500
    assert abs(h / w - 1000 / 500) < 0.02
