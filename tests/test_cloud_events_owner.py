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


def test_media_quota_evicts_oldest_media_but_keeps_events(
    production_client, monkeypatch
) -> None:
    """Bitta shovqinli sayt VPS diskini to'ldira olmasin.

    Kvotadan oshganda eng eski media o'chadi, hodisa yozuvi (statistika)
    esa qoladi — edge'dagi `outbox.prune` mantig'i bilan bir xil.
    """
    import cloud.main as main

    client, _messages = production_client
    site, _device, headers = _provision(client)

    for index in range(3):
        event_id = f"evt-quota-{index}"
        client.post(
            "/api/v1/edge/events/batch",
            headers=headers,
            json={
                "events": [
                    {
                        "event_id": event_id,
                        "event_type": "line_crossed",
                        "camera_id": "cam-1",
                        "occurred_at": f"2026-01-0{index + 1}T10:00:00+00:00",
                        "has_snapshot": True,
                    }
                ]
            },
        )
        upload = client.put(
            f"/api/v1/edge/events/{event_id}/snapshot",
            headers={**headers, "Content-Type": "image/jpeg"},
            content=b"x" * 1000,
        )
        assert upload.status_code == 200

    # Kvota: 2 ta snapshot sig'adi, 3-chisi eng eskisini siqib chiqaradi.
    monkeypatch.setenv("CHAQIMCHI_SITE_MEDIA_MAX_BYTES", "2000")
    main._purge_expired_events()

    store = main.get_event_store()
    events = {e["event_id"]: e for e in store.list_events(site["site_id"], limit=10)}
    assert len(events) == 3, "hodisa yozuvlari o'chmasligi kerak"
    assert not events["evt-quota-0"]["snapshot_key"], "eng eski media bo'shatiladi"
    assert events["evt-quota-2"]["snapshot_key"], "eng yangi media qoladi"
    assert store.media_usage_bytes(site["site_id"]) <= 2000


def test_claim_is_rate_limited(production_client) -> None:
    """Pairing kodni qo'pol kuch bilan terib bo'lmasin.

    Kod 6 hex belgi va 48 soat yashaydi; cheklovsiz bu endpoint begona
    do'konning qurilma tokenini (u orqali RTSP parollarini) topib olish
    uchun ochiq eshik bo'lardi.  Halol qurilma 1-2 marta claim qiladi.
    """
    client, _messages = production_client

    responses = [
        client.post("/api/v1/devices/claim", json={"pairing_code": "AAAAAA"}).status_code
        for _ in range(12)
    ]

    assert 429 in responses, "claim so'rovlari chegaralanishi shart"
    assert responses[0] == 400, "birinchi urinishlar odatdagidek tekshirilsin"


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


# ── Kirish havolasi: `/owner?key=<token>` ────────────────────────────────
#
# Kodsiz kirishning xavfsiz ko'rinishi.  Ilgari bu o'rinda Telegram ID
# ro'yxati (`CHAQIMCHI_OTP_BYPASS_IDS`) bor edi — ID sir emasligi uchun
# olib tashlandi.  Endi credential — uzun tasodifiy token: faqat admin
# yaratadi, yangi havola eskisini bekor qiladi, a'zolik har kirishda
# qayta tekshiriladi.


def _member(client, site_id: str, telegram_id: str, role: str = "owner") -> None:
    client.post(
        f"/api/v1/admin/sites/{site_id}/members",
        headers={"X-Cloud-Admin-Key": "test-admin"},
        json={"telegram_id": telegram_id, "role": role},
    )


def _make_link(client, site_id: str, telegram_id: str):
    return client.post(
        f"/api/v1/admin/sites/{site_id}/members/{telegram_id}/login-link",
        headers={"X-Cloud-Admin-Key": "test-admin"},
    )


def _key_of(response) -> str:
    url = response.json()["url"]
    assert "/owner?key=" in url
    return url.split("key=", 1)[1]


def test_link_opens_the_panel(production_client) -> None:
    """Havola bosilishi bilan panel ochiladi — kod so'ralmaydi."""
    client, messages = production_client
    site, _device, _headers = _provision(client)
    _member(client, site["site_id"], "5476000010")

    key = _key_of(_make_link(client, site["site_id"], "5476000010"))
    session = client.post("/api/v1/owner/auth/link", json={"key": key})

    assert session.status_code == 200
    token = session.json()["access_token"]
    assert session.json()["site_id"] == site["site_id"]
    events = client.get("/api/v1/owner/events", headers={"Authorization": f"Bearer {token}"})
    assert events.status_code == 200
    # Havola OTP emas — Telegramga xabar ketmasin.
    assert not messages


def test_link_needs_a_real_member(production_client) -> None:
    """Havola faqat mavjud a'zoga yaratiladi — begona ID uchun yo'q."""
    client, _messages = production_client
    site, _device, _headers = _provision(client)

    response = _make_link(client, site["site_id"], "5476000011")

    assert response.status_code == 404


def test_guessed_key_is_rejected(production_client) -> None:
    client, _messages = production_client
    _provision(client)

    response = client.post(
        "/api/v1/owner/auth/link", json={"key": "x" * 43}
    )

    assert response.status_code == 401


