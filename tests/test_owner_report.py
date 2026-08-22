"""Do'kon egasi ko'radigan kunlik hisobot.

Xom hodisa sanog'i ("line_crossed: 680") kirish va chiqishning yig'indisi —
mijozga hech narsa aytmaydi.  Bu testlar aynan mijozning savollarini
tekshiradi: nechta kirdi, qaysi soat gavjum, navbat qancha bo'ldi.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
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


def crossing(
    hour: int, direction: str, minute: int = 0, *, track_id: int | None = None, **kwargs
) -> EdgeEvent:
    return EdgeEvent(
        event_type="line_crossed",
        camera_id="eshik-01",
        direction=direction,
        line="eshik",
        track_id=track_id,
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
    """ "Bugun 12 kishi kirdi" — bu ko'pmi yoki kammi?"""
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
    """ "Qaysi tokcha oldida ko'p turishadi" — javon joylashuvi uchun."""
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
        "loitering": 0,
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

    assert "Kirdi: <b>9</b> kishi" in text
    assert "Gavjum soat: 18:00" in text
    assert "eng uzuni 7 kishi (18:22)" in text


def test_a_calm_day_message_stays_short(tmp_path: Path) -> None:
    """Har kuni "0 ta buzilish" deb yozish xabarni o'qilmaydigan qiladi."""
    text = digest_for(tmp_path, [crossing(12, "in")])

    assert "⚠️" not in text
    assert "Navbat" not in text
    assert len(text.splitlines()) <= 6


# ── Ochilish nazorati ────────────────────────────────────────────────────


def digest_with_opening(tmp_path: Path, events, open_from: str) -> str:
    store = store_with(events, tmp_path)
    return build_digest(
        "Oq Saroy",
        DAY.isoformat(),
        store.stats("site-1", day=DAY),
        store.retail_report("site-1", day=DAY),
        open_from=open_from,
        first_movement=store.first_movement_time("site-1", day=DAY),
    )


def test_on_time_opening_is_reported_without_warning(tmp_path: Path) -> None:
    text = digest_with_opening(tmp_path, [crossing(9, "in", 5)], "09:00")

    assert "Ochilish: 09:05 (jadval: 09:00)" in text
    assert "kechikish" not in text


def test_late_opening_gets_a_warning(tmp_path: Path) -> None:
    """20 daqiqadan ortiq kechikish — ega buni bilishi kerak.

    Real-vaqt alert ataylab yo'q (shovqin qoidasi): kunlik hisobotdagi
    bitta satr yetarli.
    """
    text = digest_with_opening(tmp_path, [crossing(9, "in", 45)], "09:00")

    assert "Ochilish: 09:45 (jadval: 09:00) ⚠️ kechikish" in text


def test_no_schedule_means_no_opening_line(tmp_path: Path) -> None:
    text = digest_for(tmp_path, [crossing(9, "in", 45)])

    assert "Ochilish" not in text


def test_first_movement_ignores_camera_health_events(tmp_path: Path) -> None:
    """Tungi camera_offline "do'kon ochildi" degani emas."""
    store = store_with(
        [
            EdgeEvent(
                event_type="camera_offline",
                camera_id="eshik-01",
                severity="critical",
                occurred_at=moment(3),
            ),
            crossing(9, "in", 10),
        ],
        tmp_path,
    )

    first = store.first_movement_time("site-1", day=DAY)

    from cloud import botfmt

    assert botfmt.clock(first) == "09:10"


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


# ── Kunlar bo'yicha trend ────────────────────────────────────────────────


def entries(day: date, count: int, hour: int = 12) -> List[EdgeEvent]:
    return [
        EdgeEvent(
            event_type="line_crossed",
            camera_id="eshik-01",
            direction="in",
            occurred_at=moment(hour, index % 60, day=day),
        )
        for index in range(count)
    ]


def test_the_week_shows_which_day_is_strongest(tmp_path: Path) -> None:
    """Dam olish kunlari savdo ikki barobar bo'lsa xodim jadvali shunga
    qarab tuziladi."""
    events: List[EdgeEvent] = []
    for offset, count in enumerate([210, 190, 205, 230, 310, 420, 380]):
        events += entries(date(2026, 8, 7) + timedelta(days=offset), count)
    store = store_with(events, tmp_path)

    trend = store.traffic_trend("site-1", days=7, until=date(2026, 8, 13))

    assert trend["total"] == 1945
    assert trend["busiest_day"] == {"date": "2026-08-12", "weekday": "Chorshanba", "entered": 420}
    assert trend["quietest_day"]["entered"] == 190
    assert trend["average"] == 277.9


