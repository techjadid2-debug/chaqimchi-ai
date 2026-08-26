"""Do'kon egasi kamerani o'zi qo'shadi.

Ilgari RTSP manzilini faqat admin va usta kirita olardi. Windows yo'li
o'z-o'ziga xizmat bo'lgach, egasi ham o'z kamerasini ulay olishi kerak —
lekin chegaralar (tarif, shifrlash, rol) usta yo'lidagi bilan bir xil
qat'iy qolishi shart.

Bu fayl shu tenglikni va parolning brauzerga chiqmasligini qulflaydi.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SECRET = "MaxfiyParol123"
RTSP = f"rtsp://admin:{SECRET}@192.168.1.64:554/Streaming/Channels/102"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("CHAQIMCHI_CLOUD_ADMIN_KEY", "test-admin")
    monkeypatch.setenv("CHAQIMCHI_OWNER_JWT_SECRET", "o" * 64)
    monkeypatch.setenv("CHAQIMCHI_PORTAL_JWT_SECRET", "p" * 64)
    monkeypatch.setenv("CHAQIMCHI_PUBLIC_URL", "https://chaqimchi.test")
    monkeypatch.setattr("cloud.main.DB_PATH", tmp_path / "cloud.db")
    monkeypatch.setattr("cloud.main._store", None)
    monkeypatch.setattr("cloud.main._event_store", None)
    monkeypatch.setattr("cloud.main._event_store_key", None)
    from cloud.main import app

    return TestClient(app)


@pytest.fixture
def shop(client: TestClient) -> dict:
    trial = client.post(
        "/api/v1/public/quick-trial",
        json={
            "phone": "+998 90 123 45 67",
            "full_name": "Ega Egayev",
            "company": "Namuna do'kon",
            "username": "dokonchi",
            "password": "parol12345",
            "consent": True,
            "plan": "biznes",
        },
    ).json()
    login = client.post(
        "/api/v1/auth/login", json={"username": "dokonchi", "password": "parol12345"}
    ).json()
    claimed = client.post(
        "/api/v1/devices/claim",
        json={"pairing_code": trial["pairing_code"], "label": "KASSA-PC"},
    ).json()
    return {
        "site_id": trial["site_id"],
        "owner": {"Authorization": f"Bearer {login['access_token']}"},
        "device": {
            "X-Site-Id": claimed["site_id"],
            "X-Device-Id": claimed["device_id"],
            "X-Device-Token": claimed["device_token"],
        },
    }


def scan_with_result(client: TestClient, shop: dict, streams: list) -> str:
    """Skaner topgan oqimlarni tayyorlab, `job_id` qaytaradi."""
    client.post("/api/v1/owner/scan", headers=shop["owner"], json={"kind": "onvif"})
    beat = client.post("/api/v1/edge/heartbeat", headers=shop["device"], json={}).json()
    job_id = beat["job_requested"][0]["job_id"]
    client.put(
        f"/api/v1/edge/jobs/{job_id}/result",
        headers=shop["device"],
        json={"ok": True, "result": {"streams": streams}},
    )
    return job_id


# ── Qo'lda kiritish ─────────────────────────────────────────────────


def test_the_owner_can_add_a_camera_and_the_device_learns_about_it(
    client: TestClient, shop: dict
) -> None:
    saved = client.put(
        "/api/v1/owner/cameras/camera-01",
        headers=shop["owner"],
        json={"label": "Kirish eshigi", "rtsp_url": RTSP, "enabled": True},
    )

    assert saved.status_code == 200, saved.text
    assert saved.json()["config_revision"] > 0
    # Manzil javobda qaytmaydi.
    assert SECRET not in saved.text

    # Qurilma to'liq manzilni oladi — u NVR bilan gaplashishi kerak.
    config = client.get("/api/v1/edge/config", headers=shop["device"]).json()
    assert config["cameras"][0]["source"] == RTSP


def test_the_password_is_encrypted_at_rest(client: TestClient, shop: dict, tmp_path: Path) -> None:
    """Bazani o'qigan odam NVR parolini ko'rmasin."""
    client.put(
        "/api/v1/owner/cameras/camera-01",
        headers=shop["owner"],
        json={"label": "Kirish", "rtsp_url": RTSP, "enabled": True},
    )

    raw = (tmp_path / "cloud.db").read_bytes()

    assert SECRET.encode() not in raw
    assert b"192.168.1.64" not in raw


def test_the_plan_camera_cap_still_applies(client: TestClient, shop: dict) -> None:
    """Chegara serverda — u yagona haqiqiy nazorat nuqtasi."""
    from cloud.main import get_store

    allowed = get_store().site_detail(shop["site_id"])["limits"]["max_cameras"]
    for index in range(1, allowed + 1):
        ok = client.put(
            f"/api/v1/owner/cameras/camera-{index:02d}",
            headers=shop["owner"],
            json={"label": f"Kamera {index}", "rtsp_url": RTSP, "enabled": True},
        )
        assert ok.status_code == 200, ok.text

    too_many = client.put(
        f"/api/v1/owner/cameras/camera-{allowed + 1:02d}",
        headers=shop["owner"],
        json={"label": "Ortiqcha", "rtsp_url": RTSP, "enabled": True},
    )

    assert too_many.status_code == 422


def test_a_plain_http_address_is_refused(client: TestClient, shop: dict) -> None:
    bad = client.put(
        "/api/v1/owner/cameras/camera-01",
        headers=shop["owner"],
        json={"label": "Kirish", "rtsp_url": "http://192.168.1.64/stream", "enabled": True},
    )

    assert bad.status_code == 422


# ── Skaner natijasidan saqlash ──────────────────────────────────────


def test_saving_from_a_scan_never_sends_the_password_to_the_browser(
    client: TestClient, shop: dict
) -> None:
    """Panel faqat INDEKS yuboradi; manzilni server o'zi oladi."""
    job_id = scan_with_result(
        client, shop, [{"name": "Sub", "uri": RTSP, "encoding": "H264"}]
    )

    # Panel ko'rgan narsa — parolsiz.
    listing = client.get(f"/api/v1/owner/scan/{job_id}", headers=shop["owner"])
    assert SECRET not in listing.text

    saved = client.post(
        "/api/v1/owner/cameras/from-scan",
        headers=shop["owner"],
        json={"job_id": job_id, "stream_ref": 0, "label": "Kassa zonasi"},
    )

    assert saved.status_code == 200, saved.text
    assert SECRET not in saved.text
    config = client.get("/api/v1/edge/config", headers=shop["device"]).json()
    assert config["cameras"][0]["source"] == RTSP
    assert config["cameras"][0]["label"] == "Kassa zonasi"


