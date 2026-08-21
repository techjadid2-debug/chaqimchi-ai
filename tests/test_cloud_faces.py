"""Yuz tanish (davomat, yopiq pilot): enrollment, moslash, galereya, retensiya.

Haqiqiy ONNX modellar testda ishlatilmaydi (og'ir) — `FakeFaceService`
oldindan kelishilgan vektorlar qaytaradi.  Modelning o'zi alohida qo'lda
tekshirilgan (bir odamning 2 rasmi kosinus 0.73, logotipda yuz yo'q).
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import numpy as np
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from cloud import faces
from cloud.snapshots import LocalSnapshotStore

ADMIN = {"X-Cloud-Admin-Key": "test-admin"}

#: "Rasm" baytlari → qaytariladigan vektor burchagi.  Bir xil odamning
#: rasmlari bir tomonga qaraydi.
KNOWN_FACES = {
    b"rasm-ali-1": 0.0,
    b"rasm-ali-2": 0.1,  # Ali bilan kosinus ~0.995
    b"rasm-vali-1": 1.4,  # Ali bilan kosinus ~0.17 — chegaradan past
    b"kadr-ali": 0.05,
    b"kadr-begona": 2.8,
}


def vector(angle: float) -> np.ndarray:
    # O'lcham haqiqiy modelniki bilan bir xil: moslash endi
    # `embedding_dim` ni tekshiradi va mos kelmagan yozuvni chetlab
    # o'tadi.  Dublyor 512 qoldirilsa test yashil bo'lardi-yu,
    # production'dagi filtrni umuman sinamas edi.
    out = np.zeros(faces.EMBEDDING_DIM, dtype=np.float32)
    out[0] = np.cos(angle)
    out[1] = np.sin(angle)
    return out


class FakeFaceService:
    embedding_dim = faces.EMBEDDING_DIM

    def embed_jpeg(self, data: bytes):
        angle = KNOWN_FACES.get(bytes(data))
        if angle is None:
            return None
        return faces.FaceEmbedding(vector=vector(angle), det_score=0.9)

    match = staticmethod(faces.FaceService.match)


@pytest.fixture
def pilot_client(tmp_path: Path, monkeypatch):
    import cloud.main as main

    monkeypatch.setenv("CHAQIMCHI_CLOUD_ADMIN_KEY", "test-admin")
    monkeypatch.setenv("CHAQIMCHI_OWNER_JWT_SECRET", "owner-secret-with-more-than-32-characters")
    monkeypatch.setenv("CHAQIMCHI_ENV", "test")
    monkeypatch.setenv("CHAQIMCHI_ATTENDANCE_PILOT", "1")
    monkeypatch.setenv("CHAQIMCHI_OTP_TEST_CODE", "123456")
    monkeypatch.setenv("CHAQIMCHI_EMBEDDING_KEY", Fernet.generate_key().decode())
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("CHAQIMCHI_S3_ENDPOINT", raising=False)
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "cloud.db")
    monkeypatch.setattr(main, "_store", None)
    monkeypatch.setattr(main, "_event_store", None)
    monkeypatch.setattr(main, "_event_store_key", None)
    monkeypatch.setattr(main, "_snapshots", LocalSnapshotStore(tmp_path / "snapshots"))
    monkeypatch.setattr(faces, "_service", FakeFaceService())
    monkeypatch.setattr(faces, "available", lambda: (True, "test"))
    with TestClient(main.app) as client:
        yield client


def _site_with_device(client: TestClient):
    site = client.post(
        "/api/v1/admin/sites",
        headers=ADMIN,
        json={"name": "Yuz-1", "plan": "lite"},
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


def _employee(client: TestClient, site_id: str, name: str = "Ali") -> dict:
    response = client.post(
        f"/api/v1/admin/sites/{site_id}/employees",
        headers=ADMIN,
        json={"name": name, "consent": True, "consent_note": "test"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _upload_photo(client: TestClient, site_id: str, employee_id: str, data: bytes):
    return client.post(
        f"/api/v1/admin/sites/{site_id}/faces/employees/{employee_id}/photos",
        headers={**ADMIN, "Content-Type": "image/jpeg"},
        content=data,
    )


def _send_face_capture(client: TestClient, headers: dict, event_id: str, data: bytes):
    batch = client.post(
        "/api/v1/edge/events/batch",
        headers=headers,
        json={
            "events": [
                {
                    "event_id": event_id,
                    "event_type": "face_captured",
                    "camera_id": "camera-01",
                    "severity": "info",
                    "track_id": 42,
                    "has_snapshot": True,
                }
            ]
        },
    )
    assert batch.status_code == 200, batch.text
    upload = client.put(
        f"/api/v1/edge/events/{event_id}/snapshot",
        headers={**headers, "Content-Type": "image/jpeg"},
        content=data,
    )
    return upload


# ── Enrollment ───────────────────────────────────────────────────────────


def test_photo_upload_enrolls_the_employee(pilot_client) -> None:
    site, _headers = _site_with_device(pilot_client)
    employee = _employee(pilot_client, site["site_id"])

    response = _upload_photo(pilot_client, site["site_id"], employee["id"], b"rasm-ali-1")

    assert response.status_code == 200
    listing = pilot_client.get(f"/api/v1/admin/sites/{site['site_id']}/faces", headers=ADMIN).json()
    target = next(e for e in listing["employees"] if e["id"] == employee["id"])
    assert target["enrollment_status"] == "enrolled"
    assert len(target["photos"]) == 1


def test_embeddings_are_never_stored_in_plaintext(pilot_client, tmp_path: Path) -> None:
    """Baza fayli o'g'irlansa ham yuz vektori o'qilmasin."""
    import cloud.main as main

    site, _headers = _site_with_device(pilot_client)
    employee = _employee(pilot_client, site["site_id"])
    _upload_photo(pilot_client, site["site_id"], employee["id"], b"rasm-ali-1")

    rows = main.get_event_store().face_embeddings(site["site_id"])
    assert len(rows) == 1
    encrypted = rows[0]["embedding_b64"]
    plain = vector(0.0)
    decrypted = faces.decrypt_embedding(encrypted)
    assert float(np.dot(decrypted, plain)) > 0.999
    # Shifrlangan matn ichida vektor baytlari ochiq yotmaydi.
    assert plain.tobytes() not in encrypted.encode("ascii")


