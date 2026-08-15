"""Kamera yopildimi, burildimi yoki bo'yaldimi.

Kadrlar sun'iy: to'qimali (harakatsiz, lekin tafsilotli) manzara me'yor
bo'ladi, keyin uni qoraytiramiz, xiralashtiramiz yoki butunlay boshqasiga
almashtiramiz.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from chaqimchi_ai.retail.tamper import (
    BLURRED,
    DARK,
    FREEZE,
    FROZEN,
    MOVED,
    TAMPER,
    TamperDetector,
)


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


#: Har kadrga qo'shiladigan sensor shovqini.
#
# Haqiqiy kamera hech qachon bayt-bayt bir xil kadr bermaydi — matritsa
# shovqini har kadrda bir-ikki birlikka o'zgaradi.  Testlar ham shuni
# taqlid qilishi kerak, aks holda ular "qotib qolgan oqim" ni tekshirib
# qo'yadi va buzilish mantig'i sinalmay qoladi.
_noise = np.random.default_rng(7)


def live(frame: np.ndarray) -> np.ndarray:
    """Kadrni sensor shovqini bilan — tirik kameradagidek."""
    jitter = _noise.integers(-1, 2, size=frame.shape, dtype=np.int16)
    return np.clip(frame.astype(np.int16) + jitter, 0, 255).astype(np.uint8)


def warm(detector: TamperDetector, frame: np.ndarray, *, count: int = 31) -> None:
    for index in range(count):
        assert detector.update(live(frame), now=float(index) * 0.2) is None


def feed(detector: TamperDetector, frame: np.ndarray, *, start: float, stop: float, step: float = 0.2):
    alert = None
    moment = start
    while moment <= stop:
        result = detector.update(live(frame), now=moment)
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


# ── Qotib qolgan oqim ────────────────────────────────────────────────────


def frozen_feed(detector: TamperDetector, frame: np.ndarray, *, start: float, stop: float, step: float = 0.2):
    """Aynan bitta kadr qayta-qayta — dekoder yoki NVR qotib qolgani."""
    alert = None
    moment = start
    while moment <= stop:
        result = detector.update(frame, now=moment)
        alert = alert or result
        moment += step
    return alert


def test_a_stalled_stream_is_reported() -> None:
    """Eng jimgina buziladigan holat.

    RTSP ochiq, `grab()` va `retrieve()` muvaffaqiyatli qaytadi, lekin kadr
    o'zgarmaydi. Harakat yo'q degani filtr uni to'sadi, buzilish imzosi ham
    o'zgarmaydi — tizim butunlay sog'lom ko'rinadi.
    """
    detector = TamperDetector(frozen_sec=20.0)
    still = scene()

    alert = frozen_feed(detector, still, start=0.0, stop=30.0)

    assert alert is not None
    assert alert.kind == FREEZE
    assert alert.reason == FROZEN
    assert alert.duration_sec >= 20.0
    assert detector.frozen is True
    assert detector.stats()["freezes"] == 1


def test_a_live_camera_is_never_called_frozen() -> None:
    """Sensor shovqini tufayli haqiqiy kadr hech qachon bayt-bayt bir xil
    bo'lmaydi — shu sabab bu tekshiruv chegara sozlashni talab qilmaydi."""
    detector = TamperDetector(frozen_sec=5.0)

    assert feed(detector, scene(), start=0.0, stop=120.0) is None
    assert detector.frozen is False


def test_the_freeze_alert_fires_once_not_every_frame() -> None:
    detector = TamperDetector(frozen_sec=10.0)
    still = scene()

    first = frozen_feed(detector, still, start=0.0, stop=20.0)
    second = frozen_feed(detector, still, start=20.2, stop=90.0)

    assert first is not None
    assert second is None
    assert detector.stats()["freezes"] == 1


def test_a_recovered_stream_can_freeze_again() -> None:
    """NVR bir marta qotib, tuzalib, keyin yana qotishi mumkin."""
    detector = TamperDetector(frozen_sec=10.0)
    still = scene()

    assert frozen_feed(detector, still, start=0.0, stop=20.0) is not None
    # Oqim tiklandi.
    assert feed(detector, still, start=20.2, stop=40.0) is None
    assert detector.frozen is False
    # Va yana qotdi.
    assert frozen_feed(detector, still, start=40.2, stop=60.0) is not None
    assert detector.stats()["freezes"] == 2


def test_a_stream_frozen_from_the_first_frame_is_still_caught() -> None:
    """NVR qayta yuklangan bo'lsa oqim boshidanoq qotgan bo'ladi —
    me'yorni "o'rganish" davri buni yashirib qo'ymasligi kerak."""
    detector = TamperDetector(frozen_sec=15.0, warmup_frames=200)

    assert frozen_feed(detector, scene(), start=0.0, stop=25.0) is not None


def test_freeze_and_tamper_are_reported_separately() -> None:
    """Ikkalasi bir xil yo'ldan chiqadi, lekin hodisa turi boshqa:
    qotgan oqimni "kamera yopilgan" deb aytish o'rnatuvchini noto'g'ri
    joyga yuboradi."""
    detector = TamperDetector(min_duration_sec=10.0, frozen_sec=1000.0)
    warm(detector, scene())

    alert = feed(detector, np.zeros((180, 320, 3), dtype=np.uint8), start=10.0, stop=25.0)

    assert alert is not None
    assert alert.kind == TAMPER
    assert alert.reason == DARK
