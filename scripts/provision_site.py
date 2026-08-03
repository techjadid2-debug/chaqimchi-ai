#!/usr/bin/env python3
"""Yangi mijoz (sayt) yaratish — cloud admin CLI."""

from __future__ import annotations

import argparse
import json
import os
import sys

import httpx

DEFAULT_URL = os.environ.get("CHAQIMCHI_CLOUD_URL", "http://127.0.0.1:8750")


def main() -> int:
    parser = argparse.ArgumentParser(description="Chaqimchi — mijoz ochish")
    parser.add_argument("name", help="Mijoz / joy nomi")
    parser.add_argument(
        "--plan",
        choices=["starter", "business", "enterprise"],
        default="business",
    )
    parser.add_argument("--months", type=int, default=12)
    parser.add_argument("--cloud-url", default=DEFAULT_URL)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    admin_key = os.environ.get("CHAQIMCHI_CLOUD_ADMIN_KEY", "").strip()
    if not admin_key:
        print("CHAQIMCHI_CLOUD_ADMIN_KEY muhit o‘zgaruvchisi kerak", file=sys.stderr)
        return 1

    url = args.cloud_url.rstrip("/")
    with httpx.Client(timeout=30.0) as client:
        r = client.post(
            f"{url}/api/v1/admin/sites",
            headers={"X-Cloud-Admin-Key": admin_key},
            json={
                "name": args.name,
                "plan": args.plan,
                "subscription_months": args.months,
            },
        )
        r.raise_for_status()
        data = r.json()

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(f"Sayt: {data['site_id']}")
        print(f"Tarif: {data['plan']} — {data['subscription_until']}")
        print(f"Pairing kod (48 soat): {data['pairing_code']}")
        print(f"O‘rnatish narxi (reja): {data['limits']['install_price_uzs']:,} so‘m")
        print(f"Oylik: {data['limits']['monthly_price_uzs']:,} so‘m")
        print("\nEdge config.yaml:")
        print("license:")
        print("  enabled: true")
        print(f"  cloud_url: \"{url}\"")
        print(f"  pairing_code: \"{data['pairing_code']}\"")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