def test_every_day_appears_even_when_the_shop_was_closed(tmp_path: Path) -> None:
    """Bo'sh kun grafikda bo'sh ustun bo'lib turishi kerak — yo'qolib
    ketsa hafta qisqarib ko'rinardi."""
    store = store_with(entries(date(2026, 8, 13), 5), tmp_path)

    trend = store.traffic_trend("site-1", days=7, until=date(2026, 8, 13))

    assert len(trend["daily"]) == 7
    assert [item["entered"] for item in trend["daily"]] == [0, 0, 0, 0, 0, 0, 5]
    assert trend["daily"][-1]["weekday"] == "Payshanba"


def test_the_period_is_compared_with_the_previous_one(tmp_path: Path) -> None:
    """7 kun ↔ oldingi 7 kun.  Aks holda o'sish bayram kuni tufayli ekanini
    bilib bo'lmasdi."""
    events = entries(date(2026, 8, 13), 120) + entries(date(2026, 8, 6), 100)
    store = store_with(events, tmp_path)

    trend = store.traffic_trend("site-1", days=7, until=date(2026, 8, 13))

    assert trend["previous_total"] == 100
    assert trend["change_percent"] == 20.0


def test_a_long_period_is_capped(tmp_path: Path) -> None:
    store = store_with([], tmp_path)

    assert store.traffic_trend("site-1", days=5000)["days"] == 90
    assert store.traffic_trend("site-1", days=0)["days"] == 1


def test_an_empty_period_has_no_strongest_day(tmp_path: Path) -> None:
    store = store_with([], tmp_path)

    trend = store.traffic_trend("site-1", days=7, until=DAY)

    assert trend["busiest_day"] is None
    assert trend["total"] == 0
    assert trend["change_percent"] is None


def test_trend_days_use_tashkent_boundaries(tmp_path: Path) -> None:
    """Kechki 23:30 dagi mijoz o'sha kunga tegishli, ertangiga emas."""
    store = store_with(
        [
            EdgeEvent(
                event_type="line_crossed",
                camera_id="eshik-01",
                direction="in",
                occurred_at=moment(23, 30, day=date(2026, 8, 12)),
            )
        ],
        tmp_path,
    )

    trend = store.traffic_trend("site-1", days=2, until=DAY)

    assert [item["entered"] for item in trend["daily"]] == [1, 0]


# ── Digest xizmati: bo'sh kun va mute ────────────────────────────────────


def _digest_service(store, sent):
    from cloud.digest import DailyDigestService

    async def sender(chat_id, text):
        sent.append((chat_id, text))

    return DailyDigestService(store, lambda: [{"id": "site-1", "name": "Oq Saroy"}], sender)


def _tashkent_evening():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime(DAY.year, DAY.month, DAY.day, 21, 30, tzinfo=ZoneInfo("Asia/Tashkent"))


def test_empty_day_digest_is_not_sent(tmp_path: Path) -> None:
    """Bo'sh kun uchun "Kirdi: 0" xabari — shovqin; yuborilmaydi."""
    import asyncio

    store = store_with([], tmp_path)
    store.add_member("site-1", "111", role="owner")
    sent: List = []
    service = _digest_service(store, sent)

    count = asyncio.run(service.check_once(_tashkent_evening()))

    assert count == 0 and sent == []
    # Belgilab qo'yiladi — har daqiqada qayta urinilmasin.
    assert store.digest_was_sent("site-1", DAY.isoformat())


def test_muted_member_does_not_get_the_digest(tmp_path: Path) -> None:
    """A'zo o'zi uchun kunlik hisobotni o'chira oladi (yangi panel sozlamasi)."""
    import asyncio

    store = store_with([crossing(12, "in")], tmp_path)
    store.add_member("site-1", "111", role="owner")
    muted = store.add_member("site-1", "222", role="manager")
    store.set_digest_muted("site-1", str(muted["id"]), True)
    sent: List = []
    service = _digest_service(store, sent)

    asyncio.run(service.check_once(_tashkent_evening()))

    assert [chat_id for chat_id, _ in sent] == ["111"], "faqat mute qilmagan a'zo olsin"


# ── Haftalik hisobot (dushanba 09:00) ────────────────────────────────────

