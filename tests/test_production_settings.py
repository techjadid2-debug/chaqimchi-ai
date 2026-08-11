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
