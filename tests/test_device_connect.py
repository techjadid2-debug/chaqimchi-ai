"""Qurilmani do'kon egasi bulutdan ulashi.

Eski oqimda pairing kodini admin yoki usta yaratib egaga berardi. Egasi
dasturni o'zi o'rnatib, keyin ro'yxatdan o'tsa, hech qanday kod yo'q edi
va u kimdan so'rashini ham bilmasdi.

Yangi oqim yo'nalishni teskari qiladi:

    qurilma o'zini tanishtiradi  →  egasi panelidan ko'rib tasdiqlaydi
                                 →  qurilma kelib tokenini oladi

Bu fayl aynan shu uch qadamni va uning atrofidagi xavfsizlik
chegaralarini qulflaydi.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

FINGERPRINT = "aa11bb22cc33dd44"
OTHER_FINGERPRINT = "ff99ee88dd77cc66"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("CHAQIMCHI_CLOUD_ADMIN_KEY", "test-admin")
    monkeypatch.setenv("CHAQIMCHI_OWNER_JWT_SECRET", "o" * 64)
    monkeypatch.setenv("CHAQIMCHI_PORTAL_JWT_SECRET", "p" * 64)
    monkeypatch.setenv("CHAQIMCHI_PUBLIC_URL", "https://chaqimchi.test")
    monkeypatch.setenv("CHAQIMCHI_APP_URL", "https://app.chaqimchi.test")
    monkeypatch.setattr("cloud.main.DB_PATH", tmp_path / "cloud.db")
    monkeypatch.setattr("cloud.main._store", None)
    monkeypatch.setattr("cloud.main._event_store", None)
    monkeypatch.setattr("cloud.main._event_store_key", None)
    from cloud.main import app

    return TestClient(app)


def hello(client: TestClient, **overrides: object) -> dict:
    body = {"fingerprint": FINGERPRINT, "label": "KASSA-PC", "local_ip": "192.168.1.55"}
    body.update(overrides)
    response = client.post("/api/v1/public/device-hello", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def owner_token(client: TestClient, *, username: str = "dokonchi") -> tuple[str, str]:
    """Do'kon ochadi va egasining tokenini qaytaradi."""
    trial = client.post(
        "/api/v1/public/quick-trial",
        json={
            "phone": "+998 90 123 45 67",
            "full_name": "Ega Egayev",
            "company": "Namuna do'kon",
            "username": username,
            "password": "parol12345",
            "consent": True,
        },
    )
    assert trial.status_code == 200, trial.text
    login = client.post(
        "/api/v1/auth/login", json={"username": username, "password": "parol12345"}
    )
    assert login.status_code == 200, login.text
    return login.json()["access_token"], trial.json()["site_id"]


# ── Tanishtirish ────────────────────────────────────────────────────


def test_hello_gives_a_link_the_owner_can_open(client: TestClient) -> None:
    state = hello(client)

    assert state["status"] == "pending"
    assert state["connect_url"].startswith("https://app.chaqimchi.test/owner?connect=")
    assert state["connect_token"] in state["connect_url"]
    assert len(state["verify_code"]) == 6
    assert state["expires_in_sec"] > 0


def test_the_same_computer_does_not_pile_up_rows(client: TestClient) -> None:
    """Qayta ishga tushgan qurilma egasining panelida bir marta chiqsin.

    Har `hello` yangi qator yaratsa, bitta kompyuter o'nlab marta
    ko'rinib, egasi qaysinisini tasdiqlashni bilmasdi.
    """
    first = hello(client)
    second = hello(client)

    assert second["pending_id"] == first["pending_id"]
    # Tekshiruv kodi saqlanadi: egasi uni lokal ekranda ko'rgan
    # bo'lishi mumkin, almashtirsak u yolg'on chiqardi.
    assert second["verify_code"] == first["verify_code"]
    # Token esa aylanadi — eskisi darhol o'ladi.
    assert second["connect_token"] != first["connect_token"]
    assert client.get(f"/api/v1/public/device-connect?token={first['connect_token']}").status_code == 404


