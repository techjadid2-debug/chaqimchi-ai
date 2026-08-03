"""To'lov provayderlari sozlamalari — muhit o'zgaruvchilaridan.

Kalitlar konfig faylda emas, `.env` da: ular maxfiy va serverga bog'liq.
Sozlanmagan provayder shunchaki "yo'q" bo'ladi — server baribir ishlaydi.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

#: Payme summani tiyinda kutadi, Click — so'mda.
TIYIN = 100


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class PaymeConfig:
    """Payme Merchant API (https://developer.help.paycom.uz)."""

    merchant_id: str
    key: str
    checkout_url: str = "https://checkout.paycom.uz"
    #: `account` ichidagi maydon nomi — Payme kabinetida shu nom ko'rsatiladi.
    account_field: str = "invoice_id"

    @property
    def configured(self) -> bool:
        return bool(self.merchant_id and self.key)


@dataclass(frozen=True)
class ClickConfig:
    """Click SHOP-API (Prepare / Complete)."""

    service_id: str
    merchant_id: str
    secret_key: str
    checkout_url: str = "https://my.click.uz/services/pay"

    @property
    def configured(self) -> bool:
        return bool(self.service_id and self.merchant_id and self.secret_key)


def payme_config() -> PaymeConfig:
    return PaymeConfig(
        merchant_id=_env("CHAQIMCHI_PAYME_MERCHANT_ID"),
        key=_env("CHAQIMCHI_PAYME_KEY"),
        checkout_url=_env("CHAQIMCHI_PAYME_CHECKOUT_URL", "https://checkout.paycom.uz"),
        account_field=_env("CHAQIMCHI_PAYME_ACCOUNT_FIELD", "invoice_id"),
    )


def click_config() -> ClickConfig:
    return ClickConfig(
        service_id=_env("CHAQIMCHI_CLICK_SERVICE_ID"),
        merchant_id=_env("CHAQIMCHI_CLICK_MERCHANT_ID"),
        secret_key=_env("CHAQIMCHI_CLICK_SECRET"),
        checkout_url=_env("CHAQIMCHI_CLICK_CHECKOUT_URL", "https://my.click.uz/services/pay"),
    )


def public_url() -> str:
    """To'lovdan keyin mijoz qaytadigan tashqi manzil (`https://cloud.example.uz`)."""
    return _env("CHAQIMCHI_PUBLIC_URL").rstrip("/")
