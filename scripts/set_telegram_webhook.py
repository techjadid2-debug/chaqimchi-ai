#!/usr/bin/env python3
"""Telegram webhook'ni bitta buyruqda o'rnatadi.

Ilgari bu qadam runbook'da qo'lda curl edi va ko'chishda unutilishi oson
edi — bot jimgina "o'lik" bo'lib qolardi.

Ishlatish (server yoki lokal, .env.production yonida):

    python scripts/set_telegram_webhook.py                # .env.production dan o'qiydi
    python scripts/set_telegram_webhook.py --check        # faqat holatni ko'rsatadi

Webhook manzili: {CHAQIMCHI_API_URL yoki CHAQIMCHI_PUBLIC_URL}/api/v1/telegram/webhook
Secret: CHAQIMCHI_TELEGRAM_WEBHOOK_SECRET (Telegram har so'rovda qaytaradi,
cloud uni tekshiradi — begona POST o'tmaydi).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path


def read_env(path: Path) -> dict:
    values: dict = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def call(token: str, method: str, params: dict | None = None) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(params or {}).encode() if params else None
    with urllib.request.urlopen(url, data=data, timeout=20) as response:  # noqa: S310 - HTTPS
        return json.loads(response.read())


def main() -> int:
    parser = argparse.ArgumentParser(description="Telegram webhook o'rnatish")
    parser.add_argument("--env-file", type=Path, default=Path(".env.production"))
    parser.add_argument("--check", action="store_true", help="faqat joriy holat")
    args = parser.parse_args()

    env = {**read_env(args.env_file)}
    import os

    for key in (
        "CHAQIMCHI_OWNER_TELEGRAM_TOKEN",
        "CHAQIMCHI_CLOUD_TELEGRAM_TOKEN",
        "CHAQIMCHI_TELEGRAM_WEBHOOK_SECRET",
        "CHAQIMCHI_API_URL",
        "CHAQIMCHI_PUBLIC_URL",
    ):
        env.setdefault(key, os.environ.get(key, ""))

    token = env.get("CHAQIMCHI_OWNER_TELEGRAM_TOKEN") or env.get("CHAQIMCHI_CLOUD_TELEGRAM_TOKEN")
    if not token:
        print("XATO: bot tokeni topilmadi (CHAQIMCHI_OWNER_TELEGRAM_TOKEN)")
        return 1

    if args.check:
        info = call(token, "getWebhookInfo")["result"]
        print(f"Joriy webhook: {info.get('url') or '(o`rnatilmagan)'}")
        if info.get("last_error_message"):
            print(f"Oxirgi xato: {info['last_error_date']}: {info['last_error_message']}")
        print(f"Kutilayotgan yangilanishlar: {info.get('pending_update_count', 0)}")
        return 0

    base = (env.get("CHAQIMCHI_API_URL") or env.get("CHAQIMCHI_PUBLIC_URL") or "").rstrip("/")
    secret = env.get("CHAQIMCHI_TELEGRAM_WEBHOOK_SECRET", "")
    if not base.startswith("https://"):
        print("XATO: CHAQIMCHI_API_URL yoki CHAQIMCHI_PUBLIC_URL https bo'lishi kerak")
        return 1
    if len(secret) < 32:
        print("XATO: CHAQIMCHI_TELEGRAM_WEBHOOK_SECRET kamida 32 belgi bo'lsin")
        return 1

    webhook = f"{base}/api/v1/telegram/webhook"
    result = call(
        token,
        "setWebhook",
        {"url": webhook, "secret_token": secret, "drop_pending_updates": "false"},
    )
    if not result.get("ok"):
        print(f"XATO: {result}")
        return 1
    print(f"OK: webhook o'rnatildi → {webhook}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
