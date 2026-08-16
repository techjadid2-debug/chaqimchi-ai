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
    clip_upload = client.put(
        "/api/v1/edge/events/evt-1/clip",
        headers={**headers, "Content-Type": "video/mp4"},
        content=b"mp4-data",
    )
    assert clip_upload.status_code == 200

    admin_headers = {"X-Cloud-Admin-Key": "test-admin"}
    member = client.post(
        f"/api/v1/admin/sites/{site['site_id']}/members",
        headers=admin_headers,
        json={"telegram_id": "101", "role": "owner"},
    )
    assert member.status_code == 200
    assert client.get("/api/v1/owner/events/evt-1/snapshot").status_code == 401
    assert client.get("/api/v1/owner/events/evt-1/clip").status_code == 401

    owner_headers = _login_owner(client, site["site_id"], telegram_id="102")
    private_snapshot = client.get("/api/v1/owner/events/evt-1/snapshot", headers=owner_headers)
    private_clip = client.get("/api/v1/owner/events/evt-1/clip", headers=owner_headers)
    assert private_snapshot.content == b"jpeg-data"
    assert private_snapshot.headers["content-type"] == "image/jpeg"
    assert private_clip.content == b"mp4-data"
    assert private_clip.headers["content-type"] == "video/mp4"


def test_late_clip_retry_does_not_duplicate_the_telegram_alert(production_client) -> None:
    client, messages = production_client
    site, _device, headers = _provision(client)
    client.post(
        f"/api/v1/admin/sites/{site['site_id']}/members",
        headers={"X-Cloud-Admin-Key": "test-admin"},
        json={"telegram_id": "404", "role": "owner"},
    )
    event = {
        "event_id": "evt-late-clip",
        "event_type": "camera_tampered",
        "severity": "critical",
        "camera_id": "camera-01",
        "has_snapshot": True,
    }

    first = client.post("/api/v1/edge/events/batch", headers=headers, json={"events": [event]})
    event["has_clip"] = True
    second = client.post("/api/v1/edge/events/batch", headers=headers, json={"events": [event]})

    assert first.json()["accepted"] == ["evt-late-clip"]
    assert second.json()["accepted"] == ["evt-late-clip"]
    assert len(messages) == 1
    assert "Rasm va klip" in messages[0][1]


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
    health = client.get("/api/v1/owner/health", headers={"Authorization": f"Bearer {token}"}).json()
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
    requested = client.post("/api/v1/owner/auth/request", json={"telegram_id": "202"})
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
    assert (
        client.get("/api/v1/owner/invoices", headers=owner_headers).json()[0]["id"]
        == invoice.json()["id"]
    )
    assert client.get("/owner").status_code == 200


def _login_owner(client: TestClient, site_id: str, telegram_id: str = "404") -> dict:
    client.post(
        f"/api/v1/admin/sites/{site_id}/members",
        headers={"X-Cloud-Admin-Key": "test-admin"},
        json={"telegram_id": telegram_id, "role": "owner", "display_name": "Owner"},
    )
    client.post("/api/v1/owner/auth/request", json={"telegram_id": telegram_id})
    verified = client.post(
        "/api/v1/owner/auth/verify",
        json={"telegram_id": telegram_id, "site_id": site_id, "code": "123456"},
    )
    return {"Authorization": f"Bearer {verified.json()['access_token']}"}


def test_owner_report_separates_entries_from_exits(production_client) -> None:
    """Mijoz "line_crossed: 3" emas, "2 kishi kirdi" degan javobni oladi."""
    client, _messages = production_client
    site, _device, headers = _provision(client)
    owner_headers = _login_owner(client, site["site_id"])
    client.post(
        "/api/v1/edge/events/batch",
        headers=headers,
        json={
            "events": [
                {
                    "event_id": f"evt-{index}",
                    "event_type": "line_crossed",
                    "camera_id": "camera-01",
                    "direction": direction,
                    "line": "eshik",
                }
                for index, direction in enumerate(["in", "in", "out"])
            ]
        },
    )

    report = client.get("/api/v1/owner/report", headers=owner_headers)

    assert report.status_code == 200
    assert report.json()["traffic"]["entered"] == 2
    assert report.json()["traffic"]["exited"] == 1


