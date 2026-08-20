"""Windows soak yig'uvchisi rost hisobot bersin.

Nega alohida skript kerak bo'ldi: `soak_n100.py` restartlarni
`systemctl show ... NRestarts` dan oladi va Windows'da `FileNotFoundError`
ni yutib **0** qaytaradi.  Ya'ni 72 soatlik sinov hisobotida "kutilmagan
restart 0" yozilardi — o'lchangani uchun emas, o'lchanmagani uchun.  Bu
yerdagi testlar aynan shu yolg'onning qaytib kelishini to'sadi.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

import pytest

from scripts.soak_windows import read_counters, read_outbox, summarize


def _samples(*counters: Dict[str, int], cameras: int = 4) -> List[Dict[str, Any]]:
    return [
        {"cameras_active": cameras, "analyzed": 100, "errors": 0, "counters": item, "outbox": {}}
        for item in counters
    ]


def test_a_crash_during_the_run_is_counted() -> None:
    """Zanjir sinov o'rtasida yiqilsa — qabul mezoni buziladi."""
    report = summarize(
        _samples({"chain_crashes": 0, "panel_boots": 1}, {"chain_crashes": 2, "panel_boots": 1}),
        duration_hours=72.0,
        cameras_expected=4,
        planned_reboots=0,
    )

    assert report["unexpected_restarts"] == 2


def test_a_panel_restart_also_counts() -> None:
    """Kompyuter kutilmaganda qayta yonsa ham bu barqarorlik nuqsoni."""
    report = summarize(
        _samples({"chain_crashes": 0, "panel_boots": 3}, {"chain_crashes": 0, "panel_boots": 4}),
        duration_hours=72.0,
        cameras_expected=4,
        planned_reboots=0,
    )

    assert report["unexpected_restarts"] == 1


def test_a_deliberate_reboot_is_not_a_defect() -> None:
    """Avtostartni sinash uchun kompyuterni ataylab qayta yoqamiz —
    bu nosozlik emas va uni mezonga qo'shish sinovni yolg'on yiqitardi."""
    report = summarize(
        _samples({"chain_crashes": 0, "panel_boots": 3}, {"chain_crashes": 0, "panel_boots": 4}),
        duration_hours=72.0,
        cameras_expected=4,
        planned_reboots=1,
    )

    assert report["unexpected_restarts"] == 0
    assert report["detail"]["planned_reboots"] == 1


def test_camera_uptime_uses_the_expected_count() -> None:
    samples = _samples({"chain_crashes": 0}, {"chain_crashes": 0}, {"chain_crashes": 0})
    samples[1]["cameras_active"] = 3  # bitta kamera tushib qoldi

    report = summarize(samples, duration_hours=72.0, cameras_expected=4, planned_reboots=0)

    assert report["cameras_min_active"] == 3
    assert report["camera_uptime_percent"] == pytest.approx(66.667, abs=0.01)


def test_a_smaller_shop_is_measured_against_its_own_camera_count() -> None:
    """Kompyuter 4 kamerani ko'tarmasa, sinov 2 kamera bilan o'tkaziladi —
    va'da ham shunga moslanadi."""
    samples = _samples({"chain_crashes": 0}, cameras=2)

    report = summarize(samples, duration_hours=72.0, cameras_expected=2, planned_reboots=0)

    assert report["camera_uptime_percent"] == 100.0


def test_lost_events_are_reported_even_if_the_queue_is_now_empty() -> None:
    """`soak_n100.py` faqat oxirgi namunadagi navbatni olardi.

    Hodisa yo'lda tashlangan bo'lsa (`dead_letter`) navbat bo'sh
    ko'rinardi va "yo'qolgan kritik hodisa 0" degan yolg'on chiqardi.
    """
    samples = _samples({"chain_crashes": 0})
    samples[-1]["outbox"] = {"pending": 0, "critical": 0, "poisoned": 3}

    report = summarize(samples, duration_hours=72.0, cameras_expected=4, planned_reboots=0)

    assert report["undelivered_critical_events"] == 3


def test_temperature_is_reported_as_not_measured() -> None:
    """Windows'da harorat manbasi yo'q.  `null` — "o'lchanmadi", "sovuq"
    emas; qabul profili buni rad etish sababi qilmasligi kerak."""
    report = summarize(
        _samples({"chain_crashes": 0}), duration_hours=72.0, cameras_expected=4, planned_reboots=0
    )

    assert report["max_temperature_c"] is None
    assert report["platform"] == "windows"


def test_an_empty_run_does_not_crash() -> None:
    report = summarize([], duration_hours=0.0, cameras_expected=4, planned_reboots=0)

    assert report["samples"] == 0
    assert report["camera_uptime_percent"] == 0.0


# ── Manbalarni o'qish ───────────────────────────────────────────────────


def test_counters_are_read_from_the_data_dir(tmp_path: Path) -> None:
    (tmp_path / "counters.json").write_text(
        json.dumps({"chain_crashes": 2, "panel_boots": 5, "since": "2026-08-20T00:00:00+00:00"}),
        encoding="utf-8",
    )

    data = read_counters(tmp_path)

    assert data["chain_crashes"] == 2
    assert "since" not in data, "matn maydonlari sonlar orasiga tushmasin"


def test_a_fresh_computer_has_no_counters(tmp_path: Path) -> None:
    assert read_counters(tmp_path) == {}
    assert read_outbox(tmp_path) == {"pending": 0, "critical": 0, "poisoned": 0}


def test_the_queue_is_read_without_locking_it(tmp_path: Path) -> None:
    """Navbatni retail zanjiri yozadi — yig'uvchi uni qulflab qo'ymasin."""
    db = tmp_path / "data" / "outbox.db"
    db.parent.mkdir(parents=True)
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE outbox (event_id TEXT PRIMARY KEY, payload TEXT, "
        "created_at TEXT, priority INTEGER DEFAULT 10, sent_at TEXT)"
    )
    conn.execute("CREATE TABLE dead_letter (event_id TEXT PRIMARY KEY)")
    conn.executemany(
        "INSERT INTO outbox (event_id, payload, created_at, priority, sent_at) VALUES (?,?,?,?,?)",
        [
            ("a", "{}", "2026-08-20T00:00:00Z", 30, None),  # kritik, navbatda
            ("b", "{}", "2026-08-20T00:00:00Z", 10, None),  # oddiy, navbatda
            ("c", "{}", "2026-08-20T00:00:00Z", 30, "2026-08-20T00:01:00Z"),  # yuborilgan
        ],
    )
    conn.execute("INSERT INTO dead_letter (event_id) VALUES ('d')")
    conn.commit()
    conn.close()

    stats = read_outbox(tmp_path)

    assert stats["pending"] == 2, "yuborilgani navbat emas"
    assert stats["critical"] == 1
    assert stats["poisoned"] == 1
