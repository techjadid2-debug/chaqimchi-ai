import numpy as np

from chaqimchi_ai.roi import RoiConfig, apply_roi


def test_apply_roi_crops_center() -> None:
    img = np.zeros((100, 200, 3), dtype=np.uint8)
    img[25:75, 50:150] = 255
    roi = RoiConfig(enabled=True, normalized=True, x1=0.25, y1=0.25, x2=0.75, y2=0.75)
    out = apply_roi(img, roi)
    assert out.shape[0] == 50
    assert out.shape[1] == 100
