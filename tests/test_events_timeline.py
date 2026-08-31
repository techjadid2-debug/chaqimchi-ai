"""Hodisalar vaqt lentasi: kunning HAMMA soati, kesilmagan namunadan emas.

Nega alohida marshrut kerak bo'ldi: `/owner/events` "oxirgi N ta" beradi
va limiti 500 ta.  Gavjum do'konda (qurilma kuniga ~7 600 xom hodisa
yasaydi) bu kunning faqat oxirgi qismi degani — lenta ertalabki soatlarni
bo'sh ko'rsatardi.  Bu "ma'lumot yo'q" emas, YOLG'ON edi.

Vaqtlar bu faylda ATAYLAB qotirilgan.  `datetime.now()` ga tayangan test
23:59 da kun chegarasidan o'tib tasodifan yiqiladi.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cloud import ratelimit
from cloud.notify import event_label
from cloud.snapshots import LocalSnapshotStore

ADMIN = {"X-Cloud-Admin-Key": "test-admin"}

#: Toshkent = UTC+5, yozgi vaqt yo'q.  Testdagi hamma UTC belgisi shu
#: farq bilan mahalliy soatga o'giriladi.
TASHKENT_OFFSET_HOURS = 5

#: Sinov kuni — o'tgan, lekin `CLOCK_PAST_WARN` (730 kun) ichida.
DAY = "2026-08-20"


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

    # Fon halqalari no-op: `TestClient` ochilishi bilan `_maintenance_loop`
    # alohida oqimda darhol purge boshlaydi va test endigina yozgan
    # hodisalarni o'chirib yuborishi mumkin (uch haftalik beqaror test
    # aynan shundan edi).
    async def no_background_loop() -> None:
        return None

    monkeypatch.setattr(main, "_maintenance_loop", no_background_loop)
    monkeypatch.setattr(main, "_history_rollup_loop", no_background_loop)

    ratelimit.limiter().reset()
    with TestClient(main.app) as test_client:
        yield test_client
    ratelimit.limiter().reset()


def _provision(client: TestClient):
    site = client.post(
        "/api/v1/admin/sites", headers=ADMIN, json={"name": "Lenta", "plan": "enterprise"}
    ).json()
    device = client.post(
        "/api/v1/devices/claim", json={"pairing_code": site["pairing_code"]}
    ).json()
    return site, {
        "X-Site-Id": device["site_id"],
        "X-Device-Id": device["device_id"],
        "X-Device-Token": device["device_token"],
    }


def _owner(client: TestClient, site_id: str, telegram_id: str = "707") -> dict:
    client.post(
        f"/api/v1/admin/sites/{site_id}/members",
        headers=ADMIN,
        json={"telegram_id": telegram_id, "role": "owner"},
    )
    client.post("/api/v1/owner/auth/request", json={"telegram_id": telegram_id})
    verified = client.post(
        "/api/v1/owner/auth/verify",
        json={"telegram_id": telegram_id, "site_id": site_id, "code": "123456"},
    )
    return {"Authorization": f"Bearer {verified.json()['access_token']}"}


def _utc_for(local_hour: int, minute: int = 0, day: str = DAY) -> str:
    """Toshkent soati -> UTC ISO.  Kun chegarasidan o'tsa ham to'g'ri."""
    local = datetime.fromisoformat(f"{day}T00:00:00+05:00") + timedelta(
        hours=local_hour, minutes=minute
    )
    return local.astimezone(timezone.utc).isoformat()


def _send(client: TestClient, headers: dict, events: list) -> None:
    for start in range(0, len(events), 200):
        response = client.post(
            "/api/v1/edge/events/batch",
            headers=headers,
            json={"events": events[start : start + 200]},
        )
        assert response.status_code == 200, response.text


def _timeline(client: TestClient, owner: dict, **params) -> dict:
    query = "&".join(f"{key}={value}" for key, value in params.items())
    response = client.get(
        f"/api/v1/owner/events/timeline?{query}" if query else "/api/v1/owner/events/timeline",
        headers=owner,
    )
    assert response.status_code == 200, response.text
    return response.json()


# ── Asosiy da'vo ─────────────────────────────────────────────────────────


def test_the_timeline_covers_the_whole_day_not_the_last_500_events(client: TestClient) -> None:
    """600 ta hodisadan ERTALABKISI ham ko'rinsin.

    `list_events` bo'lganda 500 talik kesim eng eski 100 tasini tashlab
    yuborardi — ya'ni aynan shu 03:00 dagi hodisa lentada bo'lmasdi.
    """
    site, headers = _provision(client)
    owner = _owner(client, site["site_id"])

    events = [
        {
            "event_id": "erta-03",
            "event_type": "camera_tampered",
            "severity": "critical",
            "camera_id": "camera-01",
            "occurred_at": _utc_for(3),
        }
    ]
    for index in range(599):
        events.append(
            {
                "event_id": f"oqim-{index}",
                "event_type": "line_crossed",
                "direction": "in",
                "camera_id": "camera-01",
                "occurred_at": _utc_for(18, index % 60),
            }
        )
    _send(client, headers, events)

    timeline = _timeline(client, owner, date=DAY)

    assert timeline["total"] == 600
    assert timeline["hours"][3]["total"] == 1, "ertalabki hodisa kesilib qolmasin"
    assert timeline["hours"][3]["by_type"]["camera_tampered"] == 1
    assert timeline["hours"][18]["total"] == 599


