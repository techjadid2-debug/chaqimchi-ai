"""Oylik smena hisoboti — kim qancha kechikdi.

Ma'lumot allaqachon yig'ilardi: `attendance_daily` da `late_minutes`,
`early_leave_minutes` va `checkout_missing` bor edi.  Yo'q narsa —
JAMLASH.  Do'kon egasi kunma-kun 30 qatorni ko'zdan kechirib, kechikish
daqiqalarini qo'lda qo'shib chiqmaydi; oy oxirida uning savoli bitta:
"kim kechikyapti va bu menga qancha vaqtga tushdi".
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from chaqimchi_ai.event_models import EdgeEvent
from cloud.event_store import EventStore

TASHKENT = ZoneInfo("Asia/Tashkent")
SITE = "smena-1"


@pytest.fixture
def store(tmp_path: Path) -> EventStore:
    return EventStore(sqlite_path=tmp_path / "events.db")


def _seen(store: EventStore, employee_id: str, when: datetime) -> None:
    """Xodim kamerada ko'rindi."""
    store.ingest(
        SITE,
        "dev-1",
        [
            EdgeEvent(
                event_type="employee_seen",
                camera_id="camera-01",
                severity="info",
                person_id=employee_id,
                score=0.9,
                occurred_at=when.astimezone(ZoneInfo("UTC")).isoformat(),
                track_id=1,
            )
        ],
    )


def _worker(store: EventStore, name: str, *, start: str = "09:00", end: str = "18:00") -> str:
    employee = store.create_employee(SITE, name=name)
    # Ishga kirish sanasini orqaga suramiz.  Ikki cheklov bir-biriga
    # qarama-qarshi: hisobot xodim YARATILGANIDAN oldingi kunlarni
    # hisoblamaydi (to'g'ri), qabul esa KELAJAKDAGI vaqtni rad etadi
    # ("Qurilma soati oldinda").  Ya'ni sinov kunlari o'tmishda bo'lishi
    # va xodim ulardan ham oldin "ishga kirgan" bo'lishi kerak.
    with store._connect() as conn:
        conn.execute(
            store._sql("UPDATE employees SET created_at=? WHERE id=?"),
            ("2026-01-01T00:00:00+00:00", employee["id"]),
        )
    store.replace_employee_schedules(
        SITE,
        employee["id"],
        [
            {"weekday": day, "start_time": start, "end_time": end, "grace_minutes": 5,
             "enabled": True}
            for day in range(5)  # dushanba–juma
        ],
    )
    return employee["id"]


def _monday(week_offset: int = 0) -> date:
    """Sinov uchun O'TGAN dushanba.

    Qat'iy sana ishlatib bo'lmaydi: `attendance_report` xodim
    YARATILGANIDAN oldingi kunlarni umuman hisobga olmaydi (va bu
    to'g'ri — ishga kirmagan odamning kelmagani "qoidabuzarlik" emas).
    Sinovdagi xodim esa hozir yaratiladi.
    """
    today = datetime.now(TASHKENT).date()
    # O'TGAN dushanba: hodisa vaqti kelajakda bo'lsa qabul uni server
    # vaqtiga almashtiradi va sinov ma'nosini yo'qotadi.
    back = today.weekday() + 7 * (week_offset + 1)
    return today - timedelta(days=back)


def test_late_minutes_are_summed_per_employee(store: EventStore) -> None:
    ali = _worker(store, "Ali")
    monday = _monday()

    # Dushanba 20 daqiqa kechikdi, seshanba 10.
    _seen(store, ali, datetime.combine(monday, datetime.min.time(), TASHKENT).replace(hour=9, minute=20))
    _seen(store, ali, datetime.combine(monday, datetime.min.time(), TASHKENT).replace(hour=18, minute=5))
    tuesday = monday + timedelta(days=1)
    _seen(store, ali, datetime.combine(tuesday, datetime.min.time(), TASHKENT).replace(hour=9, minute=10))
    _seen(store, ali, datetime.combine(tuesday, datetime.min.time(), TASHKENT).replace(hour=18, minute=2))

    summary = store.shift_summary(
        SITE,
        start=monday,
        end=tuesday,
        now=datetime.now(TASHKENT),
    )

    assert summary["employees"] == 1
    row = summary["rows"][0]
    assert row["employee_name"] == "Ali"
    assert row["ish_kunlari"] == 2
    assert row["kelgan_kunlar"] == 2
    assert row["kechikkan_kunlar"] == 2
    # (20 - 5) + (10 - 5) — har kuni 5 daqiqa `grace_minutes` ayiriladi.
    assert row["jami_kechikish_daq"] == 20
    assert row["ortacha_kechikish_daq"] == 10.0
    assert summary["jami"]["kechikish_daq"] == 20


