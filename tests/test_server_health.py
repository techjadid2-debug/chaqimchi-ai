"""Bulut serverining o'z holati: o'lchash va ogohlantirish.

Bu yerdagi asosiy qoida — **yolg'on raqam yozmaslik**.  O'lchab
bo'lmagan ko'rsatkich javobga umuman kirmasligi kerak: panelda "0%"
turgan bo'lsa, uni hech kim tekshirmaydi va server o'lgan payt ham
hammasi joyida ko'rinardi.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cloud import alerts, server_health


@pytest.fixture(autouse=True)
def _fresh_sampler():
    """Har test toza holatdan boshlansin — CPU delta modul holatida."""
    server_health._last_sample = None
    server_health._last_percent = None
    yield
    server_health._last_sample = None
    server_health._last_percent = None


# ── /proc/stat va CPU ────────────────────────────────────────────────

STAT_ONE = "cpu  100 0 50 800 50 0 0 0 0 0\ncpu0 100 0 50 800 50 0 0 0 0 0\n"
#: Ikkinchi namuna: jami +200, shundan bo'sh +100 → bandlik 50%.
STAT_TWO = "cpu  150 0 75 850 75 0 0 0 0 0\ncpu0 150 0 75 850 75 0 0 0 0 0\n"


def test_the_first_reading_reports_nothing_instead_of_guessing() -> None:
    """Solishtiradigan oldingi namuna yo'q.

    Bir martalik o'qish yuklanishdan beri o'rtachani berardi — u
    haftalab o'zgarmaydi va "hozir nima bo'lyapti" degan savolga
    umuman javob bermaydi.
    """
    assert server_health._parse_proc_stat(STAT_ONE) is not None
    server_health._last_sample = None

    # Birinchi chaqiruv namunani eslab qoladi, lekin foiz bermaydi.
    assert server_health._parse_proc_stat(STAT_ONE) == (150, 1000)


def test_cpu_percent_comes_from_the_gap_between_two_readings(monkeypatch) -> None:
    texts = iter([STAT_ONE, STAT_TWO])
    monkeypatch.setattr(server_health, "_read", lambda path: next(texts, None))

    assert server_health.cpu_percent() is None  # birinchi namuna
    assert server_health.cpu_percent() == pytest.approx(50.0)


def test_idle_and_iowait_both_count_as_free() -> None:
    """`iowait` ni band deb sanash diskka qaraydigan serverda CPU'ni
    doim 90% ko'rsatardi — holbuki protsessor ish bajarmayapti."""
    busy, total = server_health._parse_proc_stat("cpu 10 0 10 60 20 0 0 0 0 0")

    assert total == 100
    assert busy == 20  # 100 - (idle 60 + iowait 20)


def test_two_calls_in_the_same_tick_keep_the_last_answer(monkeypatch) -> None:
    """Nolga bo'linish o'rniga oxirgi ma'lum qiymat."""
    texts = iter([STAT_ONE, STAT_TWO, STAT_TWO])
    monkeypatch.setattr(server_health, "_read", lambda path: next(texts, None))

    server_health.cpu_percent()
    first = server_health.cpu_percent()

    assert server_health.cpu_percent() == first


def test_a_broken_stat_line_hides_the_metric(monkeypatch) -> None:
    monkeypatch.setattr(server_health, "_read", lambda path: "cpu abc def\n")

    assert server_health.cpu_percent() is None


# ── /proc/meminfo ────────────────────────────────────────────────────


def test_memory_uses_available_not_free() -> None:
    """Linux bo'sh xotirani keshga beradi va u `MemFree` da
    ko'rinmaydi.  `MemFree` bilan hisoblansa har bir sog'lom server
    "xotira tugadi" deb ogohlantirardi."""
    text = "MemTotal:  1000 kB\nMemFree:  50 kB\nMemAvailable:  400 kB\n"

    assert server_health._parse_meminfo(text) == pytest.approx(60.0)


def test_memory_without_the_available_line_reports_nothing() -> None:
    assert server_health._parse_meminfo("MemTotal: 1000 kB\n") is None


# ── snapshot ─────────────────────────────────────────────────────────


def test_a_metric_that_cannot_be_measured_is_left_out_entirely(monkeypatch) -> None:
    """Nol yozish eng yomon variant: panelda ishonchli ko'ringan,
    lekin yolg'on raqam turadi."""
    monkeypatch.setattr(server_health, "cpu_percent", lambda: None)
    monkeypatch.setattr(server_health, "ram_percent", lambda: None)
    monkeypatch.setattr(server_health, "temperature_c", lambda: None)
    monkeypatch.setattr(server_health, "load_1m", lambda: None)
    monkeypatch.setattr(server_health, "disk_percent", lambda: 41.0)
    monkeypatch.setattr(server_health, "free_disk_gb", lambda: 12.5)

    data = server_health.snapshot()

    assert data == {"disk_percent": 41.0, "free_disk_gb": 12.5}
    assert "cpu_percent" not in data
    assert "temperature_c" not in data


