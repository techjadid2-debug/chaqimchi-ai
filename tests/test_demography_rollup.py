"""Kunlik demografiya yig'indisi: haftalik, oylik va yillik natijalar.

Nega bu jadval kerak: xom hodisalar tarif muddati bo'yicha
o'chiriladi (`purge_site`, odatda 30 kun).  Hisobot esa demografiyani
har safar o'sha hodisalardan qaytadan hisoblaydi — ya'ni haftalik
dinamika chegarada, oylik qisman, yillik esa UMUMAN mumkin emas edi.

Bu yerdagi eng qimmat xato — **tartib**: yig'indi hodisalar
o'chirilishidan OLDIN yozilishi kerak.  Tartib almashsa yig'indi bo'sh
chiqadi va o'sha kun butunlay yo'qoladi; uni keyin tiklab bo'lmaydi.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path

import pytest

from chaqimchi_ai.event_models import EdgeEvent
from cloud.event_store import EventStore

#: Bir kunlik namuna: 6 ayol, 4 erkak, yosh guruhlari aralash.
PEOPLE = [
    ("ayol", 24), ("ayol", 31), ("ayol", 55), ("ayol", 16), ("ayol", 29), ("ayol", 38),
    ("erkak", 28), ("erkak", 42), ("erkak", 67), ("erkak", 22),
]


@pytest.fixture
def store(tmp_path: Path) -> EventStore:
    return EventStore(sqlite_path=tmp_path / "events.db")


def _crossings(store: EventStore, site_id: str, day: date, *, people=None, first_track=0) -> None:
    when = datetime.combine(day, time(15, 0)).isoformat()
    rows = people if people is not None else PEOPLE
    store.ingest(site_id, "device-1", [
        EdgeEvent(
            event_type="line_crossed",
            camera_id="camera-01",
            direction="in",
            track_id=first_track + index,
            occurred_at=when,
            metadata={"demografiya": {"jins": jins, "yosh": yosh}},
        )
        for index, (jins, yosh) in enumerate(rows)
    ])


# ── Kunlik yozuv ─────────────────────────────────────────────────────


def test_a_finished_day_is_written_as_plain_numbers(store: EventStore) -> None:
    day = date.today() - timedelta(days=2)
    _crossings(store, "s1", day)

    row = store.rollup_demography("s1", day)

    assert row["counted"] == 10
    assert row["ayol"] == 6
    assert row["erkak"] == 4
    assert row["age_under18"] == 1
    assert row["age_60_plus"] == 1


def test_the_rollup_matches_the_daily_report_exactly(store: EventStore) -> None:
    """Ikki joyda ikki xil son chiqsa, mijoz qaysi biriga ishonishni
    bilmasdi."""
    day = date.today() - timedelta(days=3)
    _crossings(store, "s1", day)
    report = store.retail_report("s1", day=day)["demografiya"]

    row = store.rollup_demography("s1", day)

    assert row["counted"] == report["hisoblangan"]
    assert row["age_18_30"] == report["yosh"]["18-30"]
    assert round(row["ayol"] / row["counted"] * 100) == report["jins"]["ayol"]


def test_writing_the_same_day_twice_does_not_double_it(store: EventStore) -> None:
    """Yig'ish qayta ishga tushsa (bulut restart bo'lsa) son ikki
    barobar bo'lib ketmasin."""
    day = date.today() - timedelta(days=2)
    _crossings(store, "s1", day)

    store.rollup_demography("s1", day)
    store.rollup_demography("s1", day)

    assert store.demography_range("s1", start=day, end=day)["hisoblangan"] == 10


def test_a_day_with_no_visitors_is_still_recorded(store: EventStore) -> None:
    """«Hech kim kirmagan» ham ma'lumot.

    Yozmasak, keyingi yig'ishda o'sha kun har safar qaytadan
    tekshirilardi — hodisalar esa allaqachon o'chirilgan bo'lardi.
    """
    day = date.today() - timedelta(days=2)

    store.rollup_demography("s1", day)

    assert store.demography_range("s1", start=day, end=day)["kunlar"] == 1


