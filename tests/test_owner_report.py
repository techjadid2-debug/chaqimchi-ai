"""Do'kon egasi ko'radigan kunlik hisobot.

Xom hodisa sanog'i ("line_crossed: 680") kirish va chiqishning yig'indisi —
mijozga hech narsa aytmaydi.  Bu testlar aynan mijozning savollarini
tekshiradi: nechta kirdi, qaysi soat gavjum, navbat qancha bo'ldi.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

from chaqimchi_ai.event_models import EdgeEvent
from cloud.digest import build_digest
from cloud.event_store import EventStore

TASHKENT = ZoneInfo("Asia/Tashkent")
DAY = date(2026, 8, 13)


def moment(hour: int, minute: int = 0, *, day: date = DAY) -> str:
    local = datetime(day.year, day.month, day.day, hour, minute, tzinfo=TASHKENT)
    return local.astimezone(timezone.utc).isoformat()


def store_with(events: List[EdgeEvent], tmp_path: Path) -> EventStore:
    store = EventStore(sqlite_path=tmp_path / "events.db")
    store.ingest("site-1", "device-1", events)
    return store


def crossing(hour: int, direction: str, minute: int = 0, **kwargs) -> EdgeEvent:
    return EdgeEvent(
        event_type="line_crossed",
        camera_id="eshik-01",
        direction=direction,
        line="eshik",
        occurred_at=moment(hour, minute, **kwargs),
    )


# ── Kirish/chiqish ───────────────────────────────────────────────────────


def test_entries_and_exits_are_counted_separately(tmp_path: Path) -> None:
    """Eng muhim tuzatish: bitta "line_crossed" soni ikkalasini aralashtirardi."""
    store = store_with(
        [crossing(10, "in", index) for index in range(7)]
        + [crossing(19, "out", index) for index in range(4)],
        tmp_path,
    )

    report = store.retail_report("site-1", day=DAY)

    assert report["traffic"]["entered"] == 7
    assert report["traffic"]["exited"] == 4
    assert report["traffic"]["inside_estimate"] == 3


def test_the_busiest_hour_is_reported(tmp_path: Path) -> None:
    """Xodim jadvali shu raqamga qarab tuziladi."""
    store = store_with(
        [crossing(11, "in", index) for index in range(3)]
        + [crossing(18, "in", index) for index in range(9)]
        + [crossing(20, "in", index) for index in range(2)],
        tmp_path,
    )

    busiest = store.retail_report("site-1", day=DAY)["traffic"]["busiest_hour"]

    assert busiest == {"hour": 18, "entered": 9, "exited": 0}


def test_hourly_breakdown_covers_the_whole_day(tmp_path: Path) -> None:
    store = store_with([crossing(9, "in"), crossing(9, "in", 30)], tmp_path)

    hourly = store.retail_report("site-1", day=DAY)["traffic"]["hourly"]

    assert len(hourly) == 24
    assert hourly[9] == {"hour": 9, "entered": 2, "exited": 0}
    assert hourly[10]["entered"] == 0


def test_yesterday_is_compared(tmp_path: Path) -> None:
    """"Bugun 12 kishi kirdi" — bu ko'pmi yoki kammi?"""
    store = store_with(
        [crossing(12, "in", index) for index in range(12)]
        + [crossing(12, "in", index, day=date(2026, 8, 12)) for index in range(10)],
        tmp_path,
    )

    traffic = store.retail_report("site-1", day=DAY)["traffic"]

    assert traffic["entered_yesterday"] == 10
    assert traffic["change_percent"] == 20.0


def test_no_data_yesterday_shows_no_percentage(tmp_path: Path) -> None:
    """Noldan foiz hisoblab bo'lmaydi — panelda ko'rsatilmaydi."""
    store = store_with([crossing(12, "in")], tmp_path)

    assert store.retail_report("site-1", day=DAY)["traffic"]["change_percent"] is None


def test_a_quiet_day_has_no_busiest_hour(tmp_path: Path) -> None:
    store = store_with([], tmp_path)

    report = store.retail_report("site-1", day=DAY)

    assert report["traffic"]["busiest_hour"] is None
    assert report["traffic"]["entered"] == 0


# ── Navbat va dwell ──────────────────────────────────────────────────────


def queue_event(hour: int, minute: int, length: int) -> EdgeEvent:
    return EdgeEvent(
        event_type="queue_threshold_exceeded",
        camera_id="kassa-01",
        zone="kassa",
        queue_length=length,
        occurred_at=moment(hour, minute),
    )


def test_the_longest_queue_and_its_time_are_reported(tmp_path: Path) -> None:
    store = store_with(
        [queue_event(12, 10, 5), queue_event(18, 22, 9), queue_event(19, 5, 6)], tmp_path
    )

    queue = store.retail_report("site-1", day=DAY)["queue"]

    assert queue["alerts"] == 3
    assert queue["longest"] == 9
    assert queue["longest_at"] == "18:22"
    assert queue["average"] == 6.7