# 2026-08-17 — dushanba; o'tgan hafta 10–16 avgust (ISO 33-hafta).
MONDAY = date(2026, 8, 17)


def _monday_morning():
    return datetime(MONDAY.year, MONDAY.month, MONDAY.day, 9, 30, tzinfo=TASHKENT)


def _week_store(tmp_path: Path) -> EventStore:
    events: List[EdgeEvent] = []
    for offset, count in enumerate([50, 60, 55, 70, 90, 120, 100]):
        events += entries(date(2026, 8, 10) + timedelta(days=offset), count)
    return store_with(events, tmp_path)


def test_weekly_report_goes_out_monday_morning(tmp_path: Path) -> None:
    import asyncio

    store = _week_store(tmp_path)
    store.add_member("site-1", "111", role="owner")
    sent: List = []
    service = _digest_service(store, sent)

    count = asyncio.run(service.check_once(_monday_morning()))

    assert count == 1 and len(sent) == 1
    text = sent[0][1]
    assert "haftalik hisobot" in text
    assert "Hafta davomida kirdi: <b>545</b> kishi" in text
    assert "Eng gavjum kun: Shanba — 120 kishi" in text
    # Belgi ISO hafta ko'rinishida — kunlik sana bilan to'qnashmaydi.
    assert store.digest_was_sent("site-1", "2026-W33")
    # Ertalab 09:30 da kunlik hisobot hali ketmagan (u 21:00 da).
    assert not store.digest_was_sent("site-1", MONDAY.isoformat())


def test_weekly_report_is_sent_only_once(tmp_path: Path) -> None:
    import asyncio

    store = _week_store(tmp_path)
    store.add_member("site-1", "111", role="owner")
    sent: List = []
    service = _digest_service(store, sent)

    asyncio.run(service.check_once(_monday_morning()))
    asyncio.run(service.check_once(_monday_morning()))

    assert len(sent) == 1


def test_weekly_is_skipped_on_other_days(tmp_path: Path) -> None:
    import asyncio

    store = _week_store(tmp_path)
    store.add_member("site-1", "111", role="owner")
    sent: List = []
    service = _digest_service(store, sent)

    tuesday = datetime(2026, 8, 18, 9, 30, tzinfo=TASHKENT)
    asyncio.run(service._weekly_once(tuesday))

    assert sent == []


def test_empty_week_sends_nothing(tmp_path: Path) -> None:
    import asyncio

    store = store_with([], tmp_path)
    store.add_member("site-1", "111", role="owner")
    sent: List = []
    service = _digest_service(store, sent)

    asyncio.run(service.check_once(_monday_morning()))

    assert sent == []
    assert store.digest_was_sent("site-1", "2026-W33"), "qayta urinilmasin"


def test_camera_uptime_is_computed_from_offline_pairs(tmp_path: Path) -> None:
    """Hafta ichida 1 kamera 2 soat o'chgan → uptime ≈ 98.8%."""
    week_day = date(2026, 8, 12)
    store = store_with(
        [
            EdgeEvent(
                event_type="camera_offline",
                camera_id="eshik-01",
                severity="critical",
                occurred_at=moment(10, day=week_day),
            ),
            EdgeEvent(
                event_type="camera_recovered",
                camera_id="eshik-01",
                severity="info",
                occurred_at=moment(12, day=week_day),
            ),
        ],
        tmp_path,
    )

    uptime = store.camera_uptime_percent("site-1", start=date(2026, 8, 10), end=date(2026, 8, 16))

    assert uptime == 98.8


def test_uptime_is_full_when_no_outage_was_recorded(tmp_path: Path) -> None:
    store = store_with([], tmp_path)

    assert (
        store.camera_uptime_percent("site-1", start=date(2026, 8, 10), end=date(2026, 8, 16))
        == 100.0
    )


# ── Demografiya: jins/yosh (xodimlarsiz) ─────────────────────────────────


def demo_crossing(hour: int, minute: int, track: int, jins: str, yosh: int) -> EdgeEvent:
    return EdgeEvent(
        event_type="line_crossed",
        camera_id="eshik-01",
        direction="in",
        line="eshik",
        track_id=track,
        occurred_at=moment(hour, minute),
        metadata={"demografiya": {"jins": jins, "yosh": yosh}},
    )