# ── Yetishmayotgan kunlarni yig'ish ──────────────────────────────────


def test_a_gap_of_several_days_is_filled_in_one_pass(store: EventStore) -> None:
    """Bulut bir necha soat o'chib tursa yoki qurilma hodisalarni
    kechikib yuborsa, o'sha kunlar tashlab ketilmasin."""
    today = date.today()
    for back in (1, 2, 3):
        _crossings(store, "s1", today - timedelta(days=back), first_track=back * 100)

    written = store.rollup_pending_demography("s1")

    assert written == store.ROLLUP_LOOKBACK_DAYS
    assert store.demography_range(
        "s1", start=today - timedelta(days=3), end=today - timedelta(days=1)
    )["hisoblangan"] == 30


def test_today_is_never_rolled_up(store: EventStore) -> None:
    """Bugungi kun hali TUGAMAGAN.

    Yozib qo'yilsa, kun davomida panel eskirgan yig'indini
    ko'rsatardi — hisobot esa o'sha kunni jonli hisoblaydi va ikkalasi
    bir-biriga mos kelmasdi.
    """
    today = date.today()
    _crossings(store, "s1", today)

    store.rollup_pending_demography("s1")

    assert store.demography_range("s1", start=today, end=today)["kunlar"] == 0


def test_an_already_written_day_is_not_recomputed(store: EventStore) -> None:
    today = date.today()
    store.rollup_demography("s1", today - timedelta(days=1))

    written = store.rollup_pending_demography("s1")

    assert written == store.ROLLUP_LOOKBACK_DAYS - 1


# ── Davr bo'yicha o'qish ─────────────────────────────────────────────


def test_a_week_adds_up_the_days_inside_it(store: EventStore) -> None:
    today = date.today()
    for back in (1, 3, 6):
        _crossings(store, "s1", today - timedelta(days=back), first_track=back * 100)
        store.rollup_demography("s1", today - timedelta(days=back))
    # Oynadan tashqarida — qo'shilmasligi kerak.
    _crossings(store, "s1", today - timedelta(days=20), first_track=9000)
    store.rollup_demography("s1", today - timedelta(days=20))

    week = store.demography_range("s1", start=today - timedelta(days=7), end=today - timedelta(days=1))

    assert week["hisoblangan"] == 30
    # Namunada 18-30 guruhida to'rt kishi (24, 29, 28, 22) — uch kun × 4.
    assert week["yosh"]["18-30"] == 12


def test_percentages_come_from_totals_not_from_daily_averages(store: EventStore) -> None:
    """Kunlik foizlarning o'rtachasi noto'g'ri bo'lardi: 2 mijozli kun
    500 mijozli kun bilan teng og'irlikka ega bo'lib qolardi."""
    today = date.today()
    # Birinchi kun: 1 ayol.  Ikkinchi kun: 9 erkak.
    _crossings(store, "s1", today - timedelta(days=1), people=[("ayol", 30)], first_track=10)
    _crossings(
        store, "s1", today - timedelta(days=2),
        people=[("erkak", 30)] * 9, first_track=20,
    )
    store.rollup_demography("s1", today - timedelta(days=1))
    store.rollup_demography("s1", today - timedelta(days=2))

    week = store.demography_range("s1", start=today - timedelta(days=7), end=today - timedelta(days=1))

    # To'g'ri javob 10% (1/10), kunlik o'rtacha esa 50% berardi.
    assert week["jins"]["ayol"] == 10


def test_the_owner_sees_how_many_days_actually_had_visitors(store: EventStore) -> None:
    """30 kundan faqat 5 tasida ma'lumot bo'lsa, qurilma o'sha kunlari
    ishlamagan — va buni do'kon egasi bilishi kerak.  Bitta son bilan
    bu jimgina yashirinardi."""
    today = date.today()
    _crossings(store, "s1", today - timedelta(days=1))
    store.rollup_pending_demography("s1")

    week = store.demography_range("s1", start=today - timedelta(days=7), end=today - timedelta(days=1))

    assert week["kunlar"] == 7
    assert week["mijozli_kunlar"] == 1


