"""Do'kon kompyuterining soati noto'g'ri bo'lsa hisobot buzilmasin.

`occurred_at` qurilmaning devor soatidan olinadi.  Do'kon kompyuteri —
2014-yilgi i5, unda CMOS batareyasi o'lishi odatiy hol, NTP esa hech
qayerda majburiy emas.  Cloud bu qiymatni tekshirmasdan saqlardi va
undan **retention**, **kunlik hisobot** va **grafik** hisoblanardi:

* kelajak sanali yozuv hech qachon o'chmasdi va ro'yxat boshida
  abadiy turib olardi (`ORDER BY occurred_at DESC`);
* yaroqsiz sana kunlik hisobot va grafikni BUTUNLAY 500 qilardi —
  mijoz paneli qayta ochilganda ham tuzalmasdi.

Ikkinchisining sharti aniq: sana satr sifatida kun oralig'iga tushishi,
lekin ochilmasligi kerak (`2026-08-13T09:99:99`).  Butunlay begona satr
(`"n/a"`) oraliqdan tashqarida qolgani uchun so'rovga umuman
tushmaydi — shuning uchun quyidagi test aynan haqiqiy holatni oladi.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from chaqimchi_ai.event_models import EdgeEvent
from cloud.event_store import EventStore

TASHKENT_DAY = date(2026, 8, 13)


def _store(tmp_path: Path) -> EventStore:
    return EventStore(sqlite_path=tmp_path / "events.db")


def _crossing(occurred_at: str, event_id: str = "e1") -> EdgeEvent:
    return EdgeEvent(
        event_id=event_id,
        event_type="line_crossed",
        camera_id="eshik-01",
        direction="in",
        line="eshik",
        occurred_at=occurred_at,
    )


#: Toshkent kuni UTC da soat 19:00 da boshlanadi, ya'ni bu satr kun
#: oralig'iga tushadi — lekin daqiqasi yaroqsiz.
IN_RANGE_BUT_BROKEN = "2026-08-13T09:99:99+00:00"


def test_a_broken_timestamp_does_not_break_the_whole_report(tmp_path: Path) -> None:
    """Bitta buzuq yozuv butun do'konning hisobotini o'ldirmasin.

    Ilgari `ValueError: minute must be in 0..59` chiqib, o'sha do'kon
    uchun kunlik hisobot ham, grafik ham 500 qaytarardi."""
    store = _store(tmp_path)
    store.ingest("site-1", "dev-1", [_crossing(IN_RANGE_BUT_BROKEN, "buzuq")])

    report = store.retail_report("site-1", day=TASHKENT_DAY)
    trend = store.traffic_trend("site-1", days=7, until=TASHKENT_DAY)

    assert report["traffic"]["entered"] >= 0
    assert len(trend["daily"]) == 7


def test_a_future_clock_is_pulled_back_to_server_time(tmp_path: Path) -> None:
    """Kelajakdagi yozuv hech qachon o'chmasdi va ro'yxat boshida
    abadiy turardi."""
    store = _store(tmp_path)
    far_future = (datetime.now(timezone.utc) + timedelta(days=400)).isoformat()

    store.ingest("site-1", "dev-1", [_crossing(far_future)])

    stored = _stored_time(store)["occurred_at"]
    assert datetime.fromisoformat(stored) <= datetime.now(timezone.utc) + timedelta(minutes=5)


def test_a_dead_cmos_battery_is_logged_but_the_data_is_not_faked(
    tmp_path: Path, caplog
) -> None:
    """Buzuq soatli hodisani "hozir" ga surish jozibali, lekin noto'g'ri:
    butun kunlik yuklama yuborilgan daqiqaga yig'ilib qolardi va do'kon
    egasi soatlik grafikda **soxta mijozlar** ko'rardi.

    Bir yillik arxiv sotilgan mijozda (enterprise = 365 kun) eski hodisa
    umuman qonuniy holat, ya'ni "eski = buzuq" degan qoida ham ishlamaydi.
    Shuning uchun vaqt saqlanadi, muammo esa jurnalga yoziladi.
    """
    import logging

    store = _store(tmp_path)
    with caplog.at_level(logging.WARNING):
        store.ingest("site-1", "dev-1", [_crossing("2014-03-05T10:00:00+00:00")])

    assert datetime.fromisoformat(_stored_time(store)["occurred_at"]).year == 2014
    assert any("soati juda orqada" in record.message for record in caplog.records)


def test_a_year_old_event_is_kept_for_a_long_retention_plan(tmp_path: Path) -> None:
    """365 kunlik arxiv uchun to'lagan mijozda eski hodisa normal."""
    store = _store(tmp_path)
    long_ago = datetime.now(timezone.utc) - timedelta(days=300)

    store.ingest("site-1", "dev-1", [_crossing(long_ago.isoformat())])

    stored = datetime.fromisoformat(_stored_time(store)["occurred_at"])
    assert abs((stored - long_ago).total_seconds()) < 60


def test_a_late_upload_after_a_week_offline_keeps_its_real_time(tmp_path: Path) -> None:
    """Internet bir hafta yo'q edi — hodisalar diskda kutgan va endi
    keladi.  Ularning vaqti HAQIQIY, uni bugungi kunga surish
    hisobotni buzadi."""
    store = _store(tmp_path)
    week_ago = datetime.now(timezone.utc) - timedelta(days=6)

    store.ingest("site-1", "dev-1", [_crossing(week_ago.isoformat())])

    stored = _stored_time(store)["occurred_at"]
    assert abs((datetime.fromisoformat(stored) - week_ago).total_seconds()) < 60


def test_a_small_clock_drift_is_left_alone(tmp_path: Path) -> None:
    """Bir necha daqiqalik farq normal — uni tuzatish hodisani
    noto'g'ri soatga surib qo'yardi."""
    store = _store(tmp_path)
    slightly_ahead = datetime.now(timezone.utc) + timedelta(minutes=2)

    store.ingest("site-1", "dev-1", [_crossing(slightly_ahead.isoformat())])

    stored = _stored_time(store)["occurred_at"]
    assert abs((datetime.fromisoformat(stored) - slightly_ahead).total_seconds()) < 60


def test_a_legacy_broken_row_is_skipped_not_fatal(tmp_path: Path) -> None:
    """Yangi yozuvlar kirishda to'g'rilanadi, lekin bazada allaqachon
    turgan buzuq qator ham hisobotni yiqitmasligi kerak."""
    store = _store(tmp_path)
    store.ingest("site-1", "dev-1", [_crossing(datetime.now(timezone.utc).isoformat(), "yaxshi")])
    with store._connect() as conn:
        conn.execute(
            store._sql("UPDATE production_events SET occurred_at=? WHERE event_id=?"),
            (IN_RANGE_BUT_BROKEN, "yaxshi"),
        )

    report = store.retail_report("site-1", day=TASHKENT_DAY)
    assert report["traffic"]["entered"] == 0, "buzuq qator o'tkazib yuborilsin"


def _stored_time(store: EventStore) -> dict:
    """Bazadagi yagona yozuvning vaqti."""
    events = store.list_events("site-1", limit=10)
    rows = events["events"] if isinstance(events, dict) else events
    return rows[0]
