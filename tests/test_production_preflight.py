from cryptography.fernet import Fernet

from scripts.production_preflight import validate


def secure_env() -> dict[str, str]:
    fernet = Fernet.generate_key().decode()
    return {
        "CHAQIMCHI_ENV": "production",
        "CHAQIMCHI_DOMAIN": "chaqimchi.uz",
        "CHAQIMCHI_PUBLIC_URL": "https://chaqimchi.uz",
        "POSTGRES_DB": "chaqimchi",
        "POSTGRES_USER": "chaqimchi",
        "POSTGRES_PASSWORD": "p" * 64,
        "DATABASE_URL": "postgresql://chaqimchi:secret@postgres:5432/chaqimchi",
        "MINIO_ROOT_USER": "minio-user",
        "MINIO_ROOT_PASSWORD": "m" * 64,
        "CHAQIMCHI_S3_ENDPOINT": "http://minio:9000",
        "CHAQIMCHI_S3_ACCESS_KEY": "access-key",
        "CHAQIMCHI_S3_SECRET_KEY": "s" * 64,
        "CHAQIMCHI_S3_BUCKET": "snapshots",
        "CHAQIMCHI_SNAPSHOT_KEY": fernet,
        "CHAQIMCHI_CAMERA_SECRET_KEY": fernet,
        "CHAQIMCHI_CLOUD_ADMIN_KEY": "a" * 64,
        "CHAQIMCHI_OWNER_JWT_SECRET": "j" * 64,
        "CHAQIMCHI_PORTAL_JWT_SECRET": "q" * 64,
        "CHAQIMCHI_OWNER_TELEGRAM_TOKEN": "123456789:" + "x" * 35,
        "CHAQIMCHI_TELEGRAM_BOT_USERNAME": "chaqimchi_bot",
        "CHAQIMCHI_TELEGRAM_WEBHOOK_SECRET": "w" * 64,
        "CHAQIMCHI_TELEGRAM_LEAD_CHAT_IDS": "5476913898",
        "CHAQIMCHI_SOTQIN_RELEASE_URL": "https://chaqimchi.uz/releases/sotqin.tar.gz",
        "CHAQIMCHI_SOTQIN_RELEASE_SHA256": "a" * 64,
    }


def test_secure_cloud_env_passes_with_only_optional_warnings() -> None:
    errors, warnings = validate(secure_env())

    assert errors == []
    assert any("N100" in item for item in warnings)
    assert any("Payme/Click" in item for item in warnings)


def test_placeholder_and_missing_lead_recipient_fail_closed() -> None:
    values = secure_env()
    values["POSTGRES_PASSWORD"] = "GENERATE_A_LONG_RANDOM_PASSWORD"
    values.pop("CHAQIMCHI_TELEGRAM_LEAD_CHAT_IDS")

    errors, _warnings = validate(values)

    assert any("POSTGRES_PASSWORD placeholder" in item for item in errors)
    assert any("Telegram chat ID" in item for item in errors)


def test_bad_release_hash_and_non_https_public_url_fail() -> None:
    values = secure_env()
    values["CHAQIMCHI_PUBLIC_URL"] = "http://localhost:8750"
    values["CHAQIMCHI_SOTQIN_RELEASE_SHA256"] = "not-a-hash"

    errors, _warnings = validate(values)

    assert any("PUBLIC_URL" in item for item in errors)
    assert any("SHA-256" in item for item in errors)
