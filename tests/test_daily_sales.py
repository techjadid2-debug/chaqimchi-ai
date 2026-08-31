"""Chek soni va konversiya — «200 kirdi → 100 chek».

Konversiyaning maxraji bizda (kirish sanog'i), surati esa faqat do'kon
egasida: kassa bilan integratsiya yo'q va yaqin rejada ham yo'q.  Shu
sababdan bu yerdagi testlar ikki narsani qo'riqlaydi:

1. **Kiritilmagan kun BO'SH qoladi, nol emas.**  Nol «hech kim sotib
   olmadi» degani; bo'sh «ma'lumot yo'q».  Ikkalasini aralashtirish
   egaga do'koni haqida yolg'on gapirish demak.
2. **Kichik namunadan foiz chiqarilmaydi.**  3 kishi kirib 2 tasi
   sotib olsa «67%» chiqadi — bu o'lchov emas, tasodif.  🚻 qatori va
   `trust_score` shu intizomga allaqachon bo'ysunadi.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from cloud import value
from cloud.event_store import EventStore

DAY = date(2026, 8, 30)


@pytest.fixture
def store(tmp_path: Path) -> EventStore:
    return EventStore(sqlite_path=tmp_path / "events.db")


# ── Saqlash ──────────────────────────────────────────────────────────────


def test_a_day_without_receipts_stays_empty_not_zero(store: EventStore) -> None:
    assert store.daily_sales("site-1", DAY) is None


def test_receipts_entered_twice_overwrite_instead_of_duplicating(store: EventStore) -> None:
    """Ega kechqurun taxminiy son yozib, ertasiga kassadan aniqlashtiradi.

    Ikkinchi qator yaratilsa konversiya ikki xil javob berardi va qaysi
    biri to'g'ri ekani hech qayerdan bilinmasdi.
    """
    store.save_daily_sales("site-1", DAY, receipts=90)
    store.save_daily_sales("site-1", DAY, receipts=104)

    assert store.daily_sales("site-1", DAY)["receipts"] == 104


def test_receipts_belong_to_one_site_only(store: EventStore) -> None:
    store.save_daily_sales("site-1", DAY, receipts=100)

    assert store.daily_sales("site-2", DAY) is None


def test_a_negative_count_is_stored_as_zero(store: EventStore) -> None:
    """Manfiy chek ma'nosiz — API 422 qaytaradi, saqlagich esa nolga qisadi."""
    store.save_daily_sales("site-1", DAY, receipts=-5)

    assert store.daily_sales("site-1", DAY)["receipts"] == 0


# ── Konversiya qoidasi ───────────────────────────────────────────────────


def test_a_day_the_owner_never_filled_in_has_no_conversion() -> None:
    assert value.conversion(receipts=None, entered=200) is None


def test_the_conversion_is_a_percentage_when_the_day_is_big_enough() -> None:
    answer = value.conversion(receipts=100, entered=200)

    assert answer == {"receipts": 100, "entered": 200, "percent": 50}


def test_a_small_day_reports_numbers_not_a_percentage() -> None:
    """12 kishilik kunning foizi o'lchov emas, tasodif."""
    answer = value.conversion(receipts=8, entered=12)

    assert answer["percent"] is None
    assert answer["receipts"] == 8 and answer["entered"] == 12


def test_more_receipts_than_visitors_hides_the_percentage() -> None:
    """Chek kirganlardan ko'p bo'lishi — sanoq buzilganining belgisi.

    Jonli dalil bor: pilot do'konda chiziq noto'g'ri sozlangani uchun
    oyiga atigi 26 tashrif sanalgan.  «140% konversiya» bunday kunda
    butun hisobga bo'lgan ishonchni bir zumda yo'q qilardi.
    """
    answer = value.conversion(receipts=300, entered=200)

    assert answer["percent"] is None


def test_zero_receipts_is_data_not_a_missing_day() -> None:
    """Ega ataylab 0 yozgan bo'lsa bu ham javob — yashirilmaydi."""
    answer = value.conversion(receipts=0, entered=200)

    assert answer == {"receipts": 0, "entered": 200, "percent": 0}


# ── Xabardagi qator ──────────────────────────────────────────────────────


def test_the_line_says_how_many_visitors_bought() -> None:
    line = value.conversion_line(receipts=100, entered=200)

    assert "100" in line and "200" in line
    assert "har 2-mijoz" in line


def test_the_line_drops_the_ratio_when_almost_everyone_bought() -> None:
    """«har 1-mijoz sotib oldi» — ma'nosiz jumla."""
    line = value.conversion_line(receipts=190, entered=200)

    assert "har" not in line


def test_a_small_day_line_carries_no_percentage() -> None:
    line = value.conversion_line(receipts=8, entered=12)

    assert "%" not in line
    assert "8" in line and "12" in line


def test_no_receipts_means_no_line() -> None:
    assert value.conversion_line(receipts=None, entered=200) is None