def test_dwell_is_grouped_by_zone_and_ranked(tmp_path: Path) -> None:
    """"Qaysi tokcha oldida ko'p turishadi" — javon joylashuvi uchun."""
    events = [
        EdgeEvent(
            event_type="dwell_exceeded",
            camera_id="zal-01",
            zone=zone,
            dwell_sec=seconds,
            occurred_at=moment(14),
        )
        for zone, seconds in [
            ("tokcha-3", 120.0),
            ("tokcha-3", 300.0),
            ("tokcha-3", 180.0),
            ("kassa", 90.0),
        ]
    ]
    store = store_with(events, tmp_path)

    dwell = store.retail_report("site-1", day=DAY)["dwell"]

    assert [item["zone"] for item in dwell] == ["tokcha-3", "kassa"]
    assert dwell[0] == {
        "zone": "tokcha-3",
        "count": 3,
        "average_sec": 200.0,
        "longest_sec": 300.0,
    }


def test_security_events_are_summarised(tmp_path: Path) -> None:
    store = store_with(
        [
            EdgeEvent(
                event_type="camera_tampered",
                camera_id="kassa-01",
                severity="critical",
                occurred_at=moment(2),
            ),
            EdgeEvent(
                event_type="after_hours_presence",
                camera_id="zal-01",
                severity="warning",
                occurred_at=moment(3),
            ),
            EdgeEvent(
                event_type="zone_entered",
                camera_id="ombor-01",
                zone="ombor",
                occurred_at=moment(4),
                metadata={"restricted": True},
            ),
        ],
        tmp_path,
    )

    security = store.retail_report("site-1", day=DAY)["security"]

    assert security == {
        "camera_tampered": 1,
        "after_hours_presence": 1,
        "restricted_zone": 1,
    }


# ── Chegaralar ───────────────────────────────────────────────────────────


def test_another_sites_events_are_not_mixed_in(tmp_path: Path) -> None:
    store = store_with([crossing(12, "in")], tmp_path)
    store.ingest("site-2", "device-2", [crossing(12, "in"), crossing(13, "in")])

    assert store.retail_report("site-1", day=DAY)["traffic"]["entered"] == 1


def test_events_outside_the_local_day_are_excluded(tmp_path: Path) -> None:
    """Kun chegarasi Toshkent vaqti bo'yicha, UTC bo'yicha emas.

    UTC'da hisoblansa do'konning kechki 22:00 dagi mijozlari **ertangi** kunga
    tushib qolardi (Toshkent UTC+5).
    """
    store = store_with(
        [
            crossing(23, "in", 30),  # bugungi kech — kirishi kerak
            crossing(0, "in", 30, day=date(2026, 8, 14)),  # ertangi tun
        ],
        tmp_path,
    )

    assert store.retail_report("site-1", day=DAY)["traffic"]["entered"] == 1


def test_crossings_without_direction_are_ignored(tmp_path: Path) -> None:
    """Eski edge versiyasi `direction` yubormasligi mumkin — hisob buzilmasin."""
    store = store_with(
        [
            EdgeEvent(event_type="line_crossed", camera_id="eshik-01", occurred_at=moment(12)),
            crossing(12, "in", 5),
        ],
        tmp_path,
    )

    assert store.retail_report("site-1", day=DAY)["traffic"]["entered"] == 1


# ── Telegram xabari ──────────────────────────────────────────────────────


def digest_for(tmp_path: Path, events: List[EdgeEvent]) -> str:
    store = store_with(events, tmp_path)
    stats: Dict[str, Any] = store.stats("site-1", day=DAY)
    return build_digest("Oq Saroy", DAY.isoformat(), stats, store.retail_report("site-1", day=DAY))


def test_the_daily_message_answers_the_owners_questions(tmp_path: Path) -> None:
    text = digest_for(
        tmp_path,
        [crossing(18, "in", index) for index in range(9)] + [queue_event(18, 22, 7)],
    )

    assert "Kirdi: 9 kishi" in text
    assert "Gavjum soat: 18:00" in text
    assert "eng uzuni 7 kishi (18:22)" in text


def test_a_calm_day_message_stays_short(tmp_path: Path) -> None:
    """Har kuni "0 ta buzilish" deb yozish xabarni o'qilmaydigan qiladi."""
    text = digest_for(tmp_path, [crossing(12, "in")])

    assert "⚠️" not in text
    assert "Navbat" not in text
    assert len(text.splitlines()) <= 4


def test_security_problems_are_pushed_into_the_message(tmp_path: Path) -> None:
    text = digest_for(
        tmp_path,
        [
            crossing(12, "in"),
            EdgeEvent(
                event_type="camera_tampered",
                camera_id="kassa-01",
                severity="critical",
                occurred_at=moment(2),
            ),
        ],
    )

    assert "⚠️ 1 marta kamera buzilgan" in text