def test_new_link_revokes_the_old_one(production_client) -> None:
    """"Havola tarqalib ketdi" muammosi bitta tugma bilan yopiladi."""
    client, _messages = production_client
    site, _device, _headers = _provision(client)
    _member(client, site["site_id"], "5476000012")

    old_key = _key_of(_make_link(client, site["site_id"], "5476000012"))
    new_key = _key_of(_make_link(client, site["site_id"], "5476000012"))

    assert client.post("/api/v1/owner/auth/link", json={"key": old_key}).status_code == 401
    assert client.post("/api/v1/owner/auth/link", json={"key": new_key}).status_code == 200


def test_revoked_link_stops_working(production_client) -> None:
    client, _messages = production_client
    site, _device, _headers = _provision(client)
    _member(client, site["site_id"], "5476000013")
    key = _key_of(_make_link(client, site["site_id"], "5476000013"))

    revoke = client.delete(
        f"/api/v1/admin/sites/{site['site_id']}/members/5476000013/login-link",
        headers={"X-Cloud-Admin-Key": "test-admin"},
    )

    assert revoke.status_code == 200
    assert revoke.json()["revoked"] == 1
    assert client.post("/api/v1/owner/auth/link", json={"key": key}).status_code == 401


def test_expired_link_is_rejected(production_client) -> None:
    """Muddat tekshiruvi ham ishlaydi — abadiy havola yo'q."""
    import cloud.main as main

    client, _messages = production_client
    site, _device, _headers = _provision(client)
    _member(client, site["site_id"], "5476000014")

    key = main.get_event_store().create_login_link(
        site["site_id"],
        "5476000014",
        secret="owner-secret-with-more-than-32-characters",
        ttl_days=0,
    )

    assert client.post("/api/v1/owner/auth/link", json={"key": key}).status_code == 401


def test_disabled_member_link_stops_working(production_client) -> None:
    """A'zolik har kirishda qayta tekshiriladi.

    A'zo o'chirilgach uning qo'lidagi eski havola ham darhol o'lishi
    shart — aks holda "xodim ketdi, kirishi qoldi" bo'lardi.
    """
    import cloud.main as main

    client, _messages = production_client
    site, _device, _headers = _provision(client)
    _member(client, site["site_id"], "5476000015")
    key = _key_of(_make_link(client, site["site_id"], "5476000015"))
    member = main.get_event_store().member_for_site(site["site_id"], "5476000015")
    main.get_event_store().disable_member(site["site_id"], member["id"])

    assert client.post("/api/v1/owner/auth/link", json={"key": key}).status_code == 401


def test_otp_test_code_is_ignored_in_production(production_client, monkeypatch) -> None:
    """Production'da qat'iy test kodi ishlatilmaydi.

    Lifespan bunday serverni umuman yoqmaydi, lekin himoya bir qavat
    bilan qolmasin: env qanday bo'lmasin, so'rov paytida ham test kod
    faqat test muhitida qo'llanadi.
    """
    client, _messages = production_client
    site, _device, _headers = _provision(client)
    _member(client, site["site_id"], "5476000016")
    monkeypatch.setenv("CHAQIMCHI_ENV", "production")

    client.post("/api/v1/owner/auth/request", json={"telegram_id": "5476000016"})
    verified = client.post(
        "/api/v1/owner/auth/verify",
        json={"telegram_id": "5476000016", "site_id": site["site_id"], "code": "123456"},
    )

    assert verified.status_code == 401, "test kod production'da o'tmasin"


def test_production_startup_refuses_test_doors(tmp_path, monkeypatch) -> None:
    """Sinov eshiklari qolgan production server umuman yonmaydi."""
    import cloud.main as main

    monkeypatch.setenv("CHAQIMCHI_ENV", "production")
    monkeypatch.setenv("CHAQIMCHI_OTP_TEST_CODE", "123456")
    monkeypatch.setenv("CHAQIMCHI_OTP_BYPASS_IDS", "42")
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "cloud.db")
    monkeypatch.setattr(main, "_store", None)
    monkeypatch.setattr(main, "_event_store", None)
    monkeypatch.setattr(main, "_event_store_key", None)

    with pytest.raises(RuntimeError) as excinfo:
        with TestClient(main.app):
            pass

    assert "CHAQIMCHI_OTP_TEST_CODE" in str(excinfo.value)
    assert "CHAQIMCHI_OTP_BYPASS_IDS" in str(excinfo.value)


def test_code_login_still_works(production_client) -> None:
    """Odatdagi OTP yo'li buzilmaganini tekshiramiz."""
    client, _messages = production_client
    site, _device, _headers = _provision(client)
    _member(client, site["site_id"], "424242")

    client.post("/api/v1/owner/auth/request", json={"telegram_id": "424242"})
    verified = client.post(
        "/api/v1/owner/auth/verify",
        json={"telegram_id": "424242", "site_id": site["site_id"], "code": "123456"},
    )

    assert verified.status_code == 200
    assert verified.json()["access_token"]
