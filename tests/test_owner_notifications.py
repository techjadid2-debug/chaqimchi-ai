"""Panel qo'ng'irog'i — o'qilmagan bildirishnomalar.

Ilgari qo'ng'iroqdagi son `data.events.length` edi, ya'ni panel olgan
oxirgi 12 ta hodisa soni.  U hech qachon kamaymasdi va gavjum do'konda
abadiy "9+" bo'lib turardi: do'kon egasi uchun ma'nosiz raqam.

Bu testlar uchta narsani qulflaydi: son ROSTDAN kamayadi, `info`
darajasidagi shovqin qo'ng'iroqqa tushmaydi, va har a'zoning o'z
belgisi bor.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import cloud.main as main
from cloud.snapshots import LocalSnapshotStore

ADMIN = {"X-Cloud-Admin-Key": "test-admin"}


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
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

    async def _quiet(chat_id: str, text: str, *, reply_markup=None) -> None:
        return None

    monkeypatch.setattr(main, "_send_owner_telegram", _quiet)
    with TestClient(main.app) as test_client:
        yield test_client


def _site(client: TestClient):
    site = client.post(
        "/api/v1/admin/sites", headers=ADMIN, json={"name": "Bildirishnoma", "plan": "biznes"}
    ).json()
    device = client.post(
        "/api/v1/devices/claim", json={"pairing_code": site["pairing_code"]}
    ).json()
    return site, {
        "X-Site-Id": device["site_id"],
        "X-Device-Id": device["device_id"],
        "X-Device-Token": device["device_token"],
    }


def _member(client: TestClient, site_id: str, telegram_id: str, role: str = "owner") -> dict:
    client.post(
        f"/api/v1/admin/sites/{site_id}/members",
        headers=ADMIN,
        json={"telegram_id": telegram_id, "role": role},
    )
    client.post("/api/v1/owner/auth/request", json={"telegram_id": telegram_id})
    token = client.post(
        "/api/v1/owner/auth/verify",
        json={"telegram_id": telegram_id, "site_id": site_id, "code": "123456"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _send(client: TestClient, headers: dict, event_id: str, severity: str, when: str) -> None:
    response = client.post(
        "/api/v1/edge/events/batch",
        headers=headers,
        json={
            "events": [
                {
                    "event_id": event_id,
                    "event_type": "zone_entered" if severity != "info" else "person_detected",
                    "camera_id": "camera-01",
                    "severity": severity,
                    "occurred_at": when,
                    "metadata": {},
                }
            ]
        },
    )
    assert response.status_code in (200, 202), response.text


def test_unread_count_drops_to_zero_after_reading(client) -> None:
    """Eng muhimi: son ROSTDAN kamayadi."""
    site, device = _site(client)
    owner = _member(client, site["site_id"], "601")

    _send(client, device, "n-1", "critical", "2026-08-26T10:00:00+00:00")
    _send(client, device, "n-2", "warning", "2026-08-26T10:05:00+00:00")

    first = client.get("/api/v1/owner/notifications", headers=owner).json()
    assert first["unread"] == 2
    assert len(first["events"]) == 2
    assert all(item["unread"] for item in first["events"])
    # Mijoz `zone_entered` degan so'zni tushunmaydi — sarlavha tarjima
    # qilinishi kerak (Telegram bilan bitta manbadan).
    assert first["events"][0]["label"]

    read = client.post("/api/v1/owner/notifications/read", headers=owner).json()
    assert read["unread"] == 0

    after = client.get("/api/v1/owner/notifications", headers=owner).json()
    assert after["unread"] == 0
    # Hodisalar YO'QOLMAYDI — faqat "yangi" belgisi olinadi.
    assert len(after["events"]) == 2
    assert not any(item["unread"] for item in after["events"])


def test_a_new_event_after_reading_is_unread_again(client) -> None:
    site, device = _site(client)
    owner = _member(client, site["site_id"], "602")

    _send(client, device, "n-old", "critical", "2026-08-26T10:00:00+00:00")
    client.post("/api/v1/owner/notifications/read", headers=owner)
    _send(client, device, "n-new", "critical", "2026-08-26T11:00:00+00:00")

    result = client.get("/api/v1/owner/notifications", headers=owner).json()
    assert result["unread"] == 1
    assert result["events"][0]["event_id"] == "n-new"
    assert result["events"][0]["unread"] is True


def test_routine_counting_never_reaches_the_bell(client) -> None:
    """`info` qo'ng'iroqqa tushmaydi.

    Aks holda `person_detected` va `line_crossed` kuniga minglab kelib,
    son abadiy "9+" bo'lardi — ya'ni tuzatilayotgan muammoning aynan
    o'zi qaytardi.
    """
    site, device = _site(client)
    owner = _member(client, site["site_id"], "603")

    for index in range(25):
        _send(client, device, f"info-{index}", "info", f"2026-08-26T10:{index:02d}:00+00:00")

    result = client.get("/api/v1/owner/notifications", headers=owner).json()
    assert result["unread"] == 0
    assert result["events"] == []


def test_each_member_has_their_own_read_marker(client) -> None:
    """Egasi o'qigani menejerning qo'ng'irog'ini tozalab yubormasin."""
    site, device = _site(client)
    owner = _member(client, site["site_id"], "604", "owner")
    manager = _member(client, site["site_id"], "605", "manager")

    _send(client, device, "n-shared", "critical", "2026-08-26T10:00:00+00:00")
    assert client.get("/api/v1/owner/notifications", headers=owner).json()["unread"] == 1
    assert client.get("/api/v1/owner/notifications", headers=manager).json()["unread"] == 1

    client.post("/api/v1/owner/notifications/read", headers=owner)

    assert client.get("/api/v1/owner/notifications", headers=owner).json()["unread"] == 0
    assert client.get("/api/v1/owner/notifications", headers=manager).json()["unread"] == 1


def test_unread_count_is_independent_of_the_listed_page(client) -> None:
    """20 ta ko'rsatib, 25 ta o'qilmagan bo'lsa son 25 ni aytsin."""
    site, device = _site(client)
    owner = _member(client, site["site_id"], "606")

    for index in range(25):
        _send(client, device, f"c-{index}", "critical", f"2026-08-26T10:{index:02d}:00+00:00")

    result = client.get("/api/v1/owner/notifications?limit=20", headers=owner).json()
    assert result["unread"] == 25
    assert len(result["events"]) == 20


