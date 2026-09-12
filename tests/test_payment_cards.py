"""Saqlangan karta: ulash, tasdiqlash, yechish.

Nega bu test bor.  Karta tokeni — «pul yechish huquqi»: bazaning
nusxasi sizib ketsa u bilan to'lov qilish mumkin.  Shuning uchun
uchta narsa qulflanadi: token SHIFRLANADI, javobga CHIQMAYDI va
«kartani o'chir» deganda bazada QOLMAYDI.

Tarmoq chaqirilmaydi — `transport` tashqaridan beriladi va testda
soxta javob qaytaradi.  Provayder kalitlari hali egadan kelmagan,
ya'ni jonli sinov baribir imkonsiz.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest

from cloud.payments import cards
from cloud.payments.config import ClickConfig, PaymeConfig
from cloud.payments.store import PaymentStore
from cloud.store import CloudStore

PAYME = PaymeConfig(merchant_id="m1", key="k1")
CLICK = ClickConfig(service_id="7", merchant_id="m2", secret_key="s2")


@pytest.fixture
def store(tmp_path: Path) -> PaymentStore:
    return PaymentStore(CloudStore(tmp_path / "cloud.db"))


@pytest.fixture
def site(store: PaymentStore) -> str:
    return str(store.cloud.create_site("Do'kon", "biznes")["site_id"])


def _fake(answers: List[Dict[str, Any]]):
    """Ketma-ket javob qaytaradigan soxta transport.  So'rovlarni yozadi."""
    sent: List[Dict[str, Any]] = []

    async def transport(url: str, *, json: Dict[str, Any], headers: Dict[str, str]):
        sent.append({"url": url, "json": json, "headers": headers})
        return answers[len(sent) - 1]

    transport.sent = sent  # type: ignore[attr-defined]
    return transport


# ── Niqob: to'liq raqam hech qayerda qolmaydi ─────────────────────────


def test_the_card_number_is_never_kept_whole() -> None:
    masked = cards.mask_pan("8600 1234 5678 9012")

    assert masked == "8600 **** **** 9012"
    assert "5678" not in masked, "o'rtadagi raqamlar ochiq qolgan"


# ── Ulash oqimi ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_payme_binding_asks_for_a_code(store: PaymentStore) -> None:
    """`cards.create` faqat token beradi — SMS ALOHIDA chaqiruv.

    Ikkinchisi unutilsa mijoz kodni kutib qolardi va u hech qachon
    kelmasdi.
    """
    transport = _fake(
        [
            {"result": {"card": {"token": "tok-1", "verify": False}}},
            {"result": {"sent": True}},
        ]
    )

    card = await cards.bind_start(
        "payme", PAYME, number="8600123456789012", expire="0130", transport=transport
    )

    methods = [item["json"]["method"] for item in transport.sent]
    assert methods == ["cards.create", "cards.get_verify_code"]
    assert card.token == "tok-1" and card.verified is False
    assert card.masked_pan == "8600 **** **** 9012"
    # Karta raqami FAQAT birinchi so'rovda ketadi.
    assert "8600123456789012" not in str(transport.sent[1])


@pytest.mark.asyncio
async def test_payme_confirmation_takes_the_new_token(store: PaymentStore) -> None:
    """Tasdiqlangandan keyin token ALMASHADI — eskisini saqlab qolish
    keyingi yechishni jimgina rad ettirardi."""
    transport = _fake([{"result": {"card": {"token": "tok-2", "verify": True, "number": "8600****9012"}}}])

    card = await cards.bind_confirm("payme", PAYME, token="tok-1", code="123456", transport=transport)

    assert card.token == "tok-2" and card.verified is True


@pytest.mark.asyncio
async def test_a_provider_refusal_becomes_a_readable_error() -> None:
    """Payme xato matnini uch tilli lug'at qilib qaytaradi — mijozga
    xom JSON emas, matn ko'rsatiladi."""
    transport = _fake([{"error": {"code": -32504, "message": {"uz": "Karta bloklangan"}}}])

    with pytest.raises(cards.CardError) as raised:
        await cards.bind_start(
            "payme", PAYME, number="8600123456789012", expire="0130", transport=transport
        )

    assert "bloklangan" in raised.value.message


@pytest.mark.asyncio
async def test_click_binding_keeps_the_token_permanent() -> None:
    """`temporary: 0` — token saqlanadi.  Aks holda takroriy to'lov
    uchun karta har safar qayta ulanishi kerak bo'lardi."""
    transport = _fake([{"error_code": 0, "card_token": "ctok-1"}])

    card = await cards.bind_start(
        "click", CLICK, number="8600123456789012", expire="0130", transport=transport
    )

    assert transport.sent[0]["json"]["temporary"] == 0
    assert card.token == "ctok-1"