def test_the_first_free_slot_is_chosen_automatically(client: TestClient, shop: dict) -> None:
    """Egasi "camera-03" kabi ichki nomlar bilan ovora bo'lmasin."""
    job_id = scan_with_result(client, shop, [{"uri": RTSP}, {"uri": RTSP.replace("102", "202")}])

    first = client.post(
        "/api/v1/owner/cameras/from-scan",
        headers=shop["owner"],
        json={"job_id": job_id, "stream_ref": 0, "label": "Birinchi"},
    ).json()
    second = client.post(
        "/api/v1/owner/cameras/from-scan",
        headers=shop["owner"],
        json={"job_id": job_id, "stream_ref": 1, "label": "Ikkinchi"},
    ).json()

    assert first["camera"]["camera_id"] == "camera-01"
    assert second["camera"]["camera_id"] == "camera-02"


def test_a_stale_scan_reference_is_refused(client: TestClient, shop: dict) -> None:
    job_id = scan_with_result(client, shop, [{"uri": RTSP}])

    missing = client.post(
        "/api/v1/owner/cameras/from-scan",
        headers=shop["owner"],
        json={"job_id": job_id, "stream_ref": 7, "label": "Yo'q oqim"},
    )

    assert missing.status_code == 422
    assert "qaytadan" in missing.json()["detail"]


def test_another_shops_scan_is_invisible(client: TestClient, shop: dict) -> None:
    job_id = scan_with_result(client, shop, [{"uri": RTSP}])
    client.post(
        "/api/v1/public/quick-trial",
        json={
            "phone": "+998 90 000 00 00",
            "full_name": "Begona Odam",
            "company": "Boshqa do'kon",
            "username": "begona",
            "password": "parol12345",
            "consent": True,
        },
    )
    stranger = client.post(
        "/api/v1/auth/login", json={"username": "begona", "password": "parol12345"}
    ).json()

    stolen = client.post(
        "/api/v1/owner/cameras/from-scan",
        headers={"Authorization": f"Bearer {stranger['access_token']}"},
        json={"job_id": job_id, "stream_ref": 0, "label": "O'g'irlangan"},
    )

    assert stolen.status_code == 404


# ── O'chirish va rollar ─────────────────────────────────────────────


