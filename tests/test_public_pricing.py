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


def test_unavailable_features_are_marked_not_hidden(client, monkeypatch) -> None:
    # Inferens worker yozilmagan — hech narsa "tayyor" deb ko'rsatilmaydi.
    assert all(not item["available"] for item in client.get("/api/v1/public/pricing").json()["features"])

    monkeypatch.setenv("CHAQIMCHI_AVAILABLE_FEATURES", "person_count,queue_length")
    features = {item["code"]: item for item in client.get("/api/v1/public/pricing").json()["features"]}
    assert features["person_count"]["available"] is True
    assert features["queue_length"]["available"] is True
    assert features["watchlist"]["available"] is False


def test_lead_form_is_rate_limited(client) -> None:
    payload = {"full_name": "Ali Valiyev", "phone": "+998901112233", "consent": True}
    for _ in range(5):
        assert client.post("/api/v1/public/leads", json=payload).status_code == 200
    blocked = client.post("/api/v1/public/leads", json=payload)
    assert blocked.status_code == 429
    assert "ariza" in blocked.json()["detail"].lower()