def test_a_photo_without_a_face_is_rejected(pilot_client) -> None:
    site, _headers = _site_with_device(pilot_client)
    employee = _employee(pilot_client, site["site_id"])

    response = _upload_photo(pilot_client, site["site_id"], employee["id"], b"yuzsiz-rasm")

    assert response.status_code == 422
    assert "yuz topilmadi" in response.json()["detail"].lower()


def test_photo_limit_is_three(pilot_client) -> None:
    site, _headers = _site_with_device(pilot_client)
    employee = _employee(pilot_client, site["site_id"])
    for _ in range(3):
        assert (
            _upload_photo(pilot_client, site["site_id"], employee["id"], b"rasm-ali-1").status_code
            == 200
        )

    assert (
        _upload_photo(pilot_client, site["site_id"], employee["id"], b"rasm-ali-1").status_code
        == 422
    )


def test_deleting_the_last_photo_resets_enrollment(pilot_client) -> None:
    site, _headers = _site_with_device(pilot_client)
    employee = _employee(pilot_client, site["site_id"])
    _upload_photo(pilot_client, site["site_id"], employee["id"], b"rasm-ali-1")
    listing = pilot_client.get(f"/api/v1/admin/sites/{site['site_id']}/faces", headers=ADMIN).json()
    photo_id = next(e for e in listing["employees"] if e["id"] == employee["id"])["photos"][0]["id"]

    assert (
        pilot_client.delete(
            f"/api/v1/admin/sites/{site['site_id']}/faces/photos/{photo_id}", headers=ADMIN
        ).status_code
        == 200
    )

    listing = pilot_client.get(f"/api/v1/admin/sites/{site['site_id']}/faces", headers=ADMIN).json()
    target = next(e for e in listing["employees"] if e["id"] == employee["id"])
    assert target["enrollment_status"] == "pending" and target["photos"] == []


