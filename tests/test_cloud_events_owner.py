from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import cloud.main as main
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

    async def fake_send(chat_id: str, text: str, *, reply_markup=None) -> None:
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


def test_config_profile_matches_the_device_product(production_client) -> None:
    """Windows do'kon kompyuteri N100 pasportini olmasin.

    Ilgari hamma qurilmaga bitta profil ketardi: Windows PC o'zini
    "Intel N100" deb hisoblab, 40 GB bufer va 20 GB bo'sh joy siyosatini
    qabul qilardi.
    """
    client, _messages = production_client
    site, _device, headers = _provision(client)

    # Sotqin (product_name'siz eski claim ham shu yo'lga tushadi).
    sotqin_config = client.get("/api/v1/sotqin/config", headers=headers).json()
    assert sotqin_config["product"]["hardware_model"] == "Intel N100"
    assert sotqin_config["buffer_policy"]["max_bytes"] == 40 * 1024**3

    # Windows qurilma — o'z profili.
    code = client.post(
        f"/api/v1/admin/sites/{site['site_id']}/pairing",
        headers={"X-Cloud-Admin-Key": "test-admin"},
    ).json()["pairing_code"]
    windows = client.post(
        "/api/v1/devices/claim",
        json={"pairing_code": code, "product_name": "Chaqimchi Windows"},
    ).json()
    win_headers = {
        "X-Site-Id": windows["site_id"],
        "X-Device-Id": windows["device_id"],
        "X-Device-Token": windows["device_token"],
    }
    win_config = client.get("/api/v1/sotqin/config", headers=win_headers).json()
    assert win_config["product"]["name"] == "Chaqimchi Windows"
    assert "hardware_model" not in win_config["product"]
    assert win_config["product"]["max_cameras"] == 4
    assert "max_bytes" not in win_config["buffer_policy"], "N100 bufer siyosati ketmasin"


def test_media_quota_evicts_oldest_media_but_keeps_events(production_client, monkeypatch) -> None:
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
    # Yangi format: do'kon nomi sarlavhada, hodisa odam tilida.
    assert "Kamera yopildi" in messages[0][1]


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

    response = client.post("/api/v1/owner/auth/link", json={"key": "x" * 43})

    assert response.status_code == 401


def test_new_link_revokes_the_old_one(production_client) -> None:
    """ "Havola tarqalib ketdi" muammosi bitta tugma bilan yopiladi."""
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


# ── Telegram tartibi (minimal rejim) ─────────────────────────────────────


def test_member_gets_at_most_ten_alerts_per_hour(production_client) -> None:
    """Soatlik shaxsiy limit: undan ko'pi baribir o'qilmaydi va mijoz
    botni o'chirtiradi.  Kamera/tur soni qancha bo'lmasin — 10 ta."""
    client, messages = production_client
    site, _device, headers = _provision(client)
    _member(client, site["site_id"], "5476100001")

    for index in range(12):
        client.post(
            "/api/v1/edge/events/batch",
            headers=headers,
            json={
                "events": [
                    {
                        "event_id": f"evt-cap-{index}",
                        "event_type": "camera_tampered",
                        "severity": "critical",
                        "camera_id": f"cam-{index:02d}",
                    }
                ]
            },
        )

    assert len(messages) == 10, "soatiga 10 tadan oshmasin"


def test_alert_throttle_survives_a_restart(production_client) -> None:
    """Tormoz bazada: deploy'dan keyin xabar bo'roni bo'lmasin."""
    import cloud.main as main

    client, _messages = production_client
    _provision(client)

    store = main.get_store()
    assert store.alert_throttle_allow("site-x", "camera_tampered:cam-1") is True
    assert store.alert_throttle_allow("site-x", "camera_tampered:cam-1") is False

    # "Restart": xuddi shu DB ustida yangi CloudStore ochamiz.
    from cloud.store import CloudStore

    fresh = CloudStore(store.db_path)
    assert fresh.alert_throttle_allow("site-x", "camera_tampered:cam-1") is False, (
        "tormoz restartdan keyin ham eslab qolsin"
    )


def test_missing_chat_stops_future_sends(production_client, monkeypatch) -> None:
    """ "Chat not found" — a'zo botga /start bosmagan.  3 urinishdan keyin
    unga yuborish to'xtaydi; ilgari har batch'da log xatoga to'lardi."""
    import cloud.main as main

    client, _messages = production_client
    site, _device, headers = _provision(client)
    _member(client, site["site_id"], "5476100002")

    attempts = []

    async def failing_send(chat_id, text, *, reply_markup=None):
        attempts.append(chat_id)
        raise main.TelegramSendError(400, '{"description":"Bad Request: chat not found"}')

    monkeypatch.setattr(main, "_send_owner_telegram", failing_send)

    for index in range(5):
        client.post(
            "/api/v1/edge/events/batch",
            headers=headers,
            json={
                "events": [
                    {
                        "event_id": f"evt-nf-{index}",
                        "event_type": "camera_tampered",
                        "severity": "critical",
                        "camera_id": f"cam-nf-{index}",
                    }
                ]
            },
        )

    assert len(attempts) == 3, "3 muvaffaqiyatsizlikdan keyin urinish to'xtasin"
    member = main.get_event_store().list_members(site["site_id"])[0]
    assert int(member["notify_failures"]) >= 3


def test_owner_can_mute_the_daily_digest(production_client) -> None:
    client, _messages = production_client
    site, _device, _headers = _provision(client)
    _member(client, site["site_id"], "5476100003")
    key = _key_of(_make_link(client, site["site_id"], "5476100003"))
    token = client.post("/api/v1/owner/auth/link", json={"key": key}).json()["access_token"]

    response = client.put(
        "/api/v1/owner/digest",
        headers={"Authorization": f"Bearer {token}"},
        json={"muted": True},
    )

    assert response.status_code == 200
    import cloud.main as main

    member = main.get_event_store().list_members(site["site_id"])[0]
    assert int(member["digest_muted"]) == 1


def test_lite_plan_includes_every_feature_out_of_the_box(production_client) -> None:
    """Yagona tarif (2026-08-17): Chaqimchi Lite'da HAMMA funksiya ichida.

    Ilgari cloud_features faqat qo'lda approve qilingan assignmentlardan
    kelardi va hech bir saytga avto-biriktirilmasdi — pullik mijozning
    qurilmasi litsenziya filtri sabab hodisalarni jimgina tashlab yuborardi.
    """
    client, _messages = production_client

    site = client.post(
        "/api/v1/admin/sites",
        headers={"X-Cloud-Admin-Key": "test-admin"},
        json={"name": "Lite do'kon", "plan": "lite"},
    ).json()
    device = client.post(
        "/api/v1/devices/claim", json={"pairing_code": site["pairing_code"]}
    ).json()
    headers = {
        "X-Site-Id": device["site_id"],
        "X-Device-Id": device["device_id"],
        "X-Device-Token": device["device_token"],
    }

    config = client.get("/api/v1/sotqin/config", headers=headers).json()

    codes = {item["code"] for item in config["cloud_features"]}
    assert codes == {"person_count", "queue_length", "store_security"}
    assert all(item["camera_count"] == 4 for item in config["cloud_features"])


def test_non_sellable_plan_still_needs_assignments(production_client) -> None:
    """Maxsus tariflar (enterprise) assignment orqali boshqarilaveradi."""
    client, _messages = production_client
    _site, _device, headers = _provision(client)  # plan="enterprise"

    config = client.get("/api/v1/sotqin/config", headers=headers).json()

    assert config["cloud_features"] == []


