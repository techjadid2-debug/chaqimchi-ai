"""Saqlangan karta: ulash, tasdiqlash va undan pul yechish.

Nega alohida modul.  `payme.py` va `click.py` — **kiruvchi** callback
qabul qiluvchilar: provayder bizga so'rov yuboradi, biz javob beramiz.
Karta esa teskari yo'nalish: BIZ provayderga so'rov yuboramiz.  Ikkala
mantiqni bitta faylga qo'shish "kim kimga qo'ng'iroq qilyapti" degan
savolni chalkashtirardi.

Oqim uch qadam va u ikkala provayderda ham bir xil:

    1. `bind_start`   — karta raqami + amal qilish muddati → token,
                        provayder mijozga SMS yuboradi;
    2. `bind_confirm` — SMS kodi → token tasdiqlanadi;
    3. `charge`       — tokendan summa yechiladi.

**Karta raqami bizda SAQLANMAYDI** va hech qayerga yozilmaydi: u faqat
birinchi so'rovda provayderga o'tadi.  Bizda qoladigan narsa — token
(shifrlangan) va oxirgi to'rt raqam.

Tarmoq chaqiruvi TASHQARIDAN beriladi (`transport`): shu sababdan
modulni provayderga ulanmasdan sinash mumkin va testda soxta javob
berish uchun `httpx` ni monkeypatch qilish shart emas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Awaitable, Dict, Optional, Protocol

from cloud.payments.config import TIYIN, ClickConfig, PaymeConfig

#: Provayderga chiqadigan so'rov uchun kutish muddati.
#:
#: 20 soniya: to'lov provayderi SMS yuborishni kutadi va bu sekin
#: amal, lekin cheksiz emas — usiz kartani ulash ekrani mijozda
#: abadiy "yuborilmoqda" bo'lib qotib qolardi.
TIMEOUT_SEC = 20.0

#: `8600 1234 5678 9012` → `8600 **** **** 9012`.
_DIGITS = re.compile(r"\D+")


class CardError(Exception):
    """Provayder rad etdi.  `message` mijozga ko'rsatiladigan matn."""

    def __init__(self, message: str, *, retriable: bool = False) -> None:
        super().__init__(message)
        self.message = message
        #: Qayta urinish MA'NOLIMI.  «Mablag' yetarli emas» — ha
        #: (ertaga pul tushishi mumkin); «karta bloklangan» — yo'q.
        #: Avtomatik yechish shu bayroqqa qarab qayta urinadi.
        self.retriable = retriable


def mask_pan(number: str) -> str:
    """Ko'rsatish uchun niqob.  To'liq raqam HECH QAYERDA saqlanmaydi."""
    digits = _DIGITS.sub("", number or "")
    if len(digits) < 4:
        return "**** ****"
    return f"{digits[:4]} **** **** {digits[-4:]}"


@dataclass(frozen=True)
class BoundCard:
    """Provayder qaytargan karta.  `verified` — SMS tasdiqlanganmi."""

    token: str
    masked_pan: str
    verified: bool = False
    expires_at: Optional[str] = None


class Transport(Protocol):
    """Provayderga JSON so'rov yuboradigan chaqiruv."""

    def __call__(
        self, url: str, *, json: Dict[str, Any], headers: Dict[str, str]
    ) -> Awaitable[Dict[str, Any]]: ...


async def http_transport(
    url: str, *, json: Dict[str, Any], headers: Dict[str, str]
) -> Dict[str, Any]:
    """Haqiqiy tarmoq chaqiruvi.  Test uni almashtiradi."""
    import httpx

    async with httpx.AsyncClient(timeout=TIMEOUT_SEC) as client:
        response = await client.post(url, json=json, headers=headers)
        if response.status_code >= 500:
            # 5xx — provayder tomonidagi vaqtincha nosozlik, ya'ni
            # qayta urinish ma'noli.  4xx esa bizning so'rovimiz xato.
            raise CardError("To‘lov xizmati javob bermadi", retriable=True)
        try:
            return dict(response.json())
        except ValueError as exc:
            raise CardError("To‘lov xizmatidan tushunarsiz javob") from exc


# ── Payme (Subscribe API) ──────────────────────────────────────────────
#
# Hujjat: https://developer.help.paycom.uz/metody-subscribe-api
# Chaqiruvlar: `cards.create` → `cards.get_verify_code` → `cards.verify`
# → `receipts.create` → `receipts.pay`.


