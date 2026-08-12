from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cloud.snapshots import LocalSnapshotStore


@pytest.fixture
def production_client(tmp_path: Path, monkeypatch):
    import cloud.main as main

    monkeypatch.setenv("CHAQIMCHI_CLOUD_ADMIN_KEY", "test-admin")
    monkeypatch.setenv("CHAQIMCHI_OWNER_JWT_SECRET", "owner-secret-with-more-than-32-characters")
    monkeypatch.setenv("CHAQIMCHI_OTP_TEST_CODE", "123456")
    monkeypatch.setenv("CHAQIMCHI_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("CHAQIMCHI_S3_ENDPOINT", raising=False)
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "cloud.db")
    monkeypatch.setattr(main, "_store", None)
    monkeypatch.setattr(main, "_event_store", None)
    monkeypatch.setattr(main, "_event_store_key", None)
    monkeypatch.setattr(main, "_snapshots", LocalSnapshotStore(tmp_path / "snapshots"))

    messages = []

    async def fake_send(chat_id: str, text: str) -> None:
        messages.append((chat_id, text))

    monkeypatch.setattr(main, "_send_owner_telegram", fake_send)
    with TestClient(main.app) as client:
        yield client, messages


def _provision(client: TestClient):
    site = client.post(
        "/api/v1/admin/sites",
        headers={"X-Cloud-Admin-Key": "test-admin"},
        json={"name": "Set-1", "plan": "enterprise"},
    ).json()
    device = client.post(
        "/api/v1/devices/claim", json={"pairing_code": site["pairing_code"]}
    ).json()
    headers = {
        "X-Site-Id": device["site_id"],
        "X-Device-Id": device["device_id"],
        "X-Device-Token": device["device_token"],
    }
    return site, device, headers


def test_event_ingestion_is_idempotent_and_snapshot_is_private(production_client) -> None:
    client, _messages = production_client
    site, _device, headers = _provision(client)
    event = {
        "event_id": "evt-1",
        "event_type": "zone_entered",
        "severity": "warning",
        "camera_id": "cam-1",
        "zone": "ombor",
        "has_snapshot": True,
    }
    for _ in range(2):
        response = client.post(
            "/api/v1/edge/events/batch", headers=headers, json={"events": [event]}
        )
        assert response.status_code == 200
        assert response.json()["accepted"] == ["evt-1"]
    upload = client.put(
        "/api/v1/edge/events/evt-1/snapshot",
        headers={**headers, "Content-Type": "image/jpeg"},
        content=b"jpeg-data",
    )
    assert upload.status_code == 200

    admin_headers = {"X-Cloud-Admin-Key": "test-admin"}
    member = client.post(
        f"/api/v1/admin/sites/{site['site_id']}/members",
        headers=admin_headers,
        json={"telegram_id": "101", "role": "owner"},
    )
    assert member.status_code == 200
    assert client.get("/api/v1/owner/events/evt-1/snapshot").status_code == 401


def test_edge_health_heartbeat_is_visible_to_owner(production_client) -> None:
    client, _messages = production_client
    site, _device, headers = _provision(client)
    client.post(
        f"/api/v1/admin/sites/{site['site_id']}/members",
        headers={"X-Cloud-Admin-Key": "test-admin"},
        json={"telegram_id": "303", "role": "owner"},
    )
    client.post("/api/v1/owner/auth/request", json={"telegram_id": "303"})
    token = client.post(
        "/api/v1/owner/auth/verify",
        json={"telegram_id": "303", "site_id": site["site_id"], "code": "123456"},
    ).json()["access_token"]
    heartbeat = client.post(
        "/api/v1/edge/heartbeat",
        headers=headers,
        json={
            "cameras_active": 8,
            "temperature_c": 64.5,
            "disk_free_bytes": 1000,
            "outbox_pending": 2,
            "outbox_bytes": 300,
            "app_version": "0.3.0",
        },
    )
    assert heartbeat.status_code == 200
    health = client.get(
        "/api/v1/owner/health", headers={"Authorization": f"Bearer {token}"}
    ).json()
    assert health["devices"][0]["health"]["cameras_active"] == 8
    assert health["cameras_expected"] == 8


def test_owner_otp_login_and_tenant_event_access(production_client) -> None:
    client, messages = production_client
    site, _device, headers = _provision(client)
    client.post(
        f"/api/v1/admin/sites/{site['site_id']}/members",
        headers={"X-Cloud-Admin-Key": "test-admin"},
        json={"telegram_id": "202", "role": "owner", "display_name": "Owner"},
    )
    requested = client.post(
        "/api/v1/owner/auth/request", json={"telegram_id": "202"}
    )
    assert requested.status_code == 200
    assert requested.json()["debug_code"] == "123456"
    assert messages and messages[-1][0] == "202"

    verified = client.post(
        "/api/v1/owner/auth/verify",
        json={
            "telegram_id": "202",
            "site_id": site["site_id"],
            "code": "123456",
        },
    )
    assert verified.status_code == 200
    owner_headers = {"Authorization": f"Bearer {verified.json()['access_token']}"}

    client.post(
        "/api/v1/edge/events/batch",
        headers=headers,
        json={
            "events": [
                {
                    "event_id": "evt-owner",
                    "event_type": "person_detected",
                    "camera_id": "cam-2",
                }
            ]
        },
    )
    result = client.get("/api/v1/owner/events", headers=owner_headers)
    assert result.status_code == 200
    assert [event["event_id"] for event in result.json()["events"]] == ["evt-owner"]
    config = client.put(
        "/api/v1/owner/config",
        headers=owner_headers,
        json={
            "camera_labels": {"camera-01": "Kirish"},
            "occupancy_limit": 15,
            "loitering_sec": 90,
            "zones": [
                {
                    "name": "ombor",
                    "camera_id": "camera-01",
                    "restricted": True,
                    "polygon": [[0, 0], [1, 0], [1, 1]],
                }
            ],
        },
    )
    assert config.status_code == 200
    assert config.json()["revision"] == 1
    edge_config = client.get("/api/v1/edge/config", headers=headers).json()
    assert edge_config["config"]["occupancy_limit"] == 15

    feature_view = client.get("/api/v1/owner/features", headers=owner_headers)
    assert feature_view.status_code == 200
    assert feature_view.json()["catalog"]["price_book"]["base_fee_usd_cents"] == 2_000
    feature_request = client.put(
        "/api/v1/owner/features/request",
        headers=owner_headers,
        json={"selections": [{"feature_code": "person_count", "camera_count": 2}]},
    )
    assert feature_request.status_code == 200
    assert feature_request.json()["drafts"][0]["feature_code"] == "person_count"
    invoice = client.post("/api/v1/owner/invoices", headers=owner_headers, json={"months": 1})
    assert invoice.status_code == 200
    assert invoice.json()["pay_url"].startswith("/pay/")
    assert client.get("/api/v1/owner/invoices", headers=owner_headers).json()[0]["id"] == invoice.json()["id"]
    assert client.get("/owner").status_code == 200
