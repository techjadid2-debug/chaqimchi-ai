"""Kamera yopildimi, burildimi yoki bo'yaldimi.

Kadrlar sun'iy: to'qimali (harakatsiz, lekin tafsilotli) manzara me'yor
bo'ladi, keyin uni qoraytiramiz, xiralashtiramiz yoki butunlay boshqasiga
almashtiramiz.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from chaqimchi_ai.retail.tamper import BLURRED, DARK, MOVED, TamperDetector


def scene(seed: int = 1) -> np.ndarray:
    """Tafsilotli, o'zgarmaydigan manzara."""
    rng = np.random.default_rng(seed)
    frame = rng.integers(40, 220, size=(180, 320, 3), dtype=np.uint8)
    # Katta bloklar — 8×8 imzo aynan shularni ko'radi.
    frame[:90, :160] = 200
    frame[90:, 160:] = 60
    return frame


def moved_scene() -> np.ndarray:
    """Kamera burilgandan keyingi ko'rinish: bloklar boshqa joyda."""
    frame = scene(seed=2)
    frame[:90, :160] = 60
    frame[90:, 160:] = 200
    return frame


def warm(detector: TamperDetector, frame: np.ndarray, *, count: int = 31) -> None:
    for index in range(count):
        assert detector.update(frame, now=float(index) * 0.2) is None


def feed(detector: TamperDetector, frame: np.ndarray, *, start: float, stop: float, step: float = 0.2):
    alert = None
    moment = start
    while moment <= stop:
        result = detector.update(frame, now=moment)
        alert = alert or result
        moment += step
    return alert


# ── Buzilish turlari ─────────────────────────────────────────────────────


def test_a_covered_camera_is_reported(tmp_path=None) -> None:
    """O'g'ri birinchi navbatda kamerani yopadi."""
    detector = TamperDetector(min_duration_sec=10.0)
    warm(detector, scene())

    black = np.zeros((180, 320, 3), dtype=np.uint8)
    alert = feed(detector, black, start=10.0, stop=25.0)

    assert alert is not None
    assert alert.reason == DARK
    assert alert.score > 0.9


def test_a_sprayed_lens_is_reported() -> None:
    detector = TamperDetector(min_duration_sec=10.0)
    warm(detector, scene())

    blurred = cv2.GaussianBlur(scene(), (51, 51), 0)
    alert = feed(detector, blurred, start=10.0, stop=25.0)

    assert alert is not None
    assert alert.reason == BLURRED


def test_a_turned_camera_is_reported() -> None:
    detector = TamperDetector(min_duration_sec=10.0)
    warm(detector, scene())

    alert = feed(detector, moved_scene(), start=10.0, stop=25.0)

    assert alert is not None
    assert alert.reason == MOVED


# ── Shovqinga qarshi ─────────────────────────────────────────────────────


def test_someone_walking_past_the_lens_is_not_tampering(tmp_path=None) -> None:
    """Kamera oldidan o'tgan odam kadrni bir-ikki soniyaga to'sadi."""
    detector = TamperDetector(min_duration_sec=10.0)
    warm(detector, scene())

    black = np.zeros((180, 320, 3), dtype=np.uint8)
    assert feed(detector, black, start=10.0, stop=13.0) is None  # 3 soniya

    # Ko'rinish tiklandi — hisob noldan boshlanadi.
    assert feed(detector, scene(), start=13.2, stop=20.0) is None


def test_the_alert_fires_once_not_every_frame() -> None:
    detector = TamperDetector(min_duration_sec=10.0)
    warm(detector, scene())
    black = np.zeros((180, 320, 3), dtype=np.uint8)

    first = feed(detector, black, start=10.0, stop=25.0)
    second = feed(detector, black, start=25.2, stop=60.0)

    assert first is not None
    assert second is None
    assert detector.stats()["alerts"] == 1


def test_recovery_does_not_produce_a_second_alert() -> None:
    """Kamera ochilganda ko'rinish eski me'yorga qaytadi — hodisa yo'q.

    Shu sabab hodisa paytida me'yor **muzlatiladi**: yangi (yopilgan)
    ko'rinishni o'rganib qo'ysa, ochilish "o'zgarish" bo'lib chiqardi.
    """
    detector = TamperDetector(min_duration_sec=10.0)
    warm(detector, scene())
    black = np.zeros((180, 320, 3), dtype=np.uint8)
    assert feed(detector, black, start=10.0, stop=25.0) is not None

    assert feed(detector, scene(), start=25.2, stop=40.0) is None
    assert detector.alerted is False  # yana kuzatuvga tayyor


def test_a_permanently_turned_camera_is_accepted_and_rearmed() -> None:
    """Kamera ataylab burilgan bo'lsa detektor abadiy shu holatda qolmasin —
    aks holda keyingi haqiqiy buzilishni o'tkazib yuborardi."""
    detector = TamperDetector(min_duration_sec=10.0, accept_after_sec=100.0)
    warm(detector, scene())
    assert feed(detector, moved_scene(), start=10.0, stop=25.0) is not None

    feed(detector, moved_scene(), start=25.2, stop=200.0, step=5.0)
    assert detector.alerted is False

    # Yangi ko'rinish endi me'yor: uni yopish yana hodisa beradi.
    black = np.zeros((180, 320, 3), dtype=np.uint8)
    assert feed(detector, black, start=210.0, stop=240.0) is not None


def test_gradual_daylight_change_is_learned_not_reported() -> None:
    """Kun yorishishi buzilish emas — me'yor asta-sekin siljiydi."""
    detector = TamperDetector(min_duration_sec=10.0)
    base = scene()
    warm(detector, base)

    alert = None
    moment = 10.0
    for percent in range(100, 40, -1):  # yorug'lik asta pasayadi
        frame = (base.astype(np.float32) * (percent / 100.0)).astype(np.uint8)
        for _ in range(5):
            alert = alert or detector.update(frame, now=moment)
            moment += 0.2

    assert alert is None


def test_a_dark_scene_does_not_alert_on_being_dark() -> None:
    """Kechasi ombor doim qorong'i — mutlaq chegara noto'g'ri bo'lardi."""
    detector = TamperDetector(min_duration_sec=10.0)
    dark = np.full((180, 320, 3), 8, dtype=np.uint8)
    warm(detector, dark)

    assert feed(detector, np.zeros((180, 320, 3), dtype=np.uint8), start=10.0, stop=30.0) is None


def test_warmup_never_reports() -> None:
    """Tizim endi yoqilganda me'yor hali yo'q."""
    detector = TamperDetector(min_duration_sec=0.5, warmup_frames=30)
    frames = [scene(), np.zeros((180, 320, 3), dtype=np.uint8)] * 15

    assert all(detector.update(frame, now=index) is None for index, frame in enumerate(frames))


def test_invalid_configuration_is_rejected() -> None:
    with pytest.raises(ValueError):
        TamperDetector(min_duration_sec=0)
    with pytest.raises(ValueError):
        TamperDetector(min_duration_sec=10.0, accept_after_sec=5.0)
    with pytest.raises(ValueError):
        TamperDetector(adapt=0)