def test_days_off_are_not_counted_as_absence(store: EventStore) -> None:
    """Dam olish kuni "kelmagan kun" emas.

    Aks holda haftada ikki kun dam oladigan xodim hisobotda eng yomon
    ko'rsatkichga chiqib qolardi va raqam ma'nosini yo'qotardi.
    """
    ali = _worker(store, "Ali")
    monday = _monday()
    _seen(store, ali, datetime.combine(monday, datetime.min.time(), TASHKENT).replace(hour=8, minute=55))
    saturday = monday + timedelta(days=5)
    sunday = monday + timedelta(days=6)

    summary = store.shift_summary(
        SITE,
        start=monday,
        end=sunday,
        now=datetime.now(TASHKENT),
    )
    row = summary["rows"][0]

    # Dushanba–juma = 5 ish kuni; shanba va yakshanba jadvalda yo'q.
    assert row["ish_kunlari"] == 5
    assert row["kelmagan_kunlar"] == 4, "faqat jadvaldagi kelmagan kunlar"
    assert saturday.weekday() == 5 and sunday.weekday() == 6


def test_the_worst_offender_is_first(store: EventStore) -> None:
    """Hisobot aynan shu savolga javob beradi — pastga qarab qidirilmasin."""
    monday = _monday()
    kam = _worker(store, "Kam kechikkan")
    ko_p = _worker(store, "Ko'p kechikkan")
    base = datetime.combine(monday, datetime.min.time(), TASHKENT)
    _seen(store, kam, base.replace(hour=9, minute=12))
    _seen(store, ko_p, base.replace(hour=10, minute=30))

    summary = store.shift_summary(
        SITE, start=monday, end=monday, now=datetime.now(TASHKENT)
    )

    assert [row["employee_name"] for row in summary["rows"]][0] == "Ko'p kechikkan"


def test_a_clean_month_reports_zero_not_an_error(store: EventStore) -> None:
    ali = _worker(store, "Ali")
    monday = _monday()
    base = datetime.combine(monday, datetime.min.time(), TASHKENT)
    _seen(store, ali, base.replace(hour=8, minute=58))
    _seen(store, ali, base.replace(hour=18, minute=3))

    summary = store.shift_summary(SITE, start=monday, end=monday, now=datetime.now(TASHKENT))
    row = summary["rows"][0]

    assert row["jami_kechikish_daq"] == 0
    assert row["ortacha_kechikish_daq"] == 0.0
    assert row["kelgan_kunlar"] == 1
    assert summary["jami"]["kechikish_daq"] == 0


# ── API va Telegram xulosasi ────────────────────────────────────────────


def test_month_range_ends_today_not_in_the_future() -> None:
    """Kelajakdagi kunlar hisobotni buzadi.

    Jadval bor, kelish esa hali bo'lmagan — barcha qolgan kunlar
    "kelmagan" bo'lib chiqardi va 5-sanadagi hisobot xodimni
    25 kun kelmagan deb ko'rsatardi.
    """
    from cloud.main import _month_range

    today = datetime.now(TASHKENT).date()
    first, last = _month_range(f"{today:%Y-%m}")

    assert first == today.replace(day=1)
    assert last == today


def test_month_range_handles_february() -> None:
    """Oxirgi kun kalendardan olinadi — 30/31 qo'lda yozilsa fevral buzilardi."""
    from cloud.main import _month_range

    first, last = _month_range("2026-02")
    assert first.isoformat() == "2026-02-01"
    assert last.isoformat() == "2026-02-28"


def test_the_monthly_telegram_message_names_the_worst_offenders() -> None:
    """Xabar do'kon egasiga boradi va aynan shu ma'lumot uchun kerak.

    Lekin faqat uchtasi: to'liq ro'yxat xabarni o'qib bo'lmaydigan
    qiladi va u panelda turadi.
    """
    from cloud.digest import build_shifts

    summary = {
        "jami": {"kechikish_daq": 154, "kelmagan_kunlar": 3, "erta_ketish_daq": 0},
        "rows": [
            {"employee_name": f"Xodim {index}", "kechikkan_kunlar": 8 - index,
             "jami_kechikish_daq": 80 - index * 10}
            for index in range(5)
        ],
    }
    text = build_shifts("Namuna do'kon", "2026-07", summary)

    assert "2 soat 34 daq" in text, "jami soat va daqiqada ko'rsatilsin"
    assert "Xodim 0" in text and "Xodim 2" in text
    assert "Xodim 3" not in text, "faqat uchtasi"


def test_a_clean_month_says_so_instead_of_an_empty_table() -> None:
    from cloud.digest import build_shifts

    text = build_shifts(
        "Namuna do'kon",
        "2026-07",
        {"jami": {"kechikish_daq": 0, "kelmagan_kunlar": 0}, "rows": []},
    )
    assert "yo'q" in text
