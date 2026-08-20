"""Cloud yukini ushlab turadigan qoidalar.

Har bir test bitta aniq savolga javob beradi: bitta obyekt yoki bitta buzuq
qurilma cloud'ni (yoki Telegram botni) yiqita oladimi?
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cloud import ratelimit
from cloud.notify import throttle
from cloud.snapshots import LocalSnapshotStore

ADMIN = {"X-Cloud-Admin-Key": "test-admin"}


@pytest.fixture
def cloud(tmp_path: Path, monkeypatch):
    import cloud.main as main

    monkeypatch.setenv("CHAQIMCHI_CLOUD_ADMIN_KEY", "test-admin")
    monkeypatch.setenv("CHAQIMCHI_OWNER_JWT_SECRET", "owner-secret-with-more-than-32-characters")
    monkeypatch.setenv("CHAQIMCHI_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("CHAQIMCHI_S3_ENDPOINT", raising=False)
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "cloud.db")
    monkeypatch.setattr(main, "_store", None)
    monkeypatch.setattr(main, "_event_store", None)
    monkeypatch.setattr(main, "_event_store_key", None)
    monkeypatch.setattr(main, "_snapshots", LocalSnapshotStore(tmp_path / "snapshots"))

    sent = []

    async def fake_send(chat_id: str, text: str, *, reply_markup=None) -> None:
        sent.append((chat_id, text))

    monkeypatch.setattr(main, "_send_owner_telegram", fake_send)
    ratelimit.limiter().reset()
    throttle().reset()
    with TestClient(main.app) as client:
        yield main, client, sent
    ratelimit.limiter().reset()
    throttle().reset()


def _site(client: TestClient, name: str, plan: str = "lite"):
    site = client.post(
        "/api/v1/admin/sites", headers=ADMIN, json={"name": name, "plan": plan}
    ).json()
    device = client.post(
        "/api/v1/devices/claim", json={"pairing_code": site["pairing_code"]}
    ).json()
    headers = {
        "X-Site-Id": device["site_id"],
        "X-Device-Id": device["device_id"],
        "X-Device-Token": device["device_token"],
    }
    return site, headers


def _events(count: int, *, days_ago: int = 0, prefix: str = "evt"):
    occurred = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    return [
        {
            "event_id": f"{prefix}-{index}",
            "event_type": "zone_entered",
            # Minimal rejimda botga faqat critical boradi — bu testlar
            # yuborish MEXANIKASINI tekshiradi, siyosatni emas.
            "severity": "critical",
            "camera_id": "camera-01",
            "occurred_at": occurred,
        }
        for index in range(count)
    ]


# ── Telegram ─────────────────────────────────────────────────────────────


def test_large_batch_sends_one_message_not_one_per_event(cloud) -> None:
    _main, client, sent = cloud
    site, headers = _site(client, "Oq Saroy")
    client.post(
        f"/api/v1/admin/sites/{site['site_id']}/members",
        headers=ADMIN,
        json={"telegram_id": "555", "role": "owner"},
    )

    response = client.post(
        "/api/v1/edge/events/batch", headers=headers, json={"events": _events(500)}
    )

    assert response.status_code == 200
    assert len(sent) == 1
    assert "500 ta ogohlantirish" in sent[0][1]


def test_same_alert_is_not_repeated_every_batch(cloud) -> None:
    _main, client, sent = cloud
    site, headers = _site(client, "Oq Saroy")
    client.post(
        f"/api/v1/admin/sites/{site['site_id']}/members",
        headers=ADMIN,
        json={"telegram_id": "555", "role": "owner"},
    )

    client.post(
        "/api/v1/edge/events/batch", headers=headers, json={"events": _events(3, prefix="a")}
    )
    client.post(
        "/api/v1/edge/events/batch", headers=headers, json={"events": _events(3, prefix="b")}
    )

    assert len(sent) == 1


# ── Tezlik cheklovi ──────────────────────────────────────────────────────


def test_event_ingestion_is_rate_limited_per_device(cloud, monkeypatch) -> None:
    """Chegara rostdan ishlaydi.

    Haqiqiy chegara (600) bilan sinash 600 ta HTTP so'rov demak — test
    o'n daqiqalab ishlardi.  Shuning uchun chegara vaqtincha kichraytiriladi;
    haqiqiy qiymatning yetarliligi quyidagi alohida testda tekshiriladi.
    """
    main, client, _sent = cloud
    _site_row, headers = _site(client, "Do'kon")
    monkeypatch.setattr(main, "EVENT_BATCH_HOURLY_LIMIT", 5)

    codes = [
        client.post(
            "/api/v1/edge/events/batch",
            headers=headers,
            json={"events": _events(1, prefix=f"r{index}")},
        ).status_code
        for index in range(8)
    ]

    assert codes == [200] * 5 + [429] * 3


def test_the_hourly_limit_leaves_room_for_a_real_shop(cloud) -> None:
    """Chegara pilotni buzmasin.

    Bu 1.2-tuzatishning sababi: chegara 120 edi, edge esa har 5 soniyada
    so'rov yubordi (soatiga 720) — ~10 daqiqada 429 va abadiy sikl.
    """
    main, _client, _sent = cloud

    # `cloud_sync.batch_size` standarti 50 ta hodisa.
    assert main.EVENT_BATCH_HOURLY_LIMIT * 50 >= 25_000
    # Edge eng tez rejimda ham (5 soniyada bir) soatiga 720 so'rov qiladi;
    # chegara bundan past bo'lsa navbat to'lgan paytda 429 muqarrar.
    assert main.EVENT_BATCH_HOURLY_LIMIT >= 720 * 0.8


# ── Config polling ───────────────────────────────────────────────────────


def test_heartbeat_tells_the_device_whether_config_changed(cloud) -> None:
    main, client, _sent = cloud
    site, headers = _site(client, "Do'kon")

    first = client.post(
        "/api/v1/sotqin/heartbeat", headers=headers, json={"config_revision": 0}
    ).json()
    assert first["config_revision"] == 0
    assert first["config_changed"] is False

    # Owner sozlamani o'zgartirsa revision oshadi va qurilma buni biladi.
    main.get_event_store().update_site_config(site["site_id"], {"occupancy_limit": 30})
    second = client.post(
        "/api/v1/sotqin/heartbeat", headers=headers, json={"config_revision": 0}
    ).json()
    assert second["config_revision"] == 1
    assert second["config_changed"] is True

    third = client.post(
        "/api/v1/sotqin/heartbeat", headers=headers, json={"config_revision": 1}
    ).json()
    assert third["config_changed"] is False


# ── Arxiv muddati ────────────────────────────────────────────────────────


def test_purge_uses_each_plan_retention_not_a_fixed_30_days(cloud) -> None:
    main, client, _sent = cloud
    lite, lite_headers = _site(client, "Lite do'kon", plan="lite")  # 30 kun
    big, big_headers = _site(client, "Zavod", plan="enterprise")  # 365 kun

    client.post(
        "/api/v1/edge/events/batch",
        headers=lite_headers,
        json={"events": _events(2, days_ago=100, prefix="l")},
    )
    client.post(
        "/api/v1/edge/events/batch",
        headers=big_headers,
        json={"events": _events(2, days_ago=100, prefix="e")},
    )

    store = main.get_event_store()
    assert len(store.list_events(lite["site_id"], limit=50)) == 2

    main._purge_expired_events()

    assert store.list_events(lite["site_id"], limit=50) == []
    # 365 kunlik arxiv uchun to'lagan mijoz 100 kunlik hodisani ko'rib turishi kerak.
    assert len(store.list_events(big["site_id"], limit=50)) == 2
