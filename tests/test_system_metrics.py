"""Do'kon kompyuterining jonli ko'rsatkichlari.

Bulut bu maydonlarni anchadan beri qabul qiladi va Linux qutilari
ularni yuboradi — Windows yubormasdi.  Natijada do'kon kompyuteri
qizib ketsa yoki xotirasi tugab qolsa, buni na mijoz, na biz
bilardik: kompyuter shunchaki sekinlashardi va oxirida o'chib
qolardi.

Bu yerdagi eng muhim tekshiruv — `GetSystemTimes` tuzog'i.  Windows'da
`kernel` vaqti `idle` ni O'Z ICHIGA oladi; buni e'tiborsiz qoldirsa,
bo'sh turgan kompyuter ham 100% band ko'rinardi va har bir do'kon
"protsessor to'lgan" degan ogohlantirish olardi.
"""

from __future__ import annotations

import pytest

from chaqimchi_ai.local import cloud_config, system_metrics


@pytest.fixture(autouse=True)
def _fresh_sampler():
    system_metrics._last_cpu = None
    system_metrics._last_percent = None
    yield
    system_metrics._last_cpu = None
    system_metrics._last_percent = None


# ── Windows protsessor o'lchovi ──────────────────────────────────────


def _windows(monkeypatch, samples) -> None:
    """Windows muhitini taqlid qiladi va namunalarni navbat bilan beradi."""
    values = iter(samples)
    monkeypatch.setattr(system_metrics.os, "name", "nt")
    monkeypatch.setattr(system_metrics, "_windows_cpu_sample", lambda: next(values, None))


def test_the_first_reading_reports_nothing_instead_of_guessing(monkeypatch) -> None:
    """Solishtiradigan oldingi namuna yo'q — bir martalik o'qish
    yuklanishdan beri o'rtachani berardi va u kun bo'yi o'zgarmasdi."""
    _windows(monkeypatch, [(100, 1000)])

    assert system_metrics.cpu_percent() is None


def test_cpu_percent_comes_from_the_gap_between_two_readings(monkeypatch) -> None:
    # Ikkinchi namuna: jami +200, band +100 → 50%.
    _windows(monkeypatch, [(100, 1000), (200, 1200)])

    assert system_metrics.cpu_percent() is None
    assert system_metrics.cpu_percent() == pytest.approx(50.0)


def test_an_idle_machine_reads_near_zero_not_a_hundred(monkeypatch) -> None:
    """`GetSystemTimes` hujjatidagi tuzoq: `kernel` vaqti `idle` ni
    O'Z ICHIGA oladi.

    Bo'sh turgan kompyuterda `idle` deyarli butun `kernel` ni egallaydi.
    Band vaqt `kernel + user` deb olinsa, har bir tinch do'kon
    "protsessor to'lgan" degan ogohlantirish olardi.
    """
    # Bo'sh mashina: kernel 1000 (shundan idle 990), user 10.
    # To'g'ri hisob: band = 1000 + 10 - 990 = 20, jami = 1010.
    _windows(monkeypatch, [(0, 0), (20, 1010)])

    system_metrics.cpu_percent()

    assert system_metrics.cpu_percent() == pytest.approx(1.98, abs=0.01)


def test_two_calls_in_the_same_tick_keep_the_last_answer(monkeypatch) -> None:
    _windows(monkeypatch, [(100, 1000), (200, 1200), (200, 1200)])

    system_metrics.cpu_percent()
    first = system_metrics.cpu_percent()

    assert system_metrics.cpu_percent() == first


def test_a_failed_win32_call_hides_the_metric(monkeypatch) -> None:
    """Chaqiruv yiqilsa heartbeat baribir ketishi kerak."""

    def _boom() -> None:
        raise OSError("kernel32 topilmadi")

    monkeypatch.setattr(system_metrics.os, "name", "nt")
    monkeypatch.setattr(system_metrics, "_windows_cpu_sample", _boom)

    assert system_metrics.cpu_percent() is None


def test_windows_reports_no_temperature(monkeypatch) -> None:
    """WMI'ning termal sinfi ko'p platalarda to'ldirilmaydi, haqiqiy
    datchik esa administrator huquqi talab qiladi.  Taxmin qilgandan
    ko'ra hech narsa aytmagan halolroq."""
    monkeypatch.setattr(system_metrics.os, "name", "nt")

    assert system_metrics.temperature_c() is None


