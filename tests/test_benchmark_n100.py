"""Benchmark xulosasining mantiqi.

O'lchovning o'zi qurilmani talab qiladi, lekin "nechta kamera sotish mumkin"
degan hisob sof mantiq — va aynan shu raqamga qarab va'da beriladi.
"""

from __future__ import annotations

# O'lchov yadrosi endi paket ichida: do'kon kompyuteriga faqat
# `chaqimchi_ai` ko'chiriladi, `scripts/` esa YO'Q — ya'ni skriptda
# qolgan yadroni mijozning mashinasida ishlatib bo'lmasdi.
from chaqimchi_ai.local.benchmark import (
    BUDGET_SAFETY,
    Samples,
    capacity_verdict,
    percentile,
)


def verdict(**overrides):
    defaults = dict(
        budget_target_fps=30.0,
        cameras=8,
        per_camera_fps=2.0,
        sample_fps=5.0,
        overhead_ms=3.0,
        cores=4,
    )
    defaults.update(overrides)
    return capacity_verdict(**defaults)


# ── Sig'im ───────────────────────────────────────────────────────────────


def test_enough_capacity_is_approved() -> None:
    result = verdict()

    assert result["needed_fps"] == 16.0
    assert result["supported_cameras"] == 15
    assert result["ok"] is True
    assert result["warnings"] == []


def test_not_enough_capacity_is_rejected() -> None:
    """Aynan shu holat uchun skript yozildi: taxminga suyanib 8 kamera
    sotilsa, qurilma ulgurmaydi va hodisa kech keladi."""
    result = verdict(budget_target_fps=10.0)

    assert result["supported_cameras"] == 5
    assert result["ok"] is False
    assert "ko'tarmaydi" in result["warnings"][0]


def test_thin_headroom_is_not_good_enough() -> None:
    """Zaxira kam bo'lsa issiq kunda byudjet tushadi va kafolat buziladi."""
    result = verdict(budget_target_fps=18.0)

    assert result["supported_cameras"] == 9  # yetadi ko'ringan
    assert result["headroom_percent"] < 25
    assert result["ok"] is False


def test_frame_overhead_is_counted_in_cores() -> None:
    """Filtr va tekshiruv har kadrda ishlaydi: 8 kamera × 5 FPS = 40 marta."""
    result = verdict(overhead_ms=60.0)

    assert result["capture_load_cores"] == 2.4
    assert any("yadro" in warning for warning in result["warnings"])


def test_decode_cost_is_added_to_the_frame_load() -> None:
    without = verdict(overhead_ms=5.0)
    with_decode = verdict(overhead_ms=5.0, decode_ms=15.0)

    assert with_decode["capture_load_cores"] > without["capture_load_cores"]


def test_the_floor_guarantee_is_checked_separately() -> None:
    """O'rtacha yetsa ham har kameraning kafolatlangan minimumi bor."""
    result = verdict(budget_target_fps=3.0, per_camera_fps=0.3)

    assert result["supported_cameras"] == 10  # o'rtacha bo'yicha "yetadi"
    assert any("minimum" in warning for warning in result["warnings"])
    assert result["ok"] is False


# ── O'lchov statistikasi ─────────────────────────────────────────────────


def test_budget_target_uses_the_runtime_formula() -> None:
    """Xulosa xom tezlikka emas, byudjet qabul qiladigan songa asoslanadi."""
    samples = Samples()
    for index in range(100):
        samples.add(0.040, float(index))  # har inferens 40 ms

    summary = samples.summary(elapsed=4.0, workers=1)

    assert summary["p95_ms"] == 40.0
    assert summary["budget_target_fps"] == round(BUDGET_SAFETY * 1 / 0.040, 2)


def test_slowdown_over_time_is_visible() -> None:
    """Qurilma qizib sekinlashsa qisqa o'lchov 8 soatlik smena uchun yolg'on."""
    samples = Samples()
    for index in range(90):
        samples.add(0.030 + index * 0.0005, float(index))  # asta sekinlashadi

    stability = samples.summary(elapsed=5.0, workers=1)["stability"]

    assert stability["enough_data"] is True
    assert stability["last_third_ms"] > stability["first_third_ms"]
    assert stability["slowdown_percent"] > 15


def test_a_short_run_admits_it_has_no_answer() -> None:
    samples = Samples()
    for index in range(10):
        samples.add(0.030, float(index))

    assert samples.summary(elapsed=1.0, workers=1)["stability"] == {"enough_data": False}


def test_empty_measurement_is_not_a_crash() -> None:
    assert Samples().summary(elapsed=1.0, workers=1) == {"samples": 0}
    assert percentile([], 0.95) == 0.0
    assert percentile([1.0, 2.0, 3.0], 0.5) == 2.0


# ── Kameraning HAQIQIY o'lchami ──────────────────────────────────────────
#
# Tahlil kadrni doim 640x360 ga keltiradi, ya'ni natijadagi `frame_size`
# kamerada nima turganini AYTMAYDI.  2026-08-29 da bu sezildi: kamerani
# 720p ga o'tkazgandan keyin o'zgarish ishlaganini tekshirishning yagona
# yo'li 24 soat kutib `face_crops.written` ga qarash edi.


class _FakeCapture:
    """`cv2.VideoCapture` o'rniga: berilgan o'lchamdagi kadr qaytaradi."""

    def __init__(self, width: int, height: int, frames: int = 3) -> None:
        self._width = width
        self._height = height
        self._left = frames

    def isOpened(self) -> bool:  # noqa: N802 — cv2 nomi
        return True

    def grab(self) -> bool:
        return self._left > 0

    def retrieve(self):
        import numpy as np

        if self._left <= 0:
            return False, None
        self._left -= 1
        return True, np.zeros((self._height, self._width, 3), dtype=np.uint8)

    def release(self) -> None:
        return None


def test_the_real_stream_size_comes_from_the_frame(monkeypatch) -> None:
    """O'lcham KADRDAN olinsin, `CAP_PROP` dan emas.

    RTSP'da property'lar ba'zi kameralarda nol yoki eskirgan qiymat
    qaytaradi; dekodlangan kadr esa har doim rost.
    """
    import cv2

    from chaqimchi_ai.local import benchmark

    monkeypatch.setattr(cv2, "VideoCapture", lambda *a, **k: _FakeCapture(1280, 720))

    result = benchmark.measure_decode("rtsp://kamera/sub", seconds=0.05)

    assert result["ok"] is True
    assert result["native_width"] == 1280
    assert result["native_height"] == 720


def test_a_360p_stream_is_reported_as_such(monkeypatch) -> None:
    """Kamera o'zgartirilmagan bo'lsa eski o'lcham ko'rinsin."""
    import cv2

    from chaqimchi_ai.local import benchmark

    monkeypatch.setattr(cv2, "VideoCapture", lambda *a, **k: _FakeCapture(640, 360))

    result = benchmark.measure_decode("rtsp://kamera/sub", seconds=0.05)

    assert (result["native_width"], result["native_height"]) == (640, 360)


def test_an_unreadable_stream_does_not_invent_a_size(monkeypatch) -> None:
    """Kadr o'qilmasa o'lcham TAXMIN QILINMASIN."""
    import cv2

    from chaqimchi_ai.local import benchmark

    monkeypatch.setattr(cv2, "VideoCapture", lambda *a, **k: _FakeCapture(640, 360, frames=0))

    result = benchmark.measure_decode("rtsp://kamera/sub", seconds=0.05)

    assert result["ok"] is False
    assert "native_width" not in result