def test_photo_image_requires_admin_auth(pilot_client) -> None:
    site, _headers = _site_with_device(pilot_client)
    employee = _employee(pilot_client, site["site_id"])
    _upload_photo(pilot_client, site["site_id"], employee["id"], b"rasm-ali-1")
    listing = pilot_client.get(f"/api/v1/admin/sites/{site['site_id']}/faces", headers=ADMIN).json()
    photo_id = next(e for e in listing["employees"] if e["id"] == employee["id"])["photos"][0]["id"]
    url = f"/api/v1/admin/sites/{site['site_id']}/faces/photos/{photo_id}/image"

    assert pilot_client.get(url).status_code == 401
    ok = pilot_client.get(url, headers=ADMIN)
    assert ok.status_code == 200
    assert ok.content == b"rasm-ali-1"


# ── face_captured oqimi ──────────────────────────────────────────────────


def test_matched_capture_creates_employee_seen_and_attendance(pilot_client) -> None:
    """Butun zanjir: kadr → moslash → employee_seen → davomat hisoboti."""
    import cloud.main as main

    site, headers = _site_with_device(pilot_client)
    employee = _employee(pilot_client, site["site_id"])
    _upload_photo(pilot_client, site["site_id"], employee["id"], b"rasm-ali-1")
    config = main.get_event_store().get_site_config(site["site_id"])["config"]
    config["attendance_camera_ids"] = ["camera-01"]
    main.get_event_store().update_site_config(site["site_id"], config)

    assert _send_face_capture(pilot_client, headers, "evt-face-1", b"kadr-ali").status_code == 200

    events = pilot_client.get(
        f"/api/v1/admin/sites/{site['site_id']}/faces/events", headers=ADMIN
    ).json()["events"]
    assert len(events) == 1
    assert events[0]["person_id"] == employee["id"]
    assert events[0]["person_name"] == "Ali", "ism serverda employees'dan olinsin"
    assert events[0]["score"] and events[0]["score"] > 0.9

    seen = main.get_event_store().list_events(site["site_id"], event_type="employee_seen", limit=10)
    assert len(seen) == 1 and seen[0]["person_id"] == employee["id"]
    assert seen[0]["track_id"] == 42, "demografiya xodim chiqarishi trek orqali ishlaydi"


def test_unknown_face_stays_in_the_gallery_without_attendance(pilot_client) -> None:
    import cloud.main as main

    site, headers = _site_with_device(pilot_client)
    employee = _employee(pilot_client, site["site_id"])
    _upload_photo(pilot_client, site["site_id"], employee["id"], b"rasm-ali-1")

    _send_face_capture(pilot_client, headers, "evt-face-2", b"kadr-begona")

    events = pilot_client.get(
        f"/api/v1/admin/sites/{site['site_id']}/faces/events", headers=ADMIN
    ).json()["events"]
    assert events[0]["person_id"] is None, "notanish — hech kimga yozilmasin"
    assert (
        main.get_event_store().list_events(site["site_id"], event_type="employee_seen", limit=10)
        == []
    )


def test_capture_image_is_served_and_scoped_to_the_site(pilot_client) -> None:
    site, headers = _site_with_device(pilot_client)
    _send_face_capture(pilot_client, headers, "evt-face-3", b"kadr-begona")

    url = f"/api/v1/admin/sites/{site['site_id']}/faces/events/evt-face-3/image"
    assert pilot_client.get(url, headers=ADMIN).status_code == 200

    other = pilot_client.post(
        "/api/v1/admin/sites", headers=ADMIN, json={"name": "Boshqa", "plan": "lite"}
    ).json()
    stranger = f"/api/v1/admin/sites/{other['site_id']}/faces/events/evt-face-3/image"
    assert pilot_client.get(stranger, headers=ADMIN).status_code == 404


def test_employee_seen_media_upload_is_still_rejected(pilot_client) -> None:
    """Natija hodisasi media'siz — rasm faqat face_captured'da."""
    site, headers = _site_with_device(pilot_client)
    batch = pilot_client.post(
        "/api/v1/edge/events/batch",
        headers=headers,
        json={
            "events": [
                {
                    "event_id": "evt-seen-1",
                    "event_type": "employee_seen",
                    "camera_id": "camera-01",
                    "severity": "info",
                    "has_snapshot": True,
                }
            ]
        },
    )
    assert batch.status_code == 200
    response = pilot_client.put(
        "/api/v1/edge/events/evt-seen-1/snapshot",
        headers={**headers, "Content-Type": "image/jpeg"},
        content=b"kadr-ali",
    )
    assert response.status_code == 403


