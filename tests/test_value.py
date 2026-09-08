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
    # Panel bilan bitta yozuv: vergul kasr belgisi, katalogdagi «so'm».
    assert "3,2 mln so'm" in text
    assert "299 000 so'm" in text
    assert "10,7×" in text
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
    assert uzs(3_200_000) == "3,2 mln so'm"
    assert uzs(2_000_000) == "2 mln so'm"
    assert uzs(299_000) == "299 000 so'm"


# ── Ishonchsiz hisobni ko'rsatmaslik ────────────────────────────────────


def test_a_broken_visitor_count_produces_no_money_figure() -> None:
    """Jonli serverda ushlandi.

    Pilot do'konda kirish chizig'i noto'g'ri sozlangani uchun oyiga
    atigi 26 tashrif sanalgan.  4.5 mln kunlik savdo bilan hisob
    "har tashrif 5.4 mln so'm" va "64 mln so'm yo'qotildi" chiqardi —
    bunday raqam mahsulotga ishonchni bir zumda yo'q qiladi.
    """
    assert revenue_per_visitor(daily_revenue_uzs=4_500_000 * 31, visitors=26) is None
    assert queue_cost(queue_episodes=12, daily_revenue_uzs=4_500_000 * 31, visitors=26) is None


def test_too_few_visitors_to_average() -> None:
    """Kam sonda bitta chetlanish butun o'rtachani buzadi."""
    assert revenue_per_visitor(daily_revenue_uzs=1_000_000, visitors=29) is None
    assert revenue_per_visitor(daily_revenue_uzs=1_000_000, visitors=30) is not None


def test_a_high_ticket_shop_still_works_within_reason() -> None:
    """Chegara haqiqiy qimmat do'konni ham o'tkazishi kerak."""
    # 100 tashrif, kuniga 50 mln savdo → har tashrif 500 000 so'm.
    assert revenue_per_visitor(daily_revenue_uzs=50_000_000, visitors=100) == 500_000


# ── Avtomatik konversiya (capture rate) — kameradan, cheksiz ─────────────
#
# Raqobatchining bosh o'lchovi (visit ÷ traffic).  `passed` — do'kongacha
# yetgan odam (A1: eshik oldida ko'ringan, A2: oldidan o'tgan).  Bu
# testlar chekli konversiya bilan bir xil intizomni qo'riqlaydi: `passed`
# yo'q bo'lsa javob yo'q, kichik namunada foiz yo'q, «100% dan ortiq»
# chiqmaydi.

from cloud.value import capture_rate, capture_rate_line  # noqa: E402


def test_no_capture_rate_until_the_device_reports_passersby() -> None:
    assert capture_rate(entered=120, passed=None) is None
    assert capture_rate_line(entered=120, passed=None) is None


def test_capture_rate_is_entered_over_passed() -> None:
    data = capture_rate(entered=35, passed=100)
    assert data == {"entered": 35, "passed": 100, "percent": 35}


def test_capture_rate_hides_percent_on_a_small_sample() -> None:
    """19 o'tib 10 kirsa «53%» tasodif — faqat sonlar ko'rsatiladi."""
    data = capture_rate(entered=10, passed=19)
    assert data["percent"] is None
    assert "yaqinlashdi" in capture_rate_line(entered=10, passed=19)


def test_capture_rate_refuses_more_entered_than_passed() -> None:
    """Kirgan «o'tgan»dan ko'p — sanoq buzuq, foiz ko'rsatilmaydi."""
    assert capture_rate(entered=140, passed=100)["percent"] is None


def test_capture_rate_line_shows_the_funnel() -> None:
    assert capture_rate_line(entered=350, passed=1000) == (
        "🚶 <b>1000</b> yaqinlashdi → 350 kirdi (<b>35%</b>)"
    )


from cloud.value import select_passed  # noqa: E402


def test_outer_camera_is_the_denominator_when_present() -> None:
    """A2: tashqi kamera bo'lsa uning «o'tdi»si ustun."""
    assert select_passed(entrance_seen=400, outer_seen=1000) == 1000


def test_falls_back_to_the_entrance_camera() -> None:
    """A1: tashqi kamera yo'q — kirish kamerasi «yaqinlashdi»si."""
    assert select_passed(entrance_seen=400, outer_seen=None) == 400


def test_no_denominator_until_the_device_sends_one() -> None:
    assert select_passed(entrance_seen=None, outer_seen=None) is None
