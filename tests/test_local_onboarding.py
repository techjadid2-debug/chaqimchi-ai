from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CHAQIMCHI_CLOUD_ADMIN_KEY", "test-admin")
    db = tmp_path / "c.db"
    monkeypatch.setattr("cloud.main.DB_PATH", db)
    monkeypatch.setattr("cloud.main._store", None)
    from cloud.main import app

    return TestClient(app)


def test_onboarding_page_and_assets(client: TestClient) -> None:
    # 1. Onboarding HTML sahifasi
    res = client.get("/onboarding")
    assert res.status_code == 200
    assert "Chaqimchi" in res.text
    assert "Web-Kamerangizda Jonli AI Sinovi" in res.text
    assert "POE SWITCH" in res.text

    # 2. Onboarding JS va CSS
    js_res = client.get("/assets/local-onboarding.js")
    assert js_res.status_code == 200
    assert "toggleWebcam" in js_res.text

    css_res = client.get("/assets/local-onboarding.css")
    assert css_res.status_code == 200


def test_agent_discovery_scan_endpoint(client: TestClient) -> None:
    res = client.post("/api/v1/agent/discovery/scan")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "cameras" in data
    assert isinstance(data["cameras"], list)