def test_hello_keeps_details_it_already_knows(client: TestClient) -> None:
    """Bo'sh qiymat eskisini o'chirmasin — qurilma qayta ishga
    tushganda lokal IP'ni hali bilmasligi mumkin."""
    hello(client)
    second = hello(client, label="", local_ip="")

    peek = client.get(f"/api/v1/public/device-connect?token={second['connect_token']}").json()
    assert peek["label"] == "KASSA-PC"
    assert peek["local_ip_masked"] == "192.168.1.xxx"


# ── Tasdiqdan oldingi ko'rinish ─────────────────────────────────────


def test_peek_shows_only_what_the_owner_needs_to_compare(client: TestClient) -> None:
    state = hello(client)

    peek = client.get(f"/api/v1/public/device-connect?token={state['connect_token']}")

    assert peek.status_code == 200
    payload = peek.json()
    assert payload["label"] == "KASSA-PC"
    assert payload["verify_code"] == state["verify_code"]
    # Oxirgi oktet yashirilgan.
    assert payload["local_ip_masked"] == "192.168.1.xxx"
    assert "192.168.1.55" not in peek.text
    # Bu endpoint autentifikatsiyasiz — hech qanday sir chiqmasin.
    assert "token" not in {key.lower() for key in payload}
    assert "connect_hash" not in peek.text


def test_unknown_and_expired_tokens_look_identical(client: TestClient) -> None:
    """Aks holda endpoint "bu token haqiqiymi?" orakuliga aylanardi."""
    unknown = client.get("/api/v1/public/device-connect?token=" + "z" * 40)
    assert unknown.status_code == 404

    state = hello(client)
    token, _ = owner_token(client)
    client.post(
        "/api/v1/owner/devices/claim",
        headers={"Authorization": f"Bearer {token}"},
        json={"connect_token": state["connect_token"]},
    )
    client.post(
        "/api/v1/public/device-handover",
        json={"connect_token": state["connect_token"], "fingerprint": FINGERPRINT},
    )
    used = client.get(f"/api/v1/public/device-connect?token={state['connect_token']}")

    assert used.status_code == unknown.status_code == 404
    assert used.json()["detail"] == unknown.json()["detail"]


# ── Egasi tasdiqlaydi ───────────────────────────────────────────────


def test_owner_claims_the_device_and_it_gets_credentials(client: TestClient) -> None:
    state = hello(client)
    token, site_id = owner_token(client)

    # Tasdiqdan OLDIN qurilma hech narsa olmaydi.
    waiting = client.post(
        "/api/v1/public/device-handover",
        json={"connect_token": state["connect_token"], "fingerprint": FINGERPRINT},
    )
    assert waiting.json()["status"] == "pending"

    claim = client.post(
        "/api/v1/owner/devices/claim",
        headers={"Authorization": f"Bearer {token}"},
        json={"connect_token": state["connect_token"]},
    )
    assert claim.status_code == 200, claim.text
    assert claim.json()["site_id"] == site_id

    handover = client.post(
        "/api/v1/public/device-handover",
        json={"connect_token": state["connect_token"], "fingerprint": FINGERPRINT},
    )
    payload = handover.json()
    assert payload["status"] == "claimed"
    assert payload["site_id"] == site_id
    assert payload["device_token"]

    # Olingan hisob ma'lumotlari haqiqatan ishlaydi.
    beat = client.post(
        "/api/v1/edge/heartbeat",
        headers={
            "X-Site-Id": payload["site_id"],
            "X-Device-Id": payload["device_id"],
            "X-Device-Token": payload["device_token"],
        },
        json={},
    )
    assert beat.status_code == 200, beat.text


