"""Tariflar va texnik cheklovlar."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Literal

PlanTier = Literal[
    # Kamera bo'yicha — do'kon, ombor, ofis xavfsizligi
    "starter",
    "business",
    "enterprise",
    # Xodim bo'yicha — davomat. Qiymat kamera sonida emas, xodim sonida:
    # 200 xodimli zavodga 2 kamera yetadi, lekin 200 ta yuz kerak.
    "staff_starter",
    "staff_business",
    "staff_enterprise",
]


@dataclass(frozen=True)
class PlanLimits:
    max_cameras: int
    max_persons: int
    retention_days: int
    telegram_allowed: bool
    #: Kamera tariflarida — aniq narx. Xodim tariflarida — eng kam narx
    #: ("... dan boshlab"). Aniq summa `monthly_price()` dan olinadi.
    monthly_price_uzs: int
    install_price_uzs: int
    #: Har bir xodim uchun narx. 0 — tarif kamera bo'yicha.
    price_per_person_uzs: int = 0

    @property
    def is_per_person(self) -> bool:
        return self.price_per_person_uzs > 0

    def monthly_price(self, persons: int = 0) -> int:
        """Oylik to‘lov.

        Xodim tarifida: eng kam narx yoki `xodim × narx` — qaysi biri katta.
        Kamera tarifida `persons` e’tiborga olinmaydi.
        """
        if not self.is_per_person:
            return self.monthly_price_uzs
        return max(self.monthly_price_uzs, self.price_per_person_uzs * max(0, persons))

    def effective_max_persons(self, persons: int = 0) -> int:
        """Bazaga necha kishi sig‘adi.

        Xodim tarifida mijoz nechta xodim uchun to‘lasa, shuncha qo‘sha oladi —
        101-chisini qo‘shmoqchi bo‘lsa tarifni kengaytirishi kerak. Tijorat
        mantiqi va texnik cheklov shu yerda bir joyga keladi.
        """
        if not self.is_per_person:
            return self.max_persons
        return max(0, persons) or self.max_persons


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
    # ── Davomat tariflari (xodim bo'yicha) ────────────────────────────────
    #
    # Katta tarifda xodim arzonroq — shuning uchun mijoz o'sganda ko'tarilishni
    # o'zi so'raydi: 100 xodimda Business, 300 xodimda Enterprise arzonroq.
    "staff_starter": PlanLimits(
        max_cameras=2,
        max_persons=100,  # `persons` berilmasa shu ishlaydi
        retention_days=30,
        telegram_allowed=True,
        monthly_price_uzs=500_000,  # eng kam
        install_price_uzs=6_500_000,
        price_per_person_uzs=15_000,
    ),
    "staff_business": PlanLimits(
        max_cameras=5,
        max_persons=300,
        retention_days=90,
        telegram_allowed=True,
        monthly_price_uzs=1_200_000,
        install_price_uzs=9_500_000,
        price_per_person_uzs=12_000,
    ),
    "staff_enterprise": PlanLimits(
        max_cameras=15,
        max_persons=2000,
        retention_days=365,
        telegram_allowed=True,
        monthly_price_uzs=2_500_000,
        install_price_uzs=15_000_000,
        price_per_person_uzs=9_000,
    ),
}


def cheapest_plan_for(persons: int) -> tuple[str, int]:
    """Shu xodim soniga eng arzon davomat tarifi. (tarif, oylik narx)

    Sotuvchi qo‘lda hisoblamasin — noto‘g‘ri tarif taklif qilish oson.
    """
    options = [
        (name, limits.monthly_price(persons))
        for name, limits in PLANS.items()
        if limits.is_per_person and persons <= limits.max_persons
    ]
    if not options:
        return "staff_enterprise", PLANS["staff_enterprise"].monthly_price(persons)
    return min(options, key=lambda x: x[1])


def get_plan(plan: str) -> PlanLimits:
    key = plan.lower().strip()
    if key not in PLANS:
        raise ValueError(f"Noma'lum tarif: {plan}. Qabul: {list(PLANS)}")
    return PLANS[key]  # type: ignore[index]