def test_gate_closes_when_the_models_are_not_commercially_licensed(
    pilot_client, monkeypatch
) -> None:
    """Litsenziyasiz model bilan davomat umuman ishlamasin.

    Bu darvoza `buffalo_l` (tadqiqot litsenziyasi) sababli qurilgan edi.
    Modellar Apache-2.0 ga o'tkazilgach u ochildi — lekin MEXANIZM
    qolishi kerak: kelajakda litsenziyasi noaniq model qaytib kelsa,
    xizmat o'zi yopilsin va bu sozlamaga bog'liq bo'lmasin.
    """
    site, headers = _site_with_device(pilot_client)
    monkeypatch.setenv("CHAQIMCHI_ENV", "production")
    monkeypatch.delenv("CHAQIMCHI_ATTENDANCE_PILOT", raising=False)
    monkeypatch.setattr(faces, "MODELS_LICENSED_FOR_COMMERCIAL_USE", False)

    assert (
        pilot_client.get(f"/api/v1/admin/sites/{site['site_id']}/faces", headers=ADMIN).status_code
        == 403
    )
    assert _send_face_capture(pilot_client, headers, "evt-face-4", b"kadr-ali").status_code == 403


def test_apache_models_open_attendance_in_production(pilot_client, monkeypatch) -> None:
    """Litsenziya hal bo'lgach davomat production'da ham ishlaydi.

    Bungacha `CHAQIMCHI_FACE_MODEL_LICENSED` env bayrog'i kerak edi —
    ya'ni huquqiy tekshiruv sozlamaga bog'liq edi va uni noto'g'ri
    qo'yish tadqiqot modelini "tijoriy" qilib ko'rsatib qo'yardi.
    """
    site, _headers = _site_with_device(pilot_client)
    monkeypatch.setenv("CHAQIMCHI_ENV", "production")
    monkeypatch.delenv("CHAQIMCHI_ATTENDANCE_PILOT", raising=False)

    response = pilot_client.get(f"/api/v1/admin/sites/{site['site_id']}/faces", headers=ADMIN)
    assert response.status_code == 200


# ── Mijoz paneli (faqat o'qish) ──────────────────────────────────────────


def _owner_headers(client: TestClient, site_id: str) -> dict:
    client.post(
        f"/api/v1/admin/sites/{site_id}/members",
        headers=ADMIN,
        json={"telegram_id": "505", "role": "owner"},
    )
    client.post("/api/v1/owner/auth/request", json={"telegram_id": "505"})
    verified = client.post(
        "/api/v1/owner/auth/verify",
        json={"telegram_id": "505", "site_id": site_id, "code": "123456"},
    )
    return {"Authorization": f"Bearer {verified.json()['access_token']}"}


def test_owner_sees_employees_gallery_and_images(pilot_client) -> None:
    site, headers = _site_with_device(pilot_client)
    employee = _employee(pilot_client, site["site_id"])
    _upload_photo(pilot_client, site["site_id"], employee["id"], b"rasm-ali-1")
    _send_face_capture(pilot_client, headers, "evt-face-owner", b"kadr-ali")
    owner = _owner_headers(pilot_client, site["site_id"])

    listing = pilot_client.get("/api/v1/owner/faces", headers=owner)
    assert listing.status_code == 200
    assert listing.json()["employees"][0]["photos"], "xodim rasmi ko'rinsin"
    photo_id = listing.json()["employees"][0]["photos"][0]["id"]

    events = pilot_client.get("/api/v1/owner/faces/events", headers=owner).json()["events"]
    assert events and events[0]["person_name"] == "Ali"

    assert (
        pilot_client.get(f"/api/v1/owner/faces/photos/{photo_id}/image", headers=owner).status_code
        == 200
    )
    assert (
        pilot_client.get(
            "/api/v1/owner/faces/events/evt-face-owner/image", headers=owner
        ).status_code
        == 200
    )