def test_alert_goes_out_with_the_snapshot_photo(production_client, monkeypatch) -> None:
    """Rasmli alert: snapshot bo'lsa xabar sendPhoto bilan ketadi.

    Bot "xunuk" bo'lishining bosh sababi shu edi: snapshot cloudda yotar,
    bot esa quruq matn yuborar edi.
    """
    import asyncio

    import cloud.main as main
    from chaqimchi_ai.event_models import EdgeEvent

    client, messages = production_client
    site, _device, headers = _provision(client)
    _member(client, site["site_id"], "5476200001")

    photos = []

    async def fake_photo(chat_id, photo, caption, *, reply_markup=None):
        photos.append((chat_id, photo, caption, reply_markup))

    monkeypatch.setattr(main, "_send_owner_photo", fake_photo)

    event = EdgeEvent(
        event_id="evt-photo-1",
        event_type="camera_tampered",
        severity="critical",
        camera_id="camera-01",
        has_snapshot=True,
    )
    client.post(
        "/api/v1/edge/events/batch",
        headers=headers,
        json={
            "events": [
                {
                    "event_id": "evt-photo-1",
                    "event_type": "camera_tampered",
                    "severity": "critical",
                    "camera_id": "camera-01",
                    "has_snapshot": True,
                }
            ]
        },
    )
    # Batch paytida rasm hali kelmagan — matn ketdi.  Endi snapshot yetib
    # keldi deb faraz qilib, alert oqimini qayta chaqiramiz.
    client.put(
        "/api/v1/edge/events/evt-photo-1/snapshot",
        headers={**headers, "Content-Type": "image/jpeg"},
        content=b"jpeg-bytes",
    )
    asyncio.run(main._notify_alert(site["site_id"], [event]))

    assert photos, "snapshot bor — sendPhoto ishlatilsin"
    chat_id, photo, caption, _markup = photos[-1]
    assert photo == b"jpeg-bytes"
    assert "Set-1" in caption, "do'kon nomi sarlavhada bo'lsin"
    assert "Kamera yopildi" in caption


# ── Bot buyruqlari (/hisobot, /kamera, /panel, /yordam) ──────────────────


def _webhook(client, text: str, chat_id: int = 900111):
    return client.post(
        "/api/v1/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "webhook-test"},
        json={"message": {"chat": {"id": chat_id, "type": "private"}, "text": text}},
    )


@pytest.fixture
def bot_member_client(production_client, monkeypatch):
    """Webhook + saytga ulangan a'zo bilan tayyor muhit."""
    client, messages = production_client
    monkeypatch.setenv("CHAQIMCHI_TELEGRAM_WEBHOOK_SECRET", "webhook-test")
    site, device, headers = _provision(client)
    client.post(
        f"/api/v1/admin/sites/{site['site_id']}/members",
        headers={"X-Cloud-Admin-Key": "test-admin"},
        json={"telegram_id": "900111", "role": "owner"},
    )
    return client, messages, site, headers


def test_hisobot_command_sends_the_daily_report(bot_member_client) -> None:
    client, messages, site, headers = bot_member_client
    client.post(
        "/api/v1/edge/events/batch",
        headers=headers,
        json={
            "events": [
                {
                    "event_id": "evt-in-1",
                    "event_type": "line_crossed",
                    "camera_id": "camera-01",
                    "direction": "in",
                }
            ]
        },
    )
    messages.clear()

    assert _webhook(client, "/hisobot").status_code == 200

    assert len(messages) == 1
    text = messages[0][1]
    assert "kunlik hisobot" in text
    assert "Kirdi: <b>1</b> kishi" in text
    assert "📷 Kamera:" in text


def test_old_commands_stay_as_aliases(bot_member_client) -> None:
    """/today va /status yodlab qolganlar uchun ishlashda davom etadi."""
    client, messages, _site, _headers = bot_member_client

    assert _webhook(client, "/today").status_code == 200

    assert len(messages) == 1
    assert "Bugun hali hodisa yo'q" in messages[0][1]


def test_yordam_lists_the_commands(bot_member_client) -> None:
    client, messages, _site, _headers = bot_member_client

    _webhook(client, "/yordam")

    assert "/hisobot" in messages[0][1]
    assert "/kamera" in messages[0][1]


def test_panel_command_gives_a_fresh_login_link(bot_member_client) -> None:
    client, messages, _site, _headers = bot_member_client

    _webhook(client, "/panel")

    assert "oldingi kirish havolangiz endi ishlamaydi" in messages[0][1]


def test_unknown_text_gets_a_short_hint(bot_member_client) -> None:
    client, messages, _site, _headers = bot_member_client

    _webhook(client, "salom")

    assert messages[0][1] == "Buyruqlar: /hisobot, /kamera, /panel, /yordam"


def test_kamera_without_cameras_explains_itself(bot_member_client) -> None:
    client, messages, _site, _headers = bot_member_client

    _webhook(client, "/kamera")

    assert "Kameralar hali ulanmagan" in messages[0][1]


def test_kamera_sends_the_last_preview_and_requests_a_new_one(
    bot_member_client, monkeypatch
) -> None:
    from cryptography.fernet import Fernet

    import cloud.main as main

    client, messages, site, _headers = bot_member_client
    monkeypatch.setenv("CHAQIMCHI_CAMERA_SECRET_KEY", Fernet.generate_key().decode())
    store = main.get_store()
    store.upsert_camera(site["site_id"], "camera-01", label="Kirish", rtsp_url="rtsp://demo/1")
    main.get_snapshot_store().put("previews/p1.jpg", b"preview-bytes")
    store.set_camera_preview(site["site_id"], "camera-01", "previews/p1.jpg")
    photos = []

    async def fake_photo(chat_id, photo, caption, *, reply_markup=None):
        photos.append((chat_id, photo, caption))

    monkeypatch.setattr(main, "_send_owner_photo", fake_photo)

    _webhook(client, "/kamera")

    assert photos and photos[0][1] == b"preview-bytes"
    assert "Kirish" in photos[0][2]
    # Keyingi heartbeat'da yangi kadr kelsin.
    assert store.pending_preview_cameras(site["site_id"]) == ["camera-01"]
    assert any("Yangi rasm so'raldi" in m[1] for m in messages)


# ── Ichki narx mijozga chiqmasin ─────────────────────────────────────────
#
# `public_pricing` izohida qoida aniq yozilgan: tannarx va marja "javobga
# chiqmaydi — ular faqat admin endpointida qoladi".  Mijoz marshrutlari bu
# qoidani buzardi: `list_feature_catalog()` `p.cost_usd_cents` ni tanlaydi,
# `feature_quote()` esa `cost_usd_cents` bilan `gross_margin_percent` ni
# qaytaradi, ikkalasi ham to'g'ridan-to'g'ri mijoz brauzeriga ketardi.
#
# Bu mavhum xavf emas: do'kon egasi F12 bosib biz qancha foyda
# olayotganimizni o'qiy olardi — narx bo'yicha gaplashayotgan paytda.

#: Mijoz javobida hech qachon uchramasligi kerak bo'lgan kalitlar.
INTERNAL_MONEY_KEYS = ("cost_usd_cents", "cost_total_usd_cents", "gross_margin_percent")


def _assert_no_internal_money(payload, where: str) -> None:
    """Javobning ISTALGAN chuqurligida ichki narx bo'lmasin."""
    if isinstance(payload, dict):
        for key, value in payload.items():
            assert key not in INTERNAL_MONEY_KEYS, f"{where}: `{key}` mijozga ketyapti"
            _assert_no_internal_money(value, f"{where}.{key}")
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            _assert_no_internal_money(item, f"{where}[{index}]")


def test_owner_never_sees_our_cost_or_margin(production_client) -> None:
    client, _messages = production_client
    site, _device, _headers = _provision(client)
    owner_headers = _login_owner(client, site["site_id"])

    catalog = client.get("/api/v1/owner/features", headers=owner_headers)
    assert catalog.status_code == 200
    _assert_no_internal_money(catalog.json(), "/features")

    quote = client.post(
        "/api/v1/owner/features/quote",
        headers=owner_headers,
        json={"selections": [{"feature_code": "person_count", "camera_count": 2}]},
    )
    assert quote.status_code == 200
    _assert_no_internal_money(quote.json(), "/features/quote")

    draft = client.put(
        "/api/v1/owner/features/request",
        headers=owner_headers,
        json={"selections": [{"feature_code": "person_count", "camera_count": 2}]},
    )
    assert draft.status_code == 200
    _assert_no_internal_money(draft.json(), "/features/request")


