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


def test_only_the_shop_plan_is_offered_for_sale() -> None:
    """Sotuvchiga sotilmaydigan tarif taklif qilinmasin.

    Eski tariflar `PLANS` da qoladi — mavjud obyektlar va hisob-fakturalar
    ular orqali hisoblanadi — lekin yangi obyekt yaratishda ko'rinmaydi
    (`docs/DOKON_MVP.md`: faqat do'kon MVP sotiladi).
    """
    from chaqimchi_ai.licensing.plans import SELLABLE_PLANS, is_sellable

    assert SELLABLE_PLANS == frozenset({"lite"})
    assert is_sellable("lite") is True
    assert is_sellable("  LITE ") is True
    for legacy in ("starter", "business", "enterprise", "staff_starter"):
        assert legacy in PLANS, legacy  # hisob-kitob uchun hali kerak
        assert is_sellable(legacy) is False, legacy


def test_admin_panel_offers_exactly_the_sellable_plans() -> None:
    """HTML va kod bir-biridan ajralib ketmasin."""
    import re
    from pathlib import Path

    from chaqimchi_ai.licensing.plans import SELLABLE_PLANS

    html = (Path(__file__).resolve().parents[1] / "cloud" / "static" / "admin.html").read_text()
    form = html[html.index('id="cPlan"') : html.index("</select>", html.index('id="cPlan"'))]
    offered = set(re.findall(r'<option value="([^"]+)"', form))

    assert offered == set(SELLABLE_PLANS)
