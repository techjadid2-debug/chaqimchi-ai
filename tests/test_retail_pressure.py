"""Qurilma bosimi va uning byudjetga ulanishi.

Bu tekshiruvning sababi aniq regressiya: `budget.set_pressure()` yozilgan,
`RetailRunner` uni har housekeeping tikida chaqiradigan qilib qurilgan, lekin
`service.build_runner()` `pressure=` argumentini **umuman uzatmasdi**.
Natijada `budget.py` dagi `pressure >= 0.85` tarmog'i yozilganidan beri bir
marta ham ishlamagan: byudjet faqat latency bo'yicha sozlanardi va qurilma
qizib ketganini kech bilardi.

Hech qanday `/proc` yoki `/sys` talab qilinmaydi — uch manba ham
injektsiya qilinadi.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pytest

from chaqimchi_ai.retail.pressure import (
    CPU_CEILING,
    MEMORY_CEILING,
    TEMP_CEILING_C,
    TEMP_FLOOR_C,
    SystemPressure,
    read_memory_ratio,
    read_temperature_c,
)


def gauge(
    *,
    cpu: float = 0.0,
    memory: float = 0.0,
    temperature: Optional[float] = None,
) -> SystemPressure:
    return SystemPressure(
        load_reader=lambda: cpu,
        memory_reader=lambda: memory,
        temperature_reader=lambda: temperature,
    )


# ── Shkala ───────────────────────────────────────────────────────────────


def test_an_idle_device_stays_well_below_the_backoff_threshold() -> None:
    """Byudjet 0.85 dan boshlab tushiradi (`budget.py`).  Tinch do'kondagi
    qurilma unga yaqinlashmasligi kerak, aks holda byudjet bekorga
    pasayib turardi."""
    idle = gauge(cpu=0.05, memory=0.2, temperature=45.0).read()

    assert idle < 0.6
    # Umuman nol emas: bosim uzluksiz shkala, "band emas" degani "hech narsa
    # ishlatilmayapti" degani emas.
    assert idle > 0.0


def test_cpu_at_the_ceiling_is_full_pressure() -> None:
    """Talablar hujjatidagi "o'rtacha CPU <= 80%" shundan keladi."""
    assert gauge(cpu=CPU_CEILING).read() == pytest.approx(1.0)
    assert gauge(cpu=CPU_CEILING / 2).read() == pytest.approx(0.5)


def test_memory_ceiling_matches_the_65_gb_budget() -> None:
    """8 GB qurilmada 6.5 GB — 0.81."""
    assert MEMORY_CEILING == pytest.approx(6.5 / 8.0, abs=0.01)
    assert gauge(memory=MEMORY_CEILING).read() == pytest.approx(1.0)


def test_temperature_only_counts_above_the_floor() -> None:
    """Issiq, lekin normal qurilma byudjetni tushirmasin."""
    assert gauge(temperature=TEMP_FLOOR_C).read() == 0.0
    assert gauge(temperature=TEMP_FLOOR_C - 20).read() == 0.0
    middle = (TEMP_FLOOR_C + TEMP_CEILING_C) / 2
    assert gauge(temperature=middle).read() == pytest.approx(0.5)
    assert gauge(temperature=TEMP_CEILING_C).read() == pytest.approx(1.0)
    assert gauge(temperature=110.0).read() == pytest.approx(1.0)


def test_the_worst_signal_wins_not_the_average() -> None:
    """CPU bo'sh bo'lsa-yu qurilma qizib ketgan bo'lsa, o'rtacha buni
    yashirib qo'yardi — byudjet esa aynan shunda tushishi kerak."""
    hot = gauge(cpu=0.0, memory=0.0, temperature=TEMP_CEILING_C)

    assert hot.read() == pytest.approx(1.0)
    assert hot.stats() == {"cpu": 0.0, "memory": 0.0, "temperature": 1.0}


def test_stats_show_which_signal_caused_the_pressure() -> None:
    """Log'da "bosim 0.9" foydasiz; "xotira 0.9" nima qilishni aytadi."""
    meter = gauge(cpu=CPU_CEILING * 0.5, memory=MEMORY_CEILING * 0.9, temperature=60.0)

    meter.read()

    assert meter.stats()["memory"] > meter.stats()["cpu"]
    assert meter.stats()["temperature"] == 0.0


# ── Yiqilishga chidamlilik ───────────────────────────────────────────────


