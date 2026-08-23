"""Pulga tarjima — nima aytiladi va nima AYTILMAYDI.

Bu qatlamning butun qiymati ishonchda: bir marta o'ylab topilgan raqam
ko'rsatsak, mijoz uni tekshiradi, to'g'ri kelmaydi va boshqa hech qachon
ishonmaydi.  Shuning uchun testlarning yarmi raqamni emas, raqamning
YO'QLIGINI tekshiradi.
"""

from __future__ import annotations

from cloud.value import daily_line, monthly_receipt, queue_cost, revenue_per_visitor, uzs

REPORT = {"traffic": {"entered": 100}, "queue": {"alerts": 3}}


# ── Hisoblanmaydigan holatlar ────────────────────────────────────────────


def test_no_money_line_when_the_owner_never_told_us_their_revenue() -> None:
    """Standart qiymat bilan to'ldirish — o'ylab topilgan raqamni haqiqat qilib ko'rsatish."""
    assert daily_line(REPORT, 0) is None
    assert revenue_per_visitor(daily_revenue_uzs=0, visitors=100) is None


def test_no_money_line_when_nobody_came() -> None:
    """Nolga bo'lish emas, shunchaki hisoblab bo'lmaydi."""
    report = {"traffic": {"entered": 0}, "queue": {"alerts": 3}}
    assert daily_line(report, 5_000_000) is None


def test_no_money_line_on_a_calm_day() -> None:
    """Navbat uzun bo'lmagan kunda yo'qotish haqida gapirish — shovqin."""
    report = {"traffic": {"entered": 100}, "queue": {"alerts": 0}}
    assert daily_line(report, 5_000_000) is None


# ── Hisob mijozning O'Z raqamlaridan chiqadi ────────────────────────────


def test_revenue_per_visitor_comes_from_the_owners_own_numbers() -> None:
    """O'rtacha chek O'YLAB TOPILMAYDI — savdo / haqiqiy tashrif soni."""
    assert revenue_per_visitor(daily_revenue_uzs=4_500_000, visitors=100) == 45_000


def test_queue_cost_shows_its_whole_arithmetic() -> None:
    """Mijoz raqamni tekshira olishi kerak — barcha oraliq qiymat javobda."""
    cost = queue_cost(queue_episodes=3, daily_revenue_uzs=4_500_000, visitors=100)
    assert cost == {
        "episodes": 3,
        "lost_customers": 3,
        "per_visitor_uzs": 45_000,
        "lost_uzs": 135_000,
    }


def test_daily_line_always_says_it_is_an_estimate() -> None:
    line = daily_line(REPORT, 4_500_000)
    assert line is not None
    assert "Taxminan" in line
    assert "bo'lishi mumkin" in line


# ── Oylik chek ───────────────────────────────────────────────────────────


def test_monthly_receipt_compares_the_loss_with_the_price() -> None:
    """Mijoz obunani uzaytirishdan oldin aynan shu savolga javob izlaydi."""
    text = monthly_receipt(
        site_name="Oq Saroy",
        month_label="Avgust",
        lost_uzs=3_200_000,
        monthly_price_uzs=299_000,
    )
    assert "3.2 mln so'm" in text
    assert "299 000 so'm" in text
    assert "10.7×" in text
    assert "taxminiy" in text


def test_monthly_receipt_does_not_boast_when_the_loss_is_small() -> None:
    """Yo'qotish obunadan kam bo'lsa "necha barobar" degan maqtov CHIQMASIN."""
    text = monthly_receipt(
        site_name="Oq Saroy",
        month_label="Avgust",
        lost_uzs=120_000,
        monthly_price_uzs=299_000,
    )
    assert "×" not in text
    assert "120 000 so'm" in text


# ── Ko'rinish ────────────────────────────────────────────────────────────


def test_large_sums_are_readable() -> None:
    """«3200000 so'm» o'qilmaydi — do'kon egasi nolni sanab o'tirmasin."""
    assert uzs(3_200_000) == "3.2 mln so'm"
    assert uzs(2_000_000) == "2 mln so'm"
    assert uzs(299_000) == "299 000 so'm"