def test_owner_report_rejects_a_broken_date(production_client) -> None:
    client, _messages = production_client
    site, _device, _headers = _provision(client)
    owner_headers = _login_owner(client, site["site_id"])

    answer = client.get("/api/v1/owner/report?date=13-08-2026", headers=owner_headers)

    assert answer.status_code == 422


def test_owner_events_carry_uzbek_labels(production_client) -> None:
    """Panelda `line_crossed` emas, "Kirish/chiqish" ko'rinishi kerak."""
    client, _messages = production_client
    site, _device, headers = _provision(client)
    owner_headers = _login_owner(client, site["site_id"])
    client.post(
        "/api/v1/edge/events/batch",
        headers=headers,
        json={
            "events": [
                {
                    "event_id": "evt-label",
                    "event_type": "camera_tampered",
                    "severity": "critical",
                    "camera_id": "camera-01",
                }
            ]
        },
    )

    events = client.get("/api/v1/owner/events", headers=owner_headers).json()["events"]

    assert events[0]["label"] == "Kamera yopildi yoki burildi"


def test_owner_report_needs_authentication(production_client) -> None:
    client, _messages = production_client
    _provision(client)

    assert client.get("/api/v1/owner/report").status_code in {401, 403}


def test_owner_trend_returns_a_full_week(production_client) -> None:
    client, _messages = production_client
    site, _device, headers = _provision(client)
    owner_headers = _login_owner(client, site["site_id"], telegram_id="505")
    client.post(
        "/api/v1/edge/events/batch",
        headers=headers,
        json={
            "events": [
                {
                    "event_id": "evt-trend",
                    "event_type": "line_crossed",
                    "camera_id": "camera-01",
                    "direction": "in",
                }
            ]
        },
    )

    trend = client.get("/api/v1/owner/trend?days=7", headers=owner_headers).json()

    assert len(trend["daily"]) == 7
    assert trend["total"] == 1
    # Bugun oxirgi ustun bo'lishi kerak — grafik chapdan o'ngga o'sadi.
    assert trend["daily"][-1]["entered"] == 1


# ── Sinov rejimi: kodsiz kirish ──────────────────────────────────────────
#
# Mijozga ko'rsatish uchun vaqtincha yoqilgan imtiyoz.  Bu **ataylab
# qo'yilgan zaiflik**, shuning uchun chegaralari testda qat'iy
# belgilanadi: standart holatda o'chiq, faqat ro'yxatdagi ID ga, va
# faqat haqiqiy a'zoga.


# Har test **o'z** Telegram ID sidan foydalanadi.  `ratelimit` baketi
# telegram_id bo'yicha va testlar orasida umumiy: bir xil ID uchinchi
# so'rovdan keyin 429 oladi va tekshirilayotgan mantiqqa umuman yetib
# bormaydi — test esa sababini aytmasdan qulardi.


def _member(client, site_id: str, telegram_id: str, role: str = "owner") -> None:
    client.post(
        f"/api/v1/admin/sites/{site_id}/members",
        headers={"X-Cloud-Admin-Key": "test-admin"},
        json={"telegram_id": telegram_id, "role": role},
    )