def test_the_owner_still_gets_the_price_they_need_to_decide(production_client) -> None:
    """Tannarxni olib tashlash mijozga kerakli narxni ham o'chirmasin —
    aks holda funksiya so'rash oynasi narxsiz qoladi."""
    client, _messages = production_client
    site, _device, _headers = _provision(client)
    owner_headers = _login_owner(client, site["site_id"])

    quote = client.post(
        "/api/v1/owner/features/quote",
        headers=owner_headers,
        json={"selections": [{"feature_code": "person_count", "camera_count": 2}]},
    ).json()

    assert quote["monthly_uzs"] > 0, "mijoz so'mdagi narxni ko'rishi kerak"
    assert quote["monthly_usd_cents"] > 0
    assert quote["features"][0]["feature_code"] == "person_count"

    catalog = client.get("/api/v1/owner/features", headers=owner_headers).json()
    assert catalog["catalog"]["features"][0]["monthly_usd_cents"] > 0


def test_the_admin_still_sees_the_margin(production_client) -> None:
    """Marja bizga KERAK — u faqat admin tomonda qolishi shart."""
    client, _messages = production_client
    admin = {"X-Cloud-Admin-Key": "test-admin"}

    catalog = client.get("/api/v1/admin/features", headers=admin).json()
    assert any("cost_usd_cents" in item for item in catalog["features"])


# ── Telegramni bir bosishda ulash ────────────────────────────────────────
#
# Panelda a'zo qo'shish uchun RAQAMLI Telegram ID so'ralardi.  Do'kon
# egasi o'z ID sini ham, xodimining ID sini ham bilmaydi, panel esa uni
# topish yo'lini ko'rsatmasdi — ya'ni funksiya amalda ishlamasdi.
#
# Endi panel havola beradi, odam uni bosadi, bot uni a'zo qiladi.


#: Webhook siri — Telegram har so'rovda shu sarlavhani yuboradi.
BOT_SECRET = "webhook-secret-for-tests"


def _bot_start(client, telegram_id: str, payload: str = ""):
    text = f"/start {payload}".strip()
    return client.post(
        "/api/v1/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": BOT_SECRET},
        json={"message": {"chat": {"id": int(telegram_id), "type": "private"}, "text": text}},
    )


def test_a_customer_connects_telegram_without_typing_any_id(
    production_client, monkeypatch
) -> None:
    monkeypatch.setenv("CHAQIMCHI_TELEGRAM_BOT_USERNAME", "chaqimchi_ai_bot")
    monkeypatch.setenv("CHAQIMCHI_TELEGRAM_WEBHOOK_SECRET", BOT_SECRET)
    client, _messages = production_client
    site, _device, _headers = _provision(client)
    owner_headers = _login_owner(client, site["site_id"], telegram_id="900")

    invite = client.post(
        "/api/v1/owner/telegram-invite", headers=owner_headers, json={"role": "manager"}
    )
    assert invite.status_code == 200
    url = invite.json()["url"]
    assert url.startswith("https://t.me/chaqimchi_ai_bot?start=")
    token = url.split("start=")[1]

    # Xodim havolani bosadi — hech qanday raqam yozmaydi.
    assert _bot_start(client, "901", token).status_code == 200

    members = client.get("/api/v1/owner/members", headers=owner_headers).json()["members"]
    assert {str(m["telegram_id"]) for m in members} == {"900", "901"}
    assert next(m for m in members if str(m["telegram_id"]) == "901")["role"] == "manager"


def test_an_invite_works_only_once(production_client, monkeypatch) -> None:
    """Havola credential: uni bosgan odam panelga kiradi.  Bir marta
    ishlatilgach boshqa hech kimni ichkariga kiritmasin."""
    monkeypatch.setenv("CHAQIMCHI_TELEGRAM_BOT_USERNAME", "chaqimchi_ai_bot")
    monkeypatch.setenv("CHAQIMCHI_TELEGRAM_WEBHOOK_SECRET", BOT_SECRET)
    client, _messages = production_client
    site, _device, _headers = _provision(client)
    owner_headers = _login_owner(client, site["site_id"], telegram_id="910")

    token = client.post(
        "/api/v1/owner/telegram-invite", headers=owner_headers, json={}
    ).json()["url"].split("start=")[1]

    _bot_start(client, "911", token)
    _bot_start(client, "912", token)   # o'sha havola, boshqa odam

    members = client.get("/api/v1/owner/members", headers=owner_headers).json()["members"]
    assert "912" not in {str(m["telegram_id"]) for m in members}


def test_an_expired_invite_is_refused(production_client, monkeypatch) -> None:
    import cloud.main as main

    monkeypatch.setenv("CHAQIMCHI_TELEGRAM_BOT_USERNAME", "chaqimchi_ai_bot")
    monkeypatch.setenv("CHAQIMCHI_TELEGRAM_WEBHOOK_SECRET", BOT_SECRET)
    client, _messages = production_client
    site, _device, _headers = _provision(client)
    owner_headers = _login_owner(client, site["site_id"], telegram_id="920")

    token = client.post(
        "/api/v1/owner/telegram-invite", headers=owner_headers, json={}
    ).json()["url"].split("start=")[1]

    store = main.get_event_store()
    with store._connect() as conn:
        conn.execute(
            store._sql("UPDATE telegram_invites SET expires_at=?"),
            ("2020-01-01T00:00:00+00:00",),
        )

    _bot_start(client, "921", token)

    members = client.get("/api/v1/owner/members", headers=owner_headers).json()["members"]
    assert "921" not in {str(m["telegram_id"]) for m in members}


def test_a_random_start_payload_does_not_grant_access(
    production_client, monkeypatch
) -> None:
    """Botga tasodifiy matn bilan `/start` bosgan odam a'zo bo'lib
    qolmasin."""
    monkeypatch.setenv("CHAQIMCHI_TELEGRAM_BOT_USERNAME", "chaqimchi_ai_bot")
    monkeypatch.setenv("CHAQIMCHI_TELEGRAM_WEBHOOK_SECRET", BOT_SECRET)
    client, _messages = production_client
    site, _device, _headers = _provision(client)
    owner_headers = _login_owner(client, site["site_id"], telegram_id="930")

    _bot_start(client, "931", "oddiy-matn")

    members = client.get("/api/v1/owner/members", headers=owner_headers).json()["members"]
    assert "931" not in {str(m["telegram_id"]) for m in members}


def test_a_second_tap_does_not_say_the_link_expired(
    production_client, monkeypatch
) -> None:
    """Telegram javob kelmasa update'ni QAYTA yuboradi.  Havola esa bir
    martalik — ikkinchi urinishda "eskirgan" deb yozilardi, holbuki
    o'sha odam allaqachon ulangan edi.

    Ayni holat mijoz havolani ikki marta bosganda ham yuz beradi."""
    monkeypatch.setenv("CHAQIMCHI_TELEGRAM_BOT_USERNAME", "chaqimchi_ai_bot")
    monkeypatch.setenv("CHAQIMCHI_TELEGRAM_WEBHOOK_SECRET", BOT_SECRET)
    client, messages = production_client
    site, _device, _headers = _provision(client)
    owner_headers = _login_owner(client, site["site_id"], telegram_id="960")

    token = client.post(
        "/api/v1/owner/telegram-invite", headers=owner_headers, json={}
    ).json()["url"].split("start=")[1]

    _bot_start(client, "961", token)
    _bot_start(client, "961", token)

    assert "eskirgan" not in messages[-1][1].lower(), messages[-1][1]
    members = client.get("/api/v1/owner/members", headers=owner_headers).json()["members"]
    assert sum(1 for m in members if str(m["telegram_id"]) == "961") == 1


