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


# ── Avtomatik yechish: ikki barobar pul olinmasin ─────────────────────


def test_the_mark_is_set_before_the_charge(store: PaymentStore, site: str) -> None:
    """Belgi yechishdan OLDIN qo'yiladi.

    Jarayon yechish O'RTASIDA yiqilsa (provayder javobi kelgan, biz
    uni yozishga ulgurmagan) keyingi yurishda ikkinchi marta
    yechilardi — mijozdan ikki barobar pul olish eng qimmat xato.
    """
    store.save_card(site, provider="payme", token="a", masked_pan="1111 **** **** 1111")
    store.mark_card_verified(site)

    assert store.begin_charge_attempt(site) is True
    # Belgi QO'YILDI — o'sha kunda ikkinchi urinish rad etiladi.
    assert store.begin_charge_attempt(site) is False
    assert int(store.get_card(site)["attempts"]) == 1


def test_an_unverified_card_is_never_charged(store: PaymentStore, site: str) -> None:
    store.save_card(site, provider="payme", token="a", masked_pan="1111 **** **** 1111")

    assert store.begin_charge_attempt(site) is False


def test_the_attempts_run_out(store: PaymentStore, site: str) -> None:
    """Uchtadan keyin qo'lda to'lovga qaytadi — cheksiz urinish
    provayderda ham, mijozda ham shovqin bo'lardi."""
    store.save_card(site, provider="payme", token="a", masked_pan="1111 **** **** 1111")
    store.mark_card_verified(site)

    conn = store._connect()
    for expected in (True, True, True, False):
        # Har urinish BOSHQA kunda: kunlik darvoza alohida tekshiriladi.
        assert store.begin_charge_attempt(site) is expected, expected
        conn.execute(
            "UPDATE payment_cards SET last_attempt_at='2020-01-01T00:00:00+00:00' "
            "WHERE site_id=?",
            (site,),
        )
        conn.commit()
    conn.close()


def test_a_successful_charge_resets_the_counter(store: PaymentStore, site: str) -> None:
    """Keyingi davr toza boshlansin — aks holda uchinchi oyda
    avtomatik to'lov o'zi o'chib qolardi."""
    store.save_card(site, provider="payme", token="a", masked_pan="1111 **** **** 1111")
    store.mark_card_verified(site)
    store.begin_charge_attempt(site)

    store.finish_charge_attempt(site, ok=True)

    card = store.get_card(site)
    assert int(card["attempts"]) == 0 and card["last_error"] is None


def test_a_failed_charge_keeps_the_counter(store: PaymentStore, site: str) -> None:
    store.save_card(site, provider="payme", token="a", masked_pan="1111 **** **** 1111")
    store.mark_card_verified(site)
    store.begin_charge_attempt(site)

    store.finish_charge_attempt(site, ok=False, error="Mablag‘ yetarli emas")

    card = store.get_card(site)
    assert int(card["attempts"]) == 1
    assert "yetarli emas" in card["last_error"]


def test_the_auto_renew_job_runs_only_on_the_leader() -> None:
    """Ikki worker bir vaqtda yursa mijozdan ikki barobar pul olinardi.

    Fon vazifalari `cloud/leader.py` darvozasi ortida — bu qoida
    2026-09-09 da kunlik hisobot ikki marta yuborilgani uchun
    kiritilgan edi va pul bilan ishlaganda narxi yanada yuqori.
    """
    main = (Path(__file__).resolve().parents[1] / "cloud" / "main.py").read_text(encoding="utf-8")
    loop = main[main.index("async def _maintenance_loop"):]
    loop = loop[: loop.index("async def _lead_notification_loop")]

    assert "_auto_renew_subscriptions()" in loop, "vazifa umuman chaqirilmaydi"
    assert "_is_leader()" in loop, "yetakchi darvozasi yo'q"


def test_the_auto_renew_reuses_a_pending_invoice() -> None:
    """Ikkinchi hisob ochilsa ega ikkita boshqa summani ko'rardi."""
    main = (Path(__file__).resolve().parents[1] / "cloud" / "main.py").read_text(encoding="utf-8")
    block = main[main.index("async def _auto_renew_one"):]
    block = block[: block.index("async def _auto_renew_subscriptions")]

    assert 'item["state"] == "pending"' in block
    assert "mark_paid(" in block, "to'langan hisob obunani uzaytirmaydi"
    # Kalitlar yo'q bo'lsa urinish ham qilinmaydi.
    assert "config.configured" in block