# ── Mijoz o'zi rasm qo'shadi ────────────────────────────────────────────
#
# Ilgari rasm yuklash faqat admin panelda edi ("rozilikni kim olganini
# bitta qo'lda ushlab turish uchun").  Amalda bu har bir xodim uchun
# do'kon egasi operatorga murojaat qilishi kerak degani edi — ya'ni
# funksiya ishlamasdi.


def _owner_upload(client, owner: dict, employee_id: str, data: bytes, content_type="image/jpeg"):
    return client.post(
        f"/api/v1/owner/faces/employees/{employee_id}/photos",
        headers={**owner, "Content-Type": content_type},
        content=data,
    )


def test_the_customer_can_enroll_an_employee_from_their_own_panel(pilot_client) -> None:
    site, _headers = _site_with_device(pilot_client)
    employee = _employee(pilot_client, site["site_id"])
    owner = _owner_headers(pilot_client, site["site_id"])

    response = _owner_upload(pilot_client, owner, employee["id"], b"rasm-ali-1")

    assert response.status_code == 200, response.text
    listing = pilot_client.get("/api/v1/owner/faces", headers=owner).json()
    assert listing["employees"][0]["photos"], "rasm ro'yxatda ko'rinsin"
    assert listing["employees"][0]["enrollment_status"] == "enrolled"


def test_the_customer_cannot_touch_another_shops_employee(pilot_client) -> None:
    """`employee_id` havolada keladi — boshqa do'konning xodimiga rasm
    yuklab bo'lmasligi shu yerda qulflanadi."""
    first, _ = _site_with_device(pilot_client)
    second = pilot_client.post(
        "/api/v1/admin/sites", headers=ADMIN, json={"name": "Begona", "plan": "lite"}
    ).json()
    stranger = _employee(pilot_client, second["site_id"], name="Begona xodim")
    owner = _owner_headers(pilot_client, first["site_id"])

    response = _owner_upload(pilot_client, owner, stranger["id"], b"rasm-ali-1")

    assert response.status_code == 404


def test_a_photo_without_a_face_is_refused_with_a_readable_reason(pilot_client) -> None:
    site, _ = _site_with_device(pilot_client)
    employee = _employee(pilot_client, site["site_id"])
    owner = _owner_headers(pilot_client, site["site_id"])

    response = _owner_upload(pilot_client, owner, employee["id"], b"logotip")

    assert response.status_code == 422
    assert "yuz topilmadi" in response.json()["detail"]


def test_only_images_are_accepted(pilot_client) -> None:
    """Boshqa turdagi fayl bekorga CPU yemasin (har rasm ~0.5 s)."""
    site, _ = _site_with_device(pilot_client)
    employee = _employee(pilot_client, site["site_id"])
    owner = _owner_headers(pilot_client, site["site_id"])

    response = _owner_upload(
        pilot_client, owner, employee["id"], b"rasm-ali-1", content_type="application/pdf"
    )

    assert response.status_code == 415


def test_the_customer_can_delete_a_photo(pilot_client) -> None:
    site, _ = _site_with_device(pilot_client)
    employee = _employee(pilot_client, site["site_id"])
    owner = _owner_headers(pilot_client, site["site_id"])
    photo = _owner_upload(pilot_client, owner, employee["id"], b"rasm-ali-1").json()

    assert (
        pilot_client.delete(
            f"/api/v1/owner/faces/photos/{photo['id']}", headers=owner
        ).status_code
        == 200
    )
    listing = pilot_client.get("/api/v1/owner/faces", headers=owner).json()
    assert not listing["employees"][0]["photos"]
    assert listing["employees"][0]["enrollment_status"] == "pending", (
        "oxirgi rasm o'chsa xodim yana 'rasm kutilmoqda' bo'lsin"
    )


# ── Tarif chegarasi ─────────────────────────────────────────────────────