def test_events_replayed_after_an_outage_are_still_unread(client) -> None:
    """Internet uzilib qayta ulanganda kelgan hodisalar YO'QOLMASIN.

    Bu mahsulotning asosiy stsenariysi: aloqa yo'q bo'lsa hodisalar
    qurilmadagi `outbox.db` da navbatda turadi va keyin ESKI sanalar
    bilan keladi.

    Agar "o'qildi" belgisi `occurred_at` bilan solishtirilsa, bunday
    hodisa jimgina o'qilgan bo'lib chiqadi — ya'ni ega aynan uzilish
    paytidagi, eng muhim hodisalarni HECH QACHON ko'rmaydi.  Shuning
    uchun solishtirish `created_at` (bulut qachon bilgani) bo'yicha.
    """
    site, device = _site(client)
    owner = _member(client, site["site_id"], "607")

    _send(client, device, "before-outage", "critical", "2026-08-26T09:00:00+00:00")
    client.post("/api/v1/owner/notifications/read", headers=owner)
    assert client.get("/api/v1/owner/notifications", headers=owner).json()["unread"] == 0

    # Uzilish paytida sodir bo'lgan — sanasi o'qish belgisidan ham,
    # avvalgi hodisadan ham ORQADA.
    _send(client, device, "during-outage", "critical", "2026-08-26T08:00:00+00:00")

    result = client.get("/api/v1/owner/notifications", headers=owner).json()
    assert result["unread"] == 1, "kechikkan hodisa o'qilmagan bo'lib qolsin"
    replayed = next(item for item in result["events"] if item["event_id"] == "during-outage")
    assert replayed["unread"] is True