# ── Ega paneli: karta API'si ──────────────────────────────────────────


@pytest.fixture
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("ENES_CLOUD_ADMIN_KEY", "test-admin")
    monkeypatch.setenv("ENES_OWNER_JWT_SECRET", "o" * 64)
    monkeypatch.setenv("ENES_PORTAL_JWT_SECRET", "p" * 64)
    monkeypatch.setattr("cloud.main.DB_PATH", tmp_path / "cloud.db")
    monkeypatch.setattr("cloud.main._store", None)
    monkeypatch.setattr("cloud.main._event_store", None)
    monkeypatch.setattr("cloud.main._event_store_key", None)
    monkeypatch.setattr("cloud.main._payments", None, raising=False)
    from cloud.main import app

    return TestClient(app)


@pytest.fixture
def owner(api) -> Dict[str, Any]:
    trial = api.post(
        "/api/v1/public/quick-trial",
        json={
            "phone": "+998 90 123 45 67",
            "full_name": "Ega Egayev",
            "company": "Namuna do'kon",
            "username": "dokonchi",
            "password": "parol12345",
            "consent": True,
        },
    ).json()
    login = api.post(
        "/api/v1/auth/login", json={"username": "dokonchi", "password": "parol12345"}
    ).json()
    return {
        "site_id": trial["site_id"],
        "headers": {"Authorization": f"Bearer {login['access_token']}"},
    }


def test_the_trial_starts_without_a_card(api, owner: Dict[str, Any]) -> None:
    """Ega qarori: kartasiz 7 kun.  Ro'yxatdan o'tishda karta
    so'ralmaydi, ya'ni har yangi do'kon aynan shu muddat bilan
    boshlanadi."""
    from cloud.main import SELF_SERVICE_TRIAL_DAYS_DEFAULT, get_store

    assert SELF_SERVICE_TRIAL_DAYS_DEFAULT == 7
    status = get_store().subscription_status(owner["site_id"])
    assert 5 <= int(status["days_left"]) <= 7


def test_the_panel_is_told_when_no_provider_is_connected(api, owner: Dict[str, Any]) -> None:
    """Payme/Click kalitlari hali egadan kelmagan — ikkalasi ham
    `False` bo'lishi NORMAL holat.  Panel shunda bo'limni umuman
    ko'rsatmaydi: ishlamaydigan tugma «buzuq» taassurotini beradi."""
    answer = api.get("/api/v1/owner/card", headers=owner["headers"]).json()

    assert answer["card"] is None
    assert answer["providers"] == {"payme": False, "click": False}


def test_binding_is_refused_while_the_provider_is_off(api, owner: Dict[str, Any]) -> None:
    response = api.post(
        "/api/v1/owner/card",
        headers=owner["headers"],
        json={"provider": "payme", "number": "8600123456789012", "expire": "0130"},
    )

    assert response.status_code == 503
    assert "bog‘laning" in response.json()["detail"] or "contact" in response.json()["detail"]


def test_the_card_answer_never_carries_the_token(api, owner: Dict[str, Any]) -> None:
    """Token — «pul yechish huquqi»: u javobga chiqmasligi kerak."""
    from cloud.main import get_payments

    get_payments().save_card(
        owner["site_id"], provider="payme", token="tok-secret", masked_pan="8600 **** **** 9012"
    )

    body = api.get("/api/v1/owner/card", headers=owner["headers"]).text

    assert "tok-secret" not in body
    assert "8600 **** **** 9012" in body


def test_forgetting_the_card_over_the_api(api, owner: Dict[str, Any]) -> None:
    from cloud.main import get_payments

    get_payments().save_card(
        owner["site_id"], provider="payme", token="tok", masked_pan="8600 **** **** 9012"
    )

    assert api.delete("/api/v1/owner/card", headers=owner["headers"]).json()["ok"] is True
    assert get_payments().get_card(owner["site_id"]) is None


