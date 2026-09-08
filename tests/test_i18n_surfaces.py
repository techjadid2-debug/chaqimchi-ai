"""Uch til — SERVER chizadigan sirtlar (F5).

Panel o'z matnini brauzerda chizadi; Telegram, kunlik hisobot, CSV va
tarif kartasi esa serverda yasaladi va tilni SO'ROVCHIDAN yoki
QABUL QILUVCHIDAN olishi kerak.  Bu testlar aynan shu chegarani
qulflaydi: ruscha a'zo ruscha, o'zbek a'zo o'zbekcha oladi — bitta
do'konda, bitta yuborishda.

Matn taqqoslanmaydi (tarjima tahriri testga tegmasin) — katalogdan
olingan kalit matni yoki tilning ko'rinadigan belgisi tekshiriladi.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from cloud import i18n
from cloud.digest import build_digest
from cloud.notify import summarize
from enes.event_models import EdgeEvent
from tests.test_cloud_events_owner import (  # noqa: F401 — fixture shu import bilan keladi
    _login_owner,
    _provision,
    production_client,
)
from tests.test_owner_report import (
    DAY,
    _digest_service,
    _tashkent_evening,
    crossing,
    queue_event,
    store_with,
)

#: Ruscha matnning ishonchli belgisi — kirill harfi.  Lotin o'zbekchada
#: bitta ham kirill harfi yo'q, shuning uchun "tarjima ketdimi" degan
#: savolga bu belgi jumlani solishtirmasdan javob beradi.
CYRILLIC = set("абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ")


def _has_cyrillic(text: str) -> bool:
    return any(ch in CYRILLIC for ch in text)


# ── Kunlik hisobot ───────────────────────────────────────────────────────


def test_each_member_gets_the_digest_in_their_own_language(tmp_path: Path) -> None:
    """Bitta do'kon, ikki a'zo, ikki til — bitta yuborishda.

    Ilgari `_deliver` bitta tayyor matnni hammaga jo'natardi; ruscha
    menejer o'zbekcha hisobot olardi.
    """
    store = store_with(
        [crossing(18, "in", index) for index in range(9)] + [queue_event(18, 22, 7)],
        tmp_path,
    )
    store.add_member("site-1", "111", role="owner")
    manager = store.add_member("site-1", "222", role="manager")
    store.set_member_language("site-1", str(manager["id"]), "ru")
    sent: list = []
    service = _digest_service(store, sent)

    asyncio.run(service.check_once(_tashkent_evening()))

    by_chat = {chat: text for chat, text in sent}
    assert set(by_chat) == {"111", "222"}
    assert i18n.tg("uz", "digest.daily.entered", count=9) in by_chat["111"]
    assert i18n.tg("ru", "digest.daily.entered", count=9) in by_chat["222"]
    assert not _has_cyrillic(by_chat["111"])


def test_the_russian_digest_leaves_no_uzbek_behind(tmp_path: Path) -> None:
    """Yarim tarjima — eng yomon holat: ega ikki tilni aralash o'qiydi."""
    store = store_with(
        [crossing(18, "in", index) for index in range(9)] + [queue_event(18, 22, 7)],
        tmp_path,
    )
    text = build_digest(
        "Oq Saroy",
        DAY.isoformat(),
        store.stats("site-1", day=DAY),
        store.retail_report("site-1", day=DAY),
        lang="ru",
    )

    assert _has_cyrillic(text)
    for uzbek in ("Kirdi", "kishi", "Navbat", "Gavjum", "so'm", "hisobot"):
        assert uzbek not in text, f"ruscha hisobotda o'zbekcha qoldi: {uzbek}"


# ── Hodisa ogohlantirishi ────────────────────────────────────────────────


def test_the_alert_summary_follows_the_recipient_language() -> None:
    events = [EdgeEvent(event_type="camera_tampered", camera_id="camera-01", severity="critical")]

    russian = summarize(events, site_name="Oq Saroy", lang="ru")
    uzbek = summarize(events, site_name="Oq Saroy")

    assert i18n.tg("ru", "event.camera_tampered") in russian
    assert i18n.tg("uz", "event.camera_tampered") in uzbek
    assert not _has_cyrillic(uzbek)


# ── CSV ──────────────────────────────────────────────────────────────────


