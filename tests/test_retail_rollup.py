"""Kunlik va soatlik RAQAMLAR xom hodisalardan alohida yashaydi.

Nega bu jadval kerak: panelning har bir raqami (`retail_report`,
`traffic_trend`) har safar `production_events` dan qayta hisoblanardi,
xom hodisalar esa tarif muddatida (30/90/365 kun) o'chadi.  Ya'ni
30-kuni mijozning o'sha kungi kirish soni, soatlik grafigi, navbati va
xavfsizlik sanog'i BUTUNLAY yo'qolardi va buni hech narsa aytmasdi.

Demografiya uchun bu allaqachon hal qilingan (`test_demography_rollup`);
bu yerdagi jadvallar qolgan raqamlarni o'sha yo'lga qo'yadi.

Eng qimmat xato — **tartib**: yig'indi hodisalar o'chirilishidan OLDIN
yozilishi kerak.  Tartib almashsa yig'indi bo'sh chiqadi va kunni
tiklab bo'lmaydi.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from chaqimchi_ai.event_models import EdgeEvent
from cloud.event_store import EventStore

#: Hisobot va yig'indi shu mintaqada kun chegarasini qo'yadi — test
#: ham aynan shunda yozsin, aks holda soat indeksi siljib ketadi.
_TASHKENT = ZoneInfo("Asia/Tashkent")
SITE = "site-a"


@pytest.fixture
def store(tmp_path: Path) -> EventStore:
    return EventStore(sqlite_path=tmp_path / "events.db")


def _day_of_shopping(store: EventStore, day: date, *, entered: int = 5) -> None:
    """Bir kunlik namuna: kirishlar, chiqishlar va bitta navbat signali."""
    events = []
    for index in range(entered):
        events.append(
            EdgeEvent(
                event_type="line_crossed",
                camera_id="camera-01",
                direction="in",
                track_id=index,
                occurred_at=datetime.combine(day, time(10, 0), tzinfo=_TASHKENT).isoformat(),
            )
        )
    events.append(
        EdgeEvent(
            event_type="line_crossed",
            camera_id="camera-01",
            direction="out",
            track_id=900,
            occurred_at=datetime.combine(day, time(19, 0), tzinfo=_TASHKENT).isoformat(),
        )
    )
    events.append(
        EdgeEvent(
            event_type="queue_threshold_exceeded",
            camera_id="camera-02",
            queue_length=4,
            occurred_at=datetime.combine(day, time(13, 0), tzinfo=_TASHKENT).isoformat(),
        )
    )
    store.ingest(SITE, "device-1", events)


# ── Yig'indi hisobot bilan bir xil bo'lsin ───────────────────────────


def test_the_rollup_matches_the_live_report(store: EventStore) -> None:
    """Eng muhim qulf.

    Ikkita manba (xom hisobot va yig'indi) uzoqlashsa, mijoz panel bilan
    hisobot orasidan qaysi raqamga ishonishni bilmasdi.  Shu sababdan
    yig'indi `retail_report` ning O'ZIDAN yoziladi, qayta hisoblanmaydi.
    """
    day = date.today() - timedelta(days=2)
    _day_of_shopping(store, day)

    live = store._retail_report_from_events(SITE, day=day)  # noqa: SLF001 — manbani solishtiramiz
    store.rollup_retail(SITE, day)

    assert store.retail_report(SITE, day=day) == live


def test_the_hourly_numbers_are_stored(store: EventStore) -> None:
    day = date.today() - timedelta(days=2)
    _day_of_shopping(store, day, entered=5)

    store.rollup_retail(SITE, day)

    hourly = store.retail_report(SITE, day=day)["traffic"]["hourly"]
    assert len(hourly) == 24
    assert hourly[10]["entered"] == 5
    assert hourly[19]["exited"] == 1


# ── Xom hodisa o'chgandan keyin ham raqam qolsin ─────────────────────


def test_a_finished_day_survives_the_purge(store: EventStore) -> None:
    """Butun tuzatishning sababi."""
    day = date.today() - timedelta(days=40)
    _day_of_shopping(store, day, entered=7)
    store.rollup_retail(SITE, day)

    store.purge_site(SITE, retention_days=30)

    assert store._events_of_day(SITE, day, _TASHKENT) == [], "xom hodisa o'chgan bo'lsin"  # noqa: SLF001
    report = store.retail_report(SITE, day=day)
    assert report["traffic"]["entered"] == 7, "raqam yig'indidan kelishi kerak"
    assert report["queue"]["longest"] == 4


def test_the_trend_reads_the_rollup_after_the_events_are_gone(store: EventStore) -> None:
    day = date.today() - timedelta(days=40)
    _day_of_shopping(store, day, entered=7)
    store.rollup_retail(SITE, day)
    store.purge_site(SITE, retention_days=30)

    trend = store.traffic_trend(SITE, days=45)

    entered = {item["date"]: item["entered"] for item in trend["daily"]}
    assert entered[day.isoformat()] == 7


# ── Chegaralar ───────────────────────────────────────────────────────


def test_today_is_never_read_from_the_rollup(store: EventStore) -> None:
    """Bugungi kun hali tugamagan — u har daqiqada o'zgaradi."""
    today = date.today()
    _day_of_shopping(store, today, entered=2)
    store.rollup_retail(SITE, today)  # ataylab: eskirgan yozuv qoldiramiz
    _day_of_shopping(store, today, entered=3)

    # Yig'indida 2 ta kirish yozilgan, xom hodisalarda esa endi 5 ta.
    assert store.retail_report(SITE, day=today)["traffic"]["entered"] == 5


def test_a_missing_rollup_falls_back_to_the_events(store: EventStore) -> None:
    """Yig'indining yo'qligi raqamni yo'qotmasin."""
    day = date.today() - timedelta(days=2)
    _day_of_shopping(store, day, entered=4)

    assert store.retail_report(SITE, day=day)["traffic"]["entered"] == 4


def test_pending_days_are_rolled_up_but_today_is_left_alone(store: EventStore) -> None:
    yesterday = date.today() - timedelta(days=1)
    _day_of_shopping(store, yesterday, entered=3)
    _day_of_shopping(store, date.today(), entered=9)

    store.rollup_pending_retail(SITE)

    assert store.retail_rollup(SITE, yesterday)["traffic"]["entered"] == 3
    assert store.retail_rollup(SITE, date.today()) is None


def test_rolling_up_twice_updates_instead_of_duplicating(store: EventStore) -> None:
    day = date.today() - timedelta(days=2)
    _day_of_shopping(store, day, entered=2)
    store.rollup_retail(SITE, day)
    _day_of_shopping(store, day, entered=3)

    store.rollup_retail(SITE, day)

    assert store.retail_rollup(SITE, day)["traffic"]["entered"] == 5


# ── Media 48 soat ────────────────────────────────────────────────────


def test_a_promised_image_that_never_arrived_stops_being_promised(
    store: EventStore,
) -> None:
    """`has_snapshot=1`, lekin kalit yo'q — panel 404 beradigan tugma.

    Qurilma hodisani «rasmim bor» deb yuborib, rasmni keyin yuklaydi.
    Yuklash yiqilsa bayroq qoladi-yu kalit hech qachon kelmaydi.  Jonli
    bazada 2026-08-30 da shunday 39 ta qator bor edi.
    """
    old = datetime.now(_TASHKENT) - timedelta(days=5)
    store.ingest(SITE, "device-1", [
        EdgeEvent(
            event_type="loitering",
            camera_id="camera-01",
            occurred_at=old.isoformat(),
            has_snapshot=True,
        )
    ])
    event_id = store.list_events(SITE, limit=1)[0]["event_id"]
    assert store.event(SITE, event_id)["has_snapshot"] == 1

    store.purge_media_older_than(SITE, hours=48)

    assert store.event(SITE, event_id)["has_snapshot"] == 0
    assert store.event(SITE, event_id) is not None, "hodisaning o'zi qolsin"


def test_media_inside_the_window_is_left_alone(store: EventStore) -> None:
    recent = datetime.now(_TASHKENT) - timedelta(hours=5)
    store.ingest(SITE, "device-1", [
        EdgeEvent(
            event_type="camera_tampered",
            camera_id="camera-01",
            occurred_at=recent.isoformat(),
            has_snapshot=True,
        )
    ])
    event_id = store.list_events(SITE, limit=1)[0]["event_id"]

    store.purge_media_older_than(SITE, hours=48)

    assert store.event(SITE, event_id)["has_snapshot"] == 1