def test_lite_stops_at_ten_employees(pilot_client) -> None:
    """Chegara `plans.py` da yozilgan, lekin bungacha hech qayerda
    majburlanmasdi — faqat javoblarda qaytardi."""
    site, _ = _site_with_device(pilot_client)
    owner = _owner_headers(pilot_client, site["site_id"])

    codes = [
        pilot_client.post(
            "/api/v1/owner/employees",
            headers=owner,
            json={"name": f"Xodim {index}", "consent": True},
        ).status_code
        for index in range(11)
    ]

    assert codes.count(200) == 10, codes
    assert codes[-1] == 422
    detail = pilot_client.post(
        "/api/v1/owner/employees", headers=owner, json={"name": "Ortiqcha", "consent": True}
    ).json()["detail"]
    assert "10" in detail and "ro'yxatdan chiqaring" in detail


def test_a_removed_employee_frees_a_seat(pilot_client) -> None:
    site, _ = _site_with_device(pilot_client)
    owner = _owner_headers(pilot_client, site["site_id"])
    created = [
        pilot_client.post(
            "/api/v1/owner/employees",
            headers=owner,
            json={"name": f"Xodim {index}", "consent": True},
        ).json()
        for index in range(10)
    ]

    pilot_client.put(
        f"/api/v1/owner/employees/{created[0]['id']}", headers=owner, json={"active": False}
    )

    again = pilot_client.post(
        "/api/v1/owner/employees", headers=owner, json={"name": "Yangi", "consent": True}
    )
    assert again.status_code == 200, again.text


# ── Retensiya ────────────────────────────────────────────────────────────


def test_old_face_captures_are_deleted_entirely(pilot_client, monkeypatch) -> None:
    """Yuz kadri yozuvi bilan o'chadi; employee_seen statistikasi qoladi."""
    import cloud.main as main

    site, headers = _site_with_device(pilot_client)
    employee = _employee(pilot_client, site["site_id"])
    _upload_photo(pilot_client, site["site_id"], employee["id"], b"rasm-ali-1")
    _send_face_capture(pilot_client, headers, "evt-face-old", b"kadr-ali")

    store = main.get_event_store()
    old_stamp = (faces_now() - timedelta(days=20)).isoformat()
    with store._connect() as conn:
        conn.execute(
            store._sql("UPDATE production_events SET occurred_at=? WHERE event_id=?"),
            (old_stamp, "evt-face-old"),
        )

    main._purge_expired_events()

    assert store.list_face_events(site["site_id"]) == []
    seen = store.list_events(site["site_id"], event_type="employee_seen", limit=10)
    assert len(seen) == 1, "davomat statistikasi saqlanadi"


def test_deactivated_employee_faces_are_purged(pilot_client) -> None:
    """Xodim ketdi — biometrikasi ham ketadi (maintenance'da)."""
    import cloud.main as main

    site, _headers = _site_with_device(pilot_client)
    employee = _employee(pilot_client, site["site_id"])
    _upload_photo(pilot_client, site["site_id"], employee["id"], b"rasm-ali-1")
    main.get_event_store().update_employee(site["site_id"], employee["id"], active=False)

    main._purge_expired_events()

    assert main.get_event_store().list_employee_faces(site["site_id"]) == []


def faces_now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


# ── Tarif chegarasi ─────────────────────────────────────────────────────


def test_attendance_is_closed_on_the_entry_plan(pilot_client) -> None:
    """Boshlang'ich tarifida xodim davomati umuman yo'q.

    Chegara nol.  Bungacha `_check_employee_limit` "ko'pi bilan 0 ta
    xodim" deb javob berardi va mijoz kimnidir o'chirish kerak deb
    o'ylardi — holbuki tarifni ko'tarish kerak edi.
    """
    site = pilot_client.post(
        "/api/v1/admin/sites",
        headers=ADMIN,
        json={"name": "Kichik do'kon", "plan": "boshlangich"},
    ).json()
    owner = _owner_headers(pilot_client, site["site_id"])

    listing = pilot_client.get("/api/v1/owner/faces", headers=owner)
    assert listing.status_code == 200
    assert listing.json()["max_employees"] == 0

    response = pilot_client.post(
        "/api/v1/owner/employees",
        headers=owner,
        json={"name": "Ali", "consent": True},
    )
    assert response.status_code == 422
    assert "Biznes tarifidan" in response.json()["detail"]


