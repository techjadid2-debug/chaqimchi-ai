"""Tariflar va texnik cheklovlar."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Literal

PlanTier = Literal["starter", "business", "enterprise"]


@dataclass(frozen=True)
class PlanLimits:
    max_cameras: int
    max_persons: int
    retention_days: int
    telegram_allowed: bool
    monthly_price_uzs: int
    install_price_uzs: int


PLANS: Dict[PlanTier, PlanLimits] = {
    "starter": PlanLimits(
        max_cameras=1,
        max_persons=50,
        retention_days=30,
        telegram_allowed=False,
        monthly_price_uzs=790_000,
        install_price_uzs=6_500_000,
    ),
    "business": PlanLimits(
        max_cameras=3,
        max_persons=200,
        retention_days=90,
        telegram_allowed=True,
        monthly_price_uzs=1_490_000,
        install_price_uzs=9_500_000,
    ),
    "enterprise": PlanLimits(
        max_cameras=8,
        max_persons=2000,
        retention_days=365,
        telegram_allowed=True,
        monthly_price_uzs=2_990_000,
        install_price_uzs=15_000_000,
    ),
}


def get_plan(plan: str) -> PlanLimits:
    key = plan.lower().strip()
    if key not in PLANS:
        raise ValueError(f"Noma'lum tarif: {plan}. Qabul: {list(PLANS)}")
    return PLANS[key]  # type: ignore[index]
