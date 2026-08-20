from pathlib import Path

import yaml

from chaqimchi_ai.settings import AppSettings


def test_production_settings_fail_closed(monkeypatch) -> None:
    for key in ("CHAQIMCHI_API_KEY", "CHAQIMCHI_JWT_SECRET"):
        monkeypatch.delenv(key, raising=False)
    cfg = AppSettings.model_validate({"environment": "production"})
    errors = cfg.production_errors()
    assert any("autentifikatsiya" in error for error in errors)


def test_production_settings_accept_secure_config(monkeypatch) -> None:
    monkeypatch.setenv("CHAQIMCHI_API_KEY", "a" * 32)
    cfg = AppSettings.model_validate(
        {
            "environment": "production",
            "security": {"api_key_enabled": True},
            "rate_limit": {"enabled": True},
        }
    )
    assert cfg.production_errors() == []


def test_legacy_face_section_in_yaml_is_ignored() -> None:
    """Eski config.yaml'lardagi `face:` bo'limi dasturni yiqitmasin.

    Davomat to'plami arxivlangan (`archive/attendance-local`), lekin
    mijoz qurilmalarida `face:` bo'limi bor eski konfiglar qolgan.
    """
    cfg = AppSettings.model_validate({"face": {"model_name": "buffalo_l"}})
    assert not hasattr(cfg, "face")


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
