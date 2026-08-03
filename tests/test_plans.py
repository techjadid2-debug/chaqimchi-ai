from chaqimchi_ai.licensing.plans import PLANS, get_plan


def test_plans_pricing_order() -> None:
    assert PLANS["starter"].monthly_price_uzs < PLANS["business"].monthly_price_uzs
    assert PLANS["business"].max_cameras < PLANS["enterprise"].max_cameras


def test_get_plan_invalid() -> None:
    try:
        get_plan("vip")
        assert False
    except ValueError:
        pass