def test_a_failed_telegram_reply_does_not_undo_the_invite(
    production_client, monkeypatch
) -> None:
    """Tasdiq xabari ketmasa ham a'zolik saqlanib qolsin va webhook 200
    qaytarsin — aks holda Telegram cheksiz qayta urinadi."""
    import cloud.main as main

    monkeypatch.setenv("CHAQIMCHI_TELEGRAM_BOT_USERNAME", "chaqimchi_ai_bot")
    monkeypatch.setenv("CHAQIMCHI_TELEGRAM_WEBHOOK_SECRET", BOT_SECRET)
    client, _messages = production_client
    site, _device, _headers = _provision(client)
    owner_headers = _login_owner(client, site["site_id"], telegram_id="970")

    token = client.post(
        "/api/v1/owner/telegram-invite", headers=owner_headers, json={}
    ).json()["url"].split("start=")[1]

    async def broken_send(chat_id, text, *, reply_markup=None):
        raise RuntimeError("Telegram javob bermadi")

    monkeypatch.setattr(main, "_send_owner_telegram", broken_send)
    response = _bot_start(client, "971", token)

    assert response.status_code == 200
    members = client.get("/api/v1/owner/members", headers=owner_headers).json()["members"]
    assert "971" in {str(m["telegram_id"]) for m in members}


def test_the_register_button_still_works(production_client, monkeypatch) -> None:
    """Taklif tokenini o'qiyotgan kod `/start register` ni ham yutib
    yuborardi — saytdagi "Ro'yxatdan o'tish" tugmasi javob bermay qolgandi.

    Taklif tokeni har doim 32 belgi; `register` esa emas."""
    monkeypatch.setenv("CHAQIMCHI_TELEGRAM_BOT_USERNAME", "chaqimchi_ai_bot")
    monkeypatch.setenv("CHAQIMCHI_TELEGRAM_WEBHOOK_SECRET", BOT_SECRET)
    client, messages = production_client

    before = len(messages)
    response = _bot_start(client, "9501", "register")

    assert response.status_code == 200
    assert len(messages) > before, "botdan javob kelmadi"
    assert "eskirgan" not in messages[-1][1].lower()


def test_a_manager_cannot_invite_more_people(production_client, monkeypatch) -> None:
    """Xodim yangi odam taklif qila olmasin — aks holda bitta taklif
    butun do'konni ochib yuborardi."""
    monkeypatch.setenv("CHAQIMCHI_TELEGRAM_BOT_USERNAME", "chaqimchi_ai_bot")
    monkeypatch.setenv("CHAQIMCHI_TELEGRAM_WEBHOOK_SECRET", BOT_SECRET)
    client, _messages = production_client
    site, _device, _headers = _provision(client)
    owner_headers = _login_owner(client, site["site_id"], telegram_id="940")

    token = client.post(
        "/api/v1/owner/telegram-invite", headers=owner_headers, json={}
    ).json()["url"].split("start=")[1]
    _bot_start(client, "941", token)

    client.post("/api/v1/owner/auth/request", json={"telegram_id": "941"})
    manager = client.post(
        "/api/v1/owner/auth/verify",
        json={"telegram_id": "941", "site_id": site["site_id"], "code": "123456"},
    ).json()["access_token"]

    refused = client.post(
        "/api/v1/owner/telegram-invite",
        headers={"Authorization": f"Bearer {manager}"},
        json={},
    )
    assert refused.status_code == 403


# ── Uch tarif: chegara va funksiya to'plami ─────────────────────────────
#
# Uch tarif e'lon qilingach eng katta xavf — sotilgan farqning aslida
# yo'qligi.  Bungacha kamera soni qurilmada QOTIRILGAN doimiy edi va
# funksiyalar "sotiladigan har qanday tarifga hammasi" tamoyili bilan
# tarqatilardi: 149 000 to'lagan mijoz 299 000 lik mijoz bilan bir xil
# tizim olardi.  Quyidagilar shu farqni ushlab turadi.


def _site_on(client: TestClient, plan: str, name: str = "Tarif do'koni"):
    site = client.post(
        "/api/v1/admin/sites",
        headers={"X-Cloud-Admin-Key": "test-admin"},
        json={"name": name, "plan": plan},
    ).json()
    device = client.post(
        "/api/v1/devices/claim", json={"pairing_code": site["pairing_code"]}
    ).json()
    return site, {
        "X-Site-Id": device["site_id"],
        "X-Device-Id": device["device_id"],
        "X-Device-Token": device["device_token"],
    }


def test_boshlangich_device_only_gets_person_counting(production_client) -> None:
    client, _messages = production_client
    _site, headers = _site_on(client, "boshlangich")

    config = client.get("/api/v1/sotqin/config", headers=headers).json()

    codes = {item["code"] for item in config["cloud_features"]}
    assert codes == {"person_count"}
    assert all(item["camera_count"] == 2 for item in config["cloud_features"])


def test_biznes_device_gets_queue_and_security(production_client) -> None:
    client, _messages = production_client
    _site, headers = _site_on(client, "biznes")

    config = client.get("/api/v1/sotqin/config", headers=headers).json()

    codes = {item["code"] for item in config["cloud_features"]}
    assert codes == {"person_count", "queue_length", "store_security"}


def test_edge_config_camera_limit_follows_the_plan(production_client) -> None:
    """Qurilma tarifdagi kamera sonini bilishi kerak.

    Ilgari `product.max_cameras` har doim 4 edi va lokal sehrgar shu
    raqamga qarardi — ya'ni 2 kameralik tarifdagi mijoz uchinchi kamerani
    bemalol ulardi.
    """
    client, _messages = production_client
    for plan, expected in (("boshlangich", 2), ("biznes", 4), ("lite", 4)):
        _site, headers = _site_on(client, plan, name=f"Do'kon {plan}")
        config = client.get("/api/v1/sotqin/config", headers=headers).json()
        assert config["product"]["max_cameras"] == expected, plan
        assert config["product"]["guaranteed_cameras"] == expected, plan


def test_boshlangich_site_cannot_add_a_third_camera(production_client) -> None:
    """Haqiqiy nazorat cloudda: qurilmadagi fayl mijozning o'zida turadi.

    Shu sabab tekshiruv yozish yo'lining o'zida — `upsert_camera` da —
    turadi va o'rnatuvchi paneli ham, admin ham, kelajakdagi yo'llar ham
    shu bitta joydan o'tadi.
    """
    import cloud.main as main

    client, _messages = production_client
    site, _headers = _site_on(client, "boshlangich")
    store = main.get_store()

    for index in (1, 2):
        store.upsert_camera(
            site["site_id"],
            f"camera-{index:02d}",
            label=f"Kamera {index}",
            rtsp_url=f"rtsp://10.0.0.{index}/1",
        )

    with pytest.raises(ValueError, match="2 ta kamera"):
        store.upsert_camera(
            site["site_id"], "camera-03", label="Uchinchi", rtsp_url="rtsp://10.0.0.3/1"
        )

    # Mavjud kamerani TAHRIRLASH chegaraga urilmaydi — aks holda 2
    # kamerali mijoz RTSP parolini ham yangilay olmasdi.
    store.upsert_camera(
        site["site_id"], "camera-01", label="Kirish", rtsp_url="rtsp://10.0.0.9/1"
    )

    # Tarif ko'tarilsa uchinchisi ochiladi.
    store.set_plan(site["site_id"], "biznes")
    store.upsert_camera(
        site["site_id"], "camera-03", label="Uchinchi", rtsp_url="rtsp://10.0.0.3/1"
    )
    assert len(store.list_cameras(site["site_id"])) == 3