def test_a_stranger_cannot_claim_someone_elses_computer(client: TestClient) -> None:
    """Sayt SESSIYADAN olinadi, so'rovdan emas.

    Token biror yo'l bilan sizib ketsa ham, uni ushlagan odam faqat
    O'Z do'koniga biriktira oladi — begonanikiga emas.
    """
    state = hello(client)
    stranger, stranger_site = owner_token(client, username="begona")

    claim = client.post(
        "/api/v1/owner/devices/claim",
        headers={"Authorization": f"Bearer {stranger}"},
        json={"connect_token": state["connect_token"], "site_id": "boshqa-sayt"},
    )

    assert claim.status_code == 200
    # So'rovdagi `site_id` e'tiborsiz qoldirildi.
    assert claim.json()["site_id"] == stranger_site


def test_claiming_without_a_login_is_refused(client: TestClient) -> None:
    state = hello(client)

    claim = client.post(
        "/api/v1/owner/devices/claim", json={"connect_token": state["connect_token"]}
    )

    assert claim.status_code == 401


def test_the_device_must_prove_it_is_the_same_machine(client: TestClient) -> None:
    state = hello(client)
    token, _ = owner_token(client)
    client.post(
        "/api/v1/owner/devices/claim",
        headers={"Authorization": f"Bearer {token}"},
        json={"connect_token": state["connect_token"]},
    )

    stolen = client.post(
        "/api/v1/public/device-handover",
        json={"connect_token": state["connect_token"], "fingerprint": OTHER_FINGERPRINT},
    )

    assert stolen.status_code == 404


# ── Javob yo'lda yo'qolsa ───────────────────────────────────────────


def test_a_lost_response_can_be_retried_until_the_device_is_online(client: TestClient) -> None:
    """Do'kondagi internet uzilsa javob yo'qolishi mumkin.

    Qayta so'rashga ruxsat bo'lmasa, o'rnatish "muvaffaqiyatli"
    ko'rinib, qurilma esa abadiy ulanmay qolardi.
    """
    state = hello(client)
    token, _ = owner_token(client)
    client.post(
        "/api/v1/owner/devices/claim",
        headers={"Authorization": f"Bearer {token}"},
        json={"connect_token": state["connect_token"]},
    )
    body = {"connect_token": state["connect_token"], "fingerprint": FINGERPRINT}

    first = client.post("/api/v1/public/device-handover", json=body).json()
    second = client.post("/api/v1/public/device-handover", json=body).json()

    assert first["status"] == second["status"] == "claimed"
    assert second["device_id"] == first["device_id"]
    # Sir aylanadi: eski token yo'lda qolgan bo'lishi mumkin.
    assert second["device_token"] != first["device_token"]

    # Qurilma bir marta aloqaga chiqqach oyna yopiladi.
    client.post(
        "/api/v1/edge/heartbeat",
        headers={
            "X-Site-Id": second["site_id"],
            "X-Device-Id": second["device_id"],
            "X-Device-Token": second["device_token"],
        },
        json={},
    )
    third = client.post("/api/v1/public/device-handover", json=body).json()
    assert third["status"] == "already_used"
    assert "device_token" not in third


# ── Bayroq va cheklovlar ────────────────────────────────────────────


def test_the_flow_can_be_switched_off_without_an_update(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Yangi reliz tarqab bo'lgach nosozlik chiqsa, bayroq butun parkni
    eski, sinalgan yo'lga qaytaradi — OTA kutish shart emas."""
    monkeypatch.setenv("CHAQIMCHI_DEVICE_HELLO", "0")

    blocked = client.post(
        "/api/v1/public/device-hello", json={"fingerprint": FINGERPRINT, "label": "PC"}
    )

    assert blocked.status_code == 404


def test_a_flood_of_new_devices_is_capped(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CHAQIMCHI_PENDING_DEVICE_LIMIT", "1")
    hello(client)

    second = client.post(
        "/api/v1/public/device-hello",
        json={"fingerprint": OTHER_FINGERPRINT, "label": "BOSHQA-PC"},
    )

    assert second.status_code == 503


def test_the_fingerprint_shape_is_enforced(client: TestClient) -> None:
    bad = client.post("/api/v1/public/device-hello", json={"fingerprint": "qisqa"})

    assert bad.status_code == 422