def test_deleting_a_camera_bumps_the_revision(client: TestClient, shop: dict) -> None:
    saved = client.put(
        "/api/v1/owner/cameras/camera-01",
        headers=shop["owner"],
        json={"label": "Kirish", "rtsp_url": RTSP, "enabled": True},
    ).json()

    removed = client.delete("/api/v1/owner/cameras/camera-01", headers=shop["owner"])

    assert removed.status_code == 200
    assert removed.json()["config_revision"] > saved["config_revision"]
    assert client.get("/api/v1/owner/cameras", headers=shop["owner"]).json()["cameras"] == []


def test_a_manager_cannot_change_cameras(client: TestClient, shop: dict) -> None:
    """Kamera ulash do'kon uskunasiga tegadi — bu egasining ishi."""
    from cloud.main import get_event_store
    from cloud.owner_auth import issue_owner_token

    member = get_event_store().add_member(
        shop["site_id"], "777", role="manager", display_name="Menejer"
    )
    headers = {"Authorization": f"Bearer {issue_owner_token(member)}"}

    refused = client.put(
        "/api/v1/owner/cameras/camera-01",
        headers=headers,
        json={"label": "Kirish", "rtsp_url": RTSP, "enabled": True},
    )

    assert refused.status_code == 403


# ── Jonli ko'rish: yoqish, ushlab turish, to'xtatish ─────────────────
#
# Server so'rovni 90 soniyaga yozadi va `store.request_live` izohi
# "panel har 60 soniyada qayta chaqiradi" deb va'da qiladi — lekin panel
# buni HECH QACHON qilmasdi.  90 soniyadan keyin qurilma kadr yuborishni
# to'xtatardi, panel esa eski kadrni ko'rsatib, yonida o'z soatini
# tikillatib turardi: ega 5 daqiqa oldingi rasmni "jonli" deb ko'rardi.


def test_live_view_can_be_extended_and_stopped(client: TestClient, shop: dict) -> None:
    """Muddat uzayadi, to'xtatish esa DARHOL ishlaydi."""
    client.put(
        "/api/v1/owner/cameras/camera-01",
        headers=shop["owner"],
        json={"label": "Kirish", "rtsp_url": RTSP, "enabled": True},
    )

    first = client.post(
        "/api/v1/owner/cameras/camera-01/live", headers=shop["owner"], json={"overlay": True}
    )
    assert first.status_code == 200, first.text
    assert first.json()["until"], "muddat qaytsin"

    # Qurilma so'rovni heartbeat javobida ko'radi (config revizyasi
    # orqali EMAS: revizya o'zgarsa zanjir qayta ishga tushardi).
    beat = client.post("/api/v1/edge/heartbeat", headers=shop["device"], json={}).json()
    assert any(item["camera_id"] == "camera-01" for item in beat.get("live_requested") or [])

    # Panel yopilganda oqim TO'XTAYDI: aks holda qurilma yana 90
    # soniya kadr yuborib, kunlik byudjetni bekorga yeydi.
    stopped = client.post(
        "/api/v1/owner/cameras/camera-01/live", headers=shop["owner"], json={"stop": True}
    )
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["until"] is None

    after = client.post("/api/v1/edge/heartbeat", headers=shop["device"], json={}).json()
    assert not [
        item for item in (after.get("live_requested") or []) if item["camera_id"] == "camera-01"
    ], "to'xtatilgandan keyin qurilma kadr yubormasin"


def test_the_frame_carries_its_own_timestamp(client: TestClient, shop: dict) -> None:
    """Kadr sanasi javobda bo'lsin — panel klient soatiga ishonmasin.

    Usiz muzlagan rasm ustida soat tikillab turardi: server oxirgi
    saqlangan kadrni qaytaraveradi va panel har javobda vaqtni
    yangilardi.
    """
    client.put(
        "/api/v1/owner/cameras/camera-01",
        headers=shop["owner"],
        json={"label": "Kirish", "rtsp_url": RTSP, "enabled": True},
    )
    client.post("/api/v1/owner/cameras/camera-01/live", headers=shop["owner"], json={})

    uploaded = client.put(
        "/api/v1/edge/cameras/camera-01/live-frame",
        headers={**shop["device"], "Content-Type": "image/jpeg"},
        content=b"\xff\xd8\xff\xe0jonli-kadr",
    )
    assert uploaded.status_code == 200, uploaded.text

    frame = client.get("/api/v1/owner/cameras/camera-01/live-frame", headers=shop["owner"])
    assert frame.status_code == 200, frame.text
    assert frame.headers.get("X-Frame-At"), "kadr sanasi sarlavhada bo'lsin"
