
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def cloud_client(tmp_path, monkeypatch):
    monkeypatch.setenv("CHAQIMCHI_CLOUD_ADMIN_KEY", "test-admin")
    db = tmp_path / "c.db"
    monkeypatch.setattr("cloud.main.DB_PATH", db)
    monkeypatch.setattr("cloud.main._store", None)
    from cloud.main import app

    return TestClient(app)


def test_cloud_plans_and_site(cloud_client) -> None:
    r = cloud_client.get("/api/v1/plans")
    assert r.status_code == 200
    assert "starter" in r.json()["plans"]

    r2 = cloud_client.post(
        "/api/v1/admin/sites",
        headers={"X-Cloud-Admin-Key": "test-admin"},
        json={"name": "API Test", "plan": "starter", "subscription_months": 1},
    )
    assert r2.status_code == 200
    data = r2.json()
    assert data["pairing_code"]


ADMIN = {"X-Cloud-Admin-Key": "test-admin"}


def _make_site(client, name: str = "Panel Test", plan: str = "business") -> dict:
    r = client.post(
        "/api/v1/admin/sites",
        headers=ADMIN,
        json={"name": name, "plan": plan, "subscription_months": 6},
    )
    assert r.status_code == 200
    return r.json()


def test_admin_endpoints_require_key(cloud_client) -> None:
    site = _make_site(cloud_client)
    paths = [
        ("get", "/api/v1/admin/stats", None),
        ("get", f"/api/v1/admin/sites/{site['site_id']}", None),
        ("post", f"/api/v1/admin/sites/{site['site_id']}/status", {"status": "suspended"}),
        ("post", f"/api/v1/admin/sites/{site['site_id']}/pairing", None),
    ]
    for method, path, body in paths:
        call = getattr(cloud_client, method)
        r = call(path, json=body) if body else call(path)
        assert r.status_code == 401, path


def test_admin_stats(cloud_client) -> None:
    _make_site(cloud_client, "Stats", "starter")
    stats = cloud_client.get("/api/v1/admin/stats", headers=ADMIN).json()
    assert stats["total_sites"] == 1
    assert stats["active"] == 1
    assert stats["monthly_revenue_uzs"] == 790_000


def test_admin_site_detail_and_status_flow(cloud_client) -> None:
    site = _make_site(cloud_client)
    site_id = site["site_id"]

    detail = cloud_client.get(f"/api/v1/admin/sites/{site_id}", headers=ADMIN).json()
    assert detail["license_status"] == "active"
    assert detail["limits"]["max_cameras"] == 3

    r = cloud_client.post(
        f"/api/v1/admin/sites/{site_id}/status", headers=ADMIN, json={"status": "suspended"}
    )
    assert r.status_code == 200
    assert r.json()["license_status"] == "suspended"

    # Noto'g'ri holat — pydantic rad etadi.
    bad = cloud_client.post(
        f"/api/v1/admin/sites/{site_id}/status", headers=ADMIN, json={"status": "o'chirilgan"}
    )
    assert bad.status_code == 422


def test_admin_new_pairing_code(cloud_client) -> None:
    site = _make_site(cloud_client)
    r = cloud_client.post(f"/api/v1/admin/sites/{site['site_id']}/pairing", headers=ADMIN)
    assert r.status_code == 200
    code = r.json()["pairing_code"]
    assert code != site["pairing_code"]

    claimed = cloud_client.post("/api/v1/devices/claim", json={"pairing_code": code})
    assert claimed.status_code == 200
    assert claimed.json()["site_id"] == site["site_id"]


def test_admin_unknown_site_is_404(cloud_client) -> None:
    assert cloud_client.get("/api/v1/admin/sites/yo-q", headers=ADMIN).status_code == 404
    r = cloud_client.post(
        "/api/v1/admin/sites/yo-q/status", headers=ADMIN, json={"status": "active"}
    )
    assert r.status_code == 404


def test_admin_panel_page_is_served(cloud_client) -> None:
    r = cloud_client.get("/admin")
    assert r.status_code == 200
    assert "Chaqimchi Cloud" in r.text
    assert cloud_client.get("/assets/admin.css").status_code == 200
