"""Kamera tungi rejimi (`enes/retail/nightmode.py`).

Kadrlar sun'iy: rangli manzara «kunduz», uning kulrang nusxasi «IR»,
deyarli qora kadr «ko'r».  Almashuv gisterezis bilan — bir lahzalik
rangsiz kadr rejimni o'zgartirmasin.
"""

from __future__ import annotations

import cv2
import numpy as np

from enes.retail.nightmode import (
    DARK,
    DAY,
    IR,
    NightModeProbe,
    classify,
    enhance_for_detection,
    measure,
)


def colour_scene(seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    frame = rng.integers(40, 220, size=(180, 320, 3), dtype=np.uint8)
    frame[:, :, 0] = 200  # ko'k ustun — to'yinganlik yuqori
    frame[:, :, 2] = 40
    return frame


def ir_scene() -> np.ndarray:
    gray = cv2.cvtColor(colour_scene(), cv2.COLOR_BGR2GRAY)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


def dark_scene() -> np.ndarray:
    return np.full((180, 320, 3), 6, dtype=np.uint8)


def feed(probe: NightModeProbe, frame: np.ndarray, *, start: float, stop: float, step: float = 0.2):
    changes = []
    moment = start
    while moment < stop:
        change = probe.update(frame, now=moment)
        if change:
            changes.append(change)
        moment += step
    return changes


def test_colour_grey_and_black_frames_are_classified() -> None:
    assert classify(*measure(colour_scene())) == DAY
    assert classify(*measure(ir_scene())) == IR
    assert classify(*measure(dark_scene())) == DARK


def test_the_first_measurement_is_the_baseline_not_a_switch() -> None:
    """Tizim kechasi yoqilsa IR — me'yor, «o'tish» emas."""
    probe = NightModeProbe(sample_every=1)
    assert probe.update(ir_scene(), now=0.0) is None
    assert probe.mode == IR


def test_switching_to_ir_is_reported_once_after_the_hold() -> None:
    probe = NightModeProbe(hold_sec=30.0, sample_every=1)
    assert feed(probe, colour_scene(), start=0.0, stop=5.0) == []
    changes = feed(probe, ir_scene(), start=5.0, stop=60.0)
    assert changes == [(DAY, IR)]
    assert probe.mode == IR and probe.changes == 1


def test_a_brief_grey_frame_does_not_flip_the_mode() -> None:
    """Oq devor, chaqnash — 30 soniyadan qisqa rangsizlik e'tiborga olinmaydi."""
    probe = NightModeProbe(hold_sec=30.0, sample_every=1)
    feed(probe, colour_scene(), start=0.0, stop=5.0)
    assert feed(probe, ir_scene(), start=5.0, stop=15.0) == []
    assert feed(probe, colour_scene(), start=15.0, stop=20.0) == []
    assert probe.mode == DAY


def test_enhancement_brightens_a_dark_frame_but_keeps_shape() -> None:
    dark = np.full((180, 320, 3), 30, dtype=np.uint8)
    dark[60:120, 100:220] = 55  # siluet
    lit = enhance_for_detection(dark)
    assert lit.shape == dark.shape and lit.dtype == np.uint8
    assert lit.mean() > dark.mean() * 1.5
    assert enhance_for_detection(dark[:, :, 0]).ndim == 2, "kulrang kadr o'zgarmaydi"