def test_demography_is_aggregated_with_percentages_and_age_buckets(tmp_path: Path) -> None:
    store = store_with(
        [
            demo_crossing(10, 0, 1, "ayol", 25),
            demo_crossing(10, 5, 2, "ayol", 34),
            demo_crossing(10, 10, 3, "erkak", 62),
            crossing(11, "in"),  # demografiyasiz kirish — sanoqni buzmaydi
        ],
        tmp_path,
    )

    report = store.retail_report("site-1", day=DAY)

    demo = report["demografiya"]
    assert demo["hisoblangan"] == 3
    assert demo["jins"] == {"ayol": 67, "erkak": 33}
    assert demo["yosh"]["18-30"] == 1
    assert demo["yosh"]["31-45"] == 1
    assert demo["yosh"]["60+"] == 1
    assert report["traffic"]["entered"] == 4, "kirdi-chiqdi soni demografiyaga bog'liq emas"


def employee_mark(hour: int, minute: int, track: int, *, day: date = DAY) -> EdgeEvent:
    """Yuz tanish xodimni topdi — shu (kamera, trek) mijoz emas."""
    return EdgeEvent(
        event_type="employee_seen",
        camera_id="eshik-01",
        severity="info",
        track_id=track,
        person_id="xodim-1",
        occurred_at=moment(hour, minute, day=day),
    )


def test_employees_are_excluded_from_footfall_not_just_demography(
    tmp_path: Path,
) -> None:
    """Do'kon egasi «bugun nechta MIJOZ kirdi» degan raqamni sotib oladi.

    Ilgari xodim kirishi shu raqamga qo'shilardi va faqat jins/yosh
    hisobidan chiqarilardi.  Ikki xodim kuniga o'n besh martadan eshikdan
    o'tsa, 200 mijozli do'konda hisobot ~15% shishadi — `docs/DOKON_MVP.md`
    dagi ±10% mezonidan o'tmaydi.  Maxfiylik sahifasi esa mijozga
    «Xodimlar bu statistikaga kirmaydi» deb va'da beradi.
    """
    store = store_with(
        [
            demo_crossing(9, 0, 7, "erkak", 30),
            employee_mark(9, 1, 7),
            demo_crossing(12, 0, 8, "ayol", 22),  # oddiy mijoz
        ],
        tmp_path,
    )

    report = store.retail_report("site-1", day=DAY)

    demo = report["demografiya"]
    assert demo["hisoblangan"] == 1, "faqat mijoz"
    assert demo["jins"] == {"ayol": 100, "erkak": 0}

    traffic = report["traffic"]
    assert traffic["entered"] == 1, "xodim kirishi mijoz sanog'iga qo'shilmasin"
    assert traffic["xodim_chiqarilgan"] == 1, "nechta xodim o'tishi chiqarilgani ko'rinsin"
    assert traffic["hourly"][9]["entered"] == 0, "soatlik grafikda ham qolmasin"
    assert traffic["hourly"][12]["entered"] == 1


def test_employee_exit_is_excluded_too(tmp_path: Path) -> None:
    """Faqat kirishni chiqarib tashlash `inside_estimate` ni buzardi:
    xodim chiqishi qolsa do'konda «minus bir odam» bo'lib chiqadi."""
    store = store_with(
        [
            crossing(9, "in", 0, track_id=3),
            employee_mark(9, 1, 3),
            crossing(21, "out", 0, track_id=4),
            employee_mark(21, 1, 4),
            crossing(12, "in", 0, track_id=9),  # mijoz
        ],
        tmp_path,
    )

    traffic = store.retail_report("site-1", day=DAY)["traffic"]

    assert traffic["entered"] == 1
    assert traffic["exited"] == 0, "xodim chiqishi ham hisobga olinmasin"
    assert traffic["xodim_chiqarilgan"] == 2


def test_yesterday_comparison_also_excludes_employees(tmp_path: Path) -> None:
    """Kechagi raqam boshqa yo'l bilan hisoblanadi.  U xodimni chiqarmasa
    «bugun 50% kam» degan yolg'on o'sish/pasayish chiqadi."""
    yesterday = DAY - timedelta(days=1)
    store = store_with(
        [
            crossing(10, "in", 0, day=yesterday, track_id=1),
            employee_mark(10, 1, 1, day=yesterday),
            crossing(11, "in", 0, day=yesterday, track_id=2),  # mijoz
            crossing(10, "in", 0, track_id=5),  # bugun: bitta mijoz
        ],
        tmp_path,
    )

    traffic = store.retail_report("site-1", day=DAY)["traffic"]

    assert traffic["entered_yesterday"] == 1, "kecha ham faqat mijoz sanalsin"
    assert traffic["change_percent"] == 0


