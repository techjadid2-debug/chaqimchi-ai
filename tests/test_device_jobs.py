"""Bulutdan buyurilgan, qurilmada bajariladigan topshiriqlar.

Kamera qidirish do'kon tarmog'idan bajarilishi shart: WS-Discovery
multicast, /24 sweep va xususiy IP ga SOAP.  Bulut sahifasi u yerga
kira olmaydi va kirmasligi ham kerak — lokal API ataylab faqat
`127.0.0.1` ni qabul qiladi.

Shuning uchun bulutdagi tugma BUYRUQ yozadi, qurilma esa uni heartbeat
javobida ko'rib bajaradi.  Bu fayl shu kanalning shartnomasini va —
eng muhimi — NVR parolining brauzerga chiqmasligini qulflaydi.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SECRET = "MaxfiyParol123"
RTSP_WITH_PASSWORD = f"rtsp://admin:{SECRET}@192.168.1.64:554/Streaming/Channels/102"


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
    """Ulangan do'kon: egasining tokeni va qurilma sarlavhalari."""
    trial = client.post(
        "/api/v1/public/quick-trial",
        json={
            "phone": "+998 90 123 45 67",
            "full_name": "Ega Egayev",
            "company": "Namuna do'kon",
            "username": "dokonchi",
            "password": "parol12345",
            "consent": True,
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


def beat(client: TestClient, shop: dict) -> dict:
    response = client.post("/api/v1/edge/heartbeat", headers=shop["device"], json={})
    assert response.status_code == 200, response.text
    return response.json()


# ── Buyruq yetkazish ────────────────────────────────────────────────


def test_the_owner_asks_and_the_device_is_told_exactly_once(
    client: TestClient, shop: dict
) -> None:
    """Ikkinchi heartbeat bir xil skanerni qayta ishga tushirmasin."""
    beat(client, shop)  # navbat bo'sh

    started = client.post(
        "/api/v1/owner/scan", headers=shop["owner"], json={"kind": "lan_scan"}
    )
    assert started.status_code == 200, started.text
    job_id = started.json()["job"]["job_id"]

    first = beat(client, shop)
    second = beat(client, shop)

    assert [job["job_id"] for job in first["job_requested"]] == [job_id]
    assert second["job_requested"] == []


def test_the_nvr_password_reaches_the_device_but_never_the_browser(
    client: TestClient, shop: dict
) -> None:
    """Parol qurilmaga kerak (u NVR bilan gaplashadi), egaga esa yo'q."""
    client.post(
        "/api/v1/owner/scan",
        headers=shop["owner"],
        json={"kind": "onvif", "host": "192.168.1.64", "username": "admin", "password": SECRET},
    )

    told = beat(client, shop)["job_requested"][0]
    assert told["params"]["password"] == SECRET

    job_id = told["job_id"]
    client.put(
        f"/api/v1/edge/jobs/{job_id}/result",
        headers=shop["device"],
        json={"ok": True, "result": {"streams": [{"name": "Sub", "uri": RTSP_WITH_PASSWORD}]}},
    )
    seen = client.get(f"/api/v1/owner/scan/{job_id}", headers=shop["owner"])

    assert seen.status_code == 200
    assert SECRET not in seen.text
    stream = seen.json()["job"]["result"]["streams"][0]
    assert stream["safe_url"] == "rtsp://…@192.168.1.64:554/Streaming/Channels/102"
    assert stream["stream_ref"] == 0
    assert "uri" not in stream


def test_progress_travels_outside_the_heartbeat(client: TestClient, shop: dict) -> None:
    """Skanerlash 90 soniyagacha cho'ziladi, heartbeat esa 25 da javob
    berishi kerak.  Bir halqada bo'lsa sayt "oflayn" ko'rinardi."""
    client.post("/api/v1/owner/scan", headers=shop["owner"], json={"kind": "lan_scan"})
    job_id = beat(client, shop)["job_requested"][0]["job_id"]

    reported = client.post(
        f"/api/v1/edge/jobs/{job_id}/progress",
        headers=shop["device"],
        json={"percent": 40, "note": "12 ta manzil tekshirildi"},
    )

    assert reported.status_code == 200
    job = client.get(f"/api/v1/owner/scan/{job_id}", headers=shop["owner"]).json()["job"]
    assert job["progress"] == 40
    assert job["note"] == "12 ta manzil tekshirildi"
    assert job["status"] == "running"


def test_one_scan_at_a_time_per_shop(client: TestClient, shop: dict) -> None:
    """Skanerlar ustma-ust chiqsa NVR ni so'rovlar bilan ko'madi."""
    first = client.post(
        "/api/v1/owner/scan", headers=shop["owner"], json={"kind": "lan_scan"}
    ).json()
    second = client.post(
        "/api/v1/owner/scan", headers=shop["owner"], json={"kind": "channels", "host": "1.2.3.4"}
    ).json()

    assert second["job"]["job_id"] == first["job"]["job_id"]
    assert second["job"]["reused"] is True


def test_an_offline_shop_gets_a_useful_answer_not_a_spinner(
    client: TestClient, shop: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cloud.main import get_store

    real = get_store().site_detail
    monkeypatch.setattr(
        type(get_store()),
        "site_detail",
        lambda self, site_id: {**real(site_id), "connection": "offline"},
    )

    refused = client.post(
        "/api/v1/owner/scan", headers=shop["owner"], json={"kind": "lan_scan"}
    )

    assert refused.status_code == 409
    assert "aloqada emas" in refused.json()["detail"]


# ── Sinov kadri ─────────────────────────────────────────────────────


def test_a_probe_refers_to_an_earlier_scan_never_a_raw_address(
    client: TestClient, shop: dict
) -> None:
    """Xom RTSP manzilini brauzerdan qabul qilmaymiz — unda parol bor."""
    refused = client.post(
        "/api/v1/owner/scan", headers=shop["owner"], json={"kind": "probe"}
    )

    assert refused.status_code == 422
    assert "qidiruv natijasi" in refused.json()["detail"]


def test_a_test_frame_needs_no_saved_camera(client: TestClient, shop: dict) -> None:
    """Kamerani saqlashdan OLDIN tekshirish kerak, aks holda bazaga
    chala qator yozib, keyin tozalash kerak bo'lardi."""
    # Avval qidiruv: sinaladigan manzil o'sha natijadan olinadi.
    client.post("/api/v1/owner/scan", headers=shop["owner"], json={"kind": "onvif"})
    scan_id = beat(client, shop)["job_requested"][0]["job_id"]
    client.put(
        f"/api/v1/edge/jobs/{scan_id}/result",
        headers=shop["device"],
        json={"ok": True, "result": {"streams": [{"uri": RTSP_WITH_PASSWORD}]}},
    )

    started = client.post(
        "/api/v1/owner/scan",
        headers=shop["owner"],
        json={"kind": "probe", "from_job": scan_id, "stream_ref": 0},
    )
    assert started.status_code == 200, started.text
    told = beat(client, shop)["job_requested"][0]
    # Qurilma to'liq manzilni oladi — u RTSP ni ochishi kerak.
    assert told["params"]["rtsp_url"] == RTSP_WITH_PASSWORD
    job_id = told["job_id"]

    sent = client.put(
        f"/api/v1/edge/jobs/{job_id}/frame",
        headers={**shop["device"], "Content-Type": "image/jpeg"},
        content=b"\xff\xd8\xff\xdb" + b"0" * 100,
    )
    assert sent.status_code == 200, sent.text

    frame = client.get(f"/api/v1/owner/scan/{job_id}/frame", headers=shop["owner"])
    assert frame.status_code == 200
    assert frame.headers["content-type"] == "image/jpeg"
    assert frame.headers["cache-control"] == "no-store"


def test_a_frame_that_is_not_a_jpeg_is_refused(client: TestClient, shop: dict) -> None:
    client.post("/api/v1/owner/scan", headers=shop["owner"], json={"kind": "lan_scan"})
    job_id = beat(client, shop)["job_requested"][0]["job_id"]

    sent = client.put(
        f"/api/v1/edge/jobs/{job_id}/frame",
        headers={**shop["device"], "Content-Type": "text/html"},
        content=b"<script>",
    )

    assert sent.status_code == 415


# ── Chegaralar ──────────────────────────────────────────────────────


def test_a_broken_device_cannot_fill_the_database(client: TestClient, shop: dict) -> None:
    client.post("/api/v1/owner/scan", headers=shop["owner"], json={"kind": "lan_scan"})
    job_id = beat(client, shop)["job_requested"][0]["job_id"]

    huge = client.put(
        f"/api/v1/edge/jobs/{job_id}/result",
        headers=shop["device"],
        json={"ok": True, "result": {"blob": "x" * 70_000}},
    )

    assert huge.status_code == 413


def test_a_device_cannot_touch_another_shops_job(client: TestClient, shop: dict) -> None:
    client.post("/api/v1/owner/scan", headers=shop["owner"], json={"kind": "lan_scan"})
    job_id = beat(client, shop)["job_requested"][0]["job_id"]
    other = client.post(
        "/api/v1/public/quick-trial",
        json={
            "phone": "+998 90 000 00 00",
            "full_name": "Begona Odam",
            "company": "Boshqa do'kon",
            "username": "begona",
            "password": "parol12345",
            "consent": True,
        },
    ).json()
    stranger = client.post(
        "/api/v1/devices/claim",
        json={"pairing_code": other["pairing_code"], "label": "BEGONA-PC"},
    ).json()

    stolen = client.put(
        f"/api/v1/edge/jobs/{job_id}/result",
        headers={
            "X-Site-Id": stranger["site_id"],
            "X-Device-Id": stranger["device_id"],
            "X-Device-Token": stranger["device_token"],
        },
        json={"ok": True, "result": {}},
    )

    assert stolen.status_code == 404


def test_a_failed_scan_says_why(client: TestClient, shop: dict) -> None:
    client.post("/api/v1/owner/scan", headers=shop["owner"], json={"kind": "lan_scan"})
    job_id = beat(client, shop)["job_requested"][0]["job_id"]

    client.put(
        f"/api/v1/edge/jobs/{job_id}/result",
        headers=shop["device"],
        json={"ok": False, "error": "Tarmoqda kamera topilmadi"},
    )

    job = client.get(f"/api/v1/owner/scan/{job_id}", headers=shop["owner"]).json()["job"]
    assert job["status"] == "failed"
    assert job["error"] == "Tarmoqda kamera topilmadi"


def test_a_manager_cannot_start_a_scan(client: TestClient, shop: dict) -> None:
    """Skanerlash do'kon tarmog'iga tegadi — bu egasining ishi."""
    from cloud.main import get_event_store
    from cloud.owner_auth import issue_owner_token

    member = get_event_store().add_member(
        shop["site_id"], "777", role="manager", display_name="Menejer"
    )
    token = issue_owner_token(member)

    refused = client.post(
        "/api/v1/owner/scan",
        headers={"Authorization": f"Bearer {token}"},
        json={"kind": "lan_scan"},
    )

    assert refused.status_code == 403


def test_the_existing_heartbeat_keys_are_untouched(client: TestClient, shop: dict) -> None:
    """Yangi kalit eskilariga tegmasin — jonli ko'rish va ovoz
    o'nlab testda qulflangan."""
    answer = beat(client, shop)

    for key in ("preview_requested", "live_requested", "speak_requested", "job_requested"):
        assert key in answer, key


# ── Topshiriq turlari bazada ham ruxsat etilgan bo'lsin ──────────────────
#
# 2026-08-26: `clean_chains` `JOB_DEADLINE_SEC` ga qo'shildi, lekin
# `device_jobs.kind` dagi CHECK ro'yxatiga qo'shilmadi.  Test yo'q edi,
# shuning uchun xato JONLI SERVERDA 500 bo'lib chiqdi.


def test_every_known_job_kind_can_actually_be_created(tmp_path) -> None:
    """`JOB_DEADLINE_SEC` dagi har tur bazaga yozila olsin.

    Ikki ro'yxat (kod va CHECK cheklovi) ajralib ketsa yangi tur faqat
    production'da yiqiladi — aynan shunday bo'ldi.
    """
    from cloud.store import CloudStore

    store = CloudStore(tmp_path / "c.db")
    site = store.create_site("Turlar", plan="lite")

    for kind in CloudStore.JOB_DEADLINE_SEC:
        job = store.create_job(site["site_id"], kind=kind, params={}, requested_by="test")
        assert job["kind"] == kind, f"«{kind}» bazaga yozilmadi"
        # Keyingi tur uchun joy bo'shatamiz: bir vaqtda bitta tirik
        # topshiriq bo'ladi (`create_job` mavjudini qaytaradi).
        store.job_result(site["site_id"], job["job_id"], ok=True, result={})


def test_clean_chains_is_a_known_kind() -> None:
    """Yetimlarni tozalash turi ro'yxatda bo'lishi shart."""
    from cloud.store import CloudStore

    assert "clean_chains" in CloudStore.JOB_DEADLINE_SEC