def test_a_broken_reader_does_not_stop_the_others() -> None:
    """macOS'da `/sys/class/thermal` yo'q, konteynerda `/proc/meminfo`
    boshqacha bo'lishi mumkin.  O'lchov yo'qligi sababli butun zanjirni
    to'xtatish noto'g'ri bo'lardi."""

    def explode():
        raise OSError("o'qilmadi")

    meter = SystemPressure(
        load_reader=explode,
        memory_reader=lambda: MEMORY_CEILING,
        temperature_reader=explode,
    )

    assert meter.read() == pytest.approx(1.0)
    assert meter.stats()["cpu"] == 0.0


def test_a_missing_thermal_zone_is_not_pressure() -> None:
    assert gauge(cpu=0.1, temperature=None).read() < 0.2


def test_ceilings_must_be_sane() -> None:
    with pytest.raises(ValueError):
        SystemPressure(cpu_ceiling=0)
    with pytest.raises(ValueError):
        SystemPressure(temp_floor_c=90.0, temp_ceiling_c=80.0)


# ── Haqiqiy manbalar ─────────────────────────────────────────────────────


def test_memory_is_read_from_meminfo(tmp_path: Path, monkeypatch) -> None:
    """`MemAvailable` ishlatiladi, `MemFree` emas: kesh va bufer texnik
    jihatdan band, lekin kerak bo'lganda bo'shatiladi.  `MemFree` bo'yicha
    o'lchash sog'lom Linux tizimini doim "xotira tugadi" deb ko'rsatardi."""
    meminfo = tmp_path / "meminfo"
    meminfo.write_text(
        "MemTotal:        8000000 kB\n"
        "MemFree:          200000 kB\n"  # ataylab past
        "MemAvailable:    4000000 kB\n"
        "Buffers:          100000 kB\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("chaqimchi_ai.retail.pressure.Path", lambda _p: meminfo)

    assert read_memory_ratio() == pytest.approx(0.5)


def test_missing_meminfo_reports_no_pressure(monkeypatch) -> None:
    monkeypatch.setattr(
        "chaqimchi_ai.retail.pressure.Path", lambda _p: Path("/mavjud/emas/meminfo")
    )
    assert read_memory_ratio() == 0.0


def test_the_hottest_zone_wins(tmp_path: Path, monkeypatch) -> None:
    for index, milli in enumerate((41000, 67000, 0, 9999999)):
        zone = tmp_path / f"thermal_zone{index}"
        zone.mkdir()
        (zone / "temp").write_text(str(milli), encoding="utf-8")
    monkeypatch.setattr("chaqimchi_ai.retail.pressure.THERMAL_ZONES", str(tmp_path))

    # 0 va 9999999 — ma'nosiz qiymatlar, ular hisobga olinmaydi.
    assert read_temperature_c() == pytest.approx(67.0)


def test_no_thermal_zones_returns_none(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("chaqimchi_ai.retail.pressure.THERMAL_ZONES", str(tmp_path))
    assert read_temperature_c() is None


# ── Zanjirga ulanish ─────────────────────────────────────────────────────


def test_the_budget_actually_receives_the_pressure() -> None:
    """`set_pressure()` chaqirilmasa `budget.py:130` o'lik kod bo'lib qoladi."""
    from chaqimchi_ai.retail.budget import InferenceBudget

    budget = InferenceBudget(target_fps=30.0, min_fps=1.0, max_fps=60.0)
    assert budget.stats()["pressure"] == 0.0

    budget.set_pressure(gauge(temperature=TEMP_CEILING_C).read())

    assert budget.stats()["pressure"] == 1.0


def test_high_pressure_lowers_the_target_before_latency_shows_it() -> None:
    """Butun modulning ma'nosi shu: harorat ko'tarilganda kechikish hali
    ko'rinmasligi mumkin, lekin byudjet allaqachon tushishi kerak."""
    from chaqimchi_ai.retail.budget import MIN_SAMPLES, InferenceBudget

    budget = InferenceBudget(target_fps=30.0, min_fps=1.0, max_fps=60.0)
    budget.set_pressure(0.9)
    # Kechikish "sog'lom": 20 ms, ya'ni ceiling = 50 FPS > target.
    for index in range(MIN_SAMPLES + 1):
        budget.observe(0.02, now=float(index))
    budget.observe(0.02, now=100.0)

    assert budget.target_fps < 30.0