def _payme_url(config: PaymeConfig) -> str:
    # Subscribe API checkout hostida turadi va `/api` yo'lida javob
    # beradi (`checkout.paycom.uz/api`).
    return f"{config.checkout_url.rstrip('/')}/api"


def _payme_headers(config: PaymeConfig) -> Dict[str, str]:
    return {"X-Auth": config.merchant_id, "Content-Type": "application/json"}


def _payme_result(payload: Dict[str, Any]) -> Dict[str, Any]:
    error = payload.get("error")
    if error:
        message = error.get("message") if isinstance(error, dict) else None
        # Payme xato matnini uch tilda lug'at qilib qaytaradi.
        if isinstance(message, dict):
            message = message.get("uz") or message.get("ru") or message.get("en")
        raise CardError(str(message or "To‘lov xizmati rad etdi"))
    return dict(payload.get("result") or {})


async def _payme_bind_start(
    config: PaymeConfig, *, number: str, expire: str, transport: Transport
) -> BoundCard:
    result = _payme_result(
        await transport(
            _payme_url(config),
            json={
                "method": "cards.create",
                "params": {
                    "card": {"number": _DIGITS.sub("", number), "expire": _DIGITS.sub("", expire)},
                    # `save: true` — token bir martalik emas, saqlanadi.
                    "save": True,
                },
            },
            headers=_payme_headers(config),
        )
    )
    card = dict(result.get("card") or {})
    token = str(card.get("token") or "")
    if not token:
        raise CardError("To‘lov xizmati karta tokenini bermadi")
    # Kod yuborish ALOHIDA chaqiruv: `cards.create` faqat token beradi.
    _payme_result(
        await transport(
            _payme_url(config),
            json={"method": "cards.get_verify_code", "params": {"token": token}},
            headers=_payme_headers(config),
        )
    )
    return BoundCard(token=token, masked_pan=mask_pan(number), verified=bool(card.get("verify")))


async def _payme_bind_confirm(
    config: PaymeConfig, *, token: str, code: str, transport: Transport
) -> BoundCard:
    result = _payme_result(
        await transport(
            _payme_url(config),
            json={"method": "cards.verify", "params": {"token": token, "code": code}},
            headers=_payme_headers(config),
        )
    )
    card = dict(result.get("card") or {})
    # Tasdiqlangandan keyin token ALMASHADI — eskisini saqlab qolish
    # keyingi yechishni jimgina rad ettirardi.
    return BoundCard(
        token=str(card.get("token") or token),
        masked_pan=str(card.get("number") or ""),
        verified=bool(card.get("verify", True)),
    )


async def _payme_charge(
    config: PaymeConfig,
    *,
    token: str,
    amount_uzs: int,
    account: Dict[str, str],
    description: str,
    transport: Transport,
) -> str:
    receipt = _payme_result(
        await transport(
            _payme_url(config),
            json={
                "method": "receipts.create",
                "params": {
                    "amount": int(amount_uzs) * TIYIN,
                    "account": account,
                    "description": description,
                },
            },
            headers=_payme_headers(config),
        )
    )
    receipt_id = str((receipt.get("receipt") or {}).get("_id") or "")
    if not receipt_id:
        raise CardError("Hisob yaratilmadi", retriable=True)
    _payme_result(
        await transport(
            _payme_url(config),
            json={"method": "receipts.pay", "params": {"id": receipt_id, "token": token}},
            headers=_payme_headers(config),
        )
    )
    return receipt_id


# ── Click (Card Token API) ─────────────────────────────────────────────
#
# Hujjat: https://docs.click.uz/click-api-request (card_token/*).


def _click_url(config: ClickConfig, path: str) -> str:
    return f"https://api.click.uz/v2/merchant/card_token/{path}"


def _click_headers(config: ClickConfig) -> Dict[str, str]:
    # Click `Auth: merchant_user_id:digest:timestamp` kutadi; imzo
    # `click.py` dagi bilan bir xil usulda yasaladi.
    import hashlib
    import time

    stamp = str(int(time.time()))
    digest = hashlib.sha1(f"{stamp}{config.secret_key}".encode("utf-8")).hexdigest()
    return {
        "Auth": f"{config.merchant_id}:{digest}:{stamp}",
        "Content-Type": "application/json",
    }


def _click_result(payload: Dict[str, Any]) -> Dict[str, Any]:
    code = payload.get("error_code")
    if code is not None and int(code) != 0:
        raise CardError(str(payload.get("error_note") or "To‘lov xizmati rad etdi"))
    return dict(payload)


