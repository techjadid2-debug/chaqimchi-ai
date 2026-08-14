from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cloud.portal_auth import hash_password, verify_password
from cloud.store import CloudStore

ADMIN_KEY = {"X-Cloud-Admin-Key": "test-admin"}


@pytest.fixture
def portal_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
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


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_scrypt_password_hash_is_salted_and_verifiable() -> None:
    first = hash_password("StrongPass123")
    second = hash_password("StrongPass123")

    assert first.startswith("scrypt$")
    assert first != second
    assert verify_password("StrongPass123", first)
    assert not verify_password("WrongPass123", first)


def test_store_accounts_never_return_password_hash(tmp_path: Path) -> None:
    store = CloudStore(tmp_path / "cloud.db")
    account = store.create_account(
        username="installer.one",
        password="StrongPass123",
        role="installer",
        status="pending",
        full_name="Installer One",
    )

    assert "password_hash" not in account
    assert "password_hash" not in store.list_accounts()[0]
    assert store.authenticate_account("installer.one", "StrongPass123")["id"] == account["id"]


def test_admin_installer_customer_full_flow(portal_client: TestClient) -> None:
    admin = portal_client.post(
        "/api/v1/admin/accounts",
        headers=ADMIN_KEY,
        json={
            "username": "root.admin",
            "password": "RootPassword123",
            "role": "admin",
            "status": "active",
            "full_name": "Bosh Admin",
        },
    )
    assert admin.status_code == 200
    assert "password_hash" not in admin.text
    admin_login = portal_client.post(
        "/api/v1/auth/login",
        json={"username": "root.admin", "password": "RootPassword123"},
    )
    assert admin_login.status_code == 200
    admin_headers = bearer(admin_login.json()["access_token"])
    assert portal_client.get("/api/v1/admin/stats", headers=admin_headers).status_code == 200

    registered = portal_client.post(
        "/api/v1/auth/installer/register",
        json={
            "full_name": "Usta Installer",
            "phone": "+998 90 111 22 33",
            "company": "Usta Service",
            "username": "usta.one",
            "password": "Installer123",
            "consent": True,
        },
    )
    assert registered.status_code == 200
    assert registered.json()["account"]["status"] == "pending"
    pending_headers = bearer(registered.json()["access_token"])
    assert portal_client.get("/api/v1/auth/me", headers=pending_headers).status_code == 200
    assert (
        portal_client.get("/api/v1/installer/assignments", headers=pending_headers).status_code
        == 403
    )

    installer_id = registered.json()["account"]["id"]
    approved = portal_client.put(
        f"/api/v1/admin/accounts/{installer_id}",
        headers=admin_headers,
        json={"status": "active"},
    )
    assert approved.status_code == 200
    # Status o'zgargani uchun ro'yxatdan o'tishdagi pending token bekor bo'ladi.
    assert portal_client.get("/api/v1/auth/me", headers=pending_headers).status_code == 401
    installer_login = portal_client.post(
        "/api/v1/auth/login",
        json={"username": "usta.one", "password": "Installer123"},
    )
    installer_headers = bearer(installer_login.json()["access_token"])

    site = portal_client.post(
        "/api/v1/admin/sites",
        headers=admin_headers,
        json={"name": "Portal Do'kon", "plan": "lite", "subscription_months": 1},
    ).json()
    customer = portal_client.post(
        "/api/v1/admin/accounts",
        headers=admin_headers,
        json={
            "username": "shop.owner",
            "password": "CustomerPass123",
            "role": "customer",
            "status": "active",
            "full_name": "Do'kon Egasi",
            "site_id": site["site_id"],
        },
    )
    assert customer.status_code == 200
    assigned = portal_client.post(
        "/api/v1/admin/installer-assignments",
        headers=admin_headers,
        json={"installer_id": installer_id, "site_id": site["site_id"]},
    )
    assert assigned.status_code == 200

    jobs = portal_client.get("/api/v1/installer/assignments", headers=installer_headers)
    assert jobs.status_code == 200
    assert jobs.json()["assignments"][0]["site_name"] == "Portal Do'kon"
    camera = portal_client.put(
        f"/api/v1/installer/sites/{site['site_id']}/cameras/camera-01",
        headers=installer_headers,
        json={
            "label": "Asosiy kirish",
            "rtsp_url": "rtsp://user:camera-pass@10.0.0.5/sub",
            "enabled": True,
        },
    )
    assert camera.status_code == 200
    assert "camera-pass" not in camera.text
    onboarding = portal_client.get(
        f"/api/v1/installer/sites/{site['site_id']}/onboarding",
        headers=installer_headers,
    )
    assert onboarding.status_code == 200
    assert onboarding.json()["install_command"].endswith(site["pairing_code"])

    customer_login = portal_client.post(
        "/api/v1/auth/login",
        json={"username": "shop.owner", "password": "CustomerPass123"},
    )
    customer_headers = bearer(customer_login.json()["access_token"])
    cameras = portal_client.get("/api/v1/owner/cameras", headers=customer_headers)
    assert cameras.status_code == 200
    assert cameras.json()["cameras"][0]["label"] == "Asosiy kirish"
    assert "camera-pass" not in cameras.text

    assert portal_client.get("/api/v1/admin/stats", headers=installer_headers).status_code == 403
    assert (
        portal_client.get("/api/v1/installer/assignments", headers=customer_headers).status_code
        == 403
    )


def test_password_reset_revokes_existing_token(portal_client: TestClient) -> None:
    account = portal_client.post(
        "/api/v1/admin/accounts",
        headers=ADMIN_KEY,
        json={
            "username": "reset.admin",
            "password": "OldPassword123",
            "role": "admin",
            "status": "active",
            "full_name": "Reset Admin",
        },
    ).json()
    login = portal_client.post(
        "/api/v1/auth/login",
        json={"username": "reset.admin", "password": "OldPassword123"},
    ).json()
    old_headers = bearer(login["access_token"])

    reset = portal_client.post(
        f"/api/v1/admin/accounts/{account['id']}/password",
        headers=ADMIN_KEY,
        json={"new_password": "NewPassword123"},
    )
    assert reset.status_code == 200
    assert portal_client.get("/api/v1/admin/stats", headers=old_headers).status_code == 401
    assert (
        portal_client.post(
            "/api/v1/auth/login",
            json={"username": "reset.admin", "password": "NewPassword123"},
        ).status_code
        == 200
    )


def test_public_site_exposes_customer_and_installer_entry_points(
    portal_client: TestClient,
) -> None:
    homepage = portal_client.get("/")
    guide = portal_client.get("/installer-guide")
    panel = portal_client.get("/installer")

    assert homepage.status_code == guide.status_code == panel.status_code == 200
    assert "/owner" in homepage.text
    assert "/installer" in homepage.text
    assert "connect-hardware-v1.webp" in guide.text
    assert "install-software-v1.webp" in guide.text
    assert "handoff-customer-v1.webp" in guide.text
    assert "Ro‘yxatdan o‘tish" in panel.text
