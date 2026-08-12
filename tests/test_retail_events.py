"""Retail hodisa turlari va ularning cloud'gacha yetib borishi.

Kontrakt **additiv**: eski hodisa turlari va eski maydonlar tegilmaydi, aks
holda yangilanmagan qurilma hodisasi rad etilardi.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from chaqimchi_ai.event_models import EdgeEvent
from cloud import ratelimit
from cloud.event_store import EventStore
from cloud.notify import event_label, summarize
from cloud.snapshots import LocalSnapshotStore

ADMIN = {"X-Cloud-Admin-Key": "test-admin"}


def test_v1_event_types_still_validate() -> None:
    """Eski turlar buzilmasin — yangilanmagan qurilma ham ishlashda davom etsin."""
    for event_type in (
        "person_detected",
        "employee_seen",
        "zone_entered",
        "loitering",
        "occupancy_exceeded",
    ):
        event = EdgeEvent(event_type=event_type, camera_id="camera-01")  # type: ignore[arg-type]
        assert event.direction is None
        assert event.queue_length is None


def test_retail_event_carries_its_own_fields() -> None:
    event = EdgeEvent(
        event_type="line_crossed",
        camera_id="kirish",
        direction="in",
        line="eshik",
        track_id=42,
    )
    payload = event.cloud_payload()
    assert payload["direction"] == "in"
    assert payload["line"] == "eshik"
    # Lokal yo'l cloud'ga chiqmaydi.
    assert "snapshot_path" not in payload


def test_unknown_event_type_is_rejected() -> None:
    with pytest.raises(ValueError):
        EdgeEvent(event_type="shoplifting", camera_id="camera-01")  # type: ignore[arg-type]


def test_direction_is_constrained_to_in_or_out() -> None:
    with pytest.raises(ValueError):
        EdgeEvent(event_type="line_crossed", camera_id="c", direction="chapga")  # type: ignore[arg-type]


def test_every_event_type_has_an_uzbek_label() -> None:
    """Mijoz `queue_threshold_exceeded` ni tushunmaydi."""
    from typing import get_args

    from chaqimchi_ai.event_models import EventType

    for event_type in get_args(EventType):
        assert event_label(event_type) != event_type, f"{event_type} uchun nom yo'q"


def test_alert_summary_uses_the_uzbek_labels() -> None:
    events = [
        EdgeEvent(event_type="queue_threshold_exceeded", camera_id="kassa-01",
                  severity="warning", queue_length=7),
        EdgeEvent(event_type="camera_tampered", camera_id="ombor",
                  severity="critical"),
    ]
    message = summarize(events)
    assert "Navbat uzun — kassa-01" in message
    assert "Kamera yopildi yoki burildi — ombor" in message
    assert message.startswith("🔴")


# ── Cloud saqlash ────────────────────────────────────────────────────────


def test_event_store_persists_and_returns_retail_fields(tmp_path: Path) -> None:
    store = EventStore(sqlite_path=tmp_path / "events.db")
    store.ingest(
        "site-1",
        "device-1",
        [
            EdgeEvent(event_id="e1", event_type="line_crossed", camera_id="kirish",
                      direction="in", line="eshik"),
            EdgeEvent(event_id="e2", event_type="dwell_exceeded", camera_id="zal",
                      zone="tokcha-3", dwell_sec=185.5),
            EdgeEvent(event_id="e3", event_type="queue_threshold_exceeded",
                      camera_id="kassa-01", queue_length=6),
        ],
    )

    by_id = {row["event_id"]: row for row in store.list_events("site-1", limit=10)}
    assert by_id["e1"]["direction"] == "in"
    assert by_id["e1"]["line_name"] == "eshik"
    assert by_id["e2"]["dwell_sec"] == pytest.approx(185.5)
    assert by_id["e3"]["queue_length"] == 6


def test_existing_database_gains_retail_columns(tmp_path: Path) -> None:
    """Yangilanish eski bazani buzmasin va ma'lumotni yo'qotmasin."""
    path = tmp_path / "events.db"
    old = EventStore(sqlite_path=path)
    old.ingest("site-1", "device-1",
               [EdgeEvent(event_id="eski", event_type="loitering", camera_id="zal")])

    # Ikkinchi marta ochilishi migratsiyani qayta ishga tushiradi.
    fresh = EventStore(sqlite_path=path)
    fresh.ingest("site-1", "device-1",
                 [EdgeEvent(event_id="yangi", event_type="line_crossed",
                            camera_id="kirish", direction="out")])

    rows = {row["event_id"]: row for row in fresh.list_events("site-1", limit=10)}
    assert rows["eski"]["direction"] is None  # eski yozuv saqlandi
    assert rows["yangi"]["direction"] == "out"


def test_migration_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "events.db"
    for _ in range(3):
        EventStore(sqlite_path=path)  # takroriy ochilish xato bermasin


# ── Uchidan uchiga ───────────────────────────────────────────────────────


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
    ratelimit.limiter().reset()
    with TestClient(main.app) as client:
        yield main, client
    ratelimit.limiter().reset()


def test_edge_can_send_retail_events_to_cloud(cloud) -> None:
    main, client = cloud
    site = client.post("/api/v1/admin/sites", headers=ADMIN,
                       json={"name": "Do'kon", "plan": "lite"}).json()
    device = client.post("/api/v1/devices/claim",
                         json={"pairing_code": site["pairing_code"]}).json()
    headers = {
        "X-Site-Id": device["site_id"],
        "X-Device-Id": device["device_id"],
        "X-Device-Token": device["device_token"],
    }

    response = client.post(
        "/api/v1/edge/events/batch",
        headers=headers,
        json={"events": [
            EdgeEvent(event_id="in-1", event_type="line_crossed", camera_id="kirish",
                      direction="in", line="eshik").cloud_payload(),
            EdgeEvent(event_id="out-1", event_type="line_crossed", camera_id="kirish",
                      direction="out", line="eshik").cloud_payload(),
        ]},
    )

    assert response.status_code == 200
    assert response.json()["accepted"] == ["in-1", "out-1"]
    stored = main.get_event_store().list_events(device["site_id"], limit=10)
    assert sorted(row["direction"] for row in stored) == ["in", "out"]
