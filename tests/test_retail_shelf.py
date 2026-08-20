"""Bo'sh javon nazorati — modelsiz usul.

Tayyor "empty shelf" modellarining aksariyati Ultralytics YOLO asosida
va u AGPL — ya'ni `buffalo_l` bilan bo'lgan tuzoqning aynan o'zi.  Shu
sabab avval arzon yo'l sinaladi: qat'iy kamera + qat'iy zonada
modelning keragi yo'q.

O'lchov — piksel farqi emas, **chekka zichligi**: to'la javon ko'p
chekka beradi (mahsulot chegaralari, yorliqlar), bo'shagan javon esa
tekis yuza.  Bu tanlovning butun ma'nosi yorug'likka chidamlilikda,
shuning uchun aynan shu quyida tekshiriladi.
"""

from __future__ import annotations

import cv2
import numpy as np

from chaqimchi_ai.retail.shelf import MIN_SAMPLES, ShelfWatcher, crop_polygon, edge_density

FULL_SIZE = (200, 300, 3)


def shelf_image(*, products: int, brightness: int = 0) -> np.ndarray:
    """Javon: har bir mahsulot — chegarasi bor to'rtburchak."""
    frame = np.full(FULL_SIZE, 120 + brightness, dtype=np.uint8)
    for index in range(products):
        left = 10 + index * 28
        cv2.rectangle(frame, (left, 40), (left + 22, 160), (200 + brightness // 2, 200, 200), -1)
        cv2.rectangle(frame, (left, 40), (left + 22, 160), (30, 30, 30), 2)
    return frame


def test_a_full_shelf_has_more_edges_than_an_empty_one() -> None:
    assert edge_density(shelf_image(products=9)) > edge_density(shelf_image(products=1)) * 3


def test_brightness_change_alone_does_not_look_like_an_empty_shelf() -> None:
    """Chiroq yoqilishi signal bermasin.

    Piksel farqi bilan o'lchansa bu aynan yolg'on signal berardi —
    kunduzdan kechqurunga o'tish butun kadrni o'zgartiradi.
    """
    bright = edge_density(shelf_image(products=9, brightness=60))
    normal = edge_density(shelf_image(products=9))

    assert abs(bright - normal) / max(normal, 1e-6) < 0.35


def _feed(watcher: ShelfWatcher, image, *, ticks: int, start: float = 0.0, step: float = 60.0):
    """Bir necha o'lchov — etalon o'rganilsin."""
    found = []
    now = start
    for _ in range(ticks):
        result = watcher.observe("javon", image, blocked=False, now=now)
        if result:
            found.append(result)
        now += step
    return found, now


def test_nothing_is_reported_before_the_baseline_is_learned() -> None:
    """Endi yoqilgan qurilma darrov "javon bo'sh" demasin."""
    watcher = ShelfWatcher(empty_ratio=0.5, empty_sec=1.0)
    found, _ = _feed(watcher, shelf_image(products=1), ticks=MIN_SAMPLES - 1)
    assert found == []


def test_an_emptying_shelf_is_reported_once_it_stays_empty() -> None:
    watcher = ShelfWatcher(empty_ratio=0.5, empty_sec=600.0)
    _found, now = _feed(watcher, shelf_image(products=9), ticks=MIN_SAMPLES + 5)

    # Javon bo'shadi — lekin darrov emas: 15 daqiqa turishi kerak.
    empty = shelf_image(products=1)
    assert watcher.observe("javon", empty, blocked=False, now=now) is None
    assert watcher.observe("javon", empty, blocked=False, now=now + 300) is None

    alert = watcher.observe("javon", empty, blocked=False, now=now + 700)
    assert alert is not None
    assert alert["zone"] == "javon"
    assert alert["ratio"] < 0.5

    # Latch: to'ldirilmaguncha qayta aytilmaydi.
    assert watcher.observe("javon", empty, blocked=False, now=now + 1400) is None


def test_a_customer_in_front_of_the_shelf_pauses_the_measurement() -> None:
    """Odam javonni yopib turgan daqiqalar "bo'sh turdi" deb sanalmasin."""
    watcher = ShelfWatcher(empty_ratio=0.5, empty_sec=600.0)
    _found, now = _feed(watcher, shelf_image(products=9), ticks=MIN_SAMPLES + 5)

    empty = shelf_image(products=1)
    watcher.observe("javon", empty, blocked=False, now=now)          # hisob boshlandi
    watcher.observe("javon", empty, blocked=True, now=now + 300)     # mijoz keldi — bekor
    # Hisob noldan: 700 soniya o'tgan bo'lsa ham chegara to'lmagan.
    assert watcher.observe("javon", empty, blocked=False, now=now + 700) is None
    assert watcher.observe("javon", empty, blocked=False, now=now + 1400) is not None


def test_a_refilled_shelf_rearms_the_alert() -> None:
    watcher = ShelfWatcher(empty_ratio=0.5, empty_sec=60.0)
    _found, now = _feed(watcher, shelf_image(products=9), ticks=MIN_SAMPLES + 5)
    empty = shelf_image(products=1)
    watcher.observe("javon", empty, blocked=False, now=now)
    assert watcher.observe("javon", empty, blocked=False, now=now + 100) is not None

    # To'ldirildi.
    watcher.observe("javon", shelf_image(products=9), blocked=False, now=now + 200)
    watcher.observe("javon", empty, blocked=False, now=now + 300)
    assert watcher.observe("javon", empty, blocked=False, now=now + 400) is not None


def test_a_tiny_zone_is_ignored_instead_of_producing_noise() -> None:
    frame = shelf_image(products=9)
    crop = crop_polygon(frame, [(0.0, 0.0), (0.02, 0.0), (0.02, 0.02), (0.0, 0.02)])
    assert crop.size == 0

    watcher = ShelfWatcher()
    assert watcher.observe("javon", crop, blocked=False, now=1.0) is None