def test_the_disk_of_the_data_folder_is_measured(tmp_path) -> None:
    percent = system_metrics.disk_percent(str(tmp_path))

    assert percent is not None
    assert 0 <= percent <= 100


# ── Heartbeat'ga qo'shilishi ─────────────────────────────────────────


def test_a_value_that_cannot_be_measured_is_left_out_of_the_heartbeat(monkeypatch) -> None:
    """Yo'q kalit "o'lchanmagan" degani.  `null` yuborish "o'lchandi
    va nol chiqdi" bilan chalkashardi."""
    monkeypatch.setattr(system_metrics, "cpu_percent", lambda: 41.5)
    monkeypatch.setattr(system_metrics, "ram_percent", lambda: None)
    monkeypatch.setattr(system_metrics, "disk_percent", lambda: 22.0)
    monkeypatch.setattr(system_metrics, "temperature_c", lambda: None)
    monkeypatch.setattr(system_metrics, "uptime_sec", lambda: 3600.0)

    data = cloud_config._system_metrics({})

    assert data["cpu_percent"] == 41.5
    assert data["disk_percent"] == 22.0
    assert "ram_percent" not in data
    assert "temperature_c" not in data


def test_a_broken_reader_never_stops_the_heartbeat(monkeypatch) -> None:
    """Heartbeat qurilma tirikligini bildiradi — bitta o'lchov xatosi
    sabab u umuman ketmasa, bulut qurilmani "oflayn" deb belgilardi."""

    def _boom():
        raise RuntimeError("datchik javob bermadi")

    monkeypatch.setattr(system_metrics, "cpu_percent", _boom)
    monkeypatch.setattr(system_metrics, "ram_percent", lambda: 55.0)
    monkeypatch.setattr(system_metrics, "disk_percent", lambda: None)
    monkeypatch.setattr(system_metrics, "temperature_c", lambda: None)
    monkeypatch.setattr(system_metrics, "uptime_sec", lambda: None)

    data = cloud_config._system_metrics({})

    assert data == {"ram_percent": 55.0}


def test_the_chain_numbers_ride_along_when_the_chain_is_running(monkeypatch) -> None:
    """FPS va kechikish zanjirdan keladi.  Ular holat faylida bor edi,
    lekin `supervisor.status()` dan o'tmasdi — natijada admin
    paneldagi ustunlar Windows yo'lida hech qachon to'lmagan."""
    for name in ("cpu_percent", "ram_percent", "disk_percent", "temperature_c", "uptime_sec"):
        monkeypatch.setattr(system_metrics, name, lambda: None)

    data = cloud_config._system_metrics({"fps": 9.37, "inference_latency_ms": 84.2})

    assert data["fps"] == 9.4
    assert data["inference_latency_ms"] == 84.2


def test_a_stopped_chain_sends_no_fps(monkeypatch) -> None:
    for name in ("cpu_percent", "ram_percent", "disk_percent", "temperature_c", "uptime_sec"):
        monkeypatch.setattr(system_metrics, name, lambda: None)

    assert cloud_config._system_metrics({"fps": None}) == {}


def test_the_supervisor_passes_the_chain_numbers_through(tmp_path, monkeypatch) -> None:
    """Bu bo'shliq eng uzun yashiringan joy edi: zanjir raqamlarni
    yozardi, supervisor ularni tashlab yuborardi va heartbeat
    "o'lchov yo'q" deb hisoblardi."""
    from chaqimchi_ai.local.supervisor import RetailSupervisor

    monkeypatch.setenv("CHAQIMCHI_LOCAL_DIR", str(tmp_path))
    supervisor = RetailSupervisor()
    monkeypatch.setattr(
        supervisor,
        "_read_status_file",
        lambda: {"fps": 9.4, "inference_latency_ms": 84.0, "pressure": {"cpu": 0.42}},
    )

    status = supervisor.status()

    assert status["fps"] == 9.4
    assert status["inference_latency_ms"] == 84.0
    assert status["pressure"] == {"cpu": 0.42}