def test_upgrading_the_plan_opens_attendance(pilot_client) -> None:
    site = pilot_client.post(
        "/api/v1/admin/sites",
        headers=ADMIN,
        json={"name": "O'sayotgan do'kon", "plan": "boshlangich"},
    ).json()
    owner = _owner_headers(pilot_client, site["site_id"])

    pilot_client.post(
        f"/api/v1/admin/sites/{site['site_id']}/plan", headers=ADMIN, json={"plan": "biznes"}
    )

    assert pilot_client.get("/api/v1/owner/faces", headers=owner).json()["max_employees"] == 10
    created = pilot_client.post(
        "/api/v1/owner/employees",
        headers=owner,
        json={"name": "Ali", "consent": True},
    )
    assert created.status_code == 200, created.text


# ── Model migratsiyasi ──────────────────────────────────────────────────


def test_old_arcface_embeddings_are_skipped_not_misread(pilot_client) -> None:
    """512 o'lchamli eski yozuv 256 o'lchamli vektor bilan taqqoslanmasin.

    Ikki xavf bor edi va ikkalasi ham jimgina: `np.dot` o'lchamlari
    mos kelmasa XATO ko'taradi (butun moslash to'xtaydi), kesib
    taqqoslash esa MA'NOSIZ raqam beradi (begona odam xodim deb
    tanilishi mumkin).
    """
    import numpy as np

    site, _headers = _site_with_device(pilot_client)
    employee = _employee(pilot_client, site["site_id"])
    _upload_photo(pilot_client, site["site_id"], employee["id"], b"rasm-ali-1")

    import cloud.main as main

    store = main.get_event_store()
    rows = store.all_employee_faces(site_id=site["site_id"])
    assert len(rows) == 1
    assert rows[0]["embedding_dim"] == faces.EMBEDDING_DIM

    # Eski modeldan qolgan yozuvni qo'lda yasaymiz.
    store.update_employee_face_embedding(
        rows[0]["id"],
        embedding_b64=faces.encrypt_embedding(np.zeros(512, dtype=np.float32)),
        embedding_dim=512,
    )

    # Moslash yiqilmaydi va yolg'on javob bermaydi.
    probe = vector(0.0)
    candidates = [
        (str(row["employee_id"]), faces.decrypt_embedding(row["embedding_b64"]))
        for row in store.face_embeddings(site["site_id"])
    ]
    assert faces.FaceService.match(probe, candidates) is None


def test_reembedding_restores_matching(pilot_client) -> None:
    """Rasm saqlanib turgani uchun xodimni qaytadan ro'yxatga olish shart emas."""
    import numpy as np

    site, _headers = _site_with_device(pilot_client)
    employee = _employee(pilot_client, site["site_id"])
    _upload_photo(pilot_client, site["site_id"], employee["id"], b"rasm-ali-1")

    import cloud.main as main

    store = main.get_event_store()
    face_id = store.all_employee_faces(site_id=site["site_id"])[0]["id"]
    store.update_employee_face_embedding(
        face_id,
        embedding_b64=faces.encrypt_embedding(np.zeros(512, dtype=np.float32)),
        embedding_dim=512,
    )

    # `reembed_faces.py` shu ikki qadamni bajaradi: rasmni o'qiydi,
    # yangi model bilan hisoblaydi, yozuvni YANGILAYDI (o'chirib qayta
    # qo'shmaydi — `photo_key` va `created_at` joyida qoladi).
    photo = store.all_employee_faces(site_id=site["site_id"])[0]
    fresh = faces.get_face_service().embed_jpeg(b"rasm-ali-1")
    store.update_employee_face_embedding(
        photo["id"],
        embedding_b64=faces.encrypt_embedding(fresh.vector),
        embedding_dim=int(fresh.vector.shape[0]),
    )

    candidates = [
        (str(row["employee_id"]), faces.decrypt_embedding(row["embedding_b64"]))
        for row in store.face_embeddings(site["site_id"])
        if int(row["embedding_dim"]) == faces.current_embedding_dim()
    ]
    matched = faces.FaceService.match(vector(0.05), candidates)
    assert matched is not None
    assert matched[0] == employee["id"]