# ── Yechish ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_payme_charge_creates_and_pays_a_receipt() -> None:
    transport = _fake([{"result": {"receipt": {"_id": "r-1"}}}, {"result": {"receipt": {"state": 4}}}])

    receipt = await cards.charge(
        "payme",
        PAYME,
        token="tok-2",
        amount_uzs=299_000,
        account={"invoice_id": "inv-1"},
        description="Obuna",
        transport=transport,
    )

    assert receipt == "r-1"
    # Payme TIYINDA kutadi — so'mda yuborilsa summa 100 barobar kam bo'lardi.
    assert transport.sent[0]["json"]["params"]["amount"] == 29_900_000


@pytest.mark.asyncio
async def test_a_zero_charge_is_refused() -> None:
    with pytest.raises(cards.CardError):
        await cards.charge(
            "payme", PAYME, token="t", amount_uzs=0, account={}, description="", transport=_fake([])
        )


def test_a_temporary_failure_is_marked_retriable() -> None:
    """«Mablag' yetarli emas» ertaga o'tishi mumkin, «karta bloklangan»
    — yo'q.  Avtomatik yechish shu bayroqqa qarab qayta urinadi."""
    assert cards.CardError("x", retriable=True).retriable is True
    assert cards.CardError("x").retriable is False


# ── Saqlash: token chiqmasin ───────────────────────────────────────────


def test_the_token_never_leaves_the_store_by_accident(store: PaymentStore, site: str) -> None:
    saved = store.save_card(site, provider="payme", token="tok-secret", masked_pan="8600 **** **** 9012")

    assert "token" not in saved, "token javobga chiqdi"
    assert "token_ciphertext" not in saved, "shifrlangan token ham chiqmasin"
    assert store.get_card(site, include_token=True)["token"] == "tok-secret"


def test_the_token_is_encrypted_at_rest(store: PaymentStore, site: str) -> None:
    """Bazaning nusxasi sizib ketsa token bilan pul yechib bo'lmasin."""
    store.save_card(site, provider="payme", token="tok-secret", masked_pan="8600 **** **** 9012")

    conn = store._connect()
    raw = str(dict(conn.execute("SELECT * FROM payment_cards").fetchone())["token_ciphertext"])
    conn.close()

    assert "tok-secret" not in raw


def test_forgetting_a_card_really_deletes_it(store: PaymentStore, site: str) -> None:
    """`active=0` YETARLI EMAS: mijoz «o'chir» deganda pul yechish
    huquqi bazada qolib ketmasligi kerak."""
    store.save_card(site, provider="payme", token="tok-secret", masked_pan="8600 **** **** 9012")

    assert store.forget_card(site) is True

    conn = store._connect()
    rows = conn.execute("SELECT COUNT(*) AS n FROM payment_cards").fetchone()
    conn.close()
    assert int(dict(rows)["n"]) == 0


def test_only_one_card_per_shop(store: PaymentStore, site: str) -> None:
    """Ikkita faol karta bo'lsa «qaysi biridan yechildi» degan savol
    javobsiz qolardi."""
    store.save_card(site, provider="payme", token="a", masked_pan="1111 **** **** 1111")
    store.save_card(site, provider="click", token="b", masked_pan="2222 **** **** 2222")

    card = store.get_card(site, include_token=True)
    assert card["token"] == "b" and card["provider"] == "click"
    assert store.sites_with_active_cards() == []  # hali tasdiqlanmagan


def test_only_verified_cards_are_charged(store: PaymentStore, site: str) -> None:
    """Tasdiqlanmagan kartadan yechish provayderda baribir rad etiladi —
    nomzodlar ro'yxatiga umuman kirmasin."""
    store.save_card(site, provider="payme", token="a", masked_pan="1111 **** **** 1111")
    assert store.sites_with_active_cards() == []

    store.mark_card_verified(site)
    assert store.sites_with_active_cards() == [site]


def test_a_failed_charge_does_not_drop_the_card(store: PaymentStore, site: str) -> None:
    """Bir marta muvaffaqiyatsiz yechish (mablag' yetmadi) kartani
    yaroqsiz qilmaydi — o'chirish mijozni qayta ulashga majburlardi."""
    store.save_card(site, provider="payme", token="a", masked_pan="1111 **** **** 1111")
    store.mark_card_verified(site)

    store.record_card_error(site, "Mablag‘ yetarli emas")

    card = store.get_card(site)
    assert card is not None and card["verified"] is True
    assert "yetarli emas" in card["last_error"]
