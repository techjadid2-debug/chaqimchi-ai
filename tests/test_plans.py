from chaqimchi_ai.licensing.plans import PLANS, get_plan


def test_lite_is_20_usd_base_and_uses_configured_rate(monkeypatch) -> None:
    monkeypatch.setenv("CHAQIMCHI_USD_RATE_UZS", "12500")
    lite = PLANS["lite"]
    assert lite.monthly_price_usd == 20
    assert lite.monthly_price() == 250_000
    assert lite.max_cameras == 8
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