def test_an_empty_period_never_divides_by_zero(store: EventStore) -> None:
    today = date.today()

    answer = store.demography_range("s1", start=today - timedelta(days=30), end=today)

    assert answer["hisoblangan"] == 0
    assert answer["jins"] == {"ayol": 0, "erkak": 0}


# ── Eng qimmat xato: tartib ──────────────────────────────────────────


def test_the_yearly_numbers_survive_the_events_being_deleted(store: EventStore) -> None:
    """Butun g'oyaning mohiyati.

    Xom hodisalar tarif muddatida o'chiriladi.  Agar yig'indi ulardan
    OLDIN yozilgan bo'lsa, o'tgan yil raqamlari qoladi; aks holda
    hisobot bo'sh chiqardi va tarixni tiklashning iloji bo'lmasdi.
    """
    today = date.today()
    old_day = today - timedelta(days=200)
    _crossings(store, "s1", old_day)
    store.rollup_demography("s1", old_day)

    # Tarif muddati o'tdi — hodisalar o'chirildi.
    store.purge_site("s1", retention_days=30)

    assert store.retail_report("s1", day=old_day)["demografiya"]["hisoblangan"] == 0
    year = store.demography_range("s1", start=today - timedelta(days=365), end=today)
    assert year["hisoblangan"] == 10, "yig'indi hodisalarsiz ham qolishi kerak"


def test_the_rollup_runs_before_the_purge_in_maintenance() -> None:
    """Tartib kodda ham qulflanadi.

    Birov keyinchalik tozalashni yuqoriga ko'chirsa, yig'indi bo'sh
    yozila boshlardi va buni faqat bir oydan keyin, hisobot bo'shab
    qolganda sezardik.
    """
    source = (
        Path(__file__).resolve().parents[1] / "cloud" / "main.py"
    ).read_text(encoding="utf-8")
    block = source[source.index("def _purge_expired_events") :]
    block = block[: block.index("\ndef ")]

    # Yig'ish endi `_rollup_site_history` orqali: u purge'dan OLDIN
    # chaqiriladi va muvaffaqiyatsiz bo'lsa purge o'tkazib yuboriladi.
    # (2026-08-30 dan u demografiya bilan birga retail raqamlarini ham
    # yozadi — himoya ikkalasiga baravar tegishli.)
    assert block.index("_rollup_site_history") < block.index("purge_site")
    assert "continue" in block[: block.index("purge_site")], (
        "rollup xatosida sayt hodisalari purge qilinmasligi kerak"
    )


def test_the_aggregate_outlives_the_events_it_came_from() -> None:
    """Yig'indi hodisalardan uzoqroq saqlanadi — aks holda «o'tgan
    yilning shu oyi bilan solishtirish» hech qachon mumkin
    bo'lmasdi."""
    assert EventStore.DEMOGRAPHY_RETENTION_DAYS >= 730


# ── Sonlar (foiz yoniga) ─────────────────────────────────────────────


def test_gender_counts_are_exposed_alongside_percentages(store: EventStore) -> None:
    """Do'kon egasi "nechtasi" deb so'raydi — foizning o'zi javob emas.

    Sonlar ham bugungi jonli hisobotda, ham davr yig'indisida bo'lishi
    kerak; foizlar orqaga moslik uchun o'z joyida qoladi.
    """
    day = date.today() - timedelta(days=2)
    _crossings(store, "s1", day)

    report = store.retail_report("s1", day=day)["demografiya"]
    assert report["jins_soni"] == {"ayol": 6, "erkak": 4}
    assert report["jins"]["ayol"] == 60  # foiz o'z joyida

    store.rollup_demography("s1", day)
    answer = store.demography_range("s1", start=day, end=day)
    assert answer["jins_soni"] == {"ayol": 6, "erkak": 4}
    # Qamrov ko'rsatkichi: davrda jami kirganlar soni ham javobda.
    assert answer["kirgan"] == 10


def test_gender_counts_are_empty_when_nothing_was_measured(store: EventStore) -> None:
    day = date.today() - timedelta(days=2)
    report = store.retail_report("s1", day=day)["demografiya"]
    assert report["jins_soni"] == {}
