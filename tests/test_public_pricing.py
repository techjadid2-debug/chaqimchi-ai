"""Rasmiy sayt narxni cloud'dan oladi — HTMLda qo'lda yozilgan narx qolmasin.

Bungacha `site.html` ichida `$3`, `$5`, `$6` qotirilgan edi; katalog o'zgarsa
sayt eski narxni ko'rsatib turaverardi va mijoz boshqa summa to'lardi.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cloud import ratelimit


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    import cloud.main as main

    monkeypatch.setenv("CHAQIMCHI_CLOUD_ADMIN_KEY", "test-admin")
    monkeypatch.setenv("CHAQIMCHI_OWNER_JWT_SECRET", "owner-secret-with-more-than-32-characters")
    monkeypatch.setenv("CHAQIMCHI_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("CHAQIMCHI_USD_RATE_UZS", raising=False)
    monkeypatch.delenv("CHAQIMCHI_AVAILABLE_FEATURES", raising=False)
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "cloud.db")
    monkeypatch.setattr(main, "_store", None)
    monkeypatch.setattr(main, "_event_store", None)
    monkeypatch.setattr(main, "_event_store_key", None)
    ratelimit.limiter().reset()
    with TestClient(main.app) as test_client:
        yield test_client
    ratelimit.limiter().reset()


def test_pricing_serves_base_and_catalog_in_both_currencies(client) -> None:
    body = client.get("/api/v1/public/pricing").json()

    assert body["currency_default"] == "uzs"
    assert body["usd_rate_uzs"] == 13_000
    assert body["yearly_months_charged"] == 10
    # $20 baza; so'm summasi serverdagi yaxlitlash bilan bir xil.
    assert body["base"]["monthly_usd_cents"] == 2_000
    assert body["base"]["monthly_uzs"] == 260_000
    assert body["base"]["includes"]

    person_count = next(item for item in body["features"] if item["code"] == "person_count")
    assert person_count["monthly_usd_cents"] == 300
    assert person_count["monthly_uzs"] == 39_000


def test_pricing_follows_the_configured_usd_rate(client, monkeypatch) -> None:
    monkeypatch.setenv("CHAQIMCHI_USD_RATE_UZS", "14000")
    body = client.get("/api/v1/public/pricing").json()
    assert body["usd_rate_uzs"] == 14_000
    assert body["base"]["monthly_uzs"] == 280_000


def test_pricing_never_leaks_cost_or_margin(client) -> None:
    body = client.get("/api/v1/public/pricing").json()
    serialized = str(body)
    assert "cost_usd_cents" not in serialized
    assert "gross_margin_percent" not in serialized


def test_public_catalog_contains_only_store_mvp_and_keeps_acceptance_gate(
    client, monkeypatch
) -> None:
    # N100 qabul testi tugamaguncha hech narsa "tayyor" deb sotilmaydi.
    assert all(
        not item["available"] for item in client.get("/api/v1/public/pricing").json()["features"]
    )

    monkeypatch.setenv("CHAQIMCHI_AVAILABLE_FEATURES", "person_count,queue_length")
    features = {
        item["code"]: item for item in client.get("/api/v1/public/pricing").json()["features"]
    }
    assert features["person_count"]["available"] is True
    assert features["queue_length"]["available"] is True
    assert set(features) == {"person_count", "queue_length", "store_security"}
    assert features["store_security"]["available"] is False
    assert client.get("/api/v1/public/pricing").json()["max_cameras"] == 4


def test_lead_form_is_rate_limited(client) -> None:
    payload = {"full_name": "Ali Valiyev", "phone": "+998901112233", "consent": True}
    for _ in range(5):
        assert client.post("/api/v1/public/leads", json=payload).status_code == 200
    blocked = client.post("/api/v1/public/leads", json=payload)
    assert blocked.status_code == 429
    assert "ariza" in blocked.json()["detail"].lower()


# ── Uch tarif ───────────────────────────────────────────────────────────


def test_pricing_serves_three_cards_with_the_middle_one_highlighted(client) -> None:
    """Sayt uchta kartani serverdan oladi, narxni o'zi hisoblamaydi."""
    data = client.get("/api/v1/public/pricing").json()

    codes = [item["code"] for item in data["plans"]]
    assert codes == ["boshlangich", "biznes", "tarmoq"]

    boshlangich, biznes, tarmoq = data["plans"]

    assert boshlangich["monthly_uzs"] == 149_000
    assert boshlangich["max_cameras"] == 2
    assert boshlangich["highlight"] is False

    assert biznes["monthly_uzs"] == 299_000
    assert biznes["max_cameras"] == 4
    # O'rtadagisi ajratiladi: uchta teng ustun qaror qabul qilishni
    # qiyinlashtiradi.
    assert biznes["highlight"] is True
    assert biznes["badge"] == "Eng ommabop"

    # Tarmoqda son yo'q — bo'lsa `create_invoice` unga 0 so'mlik hisob
    # yozib qo'yardi.
    assert tarmoq["price_kind"] == "on_request"
    assert tarmoq["monthly_uzs"] is None
    assert tarmoq["monthly_usd_cents"] is None
    assert tarmoq["price_label"] == "So'rov bo'yicha"


def test_the_network_card_does_not_promise_a_single_login(client) -> None:
    """Bitta login bilan ko'p do'konni ko'rish kodi HALI YO'Q.

    `portal_accounts.site_id` bitta va `owner_auth.py` bitta saytga
    bog'langan.  Sayt buni va'da qilsa — sotilgan narsa yo'q bo'lib
    chiqadi.
    """
    tarmoq = next(
        item for item in client.get("/api/v1/public/pricing").json()["plans"]
        if item["code"] == "tarmoq"
    )
    assert tarmoq["note"], "Tarmoq kartasida halollik izohi bo'lishi shart"
    assert "alohida panelda" in tarmoq["note"]


def test_plan_prices_match_the_invoice_exactly(client) -> None:
    """Saytdagi narx va hisob-faktura bitta funksiyadan chiqsin.

    Ilgari `site.js` so'mga o'girish formulasini qaytadan yozgan edi —
    ikki joyda turgan formula bir-biridan uzoqlashishi mumkin.
    """
    from chaqimchi_ai.licensing.plans import PLANS

    for card in client.get("/api/v1/public/pricing").json()["plans"]:
        if card["price_kind"] != "fixed":
            continue
        assert card["monthly_uzs"] == PLANS[card["code"]].monthly_price(), card["code"]


def test_base_includes_come_from_the_biznes_plan(client) -> None:
    """Bitta ro'yxat ikki joyda yozilib, bir-biridan uzoqlashmasin."""
    from chaqimchi_ai.licensing.plans import PLANS

    data = client.get("/api/v1/public/pricing").json()
    assert data["base"]["includes"] == list(PLANS["biznes"].includes)