def test_the_csv_speaks_the_requesters_language_and_keeps_the_bom(production_client) -> None:  # noqa: F811
    """Kirillcha CSV BOM'siz Excelda «krakozyabra» bo'lib ochiladi —
    lotin o'zbekchada bu ko'rinmasdi, ruscha bilan darrov ko'rinadi."""
    client, _messages = production_client
    site, _device, headers = _provision(client)
    owner_headers = _login_owner(client, site["site_id"], telegram_id="9301")
    client.post(
        "/api/v1/edge/events/batch",
        headers=headers,
        json={
            "events": [
                {
                    "event_id": f"csv-ru-{index}",
                    "event_type": "line_crossed",
                    "camera_id": "camera-01",
                    "direction": "in",
                    "line": "Asosiy eshik",
                }
                for index in range(3)
            ]
        },
    )

    response = client.get("/api/v1/owner/report.csv", headers={**owner_headers, "X-Lang": "ru"})

    assert response.status_code == 200, response.text
    body = response.content.decode("utf-8")
    assert body.startswith("﻿")
    assert f"{i18n.tg('ru', 'csv.report.entered')},3" in body
    assert "Kirdi," not in body
    # Fayl nomi ham ruscha (lotin harflarida — brauzerlar kirill nomni
    # har xil kodlaydi), sana o'zgarmaydi.
    disposition = response.headers["content-disposition"]
    assert i18n.tg("ru", "csv.report.filename") in disposition
    assert "dokon-hisoboti" not in disposition

    # Standart so'rov — avvalgidek o'zbekcha va eski fayl nomi.
    plain = client.get("/api/v1/owner/report.csv", headers=owner_headers)
    assert "dokon-hisoboti-" in plain.headers["content-disposition"]
    assert "Kirdi,3" in plain.content.decode("utf-8")


# ── Tarif kartasi ────────────────────────────────────────────────────────


def test_the_pricing_cards_translate_with_the_lang_query(production_client) -> None:  # noqa: F811
    """Sayt `/ru/` sahifasi narxni `?lang=ru` bilan so'raydi — punktlar,
    nom va tugma ruscha kelsin; son (kamera, narx) o'zgarmasin."""
    client, _messages = production_client

    russian = client.get("/api/v1/public/pricing?lang=ru").json()
    uzbek = client.get("/api/v1/public/pricing").json()

    ru_plans = {plan["code"]: plan for plan in russian["plans"]}
    uz_plans = {plan["code"]: plan for plan in uzbek["plans"]}
    for code in ("boshlangich", "biznes", "tarmoq"):
        assert _has_cyrillic(ru_plans[code]["name"]), code
        assert _has_cyrillic(ru_plans[code]["cta"]), code
        assert _has_cyrillic(ru_plans[code]["bullets"][0]["label"]), code
        assert not _has_cyrillic(uz_plans[code]["bullets"][0]["label"]), code
        assert [b["icon"] for b in ru_plans[code]["bullets"]] == [
            b["icon"] for b in uz_plans[code]["bullets"]
        ]
    # Kamera soni matnga qotirilmagan — `limits` dagi son ikkala tilda.
    assert str(uz_plans["biznes"]["max_cameras"]) in ru_plans["biznes"]["bullets"][0]["label"]
    assert ru_plans["biznes"]["monthly_uzs"] == uz_plans["biznes"]["monthly_uzs"]
    assert ru_plans["tarmoq"]["price_label"] == i18n.tg("ru", "plan.price.on_request")


# ── Telegram bot ─────────────────────────────────────────────────────────


def _webhook_from(client, text: str, *, chat_id: int, language_code: str | None):
    sender = {"id": chat_id}
    if language_code:
        sender["language_code"] = language_code
    return client.post(
        "/api/v1/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "webhook-test"},
        json={
            "message": {
                "chat": {"id": chat_id, "type": "private"},
                "from": sender,
                "text": text,
            }
        },
    )


def test_the_bot_learns_the_language_on_first_contact_and_keeps_it(
    production_client,  # noqa: F811
    monkeypatch,
) -> None:
    """`/start` — a'zoning tilini so'ramasdan bilishning yagona payti.

    Telegram profili `ru` desa, bot ruscha javob beradi va tilni a'zoga
    yozib qo'yadi: keyingi buyruq profil tilisiz kelsa ham ruscha.
    """
    client, messages = production_client
    monkeypatch.setenv("ENES_TELEGRAM_WEBHOOK_SECRET", "webhook-test")
    site, _device, _headers = _provision(client)
    client.post(
        f"/api/v1/admin/sites/{site['site_id']}/members",
        headers={"X-Cloud-Admin-Key": "test-admin"},
        json={"telegram_id": "900222", "role": "owner"},
    )
    messages.clear()

    assert _webhook_from(client, "/start", chat_id=900222, language_code="ru").status_code == 200
    assert _webhook_from(client, "/yordam", chat_id=900222, language_code=None).status_code == 200

    assert len(messages) == 2
    welcome, helptext = messages[0][1], messages[1][1]
    assert welcome == i18n.tg("ru", "bot.welcome.member")
    assert helptext == i18n.tg("ru", "bot.help")
    assert not _has_cyrillic(i18n.tg("uz", "bot.help"))


def test_a_stranger_is_answered_in_their_telegram_language(production_client, monkeypatch) -> None:  # noqa: F811
    """A'zo bo'lmagan odam uchun tilning yagona manbasi — Telegram profili."""
    client, messages = production_client
    monkeypatch.setenv("ENES_TELEGRAM_WEBHOOK_SECRET", "webhook-test")
    messages.clear()

    assert _webhook_from(client, "/start", chat_id=900333, language_code="en").status_code == 200

    assert len(messages) == 1
    assert messages[0][1] == i18n.tg("en", "bot.welcome.guest")
