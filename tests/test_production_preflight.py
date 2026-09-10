from cryptography.fernet import Fernet

from scripts.production_preflight import validate


def secure_env() -> dict[str, str]:
    fernet = Fernet.generate_key().decode()
    return {
        "ENES_ENV": "production",
        "ENES_DOMAIN": "enes.uz",
        "ENES_PUBLIC_URL": "https://enes.uz",
        "POSTGRES_DB": "enes",
        "POSTGRES_USER": "enes",
        "POSTGRES_PASSWORD": "p" * 64,
        "DATABASE_URL": "postgresql://enes:secret@postgres:5432/enes",
        "MINIO_ROOT_USER": "minio-user",
        "MINIO_ROOT_PASSWORD": "m" * 64,
        "ENES_S3_ENDPOINT": "http://minio:9000",
        "ENES_S3_ACCESS_KEY": "access-key",
        "ENES_S3_SECRET_KEY": "s" * 64,
        "ENES_S3_BUCKET": "snapshots",
        "ENES_SNAPSHOT_KEY": fernet,
        "ENES_CAMERA_SECRET_KEY": fernet,
        "ENES_CLOUD_ADMIN_KEY": "a" * 64,
        "ENES_OWNER_JWT_SECRET": "j" * 64,
        "ENES_PORTAL_JWT_SECRET": "q" * 64,
        "ENES_OWNER_TELEGRAM_TOKEN": "123456789:" + "x" * 35,
        "ENES_TELEGRAM_BOT_USERNAME": "enes_bot",
        "ENES_TELEGRAM_WEBHOOK_SECRET": "w" * 64,
        "ENES_TELEGRAM_LEAD_CHAT_IDS": "5476913898",
        "ENES_SOTQIN_RELEASE_URL": "https://enes.uz/releases/sotqin.tar.gz",
        "ENES_SOTQIN_RELEASE_SHA256": "a" * 64,
    }


def test_secure_cloud_env_passes_with_only_optional_warnings() -> None:
    errors, warnings = validate(secure_env())

    assert errors == []
    assert any("N100" in item for item in warnings)
    assert any("Payme/Click" in item for item in warnings)


def test_placeholder_and_missing_lead_recipient_fail_closed() -> None:
    values = secure_env()
    values["POSTGRES_PASSWORD"] = "GENERATE_A_LONG_RANDOM_PASSWORD"
    values.pop("ENES_TELEGRAM_LEAD_CHAT_IDS")

    errors, _warnings = validate(values)

    assert any("POSTGRES_PASSWORD placeholder" in item for item in errors)
    assert any("Telegram chat ID" in item for item in errors)


def test_bad_release_hash_and_non_https_public_url_fail() -> None:
    values = secure_env()
    values["ENES_PUBLIC_URL"] = "http://localhost:8750"
    values["ENES_SOTQIN_RELEASE_SHA256"] = "not-a-hash"

    errors, _warnings = validate(values)

    assert any("PUBLIC_URL" in item for item in errors)
    assert any("SHA-256" in item for item in errors)
