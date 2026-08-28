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