def test_changing_the_plan_reaches_the_device(production_client) -> None:
    """Mijoz pul to'lagach funksiya keyingi pollda kelsin.

    Tarif qurilmadagi funksiya to'plamini belgilaydi, qurilma esa
    o'zgarishni faqat config revizyasi bo'yicha sezadi.  Revizya
    surilmasa mijoz qayta ishga tushirishgacha kutib qolardi.
    """
    client, _messages = production_client
    site, headers = _site_on(client, "boshlangich")
    admin = {"X-Cloud-Admin-Key": "test-admin"}

    before = client.get("/api/v1/sotqin/config", headers=headers).json()

    upgraded = client.post(
        f"/api/v1/admin/sites/{site['site_id']}/plan", headers=admin, json={"plan": "biznes"}
    )
    assert upgraded.status_code == 200
    assert upgraded.json()["plan"] == "biznes"

    after = client.get("/api/v1/sotqin/config", headers=headers).json()
    assert after["revision"] > before["revision"]
    assert {item["code"] for item in after["cloud_features"]} == {
        "person_count",
        "queue_length",
        "store_security",
    }
    assert after["product"]["max_cameras"] == 4


def test_an_unknown_plan_is_refused(production_client) -> None:
    client, _messages = production_client
    site, _headers = _site_on(client, "biznes")

    response = client.post(
        f"/api/v1/admin/sites/{site['site_id']}/plan",
        headers={"X-Cloud-Admin-Key": "test-admin"},
        json={"plan": "oltin"},
    )
    assert response.status_code == 422


def test_heatmap_and_demography_follow_the_plan(production_client) -> None:
    """Sotilgan farq haqiqatan ham bo'lsin.

    Ikkalasi ham kodda allaqachon ishlardi va hech qaysi tarifga
    bog'lanmagan edi — ya'ni 149 000 to'lagan mijoz 299 000 lik bilan bir
    xil tahlil olardi.
    """
    client, _messages = production_client
    site, headers = _site_on(client, "boshlangich")
    admin = {"X-Cloud-Admin-Key": "test-admin"}

    client.post(
        f"/api/v1/admin/sites/{site['site_id']}/members",
        headers=admin,
        json={"telegram_id": "707", "role": "owner"},
    )
    client.post("/api/v1/owner/auth/request", json={"telegram_id": "707"})
    token = client.post(
        "/api/v1/owner/auth/verify",
        json={"telegram_id": "707", "site_id": site["site_id"], "code": "123456"},
    ).json()["access_token"]
    owner = {"Authorization": f"Bearer {token}"}

    health = client.get("/api/v1/owner/health", headers=owner).json()
    assert health["plan"]["code"] == "boshlangich"
    assert "xarita" not in health["plan"]["panel_features"]

    blocked = client.get("/api/v1/owner/heatmap?camera_id=camera-01", headers=owner)
    assert blocked.status_code == 403
    assert "Biznes" in blocked.json()["detail"]

    assert "demografiya" not in client.get("/api/v1/owner/report", headers=owner).json()

    # Qurilma to'rni yuborishda XATO olmaydi — aks holda outbox uni
    # "keyin qayta yuboraman" deb saqlab, do'kon kompyuterining diskini
    # to'ldirardi.
    upload = client.post(
        "/api/v1/edge/heatmap",
        headers=headers,
        json={
            "items": [
                {
                    "camera_id": "camera-01",
                    "hour": "2026-08-21T10",
                    "grid": [[0] * 48 for _ in range(27)],
                    "frames": 10,
                }
            ]
        },
    )
    assert upload.status_code == 200
    assert upload.json()["accepted"] == 0

    # Tarif ko'tarilsa ikkalasi ham ochiladi.
    client.post(f"/api/v1/admin/sites/{site['site_id']}/plan", headers=admin, json={"plan": "biznes"})
    assert client.get("/api/v1/owner/heatmap?camera_id=camera-01", headers=owner).status_code == 200
    assert "demografiya" in client.get("/api/v1/owner/report", headers=owner).json()


def test_an_expired_subscription_stops_the_features_but_not_the_camera_alarm(
    production_client,
) -> None:
    """To'lamagan mijozning qurilmasi ishlab turaverishi kerak emas.

    Bungacha obuna muddati qurilmada UMUMAN majburlanmasdi:
    `require_device` faqat tokenni tekshirardi, `/edge/heartbeat` esa
    litsenziya maydonlarini tashlab yuborardi.  Bitta tarif va tekin
    sinov paytida bu yumshoq oqim edi; uch xil narx e'lon qilingach —
    to'lashni to'xtatishning eng oson yo'li.

    Lekin kamera sog'ligi hodisalari qurilmada filtrdan o'tmaydi
    (`HEALTH_EVENTS`), ya'ni "kamerangiz o'chdi" xabari baribir keladi.
    """
    import cloud.main as main

    client, _messages = production_client
    site, headers = _site_on(client, "biznes")
    store = main.get_store()

    assert client.get("/api/v1/sotqin/config", headers=headers).json()["cloud_features"]

    # Obunani orqaga suramiz: grace (14 kun) ham o'tib ketsin.
    with store._connect() as conn:
        conn.execute(
            "UPDATE sites SET subscription_until = ? WHERE id = ?",
            ("2020-01-01 00:00:00", site["site_id"]),
        )
        conn.commit()

    config = client.get("/api/v1/sotqin/config", headers=headers).json()
    assert config["subscription"]["status"] == "expired"
    assert config["cloud_features"] == []
    assert config["attendance"]["enabled"] is False
    # Javob YARIM emas: qurilma kutadigan maydonlar joyida qoladi.
    assert "product" in config and "cameras" in config


def test_the_grace_period_promised_on_the_site_is_honoured(production_client) -> None:
    """Sayt FAQ'i: "obuna tugagach tizim yana 14 kun ishlaydi"."""
    import cloud.main as main

    client, _messages = production_client
    site, headers = _site_on(client, "biznes")
    store = main.get_store()

    with store._connect() as conn:
        conn.execute(
            "UPDATE sites SET subscription_until = datetime('now', '-3 days') WHERE id = ?",
            (site["site_id"],),
        )
        conn.commit()

    config = client.get("/api/v1/sotqin/config", headers=headers).json()
    assert config["subscription"]["status"] == "grace"
    assert config["cloud_features"], "grace davrida tizim ishlashda davom etadi"


def test_owner_sees_the_annual_offer_with_real_amounts(production_client) -> None:
    """Yillik taklif summasi hisob-fakturadagi bilan bir xil chiqsin.

    Panelga qo'lda yozilgan raqam eng xavflisi: mijoz bir summani ko'rib,
    to'lovda boshqasini olardi.  Shu sabab bu yerda ikkalasi solishtiriladi.
    """
    client, _messages = production_client
    site, _device, _headers = _provision(client)
    owner_headers = _login_owner(client, site["site_id"])

    body = client.get("/api/v1/owner/subscription", headers=owner_headers)
    assert body.status_code == 200
    data = body.json()

    # 2 oy bepul — bu saytdagi va'da.
    assert data["free_months"] == 2
    assert data["annual_uzs"] == data["monthly_uzs"] * 10
    assert data["annual_saving_uzs"] == data["monthly_uzs"] * 2
    assert data["status"] in {"active", "grace", "expired", "suspended"}
    assert data["subscription_until"]
    assert data["grace_days"] == 14

    # Va endi eng muhimi: haqiqiy hisob-faktura ham xuddi shu summani bersin.
    invoice = client.post(
        "/api/v1/owner/invoices", headers=owner_headers, json={"months": 12}
    )
    assert invoice.status_code == 200
    assert invoice.json()["amount_uzs"] == data["annual_uzs"]


# ── Kamera inventari: qurilma o'zi bildiradi ───────────────────────────