def test_the_panel_learns_the_template_limit_and_quality(pilot_client) -> None:
    """Xodimga bir nechta shablon: panel chegarani OLDINDAN bilishi kerak.

    Server chegarani allaqachon majburlardi (`MAX_FACES_PER_EMPLOYEE`),
    lekin `GET /owner/faces` uni qaytarmasdi — panel to'rtinchi rasmni
    ham yuborardi va mijoz 422 xatosini ko'rardi.  Rasm sifati
    (`det_score`) ham bazada bor edi-yu, javobda tashlab yuborilardi:
    "nega tanimayapti" degan savolga javob yo'q edi.
    """
    site, _ = _site_with_device(pilot_client)
    employee = _employee(pilot_client, site["site_id"])
    owner = _owner_headers(pilot_client, site["site_id"])

    _owner_upload(pilot_client, owner, employee["id"], b"rasm-ali-1")

    listing = pilot_client.get("/api/v1/owner/faces", headers=owner).json()

    assert listing["max_photos"] >= 2, "shablon chegarasi panelga aytilsin"
    photo = listing["employees"][0]["photos"][0]
    assert "score" in photo, "rasm sifati ko'rinsin — xira shablonni almashtirish uchun"


def test_every_template_is_listed_not_just_the_first(pilot_client) -> None:
    """Ikkinchi va uchinchi shablon panelda KO'RINISHI kerak.

    Ilgari panel faqat `photos[0]` ni chizardi: qolganlarini na ko'rish,
    na o'chirish mumkin edi — mijoz "yana rasm qo'shdim, nega bittasi
    turibdi?" deb so'rardi.
    """
    site, _ = _site_with_device(pilot_client)
    employee = _employee(pilot_client, site["site_id"])
    owner = _owner_headers(pilot_client, site["site_id"])

    first = _owner_upload(pilot_client, owner, employee["id"], b"rasm-ali-1")
    second = _owner_upload(pilot_client, owner, employee["id"], b"rasm-ali-2")
    assert first.status_code == 200 and second.status_code == 200

    photos = pilot_client.get("/api/v1/owner/faces", headers=owner).json()["employees"][0]["photos"]

    assert len(photos) == 2
    assert len({item["id"] for item in photos}) == 2


def test_an_unknown_capture_can_become_a_template(pilot_client) -> None:
    """Do'kondagi haqiqiy kadr — eng yaxshi shablon.

    Panelda "tanilmagan kadr ko'p bo'lsa yana bitta rasm qo'shing" deb
    yozilardi, lekin buni qiladigan yo'l yo'q edi: mijoz telefondan
    qaytadan rasm olishga majbur bo'lardi.
    """
    site, headers = _site_with_device(pilot_client)
    employee = _employee(pilot_client, site["site_id"])
    owner = _owner_headers(pilot_client, site["site_id"])
    _owner_upload(pilot_client, owner, employee["id"], b"rasm-ali-1")
    _send_face_capture(pilot_client, headers, "evt-face-tpl", b"rasm-ali-2")

    response = pilot_client.post(
        f"/api/v1/owner/faces/employees/{employee['id']}/photos/from-event/evt-face-tpl",
        headers=owner,
    )

    assert response.status_code == 200, response.text
    photos = pilot_client.get("/api/v1/owner/faces", headers=owner).json()["employees"][0]["photos"]
    assert len(photos) == 2, "kadr yangi shablon bo'lib qo'shilsin"

    # Kadr endi "tanilgan" bo'lib ko'rinadi — galereyada yana notanish
    # bo'lib turishi mijozni chalg'itardi.
    events = pilot_client.get(
        f"/api/v1/admin/sites/{site['site_id']}/faces/events", headers=ADMIN
    ).json()["events"]
    assert events[0]["person_id"] == employee["id"]


def test_a_capture_from_another_shop_cannot_become_a_template(pilot_client) -> None:
    site, _headers = _site_with_device(pilot_client)
    employee = _employee(pilot_client, site["site_id"])
    owner = _owner_headers(pilot_client, site["site_id"])

    response = pilot_client.post(
        f"/api/v1/owner/faces/employees/{employee['id']}/photos/from-event/evt-yoq",
        headers=owner,
    )

    assert response.status_code == 404
