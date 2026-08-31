"""Media siyosati: qurilma va panel BIR XIL ro'yxatni bilishi.

Nega kontrakt testi kerak: `cloud` `chaqimchi_ai.retail.pipeline` ni
import qila olmaydi (u `cv2`/`numpy` tortadi va serverda ular yo'q), ya'ni
"qaysi hodisaga rasm olinadi" ro'yxati IKKI joyda yozilgan.  Ikki fayldagi
ikki qiymat bir-birini inkor qilishi mumkin va buni hech qaysi modul
testi ko'rmaydi — `limits.py` dagi yuz chegarasi aynan shundan oylab
ishlamagan.

Panelga bu nima uchun kerak: "rasm hali yuklanmagan" va "bu turdagi
hodisada rasm UMUMAN olinmaydi" ikki BOSHQA javob.  Ular bir xil
ko'rinsa, ega uchun bu jimgina yolg'on bo'ladi.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from chaqimchi_ai.retail.pipeline import SECURITY_MEDIA_EVENTS
from cloud import ratelimit
from cloud.notify import MEDIA_EVENT_TYPES
from cloud.snapshots import LocalSnapshotStore

ADMIN = {"X-Cloud-Admin-Key": "test-admin"}


def test_the_panel_and_the_device_agree_on_which_events_get_a_photo() -> None:
    assert set(MEDIA_EVENT_TYPES) == set(SECURITY_MEDIA_EVENTS)


def test_loitering_stays_out_of_the_media_list() -> None:
    """2026-08-21 o'lchovi: 7.4 soatda 29 MB rasmning 99.6% i loiteringdan.

    Kunlik 500 talik snapshot chegarasining 302 tasi kechgacha yeb
    bo'lingan, ya'ni haqiqiy o'g'rilik hodisasiga rasm ilinmay qolardi.
    Kartochkani "rasmliroq" qilish istagida uni ro'yxatga qaytarish
    vasvasasi bor — shu test to'sadi.
    """
    assert "loitering" not in MEDIA_EVENT_TYPES
    assert "line_crossed" not in MEDIA_EVENT_TYPES


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
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

    async def no_background_loop() -> None:
        return None

    monkeypatch.setattr(main, "_maintenance_loop", no_background_loop)
    monkeypatch.setattr(main, "_history_rollup_loop", no_background_loop)

    ratelimit.limiter().reset()
    with TestClient(main.app) as test_client:
        yield test_client, monkeypatch
    ratelimit.limiter().reset()


def _owner_of_new_site(client: TestClient) -> tuple[dict, dict]:
    site = client.post(
        "/api/v1/admin/sites", headers=ADMIN, json={"name": "Media", "plan": "enterprise"}
    ).json()
    device = client.post(
        "/api/v1/devices/claim", json={"pairing_code": site["pairing_code"]}
    ).json()
    client.post(
        f"/api/v1/admin/sites/{site['site_id']}/members",
        headers=ADMIN,
        json={"telegram_id": "909", "role": "owner"},
    )
    client.post("/api/v1/owner/auth/request", json={"telegram_id": "909"})
    verified = client.post(
        "/api/v1/owner/auth/verify",
        json={"telegram_id": "909", "site_id": site["site_id"], "code": "123456"},
    )
    return (
        {"Authorization": f"Bearer {verified.json()['access_token']}"},
        {
            "X-Site-Id": device["site_id"],
            "X-Device-Id": device["device_id"],
            "X-Device-Token": device["device_token"],
        },
    )


def test_the_panel_is_told_the_media_deadline(client) -> None:
    """Muddat SERVERDAN kelsin — panel «48» ni o'zida saqlamasin."""
    test_client, monkeypatch = client
    owner, _device = _owner_of_new_site(test_client)

    standart = test_client.get("/api/v1/owner/dashboard", headers=owner).json()
    assert standart["media_retention_hours"] == 48

    monkeypatch.setenv("CHAQIMCHI_MEDIA_RETENTION_HOURS", "12")
    ozgargan = test_client.get("/api/v1/owner/dashboard", headers=owner).json()

    assert ozgargan["media_retention_hours"] == 12, (
        "muddat env bilan o'zgarsa panel ham o'zgarganini ko'rsin"
    )


def test_each_event_says_whether_a_photo_was_ever_expected(client) -> None:
    """`media_expected` — «kadr yo'q» va «kadr bo'lmaydi» ni ajratadi."""
    test_client, _monkeypatch = client
    owner, device = _owner_of_new_site(test_client)
    test_client.post(
        "/api/v1/edge/events/batch",
        headers=device,
        json={
            "events": [
                {
                    "event_id": "buzilgan",
                    "event_type": "camera_tampered",
                    "severity": "critical",
                    "camera_id": "camera-01",
                    "occurred_at": "2026-08-20T09:00:00+00:00",
                },
                {
                    "event_id": "kirish",
                    "event_type": "line_crossed",
                    "direction": "in",
                    "camera_id": "camera-01",
                    "occurred_at": "2026-08-20T09:05:00+00:00",
                },
            ]
        },
    )

    events = {
        item["event_id"]: item
        for item in test_client.get("/api/v1/owner/events", headers=owner).json()["events"]
    }

    assert events["buzilgan"]["media_expected"] is True
    assert events["kirish"]["media_expected"] is False