def test_the_timeline_counts_hours_in_tashkent_time(client: TestClient) -> None:
    """23:30 UTC — Toshkentda ERTANGI kunning 04:30 i."""
    site, headers = _provision(client)
    owner = _owner(client, site["site_id"])
    _send(
        client,
        headers,
        [
            {
                "event_id": "kechqurun",
                "event_type": "line_crossed",
                "direction": "in",
                "camera_id": "camera-01",
                "occurred_at": "2026-08-20T23:30:00+00:00",
            }
        ],
    )

    kecha = _timeline(client, owner, date="2026-08-20")
    ertaga = _timeline(client, owner, date="2026-08-21")

    assert kecha["total"] == 0, "UTC kuni bo'yicha sanalmasin"
    assert ertaga["hours"][4]["total"] == 1
    assert ertaga["total"] == 1


def test_an_empty_day_returns_24_zeroed_hours_not_an_error(client: TestClient) -> None:
    """Bo'sh kun ham 24 ta katak beradi — grafikning o'qi to'liq bo'lsin.

    Panel esa `total == 0` bo'lgan soatga hech narsa chizmaydi.
    """
    site, _headers = _provision(client)
    owner = _owner(client, site["site_id"])

    timeline = _timeline(client, owner, date=DAY)

    assert len(timeline["hours"]) == 24
    assert [hour["hour"] for hour in timeline["hours"]] == list(range(24))
    assert timeline["total"] == 0
    assert timeline["types"] == []


# ── Nima ko'rinmasligi kerak ─────────────────────────────────────────────


@pytest.mark.parametrize("hidden", ["person_detected", "face_captured", "employee_seen"])
def test_noise_and_biometrics_never_reach_the_timeline(client: TestClient, hidden: str) -> None:
    """Uch tur ataylab chiqarib tashlanadi.

    `person_detected` — daqiqasiga ~100 ta, lenta faqat shundan iborat
    bo'lardi.  `face_captured` va `employee_seen` — biometrika va xodim,
    ega uchun "hodisa" emas.
    """
    site, headers = _provision(client)
    owner = _owner(client, site["site_id"])
    _send(
        client,
        headers,
        [
            {
                "event_id": "yashirin",
                "event_type": hidden,
                "camera_id": "camera-01",
                "occurred_at": _utc_for(12),
            },
            {
                "event_id": "korinsin",
                "event_type": "line_crossed",
                "direction": "in",
                "camera_id": "camera-01",
                "occurred_at": _utc_for(12),
            },
        ],
    )

    timeline = _timeline(client, owner, date=DAY)

    assert timeline["total"] == 1, f"{hidden} lentaga tushmasin"
    assert timeline["hours"][12]["by_type"] == {"line_crossed": 1}


def test_a_new_event_type_appears_without_touching_the_list(client: TestClient) -> None:
    """Ro'yxat TAQIQ, ruxsat emas — yangi tur o'zi chiqadi.

    `REPORT_EVENT_TYPES` ruxsat ro'yxati bo'lgani uchun
    `checkout_unattended` unga tushmay qolgan va ega uni oylab hech
    qayerda ko'rmagan.  Bu test o'sha xatoning takrorlanishini to'sadi:
    ruxsat ro'yxatiga o'tilsa u yiqiladi.
    """
    site, headers = _provision(client)
    owner = _owner(client, site["site_id"])
    _send(
        client,
        headers,
        [
            {
                "event_id": "javon",
                "event_type": "shelf_empty",
                "camera_id": "camera-01",
                "occurred_at": _utc_for(9),
            },
            {
                "event_id": "kassa",
                "event_type": "checkout_unattended",
                "camera_id": "camera-02",
                "occurred_at": _utc_for(9),
            },
        ],
    )

    timeline = _timeline(client, owner, date=DAY)

    kinds = {item["type"] for item in timeline["types"]}
    assert kinds == {"shelf_empty", "checkout_unattended"}


def test_the_timeline_is_tenant_scoped(client: TestClient) -> None:
    site, headers = _provision(client)
    _send(
        client,
        headers,
        [
            {
                "event_id": "meniki",
                "event_type": "line_crossed",
                "direction": "in",
                "camera_id": "camera-01",
                "occurred_at": _utc_for(10),
            }
        ],
    )
    other = client.post(
        "/api/v1/admin/sites", headers=ADMIN, json={"name": "Boshqa", "plan": "enterprise"}
    ).json()
    stranger = _owner(client, other["site_id"], telegram_id="808")

    timeline = _timeline(client, stranger, date=DAY)

    assert timeline["total"] == 0, "boshqa saytning hodisasi ko'rinmasin"