def test_listed_id_gets_a_token_without_a_code(production_client, monkeypatch) -> None:
    """Ro'yxatdagi odam kod terib o'tirmaydi."""
    client, messages = production_client
    site, _device, _headers = _provision(client)
    _member(client, site["site_id"], "5476913898")
    monkeypatch.setenv("CHAQIMCHI_OTP_BYPASS_IDS", "5476913898,7631725599")

    response = client.post(
        "/api/v1/owner/auth/request",
        json={"telegram_id": "5476913898", "site_id": site["site_id"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["bypass"] is True
    assert body["access_token"], "token darhol berilishi kerak"
    assert body["site_id"] == site["site_id"]
    # Kod yuborilmasligi ham kerak — bekorga xabar bormasin.
    assert not messages


def test_the_token_actually_opens_the_panel(production_client, monkeypatch) -> None:
    """Token haqiqiy bo'lsin — "ok" deb yolg'on aytmasin."""
    client, _messages = production_client
    site, _device, _headers = _provision(client)
    _member(client, site["site_id"], "7631725599")
    monkeypatch.setenv("CHAQIMCHI_OTP_BYPASS_IDS", "5476913898,7631725599")

    token = client.post(
        "/api/v1/owner/auth/request",
        json={"telegram_id": "7631725599", "site_id": site["site_id"]},
    ).json()["access_token"]

    events = client.get("/api/v1/owner/events", headers={"Authorization": f"Bearer {token}"})
    assert events.status_code == 200


def test_bypass_is_off_by_default(production_client, monkeypatch) -> None:
    """Muhit o'zgaruvchisi qo'yilmasa imtiyoz umuman yo'q."""
    client, _messages = production_client
    site, _device, _headers = _provision(client)
    _member(client, site["site_id"], "5476000001")
    monkeypatch.delenv("CHAQIMCHI_OTP_BYPASS_IDS", raising=False)

    body = client.post(
        "/api/v1/owner/auth/request",
        json={"telegram_id": "5476000001", "site_id": site["site_id"]},
    ).json()

    assert "access_token" not in body, "standart holatda kodsiz kirish bo'lmasin"
    assert not body.get("bypass")


def test_unlisted_id_still_needs_a_code(production_client, monkeypatch) -> None:
    """Imtiyoz aynan ro'yxatdagilarga — qolganlarga tegmaydi."""
    client, _messages = production_client
    site, _device, _headers = _provision(client)
    _member(client, site["site_id"], "999000111")
    monkeypatch.setenv("CHAQIMCHI_OTP_BYPASS_IDS", "5476913898,7631725599")

    body = client.post(
        "/api/v1/owner/auth/request",
        json={"telegram_id": "999000111", "site_id": site["site_id"]},
    ).json()

    assert "access_token" not in body


def test_bypass_does_not_let_in_a_stranger(production_client, monkeypatch) -> None:
    """Eng muhim chegara: ro'yxatda bo'lish **a'zolikni almashtirmaydi**.

    Aks holda ro'yxatga tushib qolgan ID istalgan obyektga kira olardi.
    """
    client, _messages = production_client
    _site, _device, _headers = _provision(client)
    monkeypatch.setenv("CHAQIMCHI_OTP_BYPASS_IDS", "5476000002")

    body = client.post(
        "/api/v1/owner/auth/request", json={"telegram_id": "5476000002"}
    ).json()

    # Hech qanday obyektga a'zo emas → token yo'q, sir ham oshkor bo'lmaydi.
    assert "access_token" not in body
    assert body["message"] == "Agar akkaunt mavjud bo'lsa, kod yuborildi"


def test_bypass_use_is_logged_loudly(production_client, monkeypatch, caplog) -> None:
    """Vaqtincha zaiflik jimgina qolib ketmasligi kerak."""
    import logging

    client, _messages = production_client
    site, _device, _headers = _provision(client)
    _member(client, site["site_id"], "5476000003")
    monkeypatch.setenv("CHAQIMCHI_OTP_BYPASS_IDS", "5476000003")

    with caplog.at_level(logging.WARNING):
        client.post(
            "/api/v1/owner/auth/request",
            json={"telegram_id": "5476000003", "site_id": site["site_id"]},
        )

    # `getMessage()` — `%s` o'rinlari to'ldirilgan matn; `record.message`
    # formatlashdan oldin bo'sh bo'lishi mumkin.
    messages = [record.getMessage() for record in caplog.records]
    assert any(
        "CHETLAB O'TILDI" in text and "5476000003" in text for text in messages
    ), "imtiyoz ishlatilgani ogohlantirish bo'lib logga tushsin"


def test_code_login_still_works(production_client, monkeypatch) -> None:
    """Odatdagi yo'l buzilmaganini tekshiramiz."""
    client, _messages = production_client
    site, _device, _headers = _provision(client)
    _member(client, site["site_id"], "424242")
    monkeypatch.setenv("CHAQIMCHI_OTP_BYPASS_IDS", "5476913898")

    client.post("/api/v1/owner/auth/request", json={"telegram_id": "424242"})
    verified = client.post(
        "/api/v1/owner/auth/verify",
        json={"telegram_id": "424242", "site_id": site["site_id"], "code": "123456"},
    )

    assert verified.status_code == 200
    assert verified.json()["access_token"]