def test_trend_days_also_exclude_employees(tmp_path: Path) -> None:
    """«Kunlar bo'yicha» grafik uchinchi yo'l bilan hisoblanadi — u ham
    kunlik hisobot bilan bitta raqamni ko'rsatishi kerak."""
    store = store_with(
        [
            crossing(10, "in", 0, track_id=1),
            employee_mark(10, 1, 1),
            crossing(11, "in", 0, track_id=2),  # mijoz
        ],
        tmp_path,
    )

    trend = store.traffic_trend("site-1", days=1, until=DAY)
    report = store.retail_report("site-1", day=DAY)

    assert trend["daily"][-1]["entered"] == 1
    assert trend["daily"][-1]["entered"] == report["traffic"]["entered"], (
        "grafik va kunlik hisobot bitta raqamni ko'rsatsin"
    )


def test_recycled_track_id_outside_the_window_still_counts(tmp_path: Path) -> None:
    """Trek raqami qayta ishlatilgan: xodim belgisi 6 soat oldin — mijoz sanaladi."""
    store = store_with(
        [employee_mark(9, 0, 5), demo_crossing(15, 0, 5, "ayol", 40)],
        tmp_path,
    )

    report = store.retail_report("site-1", day=DAY)

    assert report["demografiya"]["hisoblangan"] == 1
    assert report["traffic"]["entered"] == 1
    assert report["traffic"]["xodim_chiqarilgan"] == 0


def test_digest_gets_a_demography_line(tmp_path: Path) -> None:
    store = store_with(
        [demo_crossing(10, 0, 1, "ayol", 25), demo_crossing(10, 5, 2, "ayol", 28)],
        tmp_path,
    )

    text = build_digest(
        "Oq Saroy",
        DAY.isoformat(),
        store.stats("site-1", day=DAY),
        store.retail_report("site-1", day=DAY),
    )

    assert "🚻 100% ayol · 0% erkak · asosan 18-30 yosh" in text


def test_quiet_day_digest_has_no_demography_line(tmp_path: Path) -> None:
    text = digest_for(tmp_path, [crossing(12, "in")])
    assert "🚻" not in text


# ── Obuna eslatmasi ──────────────────────────────────────────────────────


def _renewal_service(store, sent, sites):
    from cloud.digest import DailyDigestService

    async def sender(chat_id, text, **kwargs):
        sent.append((chat_id, text))

    return DailyDigestService(store, lambda: sites, sender)


def _renewal_noon():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime(DAY.year, DAY.month, DAY.day, 12, 0, tzinfo=ZoneInfo("Asia/Tashkent"))


def _site(days_left: int, status: str = "active", until: str = "2026-09-20 10:00:00"):
    return {
        "id": "site-1",
        "name": "Oq Saroy",
        "license_status": status,
        "days_left": days_left,
        "subscription_until": until,
        "monthly_price_uzs": 149000,
    }


def test_renewal_reminder_is_sent_once_per_period(tmp_path: Path) -> None:
    """Bir davr uchun bitta eslatma — kuniga qayta-qayta emas."""
    import asyncio

    store = store_with([], tmp_path)
    store.add_member("site-1", "111", role="owner")
    sent: List = []
    service = _renewal_service(store, sent, [_site(5)])

    assert asyncio.run(service._renewal_once(_renewal_noon())) == 1
    # Ikkinchi tik — hech narsa ketmaydi.
    assert asyncio.run(service._renewal_once(_renewal_noon())) == 0
    assert len(sent) == 1
    assert "5 kun qoldi" in sent[0][1]
    # Yillik taklif ham shu xabarda: 149 000 × 10 = 1 490 000
    assert "1 490 000" in sent[0][1] or "1490000" in sent[0][1]


def test_paying_moves_the_date_so_the_next_period_reminds_again(tmp_path: Path) -> None:
    """To'lovdan keyin eslatmalar QAYTA ishlasin.

    Belgi obuna tugash sanasiga bog'langan — sana siljisa belgi ham yangi
    bo'ladi.  Aks holda mijoz bir marta eslatma olib, keyingi yili
    umuman eslatilmasdi.
    """
    import asyncio

    store = store_with([], tmp_path)
    store.add_member("site-1", "111", role="owner")
    sent: List = []

    service = _renewal_service(store, sent, [_site(5, until="2026-09-20 10:00:00")])
    assert asyncio.run(service._renewal_once(_renewal_noon())) == 1

    # Mijoz to'ladi — sana bir yilga siljidi.
    service = _renewal_service(store, sent, [_site(5, until="2027-09-20 10:00:00")])
    assert asyncio.run(service._renewal_once(_renewal_noon())) == 1
    assert len(sent) == 2


