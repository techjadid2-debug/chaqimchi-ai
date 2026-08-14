import pytest
from fastapi.testclient import TestClient

import chaqimchi_ai.sotqin_agent as module


def test_control_health_is_fail_closed_before_pairing(monkeypatch) -> None:
    monkeypatch.setattr(module.control, "cloud_url", "")
    monkeypatch.setattr(module.control, "site_id", "")
    monkeypatch.setattr(module.control, "device_id", "")
    monkeypatch.setattr(module.control, "device_token", "")
    response = TestClient(module.app).get("/health")
    assert response.status_code == 503
    assert response.json()["ai_model"] == "cloud-only"
    assert response.json()["product"] == "Sotqin"


def test_control_health_reports_paired_without_loading_model(monkeypatch) -> None:
    monkeypatch.setattr(module.control, "cloud_url", "https://cloud.example.uz")
    monkeypatch.setattr(module.control, "site_id", "site")
    monkeypatch.setattr(module.control, "device_id", "device")
    monkeypatch.setattr(module.control, "device_token", "token")
    response = TestClient(module.app).get("/health")
    assert response.status_code == 200
    assert response.json()["mode"] == "control-only"


def test_sotqin_config_is_validated_and_saved_atomically(tmp_path, monkeypatch) -> None:
    payload = {
        "revision": 3,
        "product": {"name": "Sotqin", "max_cameras": 8},
        "buffer_policy": {"max_days": 3, "max_bytes": 40 * 1024**3},
        "cloud_features": [
            {"code": "person_count", "camera_count": 2, "queue_kind": "batch"}
        ],
    }
    monkeypatch.setattr(module.control, "config_path", tmp_path / "config.json")
    module.control.validate_config(payload)
    module.control.persist_config(payload)
    assert module.control.config_path.stat().st_mode & 0o777 == 0o600
    assert '"revision":3' in module.control.config_path.read_text(encoding="utf-8")


def test_sotqin_rejects_wrong_product() -> None:
    try:
        module.control.validate_config(
            {"revision": 1, "product": {"name": "Boshqa", "max_cameras": 1}, "cloud_features": []}
        )
        assert False
    except ValueError as exc:
        assert "Sotqin" in str(exc)


def test_sotqin_rejects_profile_over_8_cameras_or_40gb_buffer() -> None:
    with pytest.raises(ValueError, match="8 kamera"):
        module.control.validate_config(
            {"revision": 1, "product": {"name": "Sotqin", "max_cameras": 9}, "cloud_features": []}
        )
    with pytest.raises(ValueError, match="40 GB"):
        module.control.validate_config(
            {
                "revision": 1,
                "product": {"name": "Sotqin", "max_cameras": 8},
                "buffer_policy": {"max_days": 3, "max_bytes": 41 * 1024**3},
                "cloud_features": [],
            }
        )