def test_load_always_comes_with_the_core_count(monkeypatch) -> None:
    """Yuklama yolg'iz o'zi hech narsa aytmaydi: 4.0 — to'rt yadroda
    to'liq band, o'n oltida bemalol."""
    monkeypatch.setattr(server_health, "cpu_percent", lambda: None)
    monkeypatch.setattr(server_health, "ram_percent", lambda: None)
    monkeypatch.setattr(server_health, "temperature_c", lambda: None)
    monkeypatch.setattr(server_health, "disk_percent", lambda: None)
    monkeypatch.setattr(server_health, "load_1m", lambda: (2.5, 8))

    data = server_health.snapshot()

    assert data["load_1m"] == 2.5
    assert data["cores"] == 8


def test_a_virtual_server_without_a_thermal_zone_reports_no_temperature(
    tmp_path: Path, monkeypatch
) -> None:
    """Contabo KVM'da termal zona yo'q — mehmon mashina hostning
    haroratini bilmaydi va uni taxmin qilmasligi kerak."""
    monkeypatch.setattr(server_health, "THERMAL_ROOT", tmp_path / "yoq")

    assert server_health.temperature_c() is None


def test_the_hottest_zone_wins(tmp_path: Path, monkeypatch) -> None:
    for index, milli in enumerate((42_000, 71_500, 38_000)):
        zone = tmp_path / f"thermal_zone{index}"
        zone.mkdir()
        (zone / "temp").write_text(str(milli), encoding="utf-8")
    monkeypatch.setattr(server_health, "THERMAL_ROOT", tmp_path)

    assert server_health.temperature_c() == pytest.approx(71.5)


def test_the_panel_and_the_alert_watch_the_same_disk() -> None:
    """Ikki joyda ikki xil yo'l kuzatilsa, panel «joyida» deb turgan
    payt alert «to'ldi» derdi va qaysi biriga ishonish noma'lum edi."""
    assert server_health.disk_percent() == alerts.disk_usage_percent(alerts.disk_watch_path())


# ── Ogohlantirish ────────────────────────────────────────────────────


def test_a_healthy_server_says_nothing() -> None:
    found, _ = alerts.plan_server_health_alert({"cpu_percent": 12.0, "ram_percent": 40.0}, {})

    assert found == []


def test_memory_running_out_reaches_telegram() -> None:
    found, _ = alerts.plan_server_health_alert({"ram_percent": 93.0}, {})

    assert len(found) == 1
    assert found[0].kind == "server"
    assert found[0].site_id == alerts.SERVER_SITE_ID
    assert "xotira" in found[0].text


def test_the_same_problem_is_reported_only_once() -> None:
    """Har 15 daqiqada takrorlansa xabar o'qilmay qoladi."""
    found, _ = alerts.plan_server_health_alert(
        {"ram_percent": 93.0}, {alerts.SERVER_SITE_ID: "ram"}
    )

    assert found == []


def test_a_value_wobbling_around_the_line_does_not_spam() -> None:
    """92,1 → 91,8 → 92,3 har safar «muammo/tuzaldi» juftini
    yubormasin: pastki chegara (85) gacha holat saqlanadi."""
    found, _ = alerts.plan_server_health_alert(
        {"ram_percent": 88.0}, {alerts.SERVER_SITE_ID: "ram"}
    )

    assert found == []


def test_recovery_is_announced_once_the_value_really_drops() -> None:
    found, _ = alerts.plan_server_health_alert(
        {"ram_percent": 60.0}, {alerts.SERVER_SITE_ID: "ram"}
    )

    assert len(found) == 1
    assert found[0].remember is None
    assert "qaytdi" in found[0].text


def test_a_metric_the_server_cannot_measure_never_fires() -> None:
    """Virtual serverda harorat yo'q — u hech qachon ogohlantirmasin."""
    found, _ = alerts.plan_server_health_alert({"cpu_percent": 10.0}, {})

    assert found == []


def test_the_worst_problem_is_the_one_reported() -> None:
    """Bitta xabar — bitta muammo.  Uchtasi bir vaqtda bo'lsa uchta
    xabar chatni ko'mib tashlaydi va eng muhimi ko'rinmay ketadi."""
    found, _ = alerts.plan_server_health_alert(
        {"temperature_c": 88.0, "ram_percent": 95.0, "cpu_percent": 99.0}, {}
    )

    assert len(found) == 1
    assert found[0].state == "temp"
