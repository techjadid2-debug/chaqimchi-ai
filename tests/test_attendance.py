from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import numpy as np
import pytest
from fastapi.testclient import TestClient

from chaqimchi_ai.database import FaceDatabase
from chaqimchi_ai.event_models import EdgeEvent
from chaqimchi_ai.runtime.container import AppContainer
from chaqimchi_ai.settings import AppSettings
from cloud.event_store import EventStore


def _fixed_utc_now() -> datetime:
    return datetime(2026, 8, 13, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def fixed_event_store_clock(monkeypatch):
    """Davomat testlari kalendar sanasiga bog'lanib, ertasi kuni buzilmasin."""
    monkeypatch.setattr("cloud.event_store._now", _fixed_utc_now)


def test_attendance_uses_cloud_employee_name_and_weekly_schedule(tmp_path: Path) -> None:
    store = EventStore(sqlite_path=tmp_path / "events.db")
    employee = store.create_employee(
        "site-1", name="Ali Valiyev", external_id="A-17", consent_note="signed"
    )
    store.replace_employee_schedules(
        "site-1",
        employee["id"],
        [
            {
                "weekday": 3,  # 2026-08-13 — payshanba
                "start_time": "09:00",
                "end_time": "18:00",
                "grace_minutes": 5,
                "enabled": True,
            }
        ],
    )
    store.ingest(
        "site-1",
        "device-1",
        [
            EdgeEvent(
                event_id="seen-1",
                event_type="employee_seen",
                camera_id="camera-01",
                person_id=employee["id"],
                person_name="EDGE ISMIGA ISHONILMASIN",
                occurred_at="2026-08-13T04:12:00+00:00",
            ),
            EdgeEvent(
                event_id="seen-2",
                event_type="employee_seen",
                camera_id="camera-01",
                person_id=employee["id"],
                occurred_at="2026-08-13T12:40:00+00:00",
            ),
        ],
    )

    report = store.attendance_report(
        "site-1",
        start=date(2026, 8, 13),
        end=date(2026, 8, 13),
        now=datetime(2026, 8, 13, 20, 0, tzinfo=ZoneInfo("Asia/Tashkent")),
    )

    row = report["rows"][0]
    assert row["employee_name"] == "Ali Valiyev"
    assert row["status"] == "late"
    assert row["late_minutes"] == 7
    assert row["early_leave_minutes"] == 20
    assert row["checkout_missing"] is False
    assert report["summary"] == {
        "present": 1,
        "absent": 0,
        "late": 1,
        "early_leave": 1,
        "checkout_missing": 0,
        "unscheduled": 0,
    }


def test_unknown_employee_event_is_not_counted_or_allowed_to_inject_a_name(
    tmp_path: Path,
) -> None:
    store = EventStore(sqlite_path=tmp_path / "events.db")
    store.ingest(
        "site-1",
        "device-1",
        [
            EdgeEvent(
                event_type="employee_seen",
                camera_id="camera-01",
                person_id="unknown",
                person_name="Soxta Ism",
                occurred_at="2026-08-13T04:00:00+00:00",
            )
        ],
    )
    event = store.list_events("site-1")[0]
    assert event["person_name"] is None
    report = store.attendance_report("site-1", start=date(2026, 8, 13), end=date(2026, 8, 13))
    assert report["rows"] == []


def test_departure_requires_the_configured_checkout_camera(tmp_path: Path) -> None:
    store = EventStore(sqlite_path=tmp_path / "events.db")
    employee = store.create_employee("site-1", name="Ali", consent_note="signed")
    store.replace_employee_schedules(
        "site-1",
        employee["id"],
        [
            {
                "weekday": 3,
                "start_time": "09:00",
                "end_time": "18:00",
                "grace_minutes": 5,
                "enabled": True,
            }
        ],
    )
    config = store.get_site_config("site-1")["config"]
    config["attendance_camera_roles"] = {
        "camera-01": "arrival",
        "camera-02": "departure",
    }
    store.update_site_config("site-1", config)
    store.ingest(
        "site-1",
        "device-1",
        [
            EdgeEvent(
                event_type="employee_seen",
                camera_id="camera-01",
                person_id=employee["id"],
                occurred_at="2026-08-13T04:00:00+00:00",
            ),
            EdgeEvent(
                event_type="employee_seen",
                camera_id="camera-01",
                person_id=employee["id"],
                occurred_at="2026-08-13T04:02:00+00:00",
            ),
        ],
    )

    row = store.attendance_report(
        "site-1",
        start=date(2026, 8, 13),
        end=date(2026, 8, 13),
        now=datetime(2026, 8, 13, 19, 0, tzinfo=ZoneInfo("Asia/Tashkent")),
    )["rows"][0]

    assert row["first_seen"] is not None
    assert row["last_seen"] is None
    assert row["checkout_missing"] is True
    assert row["early_leave_minutes"] == 0


def test_both_role_needs_a_separate_second_sighting_for_checkout(tmp_path: Path) -> None:
    store = EventStore(sqlite_path=tmp_path / "events.db")
    employee = store.create_employee("site-1", name="Ali", consent_note="signed")
    store.replace_employee_schedules(
        "site-1",
        employee["id"],
        [
            {
                "weekday": 3,
                "start_time": "09:00",
                "end_time": "18:00",
                "grace_minutes": 5,
                "enabled": True,
            }
        ],
    )
    config = store.get_site_config("site-1")["config"]
    config["attendance_camera_roles"] = {"camera-01": "both"}
    store.update_site_config("site-1", config)
    store.ingest(
        "site-1",
        "device-1",
        [
            EdgeEvent(
                event_type="employee_seen",
                camera_id="camera-01",
                person_id=employee["id"],
                occurred_at="2026-08-13T04:00:00+00:00",
            ),
            EdgeEvent(
                event_type="employee_seen",
                camera_id="camera-01",
                person_id=employee["id"],
                occurred_at="2026-08-13T04:02:00+00:00",
            ),
        ],
    )

    row = store.attendance_report(
        "site-1",
        start=date(2026, 8, 13),
        end=date(2026, 8, 13),
        now=datetime(2026, 8, 13, 19, 0, tzinfo=ZoneInfo("Asia/Tashkent")),
    )["rows"][0]

    assert row["first_seen"] is not None
    assert row["last_seen"] is None
    assert row["checkout_missing"] is True


def test_absence_waits_until_the_grace_period_ends(tmp_path: Path) -> None:
    store = EventStore(sqlite_path=tmp_path / "events.db")
    employee = store.create_employee("site-1", name="Ali", consent_note="signed")
    store.replace_employee_schedules(
        "site-1",
        employee["id"],
        [
            {
                "weekday": 3,
                "start_time": "09:00",
                "end_time": "18:00",
                "grace_minutes": 5,
                "enabled": True,
            }
        ],
    )

    pending = store.attendance_report(
        "site-1",
        start=date(2026, 8, 13),
        end=date(2026, 8, 13),
        now=datetime(2026, 8, 13, 9, 4, tzinfo=ZoneInfo("Asia/Tashkent")),
    )["rows"][0]
    absent = store.attendance_report(
        "site-1",
        start=date(2026, 8, 13),
        end=date(2026, 8, 13),
        now=datetime(2026, 8, 13, 9, 6, tzinfo=ZoneInfo("Asia/Tashkent")),
    )["rows"][0]

    assert pending["status"] == "pending"
    assert absent["status"] == "absent"


def test_deactivated_employee_keeps_history_but_not_future_rows(tmp_path: Path) -> None:
    store = EventStore(sqlite_path=tmp_path / "events.db")
    employee = store.create_employee("site-1", name="Ali", consent_note="signed")
    store.ingest(
        "site-1",
        "device-1",
        [
            EdgeEvent(
                event_type="employee_seen",
                camera_id="camera-01",
                person_id=employee["id"],
                occurred_at="2026-08-13T04:00:00+00:00",
            )
        ],
    )
    store.update_employee("site-1", employee["id"], active=False)

    report = store.attendance_report(
        "site-1",
        start=date(2026, 8, 13),
        end=date(2026, 8, 14),
        now=datetime(2026, 8, 14, 20, 0, tzinfo=ZoneInfo("Asia/Tashkent")),
    )

    assert [row["date"] for row in report["rows"]] == ["2026-08-13"]
    assert report["rows"][0]["status"] == "unscheduled"


def test_face_database_can_use_cloud_employee_id_without_storing_an_image(
    tmp_path: Path,
) -> None:
    db = FaceDatabase(tmp_path / "faces")
    entry = db.add_face(
        "Ali",
        np.ones(512, dtype=np.float32),
        {"kind": "employee", "cloud_managed": True},
        face_id="employee-cloud-id",
    )
    assert entry["id"] == "employee-cloud-id"
    assert set((tmp_path / "faces").iterdir()) == {
        tmp_path / "faces" / "metadata.json",
        tmp_path / "faces" / "embeddings.npy",
    }


def test_reenrollment_atomically_replaces_the_same_cloud_employee(tmp_path: Path) -> None:
    db = FaceDatabase(tmp_path / "faces")
    first = np.zeros(512, dtype=np.float32)
    first[0] = 1
    second = np.zeros(512, dtype=np.float32)
    second[1] = 1
    db.replace_face("employee-1", "Ali", first, {"cloud_managed": True})

    db.replace_face("employee-1", "Ali Valiyev", second, {"cloud_managed": True})

    assert db.count == 1
    assert db.get_person("employee-1")["name"] == "Ali Valiyev"
    assert db.embeddings is not None
    assert db.embeddings[0].tolist()[:2] == [0.0, 1.0]


def test_missing_remote_cache_does_not_erase_local_enrollment(tmp_path: Path, monkeypatch) -> None:
    from webapp.main import _load_remote_scene_cache

    db = FaceDatabase(tmp_path / "faces")
    db.add_face(
        "Ali",
        np.ones(512, dtype=np.float32),
        {"cloud_managed": True},
        face_id="employee-1",
    )
    container = SimpleNamespace(
        settings=AppSettings(),
        base_dir=tmp_path,
        remote_config_revision=0,
        remote_employees={},
        camera_manager=None,
        db_or_none=db,
    )
    monkeypatch.setenv("CHAQIMCHI_SOTQIN_CONFIG_CACHE", str(tmp_path / "missing.json"))

    _load_remote_scene_cache(container)

    assert db.get_person("employee-1") is not None


def test_attendance_service_uses_a_separate_outbox(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CHAQIMCHI_SERVICE_MODE", "attendance")
    container = AppContainer(tmp_path, settings=AppSettings())

    assert container.outbox.db_path.name == "attendance-outbox.db"


def test_attendance_service_does_not_mount_generic_person_or_vision_routes(
    tmp_path: Path, monkeypatch
) -> None:
    from webapp.main import create_app

    monkeypatch.setenv("CHAQIMCHI_SERVICE_MODE", "attendance")
    app = create_app(AppContainer(tmp_path, settings=AppSettings()))
    paths = {route.path for route in app.routes}

    assert "/api/attendance/enroll" in paths
    assert "/api/persons/add" not in paths
    assert "/api/vision/analyze" not in paths


def test_owner_employee_flow_and_csv_never_return_biometrics(tmp_path: Path, monkeypatch) -> None:
    import cloud.main as main

    monkeypatch.setenv("CHAQIMCHI_CLOUD_ADMIN_KEY", "test-admin")
    monkeypatch.setenv("CHAQIMCHI_OWNER_JWT_SECRET", "owner-secret-with-more-than-32-characters")
    monkeypatch.setenv("CHAQIMCHI_OTP_TEST_CODE", "123456")
    monkeypatch.setenv("CHAQIMCHI_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "cloud.db")
    monkeypatch.setattr(main, "_store", None)
    monkeypatch.setattr(main, "_event_store", None)
    monkeypatch.setattr(main, "_event_store_key", None)

    async def no_message(_chat_id: str, _text: str) -> None:
        return None

    monkeypatch.setattr(main, "_send_owner_telegram", no_message)
    with TestClient(main.app) as client:
        site = client.post(
            "/api/v1/admin/sites",
            headers={"X-Cloud-Admin-Key": "test-admin"},
            json={"name": "Do'kon", "plan": "lite"},
        ).json()
        device = client.post(
            "/api/v1/sotqin/claim", json={"pairing_code": site["pairing_code"]}
        ).json()
        client.post(
            f"/api/v1/admin/sites/{site['site_id']}/members",
            headers={"X-Cloud-Admin-Key": "test-admin"},
            json={"telegram_id": "900", "role": "owner"},
        )
        client.post("/api/v1/owner/auth/request", json={"telegram_id": "900"})
        token = client.post(
            "/api/v1/owner/auth/verify",
            json={"telegram_id": "900", "site_id": site["site_id"], "code": "123456"},
        ).json()["access_token"]
        owner = {"Authorization": f"Bearer {token}"}

        rejected = client.post(
            "/api/v1/owner/employees",
            headers=owner,
            json={"name": "Ali", "consent": False},
        )
        assert rejected.status_code == 422
        created = client.post(
            "/api/v1/owner/employees",
            headers=owner,
            json={"name": "Ali", "external_id": "A-1", "consent": True},
        )
        assert created.status_code == 200
        employee = created.json()
        schedule = client.put(
            f"/api/v1/owner/employees/{employee['id']}/schedule",
            headers=owner,
            json={
                "schedules": [
                    {
                        "weekday": date.today().weekday(),
                        "start_time": "09:00",
                        "end_time": "18:00",
                        "grace_minutes": 5,
                    }
                ]
            },
        )
        assert schedule.status_code == 200
        edge_headers = {
            "X-Site-Id": device["site_id"],
            "X-Device-Id": device["device_id"],
            "X-Device-Token": device["device_token"],
        }
        config = client.get("/api/v1/edge/config", headers=edge_headers).json()
        serialized = str(config)
        assert employee["id"] in serialized
        assert "embedding" not in serialized.lower()
        assert "face_image" not in serialized.lower()

        csv_response = client.get("/api/v1/owner/attendance.csv", headers=owner)
        assert csv_response.status_code == 200
        assert csv_response.headers["content-type"].startswith("text/csv")
        assert "xodim_id" in csv_response.text


def test_employee_snapshot_upload_is_rejected(tmp_path: Path, monkeypatch) -> None:
    import cloud.main as main

    monkeypatch.setenv("CHAQIMCHI_CLOUD_ADMIN_KEY", "test-admin")
    monkeypatch.setenv("CHAQIMCHI_OWNER_JWT_SECRET", "owner-secret-with-more-than-32-characters")
    monkeypatch.setenv("CHAQIMCHI_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "cloud.db")
    monkeypatch.setattr(main, "_store", None)
    monkeypatch.setattr(main, "_event_store", None)
    monkeypatch.setattr(main, "_event_store_key", None)
    with TestClient(main.app) as client:
        site = client.post(
            "/api/v1/admin/sites",
            headers={"X-Cloud-Admin-Key": "test-admin"},
            json={"name": "Do'kon", "plan": "lite"},
        ).json()
        device = client.post(
            "/api/v1/sotqin/claim", json={"pairing_code": site["pairing_code"]}
        ).json()
        headers = {
            "X-Site-Id": device["site_id"],
            "X-Device-Id": device["device_id"],
            "X-Device-Token": device["device_token"],
        }
        client.post(
            "/api/v1/edge/events/batch",
            headers=headers,
            json={
                "events": [
                    {
                        "event_id": "employee-private",
                        "event_type": "employee_seen",
                        "camera_id": "camera-01",
                        "person_id": "unknown",
                    }
                ]
            },
        )
        response = client.put(
            "/api/v1/edge/events/employee-private/snapshot",
            headers={**headers, "Content-Type": "image/jpeg"},
            content=b"private-face",
        )
        assert response.status_code == 403
        clip_response = client.put(
            "/api/v1/edge/events/employee-private/clip",
            headers={**headers, "Content-Type": "video/mp4"},
            content=b"private-video",
        )
        assert clip_response.status_code == 403
