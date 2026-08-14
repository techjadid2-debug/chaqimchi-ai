from pathlib import Path

import yaml

from chaqimchi_ai.settings import AppSettings


def test_production_settings_fail_closed(monkeypatch) -> None:
    for key in (
        "CHAQIMCHI_API_KEY",
        "CHAQIMCHI_JWT_SECRET",
        "CHAQIMCHI_EMBEDDING_KEY",
        "CHAQIMCHI_FACE_MODEL_LICENSED",
        "CHAQIMCHI_ATTENDANCE_PILOT",
        "CHAQIMCHI_FACE_MODEL_MANIFEST",
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
    monkeypatch.setenv("CHAQIMCHI_FACE_MODEL_LICENSED", "false")
    monkeypatch.setenv("CHAQIMCHI_ATTENDANCE_PILOT", "true")
    cfg = AppSettings.model_validate(
        {
            "environment": "production",
            "security": {"api_key_enabled": True},
            "rate_limit": {"enabled": True},
            "storage": {"encrypt_embeddings": True},
            "events": {"save_snapshots": False},
        }
    )
    assert cfg.production_errors() == []


def test_commercial_face_mode_requires_a_verified_bundle(tmp_path: Path, monkeypatch) -> None:
    model = tmp_path / "licensed.onnx"
    model.write_bytes(b"licensed-model")
    import hashlib
    import json

    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "licensed_for_commercial_use": True,
                "license_reference": "contract-2026-01",
                "files": {"licensed.onnx": hashlib.sha256(model.read_bytes()).hexdigest()},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CHAQIMCHI_API_KEY", "a" * 32)
    monkeypatch.setenv("CHAQIMCHI_EMBEDDING_KEY", "fernet-key-is-validated-by-storage")
    monkeypatch.setenv("CHAQIMCHI_FACE_MODEL_LICENSED", "true")
    monkeypatch.setenv("CHAQIMCHI_FACE_MODEL_MANIFEST", str(manifest))
    cfg = AppSettings.model_validate(
        {
            "environment": "production",
            "face": {"model_name": "licensed-retail-face-v1"},
            "security": {"api_key_enabled": True},
            "rate_limit": {"enabled": True},
            "storage": {"encrypt_embeddings": True},
        }
    )
    assert cfg.production_errors() == []


def test_sotqin_r1_profile_matches_the_hardware() -> None:
    root = Path(__file__).resolve().parents[1]
    profile = yaml.safe_load((root / "config" / "sotqin.yaml").read_text(encoding="utf-8"))
    assert profile["product"] == {
        "name": "Sotqin",
        "profile": "SOTQIN-N100-8-128-R1",
        "hardware_revision": "R1",
        "guaranteed_cameras": 4,
        "max_cameras": 8,
    }
    # QSV hali retail runnerga ulanmagan; konfiguratsiya yolg'on va'da bermaydi.
    assert profile["media"]["hardware_decode"] == "software"
    # Media worker (probe/filtr/buffer) AI ishlatmaydi — u faqat oqim bilan
    # ishlaydi.  Odam deteksiyasi alohida xizmatda (`retail`).
    assert profile["media"]["ai_inference"] is False
    assert profile["buffer"]["max_days"] == 3
    assert profile["buffer"]["max_bytes"] == 40 * 1024**3


def test_sotqin_profile_carries_the_on_device_ai_section() -> None:
    """Qurilmada AI ishlaydi — profil buni ko'rsatishi kerak.

    Avval bu profil "AI umuman yo'q" deb turardi va yangi odam qurilmada
    nima ishlayotganini konfigdan bilolmasdi.
    """
    root = Path(__file__).resolve().parents[1]
    settings = AppSettings.load(root / "config" / "sotqin.yaml", base_dir=root)

    assert settings.scene.enabled is True
    assert settings.scene.backend == "openvino"
    # Buffer chegaralari ikkala bo'limda bir xil bo'lishi kerak: retail
    # xizmati segmentni o'chirmasa, 128 GB disk to'ladi.
    profile = yaml.safe_load((root / "config" / "sotqin.yaml").read_text(encoding="utf-8"))
    assert settings.retail.buffer_max_bytes == profile["buffer"]["max_bytes"]
    assert settings.retail.buffer_retention_sec == profile["buffer"]["max_days"] * 24 * 3600
