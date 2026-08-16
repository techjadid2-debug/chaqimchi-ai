#!/usr/bin/env python3
"""Cloud deploydan oldin production environmentni fail-closed tekshiradi."""

from __future__ import annotations

import argparse
import re
import stat
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import urlparse

from cryptography.fernet import Fernet

PLACEHOLDER_MARKERS = ("GENERATE", "FROM_", "CHANGE_ME", "EXAMPLE", "YOUR_")
SECRET_MIN_LENGTHS = {
    "POSTGRES_PASSWORD": 32,
    "MINIO_ROOT_PASSWORD": 32,
    "CHAQIMCHI_S3_SECRET_KEY": 32,
    "CHAQIMCHI_CLOUD_ADMIN_KEY": 32,
    "CHAQIMCHI_OWNER_JWT_SECRET": 32,
    "CHAQIMCHI_PORTAL_JWT_SECRET": 32,
    "CHAQIMCHI_TELEGRAM_WEBHOOK_SECRET": 32,
}


def read_env(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for number, source in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = source.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"{number}-qator KEY=VALUE ko'rinishida emas")
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _placeholder(value: str) -> bool:
    upper = value.upper()
    return any(marker in upper for marker in PLACEHOLDER_MARKERS)


def _https(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def validate(values: Dict[str, str]) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    def require(key: str) -> str:
        value = values.get(key, "").strip()
        if not value:
            errors.append(f"{key} berilmagan")
        elif _placeholder(value):
            errors.append(f"{key} placeholder bo'lib qolgan")
        return value

    if require("CHAQIMCHI_ENV") != "production":
        errors.append("CHAQIMCHI_ENV aynan production bo'lishi shart")
    domain = require("CHAQIMCHI_DOMAIN")
    if domain.startswith(("http://", "https://")):
        errors.append("CHAQIMCHI_DOMAIN sxemasiz hostname bo'lishi kerak")
    public_url = require("CHAQIMCHI_PUBLIC_URL")
    if public_url and not _https(public_url):
        errors.append("CHAQIMCHI_PUBLIC_URL haqiqiy HTTPS manzil bo'lishi kerak")

    for key in (
        "POSTGRES_DB",
        "POSTGRES_USER",
        "MINIO_ROOT_USER",
        "CHAQIMCHI_S3_ACCESS_KEY",
        "CHAQIMCHI_S3_BUCKET",
        "CHAQIMCHI_S3_ENDPOINT",
        "CHAQIMCHI_OWNER_TELEGRAM_TOKEN",
        "CHAQIMCHI_TELEGRAM_BOT_USERNAME",
    ):
        require(key)
    database_url = require("DATABASE_URL")
    if database_url and not database_url.startswith(("postgresql://", "postgres://")):
        errors.append("DATABASE_URL PostgreSQL manzil bo'lishi shart")

    for key, minimum in SECRET_MIN_LENGTHS.items():
        value = require(key)
        if value and len(value) < minimum:
            errors.append(f"{key} kamida {minimum} belgi bo'lishi shart")

    for key in ("CHAQIMCHI_SNAPSHOT_KEY", "CHAQIMCHI_CAMERA_SECRET_KEY"):
        value = require(key)
        if value:
            try:
                Fernet(value.encode("utf-8"))
            except (TypeError, ValueError):
                errors.append(f"{key} haqiqiy Fernet kaliti emas")

    token = values.get("CHAQIMCHI_OWNER_TELEGRAM_TOKEN", "") or values.get(
        "CHAQIMCHI_CLOUD_TELEGRAM_TOKEN", ""
    )
    if token and not re.fullmatch(r"\d+:[A-Za-z0-9_-]{20,}", token):
        errors.append("Telegram bot tokeni noto'g'ri formatda")
    bot_username = values.get("CHAQIMCHI_TELEGRAM_BOT_USERNAME", "").lstrip("@")
    if bot_username and not re.fullmatch(r"[A-Za-z0-9_]{5,32}", bot_username):
        errors.append("CHAQIMCHI_TELEGRAM_BOT_USERNAME noto'g'ri formatda")
    recipients = values.get("CHAQIMCHI_TELEGRAM_LEAD_CHAT_IDS", "").strip()
    if not recipients:
        errors.append("Lead uchun kamida bitta statik Telegram chat ID berilishi shart")
    elif any(not re.fullmatch(r"-?\d+", item.strip()) for item in recipients.split(",")):
        errors.append("Telegram chat ID'lari vergul bilan ajratilgan sonlar bo'lishi kerak")

    # Sinov eshiklari production'da bo'lishi mumkin emas.  Bular env
    # orqali yoqilgani uchun eng real xavf — "demo paytida qo'yib,
    # o'chirishni unutish".  Cloud lifespan ham xuddi shu tekshiruvni
    # qiladi, lekin preflight muammoni deploy'dan OLDIN ushlaydi.
    if values.get("CHAQIMCHI_OTP_TEST_CODE", "").strip():
        errors.append(
            "CHAQIMCHI_OTP_TEST_CODE production'da taqiqlanadi — hamma "
            "mijozning OTP kodi bitta doimiy qiymat bo'lib qoladi"
        )
    if values.get("CHAQIMCHI_OTP_BYPASS_IDS", "").strip():
        errors.append(
            "CHAQIMCHI_OTP_BYPASS_IDS olib tashlangan — o'rniga admin "
            "panel yoki Telegram bot beradigan kirish havolasini ishlating"
        )

    release_url = require("CHAQIMCHI_SOTQIN_RELEASE_URL")
    release_sha = require("CHAQIMCHI_SOTQIN_RELEASE_SHA256")
    if release_url and not _https(release_url):
        errors.append("CHAQIMCHI_SOTQIN_RELEASE_URL HTTPS bo'lishi shart")
    if release_sha and not re.fullmatch(r"[0-9a-fA-F]{64}", release_sha):
        errors.append("CHAQIMCHI_SOTQIN_RELEASE_SHA256 64 xonali SHA-256 bo'lishi shart")

    if not values.get("CHAQIMCHI_N100_ACCEPTANCE_FILE", "").strip():
        warnings.append("N100 qabul fayli yo'q: public AI funksiyalari sotuvga ochilmaydi")
    if not values.get("CHAQIMCHI_AVAILABLE_FEATURES", "").strip():
        warnings.append("Public AI funksiyalari environmentda yoqilmagan")
    if not any(
        values.get(key, "").strip() for key in ("CHAQIMCHI_PAYME_KEY", "CHAQIMCHI_CLICK_SECRET")
    ):
        warnings.append("Payme/Click ulanmagan: faqat qo'lda to'lov ishlaydi")
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Chaqimchi Cloud production preflight")
    parser.add_argument("--env-file", type=Path, default=Path(".env.production"))
    args = parser.parse_args()
    if not args.env_file.is_file():
        print(f"XATO: {args.env_file} topilmadi")
        return 1
    mode = stat.S_IMODE(args.env_file.stat().st_mode)
    errors, warnings = validate(read_env(args.env_file))
    if mode & 0o077:
        errors.append(f"{args.env_file} ruxsati {mode:o}; 600 bo'lishi shart")
    for warning in warnings:
        print(f"OGOHLANTIRISH: {warning}")
    for error in errors:
        print(f"XATO: {error}")
    if errors:
        return 1
    print("OK: production environment preflight o'tdi")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