async def _click_bind_start(
    config: ClickConfig, *, number: str, expire: str, transport: Transport
) -> BoundCard:
    result = _click_result(
        await transport(
            _click_url(config, "request"),
            json={
                "service_id": int(config.service_id),
                "card_number": _DIGITS.sub("", number),
                "expire_date": _DIGITS.sub("", expire),
                # `temporary: 0` — token saqlanadi (takroriy to'lov uchun).
                "temporary": 0,
            },
            headers=_click_headers(config),
        )
    )
    token = str(result.get("card_token") or "")
    if not token:
        raise CardError("To‘lov xizmati karta tokenini bermadi")
    return BoundCard(token=token, masked_pan=mask_pan(number))


async def _click_bind_confirm(
    config: ClickConfig, *, token: str, code: str, transport: Transport
) -> BoundCard:
    result = _click_result(
        await transport(
            _click_url(config, "verify"),
            json={
                "service_id": int(config.service_id),
                "card_token": token,
                "sms_code": _DIGITS.sub("", code),
            },
            headers=_click_headers(config),
        )
    )
    return BoundCard(
        token=token, masked_pan=mask_pan(str(result.get("card_number") or "")), verified=True
    )


async def _click_charge(
    config: ClickConfig,
    *,
    token: str,
    amount_uzs: int,
    account: Dict[str, str],
    description: str,
    transport: Transport,
) -> str:
    result = _click_result(
        await transport(
            _click_url(config, "payment"),
            json={
                "service_id": int(config.service_id),
                "card_token": token,
                "amount": int(amount_uzs),
                # Bizning hisob raqamimiz — Click uni callbackda qaytaradi.
                "transaction_parameter": account.get("invoice_id", ""),
            },
            headers=_click_headers(config),
        )
    )
    payment_id = str(result.get("payment_id") or "")
    if not payment_id:
        raise CardError("To‘lov o‘tmadi", retriable=True)
    return payment_id


# ── Umumiy yuza ────────────────────────────────────────────────────────


async def bind_start(
    provider: str,
    config: Any,
    *,
    number: str,
    expire: str,
    transport: Transport = http_transport,
) -> BoundCard:
    """Karta raqamini tokenga almashtiradi va SMS yuborilishini so'raydi."""
    if provider == "payme":
        return await _payme_bind_start(config, number=number, expire=expire, transport=transport)
    if provider == "click":
        return await _click_bind_start(config, number=number, expire=expire, transport=transport)
    raise CardError(f"Noma'lum to‘lov provayderi: {provider}")


async def bind_confirm(
    provider: str,
    config: Any,
    *,
    token: str,
    code: str,
    transport: Transport = http_transport,
) -> BoundCard:
    """SMS kodini tekshiradi.  Shundan keyingina yechish mumkin."""
    if provider == "payme":
        return await _payme_bind_confirm(config, token=token, code=code, transport=transport)
    if provider == "click":
        return await _click_bind_confirm(config, token=token, code=code, transport=transport)
    raise CardError(f"Noma'lum to‘lov provayderi: {provider}")


async def charge(
    provider: str,
    config: Any,
    *,
    token: str,
    amount_uzs: int,
    account: Dict[str, str],
    description: str,
    transport: Transport = http_transport,
) -> str:
    """Tokendan summa yechadi.  Provayder tranzaksiyasining id sini qaytaradi."""
    if amount_uzs <= 0:
        raise CardError("Summa noto‘g‘ri")
    if provider == "payme":
        return await _payme_charge(
            config,
            token=token,
            amount_uzs=amount_uzs,
            account=account,
            description=description,
            transport=transport,
        )
    if provider == "click":
        return await _click_charge(
            config,
            token=token,
            amount_uzs=amount_uzs,
            account=account,
            description=description,
            transport=transport,
        )
    raise CardError(f"Noma'lum to‘lov provayderi: {provider}")


def available_providers(payme: PaymeConfig, click: ClickConfig) -> Dict[str, bool]:
    """Qaysi provayder kartani qabul qila oladi.

    Kalitlar egadan hali kelmagan, ya'ni ikkalasi ham `False` bo'lishi
    NORMAL holat — panel karta bo'limini shunda umuman ko'rsatmaydi
    (`capabilities` naqshi).
    """
    return {"payme": payme.configured, "click": click.configured}