def test_a_healthy_subscription_is_not_nagged(tmp_path: Path) -> None:
    """Obunaga 40 kun bor — hech qanday xabar ketmasin."""
    import asyncio

    store = store_with([], tmp_path)
    store.add_member("site-1", "111", role="owner")
    sent: List = []
    service = _renewal_service(store, sent, [_site(40)])

    assert asyncio.run(service._renewal_once(_renewal_noon())) == 0
    assert sent == []


def test_expired_site_gets_no_automatic_reminder(tmp_path: Path) -> None:
    """Muddati o'tgan do'konga avtomatik xabar emas — qo'ng'iroq kerak."""
    import asyncio

    store = store_with([], tmp_path)
    store.add_member("site-1", "111", role="owner")
    sent: List = []
    service = _renewal_service(store, sent, [_site(-30, status="expired")])

    assert asyncio.run(service._renewal_once(_renewal_noon())) == 0
    assert sent == []


def test_only_the_owner_is_reminded_not_the_shop_assistant(tmp_path: Path) -> None:
    """Hisobni ega to'laydi — sotuvchi bezovta qilinmaydi."""
    import asyncio

    store = store_with([], tmp_path)
    store.add_member("site-1", "111", role="owner")
    store.add_member("site-1", "222", role="manager")
    sent: List = []
    service = _renewal_service(store, sent, [_site(3)])

    assert asyncio.run(service._renewal_once(_renewal_noon())) == 1
    assert [chat for chat, _ in sent] == ["111"]


def test_grace_reminder_says_how_long_the_system_keeps_working(tmp_path: Path) -> None:
    """Grace xabarida aniq kun turishi kerak — saytdagi va'da shu."""
    import asyncio

    store = store_with([], tmp_path)
    store.add_member("site-1", "111", role="owner")
    sent: List = []
    service = _renewal_service(store, sent, [_site(-2, status="grace")])

    assert asyncio.run(service._renewal_once(_renewal_noon())) == 1
    assert "14 kun" in sent[0][1]


# ── Ishonch balli xabar sarlavhasida ─────────────────────────────────────


def test_digest_headline_leads_with_the_score_not_the_word_report(tmp_path: Path) -> None:
    """Telefon bildirishnomasi faqat BIRINCHI qatorni ko'rsatadi.

    "kunlik hisobot" do'kon egasiga hech narsa aytmaydi — u xabarni
    ochishi kerak.  "Bugun: 94 — A'lo kun" esa ochmasdan javob beradi.
    """
    store = store_with([], tmp_path)
    text = build_digest(
        "Oq Saroy",
        DAY.isoformat(),
        store.stats("site-1", day=DAY),
        store.retail_report("site-1", day=DAY),
        score={"available": True, "total": 94, "reason": None, "parts": []},
    )
    first = text.splitlines()[0]
    assert "Bugun: <b>94</b>" in first
    assert "hisobot" not in first
    assert "A'lo kun" in text


def test_digest_says_why_when_the_score_is_missing(tmp_path: Path) -> None:
    """Ball yo'q bo'lsa sababi yozilsin — jim sarlavha mijozni chalg'itadi."""
    store = store_with([], tmp_path)
    reason = "Do'kon kompyuteri 19 soatdan beri jim — ma'lumot to'liq emas"
    text = build_digest(
        "Oq Saroy",
        DAY.isoformat(),
        store.stats("site-1", day=DAY),
        store.retail_report("site-1", day=DAY),
        score={"available": False, "total": None, "reason": reason, "parts": []},
    )
    assert reason in text
    assert "Bugun:" not in text


def test_digest_without_a_score_keeps_the_old_headline(tmp_path: Path) -> None:
    """Ball hisoblanmasa xabar baribir chiqsin — orqaga moslik."""
    store = store_with([], tmp_path)
    text = build_digest(
        "Oq Saroy",
        DAY.isoformat(),
        store.stats("site-1", day=DAY),
        store.retail_report("site-1", day=DAY),
    )
    assert "kunlik hisobot" in text.splitlines()[0]