# ── Yordamchi maydonlar ──────────────────────────────────────────────────


def test_the_timeline_labels_come_from_one_place(client: TestClient) -> None:
    """Tarjima `event_label` dan — panel va Telegram bir xil gapirsin."""
    site, headers = _provision(client)
    owner = _owner(client, site["site_id"])
    _send(
        client,
        headers,
        [
            {
                "event_id": "navbat",
                "event_type": "queue_threshold_exceeded",
                "camera_id": "camera-02",
                "occurred_at": _utc_for(19),
            }
        ],
    )

    timeline = _timeline(client, owner, date=DAY)

    assert timeline["types"][0]["label"] == event_label("queue_threshold_exceeded")


def test_the_timeline_can_be_narrowed_to_one_camera(client: TestClient) -> None:
    site, headers = _provision(client)
    owner = _owner(client, site["site_id"])
    _send(
        client,
        headers,
        [
            {
                "event_id": f"cam-{index}",
                "event_type": "line_crossed",
                "direction": "in",
                "camera_id": camera,
                "occurred_at": _utc_for(11),
            }
            for index, camera in enumerate(["camera-01", "camera-02", "camera-02"])
        ],
    )

    timeline = _timeline(client, owner, date=DAY, camera_id="camera-02")

    assert timeline["total"] == 2
    assert timeline["camera_id"] == "camera-02"


def test_media_is_counted_so_the_panel_can_show_a_photo_hint(client: TestClient) -> None:
    """Soatda nechta hodisaning kadri borligi lentadan ko'rinsin."""
    site, headers = _provision(client)
    owner = _owner(client, site["site_id"])
    _send(
        client,
        headers,
        [
            {
                "event_id": "rasmli",
                "event_type": "camera_tampered",
                "severity": "critical",
                "camera_id": "camera-01",
                "occurred_at": _utc_for(14),
                "has_snapshot": True,
            },
            {
                "event_id": "rasmsiz",
                "event_type": "camera_tampered",
                "severity": "critical",
                "camera_id": "camera-01",
                "occurred_at": _utc_for(14),
            },
        ],
    )

    timeline = _timeline(client, owner, date=DAY)

    assert timeline["hours"][14]["total"] == 2
    assert timeline["hours"][14]["with_media"] == 1


def test_a_broken_date_is_refused_not_guessed(client: TestClient) -> None:
    site, _headers = _provision(client)
    owner = _owner(client, site["site_id"])

    response = client.get("/api/v1/owner/events/timeline?date=20-avgust", headers=owner)

    assert response.status_code == 422


# ── /owner/events oynasi ─────────────────────────────────────────────────


def test_owner_events_can_be_narrowed_to_one_day_and_hour(client: TestClient) -> None:
    """Lentadagi soatga bosilganda kartochkalar AYNAN o'sha soatdan kelsin."""
    site, headers = _provision(client)
    owner = _owner(client, site["site_id"])
    _send(
        client,
        headers,
        [
            {
                "event_id": f"soat-{hour}",
                "event_type": "line_crossed",
                "direction": "in",
                "camera_id": "camera-01",
                "occurred_at": _utc_for(hour),
            }
            for hour in (9, 14, 20)
        ],
    )

    kun = client.get(f"/api/v1/owner/events?date={DAY}", headers=owner).json()["events"]
    soat = client.get(f"/api/v1/owner/events?date={DAY}&hour=14", headers=owner).json()["events"]

    assert len(kun) == 3
    assert [item["event_id"] for item in soat] == ["soat-14"]


def test_events_without_a_date_still_return_the_latest(client: TestClient) -> None:
    """Sanasiz chaqiruv AVVALGIDAY ishlasin.

    Bu marshrutni bosh sahifa (`/owner/dashboard`) va qo'ng'iroq ham
    chaqiradi va ular sana bermaydi.
    """
    site, headers = _provision(client)
    owner = _owner(client, site["site_id"])
    _send(
        client,
        headers,
        [
            {
                "event_id": "sanasiz",
                "event_type": "line_crossed",
                "direction": "in",
                "camera_id": "camera-01",
                "occurred_at": _utc_for(10),
            }
        ],
    )

    events = client.get("/api/v1/owner/events", headers=owner).json()["events"]

    assert [item["event_id"] for item in events] == ["sanasiz"]


def test_a_broken_hour_is_refused(client: TestClient) -> None:
    site, _headers = _provision(client)
    owner = _owner(client, site["site_id"])

    response = client.get(f"/api/v1/owner/events?date={DAY}&hour=25", headers=owner)

    assert response.status_code == 422