def test_device_registers_its_own_cameras(production_client) -> None:
    """Sehrgarda qo'shilgan kamera mijoz panelida ko'rinsin.

    Haqiqiy do'konda `site_cameras` BO'M-BO'SH edi: mijoz kameralarni o'z
    kompyuteridagi sehrgarda qo'shgan, cloudga esa kamera yozadigan yo'l
    faqat admin va o'rnatuvchi portalida bor edi.  Natijada panelda
    `cameraList` bo'sh qolib, jonli ko'rish, do'kon xaritasi, davomat
    kamerasi va kamera rollari — to'rttasi ham jimgina ishlamasdi.
    """
    client, _messages = production_client
    site, _device, headers = _provision(client)
    owner_headers = _login_owner(client, site["site_id"], telegram_id="7001")

    assert client.get("/api/v1/owner/cameras", headers=owner_headers).json()["cameras"] == []

    answer = client.post(
        "/api/v1/edge/cameras",
        headers=headers,
        json={
            "cameras": [
                {"camera_id": "camera-01", "label": "Kirish"},
                {"camera_id": "camera-02", "label": "Kassa"},
            ]
        },
    )
    assert answer.status_code == 200

    cameras = client.get("/api/v1/owner/cameras", headers=owner_headers).json()["cameras"]
    assert [item["camera_id"] for item in cameras] == ["camera-01", "camera-02"]
    assert cameras[0]["label"] == "Kirish"
    assert cameras[0]["origin"] == "device"

    # Manzilsiz kamera qurilmaga QAYTARILMAYDI: `cloud_config.apply()`
    # aynan `source` bo'yicha ishlaydi va bo'sh manzil do'kondagi ishlab
    # turgan ro'yxatni o'chirib yuborardi.
    config = client.get("/api/v1/edge/config", headers=headers).json()
    assert all(not item.get("source") for item in config["cameras"])

    # Sehrgardan kamera olib tashlansa panelda ham qolib ketmasin.
    client.post(
        "/api/v1/edge/cameras",
        headers=headers,
        json={"cameras": [{"camera_id": "camera-01", "label": "Kirish"}]},
    )
    cameras = client.get("/api/v1/owner/cameras", headers=owner_headers).json()["cameras"]
    assert [item["camera_id"] for item in cameras] == ["camera-01"]


def test_device_does_not_overwrite_cameras_entered_in_the_panel(production_client) -> None:
    """Admin kiritgan manzil qurilma xabaridan keyin ham qolishi shart.

    Aks holda o'rnatuvchi kiritgan RTSP manzili (parol bilan) yo'qolib,
    qurilma qayta ulanganda kamera manzilsiz qolardi.
    """
    client, _messages = production_client
    site, _device, headers = _provision(client)
    saved = client.put(
        f"/api/v1/admin/sites/{site['site_id']}/camera-inventory/camera-01",
        headers={"X-Cloud-Admin-Key": "test-admin"},
        json={
            "label": "O'rnatuvchi qo'ygan",
            "rtsp_url": "rtsp://admin:parol@10.0.0.9:554/Streaming/Channels/102",
        },
    )
    assert saved.status_code == 200

    client.post(
        "/api/v1/edge/cameras",
        headers=headers,
        json={"cameras": [{"camera_id": "camera-01", "label": "Sehrgar nomi"}]},
    )

    config = client.get("/api/v1/edge/config", headers=headers).json()
    camera = next(item for item in config["cameras"] if item["camera_id"] == "camera-01")
    assert camera["source"].startswith("rtsp://")
    assert camera["label"] == "O'rnatuvchi qo'ygan"


def test_camera_count_falls_back_to_the_registered_list(production_client) -> None:
    """Panel "4 dan 2 tasi" deyishi uchun maxraj kerak.

    `cameras_expected` obyekt yaratilganda QO'LDA kiritiladi va o'zi
    ro'yxatdan o'tgan do'konda bo'sh qoladi — panel esa quruq "Qurilma
    ulangan" deb turardi.
    """
    client, _messages = production_client
    site, _device, headers = _provision(client)
    owner_headers = _login_owner(client, site["site_id"], telegram_id="7002")

    client.post(
        "/api/v1/edge/cameras",
        headers=headers,
        json={
            "cameras": [
                {"camera_id": "camera-01", "label": "Kirish"},
                {"camera_id": "camera-02", "label": "Kassa"},
            ]
        },
    )
    health = client.get("/api/v1/owner/health", headers=owner_headers).json()
    assert health["cameras_expected"] == 2


def test_camera_health_is_stored_per_camera(production_client) -> None:
    """Panelda yashil chiroq preview RASMIDAN emas, qurilmadan kelsin."""
    client, _messages = production_client
    site, _device, headers = _provision(client)
    owner_headers = _login_owner(client, site["site_id"], telegram_id="7003")

    client.post(
        "/api/v1/edge/heartbeat",
        headers=headers,
        json={
            "cameras_active": 1,
            "cameras": [
                {"camera_id": "camera-01", "connected": True, "offline": False, "codec": "H265"},
                {"camera_id": "camera-02", "connected": False, "offline": True, "reconnects": 12},
            ],
        },
    )

    health = client.get("/api/v1/owner/health", headers=owner_headers).json()
    reported = health["devices"][0]["health"]["cameras"]
    by_id = {item["camera_id"]: item for item in reported}
    assert by_id["camera-01"]["codec"] == "H265"
    assert by_id["camera-02"]["offline"] is True


def test_heatmap_can_be_asked_for_a_range_of_days(production_client) -> None:
    """Xaritada vaqt oralig'i: bitta kun ko'pincha juda kam ma'lumot.

    Server `days` ni allaqachon qabul qilardi, panel esa uni HECH QACHON
    yubormasdi — mijoz uchun bu "xarita bo'sh" degani edi.
    """
    client, _messages = production_client
    site, _device, headers = _provision(client)
    owner = _login_owner(client, site["site_id"], telegram_id="7004")

    grid = [[0] * 48 for _ in range(27)]
    grid[3][4] = 5
    for hour in ("2026-08-20T10", "2026-08-21T10"):
        client.post(
            "/api/v1/edge/heatmap",
            headers=headers,
            json={"items": [{"camera_id": "camera-01", "hour": hour, "grid": grid, "frames": 10}]},
        )

    one_day = client.get(
        "/api/v1/owner/heatmap?camera_id=camera-01&date=2026-08-21", headers=owner
    ).json()
    week = client.get(
        "/api/v1/owner/heatmap?camera_id=camera-01&date=2026-08-21&days=7", headers=owner
    ).json()

    assert one_day["points"] == 5
    assert week["points"] == 10, "oraliq so'ralganda oldingi kunlar ham qo'shilsin"


def test_device_cannot_exceed_the_plan_camera_limit(production_client) -> None:
    """Kamera chegarasi qurilma tomonidan aylanib o'tilmasin.

    Qurilmadagi tekshiruv mijozning O'Z kompyuterida turadi va uni
    tahrirlash mumkin — haqiqiy nazorat shu yerda.
    """
    client, _messages = production_client
    site = client.post(
        "/api/v1/admin/sites",
        headers={"X-Cloud-Admin-Key": "test-admin"},
        json={"name": "Ikki kamera", "plan": "boshlangich"},
    ).json()
    device = client.post(
        "/api/v1/devices/claim", json={"pairing_code": site["pairing_code"]}
    ).json()
    headers = {
        "X-Site-Id": device["site_id"],
        "X-Device-Id": device["device_id"],
        "X-Device-Token": device["device_token"],
    }

    answer = client.post(
        "/api/v1/edge/cameras",
        headers=headers,
        json={
            "cameras": [
                {"camera_id": f"camera-0{index}", "label": f"K{index}"} for index in range(1, 4)
            ]
        },
    )

    assert answer.status_code == 422
    assert "2 ta kamera" in answer.json()["detail"]


