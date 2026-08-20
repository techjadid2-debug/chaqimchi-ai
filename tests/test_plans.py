from chaqimchi_ai.licensing.plans import PLANS, get_plan


def test_lite_is_20_usd_base_and_uses_configured_rate(monkeypatch) -> None:
    monkeypatch.setenv("CHAQIMCHI_USD_RATE_UZS", "12500")
    lite = PLANS["lite"]
    assert lite.monthly_price_usd == 20
    assert lite.monthly_price() == 250_000
    assert lite.max_cameras == 4
    assert lite.retention_days == 30


def test_lite_rejects_invalid_exchange_rate(monkeypatch) -> None:
    monkeypatch.setenv("CHAQIMCHI_USD_RATE_UZS", "xato")
    try:
        PLANS["lite"].monthly_price()
        assert False
    except ValueError as exc:
        assert "CHAQIMCHI_USD_RATE_UZS" in str(exc)


def test_plans_pricing_order() -> None:
    assert PLANS["starter"].monthly_price_uzs < PLANS["business"].monthly_price_uzs
    assert PLANS["business"].max_cameras < PLANS["enterprise"].max_cameras


def test_get_plan_invalid() -> None:
    try:
        get_plan("vip")
        assert False
    except ValueError:
        pass


def test_only_the_shop_plans_are_offered_for_sale() -> None:
    """Sotuvchiga sotilmaydigan tarif taklif qilinmasin.

    Eski tariflar `PLANS` da qoladi — mavjud obyektlar va hisob-fakturalar
    ular orqali hisoblanadi — lekin yangi obyekt yaratishda ko'rinmaydi.
    """
    from chaqimchi_ai.licensing.plans import SELLABLE_PLANS, is_sellable

    assert SELLABLE_PLANS == frozenset({"boshlangich", "biznes"})
    assert is_sellable("biznes") is True
    assert is_sellable("  BIZNES ") is True
    for legacy in ("lite", "starter", "business", "enterprise", "staff_starter"):
        assert legacy in PLANS, legacy  # hisob-kitob uchun hali kerak
        assert is_sellable(legacy) is False, legacy


def test_legacy_lite_keeps_its_price_and_all_of_its_features() -> None:
    """Sotuvdan chiqarish MAVJUD mijozdan hech narsa olib qo'ymasin.

    Ikki xavf bor edi va ikkalasi ham jimgina sodir bo'lardi:

    1. `lite` ni `biznes` ga ko'chirish — bu $20 dan $23 ga jimgina narx
       ko'tarish, holbuki sayt ularga $20 va'da qilgan;
    2. `/api/v1/edge/config` zaxira mantiqi `is_sellable()` ga tayanardi —
       `lite` sotuvdan chiqishi bilan qurilma hamma funksiyani yo'qotib,
       do'kon nazoratsiz qolardi.
    """
    from chaqimchi_ai.licensing.plans import plan_feature_codes

    lite = PLANS["lite"]
    assert lite.legacy is True
    assert lite.monthly_price() == 260_000  # $20 — o'zgarmaydi
    assert lite.max_cameras == PLANS["biznes"].max_cameras
    assert lite.max_persons == PLANS["biznes"].max_persons
    assert plan_feature_codes("lite") == plan_feature_codes("biznes")


def test_the_two_sellable_plans_land_on_round_uzbek_prices() -> None:
    """Saytdagi narx do'kon egasiga yumaloq ko'rinsin.

    Formula sent × kurs / 100 bo'lgani uchun standart kursda faqat butun
    dollar yumaloq so'm beradi.  `uzs_from_cents()` mingga yuqoriga
    yaxlitlaydi — shu sabab $11.40 ham 149 000 bo'lib chiqadi.
    """
    import os

    from chaqimchi_ai.licensing.plans import uzs_from_cents

    assert PLANS["boshlangich"].monthly_price() == 149_000
    assert PLANS["biznes"].monthly_price() == 299_000

    # Kurs ko'tarilsa narx ham ko'chadi, lekin baribir yumaloq qoladi.
    os.environ["CHAQIMCHI_USD_RATE_UZS"] = "14000"
    try:
        assert uzs_from_cents(1_140) % 1_000 == 0
        assert uzs_from_cents(2_300) % 1_000 == 0
        assert PLANS["biznes"].monthly_price() == 322_000
    finally:
        del os.environ["CHAQIMCHI_USD_RATE_UZS"]


def test_tarmoq_is_not_a_billable_tier() -> None:
    """Tarmoq — saytdagi qator, bazadagi tarif emas.

    Narxsiz tarif `PLANS` ga qo'shilsa `create_invoice` unga 0 so'mlik
    hisob-faktura yozib qo'yardi.  Tarmoq mijozining har do'koni o'zining
    `biznes` obyekti sifatida ochiladi.
    """
    assert "tarmoq" not in PLANS


def test_admin_panel_offers_exactly_the_sellable_plans() -> None:
    """HTML va kod bir-biridan ajralib ketmasin."""
    import re
    from pathlib import Path

    from chaqimchi_ai.licensing.plans import SELLABLE_PLANS

    html = (Path(__file__).resolve().parents[1] / "cloud" / "static" / "admin.html").read_text()
    form = html[html.index('id="cPlan"') : html.index("</select>", html.index('id="cPlan"'))]
    offered = set(re.findall(r'<option value="([^"]+)"', form))

    assert offered == set(SELLABLE_PLANS)