def test_the_trial_bonus_is_given_once(api, owner: Dict[str, Any]) -> None:
    """Ikkinchi marta berilsa kartani qayta ulab sinovni cheksiz
    cho'zish yo'li ochilardi."""
    from cloud.main import get_store

    first = get_store().grant_trial_bonus(owner["site_id"], 7)
    second = get_store().grant_trial_bonus(owner["site_id"], 7)

    assert first is not None and first["days"] == 7
    assert second is None, "bonus ikkinchi marta berildi"


def test_the_bonus_is_not_given_after_the_trial_ended(api, owner: Dict[str, Any]) -> None:
    """Pullik obunaga tekin kun qo'shish mahsulotni arzonlashtirardi;
    bonusning ma'nosi boshqa — u kartani ulashga undaydi."""
    from cloud.main import get_store

    store = get_store()
    store.reduce_subscription(owner["site_id"], 24)

    assert store.grant_trial_bonus(owner["site_id"], 7) is None


# ── Sayt sinov muddati haqida ROST gapirsin ───────────────────────────


def test_the_site_says_the_real_trial_length() -> None:
    """Sinov 7 kunga o'tdi (ega qarori 2026-09-12).

    Sayt 14 kun deb turaverса mijoz ro'yxatdan o'tib, bir hafta
    keyin «vaqt tugadi» xabarini olardi — bu eng yomon birinchi
    taassurot.  Muddat KODDAN olinadi, testda qo'lda yozilmaydi.
    """
    from cloud.main import SELF_SERVICE_TRIAL_DAYS_DEFAULT

    static = Path(__file__).resolve().parents[1] / "cloud" / "static"
    days = SELF_SERVICE_TRIAL_DAYS_DEFAULT

    offer = (static / "oferta.html").read_text(encoding="utf-8")
    trial = offer[offer.index("6. Bepul sinov"):]
    trial = trial[: trial.index("7. To‘lov")]
    assert f"<b>{days} kun</b>" in trial, f"ofertada sinov muddati {days} kun emas"

    # Qaytarish muddati (14 kun) BOSHQA son va o'zgarmaydi.
    assert "14 kun</b> ichida Buyurtmachi" in offer, "qaytarish bandi buzilgan"

    for name in ("site.html", "site.ru.html", "site.en.html"):
        page = (static / name).read_text(encoding="utf-8")
        assert "14 kun</strong>" not in page and "14 дней</strong>" not in page
        assert "14-day free trial" not in page


def test_the_offer_does_not_yet_promise_recurring_charges() -> None:
    """Takroriy yechish bandi YURIST KO'RIGIGACHA yozilmaydi.

    Kod tayyor, lekin shartnomaviy rozilik matnini yozib qo'yib keyin
    to'g'rilash sud uchun eng yomon holat.  Karta bo'limi panelda
    provayder kalitlari yo'qligi sabab baribir ko'rinmaydi.
    """
    static = Path(__file__).resolve().parents[1] / "cloud" / "static"
    offer = (static / "oferta.html").read_text(encoding="utf-8").lower()

    for promise in ("avtomatik yechil", "takroriy to‘lov", "kartadan yechil"):
        assert promise not in offer, f"oferta yurist ko'rigisiz va'da beryapti: {promise}"


def test_the_card_block_hides_when_no_provider_is_connected() -> None:
    """Ishlamaydigan tugma «buzuq» degan taassurot beradi.

    Payme/Click kalitlari hali egadan kelmagan, ya'ni bugun hech bir
    mijozda bu bo'lim ko'rinmaydi — va bu TO'G'RI holat.
    """
    owner = (
        Path(__file__).resolve().parents[1] / "frontend" / "src" / "owner.tsx"
    ).read_text(encoding="utf-8")
    block = owner[owner.index("function CardBlock"):]
    block = block[: block.index("function BillingPage")]

    assert "if (!providers.length) return null;" in block, "darvoza yo'q"
    # Karta raqami komponent holatida QOLMASIN.
    assert 'setNumber(""); setExpire("");' in block, "raqam xotirada qolyapti"
    # Native oyna emas — Telegram WebView'da u ishlamasligi mumkin.
    assert "window.confirm" not in block