def test_loitering_snapshot_is_accepted_but_not_stored(production_client) -> None:
    """Uzoq turish rasmi saqlanmaydi — lekin qurilmaga XATO ham qaytmaydi.

    4xx qaytarilsa `cloud_sync.py` yuklash xatosini butun hodisaga yozadi
    (`outbox.fail`), hodisa 20 marta qayta yuboriladi va oxirida
    `dead_letter` ga tushib YO'QOLADI.  Ya'ni rad javob bizga kerakli
    ma'lumotni ham o'ldirardi.  Shu sabab `edge/heatmap` dagi kabi:
    qabul qilamiz, yozmaymiz.
    """
    client, _messages = production_client
    site, _device, headers = _provision(client)
    event = {
        "event_id": "loi-1",
        "event_type": "loitering",
        "severity": "warning",
        "camera_id": "cam-1",
        "has_snapshot": True,
    }
    assert (
        client.post("/api/v1/edge/events/batch", headers=headers, json={"events": [event]})
    ).status_code == 200

    upload = client.put(
        "/api/v1/edge/events/loi-1/snapshot",
        headers={**headers, "Content-Type": "image/jpeg"},
        content=b"jpeg-data",
    )
    assert upload.status_code == 200
    assert upload.json()["stored"] is False

    # Hodisaning O'ZI saqlanadi — xarita va hisobot unga tayanadi.
    owner_headers = _login_owner(client, site["site_id"], telegram_id="103")
    events = client.get("/api/v1/owner/events", headers=owner_headers)
    assert events.status_code == 200
    row = next(item for item in events.json()["events"] if item["event_id"] == "loi-1")

    # "Rasm bor" bayrog'i O'CHIRILGAN bo'lishi shart.  U qurilmaning
    # da'vosi bilan keladi va eski qurilmalarda `true` bo'lib turaveradi;
    # tozalanmasa panel rasm tugmasini ko'rsatib, mijoz bosganda 404
    # olardi.  Jonli serverda aynan shu holat kuzatildi (2026-08-21):
    # `snapshot_key` bo'sh, `snapshot_bytes` nol, lekin bayroq 1 edi.
    assert row["has_snapshot"] is False

    # Lekin rasm yo'q.
    assert client.get(
        "/api/v1/owner/events/loi-1/snapshot", headers=owner_headers
    ).status_code == 404


def test_loitering_does_not_consume_the_daily_snapshot_budget(production_client) -> None:
    """Tashlab yuboriladigan rasm kunlik 500 talik byudjetni YEMASLIGI shart.

    Muammoning o'zi aynan shu edi: jonli do'kon 7.4 soatda 302 ta rasmni
    loitering'ga sarflagan va kechqurun haqiqiy o'g'rilik hodisasiga rasm
    ilinmay qolardi.  Shu sabab chegara tekshiruvi hodisa turini
    aniqlagandan KEYIN turadi.
    """
    from cloud import ratelimit

    client, _messages = production_client
    _site, _device, headers = _provision(client)

    events = [
        {
            "event_id": f"loi-{index}",
            "event_type": "loitering",
            "severity": "warning",
            "camera_id": "cam-1",
            "has_snapshot": True,
        }
        for index in range(5)
    ] + [
        {
            "event_id": "tamper-1",
            "event_type": "camera_tampered",
            "severity": "critical",
            "camera_id": "cam-1",
            "has_snapshot": True,
        }
    ]
    client.post("/api/v1/edge/events/batch", headers=headers, json={"events": events})

    # Hodisa qabuli o'z chegarasini ishlatadi — uni hisobdan chiqaramiz,
    # shunda keyingi o'lchov FAQAT snapshot byudjetini ko'rsatadi.
    ratelimit.limiter().reset()

    for index in range(5):
        assert (
            client.put(
                f"/api/v1/edge/events/loi-{index}/snapshot",
                headers={**headers, "Content-Type": "image/jpeg"},
                content=b"jpeg-data",
            )
        ).status_code == 200

    # Beshta loitering rasmi kelgan bo'lsa ham byudjetga umuman
    # tegilmagan: hisoblagichda birorta ham yozuv yo'q.
    assert ratelimit.limiter().size() == 0

    # Haqiqiy xavfsizlik hodisasi esa byudjetni ishlatadi va rasm saqlanadi.
    tamper = client.put(
        "/api/v1/edge/events/tamper-1/snapshot",
        headers={**headers, "Content-Type": "image/jpeg"},
        content=b"jpeg-data",
    )
    assert tamper.status_code == 200
    assert tamper.json().get("stored") is not False
    assert ratelimit.limiter().size() == 1


# ── Ishonch balli ────────────────────────────────────────────────────────


