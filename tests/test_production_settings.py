from pathlib import Path

import yaml

from chaqimchi_ai.settings import AppSettings


def test_production_settings_fail_closed(monkeypatch) -> None:
    for key in (
        "CHAQIMCHI_API_KEY",
        "CHAQIMCHI_JWT_SECRET",
        "CHAQIMCHI_EMBEDDING_KEY",
        "CHAQIMCHI_FACE_MODEL_LICENSED",
    ):
        monkeypatch.delenv(key, raising=False)
    cfg = AppSettings.model_validate({"environment": "production"})
    errors = cfg.production_errors()
    assert any("autentifikatsiya" in error for error in errors)
    assert any("shifrlash" in error for error in errors)
    assert any("litsenziyasi" in error for error in errors)


def test_production_settings_accept_secure_config(monkeypatch) -> None:
    monkeypatch.setenv("CHAQIMCHI_API_KEY", "a" * 32)
    monkeypatch.setenv("CHAQIMCHI_EMBEDDING_KEY", "fernet-key-is-validated-by-storage")
    monkeypatch.setenv("CHAQIMCHI_FACE_MODEL_LICENSED", "true")
    cfg = AppSettings.model_validate(
        {
            "environment": "production",
            "security": {"api_key_enabled": True},
            "rate_limit": {"enabled": True},
            "storage": {"encrypt_embeddings": True},
        }
    )
    assert cfg.production_errors() == []


def test_lite_profile_is_the_eight_camera_orange_pi_profile(monkeypatch) -> None:
    monkeypatch.setenv("CHAQIMCHI_CLOUD_URL", "https://cloud.example.uz")
    monkeypatch.setenv("CHAQIMCHI_SITE_ID", "site-1")
    monkeypatch.setenv("CHAQIMCHI_DEVICE_ID", "device-1")
    monkeypatch.setenv("CHAQIMCHI_DEVICE_TOKEN", "device-token")
    monkeypatch.setenv("CHAQIMCHI_API_KEY", "a" * 32)
    monkeypatch.setenv("CHAQIMCHI_JWT_SECRET", "j" * 32)
    monkeypatch.setenv("CHAQIMCHI_EMBEDDING_KEY", "embedding-key")
    monkeypatch.setenv("CHAQIMCHI_FACE_MODEL_LICENSED", "true")
    for number in range(1, 9):
        monkeypatch.setenv(
            f"CAMERA_{number:02d}_RTSP",
            f"rtsp://camera-{number:02d}/sub",
        )

    root = Path(__file__).resolve().parents[1]
    cfg = AppSettings.load(root / "config" / "lite.yaml", base_dir=root)
    assert cfg.environment == "production"
    assert len(cfg.cameras) == 8
    assert cfg.license.cloud_url == "https://cloud.example.uz"
    assert cfg.cloud_sync.device_id == "device-1"
    assert cfg.production_errors() == []


def test_sotqin_r1_profile_is_cloud_only_n100_gateway() -> None:
    root = Path(__file__).resolve().parents[1]
    profile = yaml.safe_load((root / "config" / "sotqin.yaml").read_text(encoding="utf-8"))
    assert profile["product"] == {
        "name": "Sotqin",
        "profile": "SOTQIN-N100-8-128-R1",
        "hardware_revision": "R1",
        "guaranteed_cameras": 4,
        "max_cameras": 8,
    }
    assert profile["media"]["hardware_decode"] == "qsv"
    assert profile["media"]["ai_inference"] is False
    assert profile["buffer"]["max_days"] == 3
    assert profile["buffer"]["max_bytes"] == 40 * 1024**3
