"""Tariflar va texnik cheklovlar."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Literal

from chaqimchi_ai.sotqin_profile import GUARANTEED_CAMERAS, MAX_CAMERAS

PlanTier = Literal[
    # Dastlabki tijoriy mahsulot — Intel N100 asosidagi 4 kamerali do'kon MVP.
    "lite",
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

# Sotqin platforma bazasi; AI funksiyalar kamera bo'yicha ustiga qo'shiladi.
LITE_MONTHLY_PRICE_USD_CENTS = 2_000
DEFAULT_USD_RATE_UZS = 13_000


def usd_rate_uzs() -> int:
    """Hisob-faktura uchun USD/UZS kursi.

    Lite narxi USD'da qat'iy ($30), Payme/Click esa UZS qabul qiladi. Kurs
    serverda boshqariladi va hisob ochilgan paytdagi UZS summa invoice ichida
    saqlanib qoladi. Tashqi kurs servisiga runtime bog'liqlik ataylab yo'q.
    """
    raw = os.environ.get("CHAQIMCHI_USD_RATE_UZS", "").strip()
    if not raw:
        return DEFAULT_USD_RATE_UZS
    try:
        rate = int(raw)
    except ValueError as exc:
        raise ValueError("CHAQIMCHI_USD_RATE_UZS butun son bo'lishi kerak") from exc
    if not 1_000 <= rate <= 100_000:
        raise ValueError("CHAQIMCHI_USD_RATE_UZS 1000–100000 oralig'ida bo'lishi kerak")
    return rate


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
    #: USD'da sotiladigan tarif uchun sentdagi qat'iy narx. 0 — faqat UZS.
    monthly_price_usd_cents: int = 0

    @property
    def is_per_person(self) -> bool:
        return self.price_per_person_uzs > 0

    @property
    def monthly_price_usd(self) -> float:
        return self.monthly_price_usd_cents / 100

    def monthly_price(self, persons: int = 0) -> int:
        """Oylik to‘lov.

        Xodim tarifida: eng kam narx yoki `xodim × narx` — qaysi biri katta.
        Kamera tarifida `persons` e’tiborga olinmaydi.
        """
        if self.monthly_price_usd_cents:
            # Sent × (so'm / dollar) / 100. Yuqoriga yaxlitlash bir sentlik
            # qoldiq sabab invoice summasi kamayib ketmasligini ta'minlaydi.
            return (self.monthly_price_usd_cents * usd_rate_uzs() + 99) // 100
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
    "lite": PlanLimits(
        # 8 kamera apparat maksimumi, ammo sotiladigan SLA hozir 4 kamera.
        max_cameras=GUARANTEED_CAMERAS,
        max_persons=200,
        retention_days=30,
        telegram_allowed=True,
        # Faqat fallback/display qiymat; amaldagi invoice `monthly_price()`
        # orqali CHAQIMCHI_USD_RATE_UZS bilan hisoblanadi.
        monthly_price_uzs=LITE_MONTHLY_PRICE_USD_CENTS * DEFAULT_USD_RATE_UZS // 100,
        # Sotqin, NVR/kameralar va montaj alohida smeta qilinadi.
        install_price_uzs=0,
        monthly_price_usd_cents=LITE_MONTHLY_PRICE_USD_CENTS,
    ),
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
        max_cameras=MAX_CAMERAS,
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