def test_trust_score_refuses_to_grade_a_silent_shop(production_client) -> None:
    """Kompyuter o'chiq bo'lsa ball KO'RSATILMAYDI.

    Aks holda o'chib qolgan do'kon har kuni "94" ko'rsatib turardi va
    mijoz mahsulot ishlayapti deb o'ylab yurardi — bu mumkin bo'lgan
    eng yomon nosozlik.  Aynan shunday holat 2026-08-22 da bo'lgan:
    qurilma 19 soat jim turgan.
    """
    client, _messages = production_client
    site, device, _headers = _provision(client)
    owner_headers = _login_owner(client, site["site_id"], telegram_id="900")

    # Qurilmani ataylab jim qilamiz — oxirgi aloqa 20 soat oldin.
    store = main.get_store()
    conn = store._connect()
    stale = (datetime.now(timezone.utc) - timedelta(hours=20)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("UPDATE devices SET last_seen=? WHERE id=?", (stale, device["device_id"]))
    conn.commit()
    conn.close()

    body = client.get("/api/v1/owner/trust-score", headers=owner_headers).json()
    assert body["available"] is False
    assert body["total"] is None
    assert "jim" in body["reason"]
    assert body["label"] == "Ma'lumot yo'q"


def test_trust_score_needs_a_login(production_client) -> None:
    client, _messages = production_client
    assert client.get("/api/v1/owner/trust-score").status_code == 401


def test_trust_score_reports_real_events(production_client) -> None:
    """Ball haqiqiy hodisalardan hisoblanadi va qismlarini tushuntiradi."""
    client, _messages = production_client
    site, _device, headers = _provision(client)
    owner_headers = _login_owner(client, site["site_id"], telegram_id="901")

    # Heartbeat qurilmani "online" qiladi.
    client.post("/api/v1/edge/heartbeat", headers=headers, json={"cameras": []})
    # Buzilgan kamera — jiddiy hodisa, ball buni ko'rsatishi kerak.
    occurred = datetime.now(timezone.utc).isoformat()
    client.post(
        "/api/v1/edge/events/batch",
        headers=headers,
        json={
            "events": [
                {
                    "event_id": "trust-1",
                    "event_type": "camera_tampered",
                    "severity": "critical",
                    "camera_id": "camera-01",
                    "occurred_at": occurred,
                    "edge_version": "0.6.12",
                }
            ]
        },
    )

    body = client.get("/api/v1/owner/trust-score", headers=owner_headers).json()
    assert body["available"] is True
    assert 0 <= body["total"] <= 100
    codes = {part["code"] for part in body["parts"]}
    assert codes == {"traffic", "queue", "staff", "security", "cameras"}

    security = next(part for part in body["parts"] if part["code"] == "security")
    assert security["points"] == 4, "buzilgan kamera ballni tushirishi kerak"
    # Navbat zonasi chizilmagan — bu qism o'lchanmaydi, "mukammal" emas.
    queue = next(part for part in body["parts"] if part["code"] == "queue")
    assert queue["measured"] is False


# ── Pulga tarjima ────────────────────────────────────────────────────────


def test_money_is_silent_until_the_owner_tells_us_their_revenue(production_client) -> None:
    """Standart qiymat bilan to'ldirish — o'ylab topilgan raqamni haqiqat qilib ko'rsatish."""
    client, _messages = production_client
    site, _device, _headers = _provision(client)
    owner_headers = _login_owner(client, site["site_id"], telegram_id="910")

    body = client.get("/api/v1/owner/revenue", headers=owner_headers).json()
    assert body["amount_uzs"] == 0


def test_owner_can_set_and_read_back_their_revenue(production_client) -> None:
    client, _messages = production_client
    site, _device, _headers = _provision(client)
    owner_headers = _login_owner(client, site["site_id"], telegram_id="911")

    saved = client.put(
        "/api/v1/owner/revenue", headers=owner_headers, json={"amount_uzs": 4_500_000}
    )
    assert saved.status_code == 200
    assert client.get("/api/v1/owner/revenue", headers=owner_headers).json() == {
        "amount_uzs": 4_500_000
    }


def test_an_absurd_revenue_is_refused(production_client) -> None:
    """Bir nolni ortiqcha yozib yuborish oson — «42 mlrd yo'qotdingiz» ishonchni o'ldiradi."""
    client, _messages = production_client
    site, _device, _headers = _provision(client)
    owner_headers = _login_owner(client, site["site_id"], telegram_id="912")

    response = client.put(
        "/api/v1/owner/revenue", headers=owner_headers, json={"amount_uzs": 99_000_000_000}
    )
    assert response.status_code == 422


def test_revenue_needs_a_login(production_client) -> None:
    client, _messages = production_client
    assert client.get("/api/v1/owner/revenue").status_code == 401
    assert client.put("/api/v1/owner/revenue", json={"amount_uzs": 1}).status_code == 401


# ── Do'kon gapiradi ──────────────────────────────────────────────────────


def test_speak_reaches_the_device_exactly_once(production_client) -> None:
    """Ikkita heartbeat ketma-ket kelsa ibora ikki marta yangramasin."""
    client, _messages = production_client
    site, _device, headers = _provision(client)
    owner_headers = _login_owner(client, site["site_id"], telegram_id="920")

    assert client.post(
        "/api/v1/owner/speak", headers=owner_headers, json={"phrase": "deter"}
    ).status_code == 200

    first = client.post("/api/v1/edge/heartbeat", headers=headers, json={"cameras": []}).json()
    assert first["speak_requested"] == ["deter"]
    second = client.post("/api/v1/edge/heartbeat", headers=headers, json={"cameras": []}).json()
    assert second["speak_requested"] == [], "ibora ikkinchi marta berilmasligi kerak"


def test_only_catalog_phrases_are_accepted(production_client) -> None:
    """Erkin matn karnaydan aytilsa — bu xodimni haqoratlash vositasi."""
    client, _messages = production_client
    site, _device, _headers = _provision(client)
    owner_headers = _login_owner(client, site["site_id"], telegram_id="921")

    bad = client.post(
        "/api/v1/owner/speak", headers=owner_headers, json={"phrase": "Sen yomon ishlaysan"}
    )
    assert bad.status_code == 422


def test_speak_needs_owner_login(production_client) -> None:
    client, _messages = production_client
    assert client.post("/api/v1/owner/speak", json={"phrase": "deter"}).status_code == 401


def test_a_stale_request_is_never_played(production_client, monkeypatch) -> None:
    """Qurilma o'chiq bo'lsa navbat to'planmasin.

    Muddatsiz kompyuter ertalab yonganda kechagi «Diqqat! Do'kon
    kuzatuv ostida» bo'sh do'konda yangrardi.
    """
    client, _messages = production_client
    site, _device, headers = _provision(client)
    owner_headers = _login_owner(client, site["site_id"], telegram_id="922")
    client.post("/api/v1/owner/speak", headers=owner_headers, json={"phrase": "deter"})

    # So'rovni sun'iy ravishda eskirtiramiz.
    #
    # Vaqt `cloud.store._iso` formatida yozilishi SHART: baza satrlarni
    # matn sifatida solishtiradi va "2026-08-23T08:00:00" (T bilan)
    # "2026-08-23 11:00:00" (probel bilan) dan KATTA chiqadi — ya'ni
    # noto'g'ri formatda yozilgan "eski" yozuv yangi bo'lib ko'rinadi.
    from cloud.store import _iso

    store = main.get_store()
    conn = store._connect()
    past = _iso(datetime.now(timezone.utc) - timedelta(hours=3))
    conn.execute("UPDATE speak_requests SET expires_at=?", (past,))
    conn.commit()
    conn.close()

    answer = client.post("/api/v1/edge/heartbeat", headers=headers, json={"cameras": []}).json()
    assert answer["speak_requested"] == []


def test_announcement_catalog_is_offered_to_the_panel(production_client) -> None:
    client, _messages = production_client
    site, _device, _headers = _provision(client)
    owner_headers = _login_owner(client, site["site_id"], telegram_id="923")

    body = client.get("/api/v1/owner/announcements", headers=owner_headers).json()
    codes = {item["code"] for item in body["announcements"]}
    assert codes == {"deter", "till", "closing"}
    assert all(item["text"] and item["button"] for item in body["announcements"])


# ── Telegram tugmasi ─────────────────────────────────────────────────────


def _capture_answers(sink: list):
    """`_answer_callback` ASINXRON — o'rnini bosuvchi ham shunday bo'lishi kerak."""

    async def _fake(callback_id: str, text: str, *, alert: bool = False) -> None:
        sink.append(text)

    return _fake


def _callback(client, telegram_id: str, data: str):
    return client.post(
        "/api/v1/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": BOT_SECRET},
        json={
            "callback_query": {
                "id": "cb-1",
                "from": {"id": int(telegram_id)},
                "data": data,
                "message": {"chat": {"id": int(telegram_id), "type": "private"}},
            }
        },
    )


def test_pressing_the_button_makes_the_shop_speak(production_client, monkeypatch) -> None:
    """Bungacha `callback_query` UMUMAN ushlanmasdi — tugma bosish hech narsa qilmasdi."""
    monkeypatch.setenv("CHAQIMCHI_TELEGRAM_WEBHOOK_SECRET", BOT_SECRET)
    client, _messages = production_client
    site, _device, headers = _provision(client)
    _login_owner(client, site["site_id"], telegram_id="931")

    answered: list = []
    monkeypatch.setattr(main, "_answer_callback", _capture_answers(answered))

    assert _callback(client, "931", "speak:deter").status_code == 200
    assert "Diqqat" in answered[0]

    answer = client.post("/api/v1/edge/heartbeat", headers=headers, json={"cameras": []}).json()
    assert answer["speak_requested"] == ["deter"]


def test_a_stranger_cannot_make_someone_elses_shop_speak(production_client, monkeypatch) -> None:
    """`callback_data` ISHONILMAYDI — sayt bosgan odamning a'zoligidan topiladi.

    Aks holda istalgan odam o'z botiga tugma yasab, begona do'kon
    karnayini yangratardi.
    """
    monkeypatch.setenv("CHAQIMCHI_TELEGRAM_WEBHOOK_SECRET", BOT_SECRET)
    client, _messages = production_client
    site, _device, headers = _provision(client)

    answered: list = []
    monkeypatch.setattr(main, "_answer_callback", _capture_answers(answered))

    # 999 hech qaysi do'konga a'zo emas.
    assert _callback(client, "999", "speak:deter").status_code == 200
    assert "biriktirilmagan" in answered[0]

    answer = client.post("/api/v1/edge/heartbeat", headers=headers, json={"cameras": []}).json()
    assert answer["speak_requested"] == [], "begona odam do'konni gapirtira olmasligi kerak"


def test_an_unknown_button_does_not_crash_the_bot(production_client, monkeypatch) -> None:
    monkeypatch.setenv("CHAQIMCHI_TELEGRAM_WEBHOOK_SECRET", BOT_SECRET)
    client, _messages = production_client
    site, _device, _headers = _provision(client)
    _login_owner(client, site["site_id"], telegram_id="932")

    answered: list = []
    monkeypatch.setattr(main, "_answer_callback", _capture_answers(answered))
    assert _callback(client, "932", "eskirgan-tugma").status_code == 200
    assert answered
