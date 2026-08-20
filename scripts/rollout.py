#!/usr/bin/env python3
"""Yangilanishni bosqichma-bosqich tarqatish.

Windows qurilmalari yangilanishni **har 15 daqiqada** so'raydi, ya'ni
buzuq reliz chorak soatda hamma do'konga yetadi.  `docs/RELIZ_VA_OTA.md`
buni qo'lda protsedura sifatida yozib qo'ygan edi: "relizdan oldin barcha
saytlarni `hold` ga o'tkazing, 24 soat kuting, keyin qaytaring".  Yigirma
do'konda bu admin panelda yigirma marta bosish degani — va bir marta
unutish yetarli.

Shu protsedura shu yerda, bitta buyruqda:

    python3 scripts/rollout.py --holat
    python3 scripts/rollout.py --sinov <site_id>   # faqat shu do'kon yangilanadi
    python3 scripts/rollout.py --hammaga           # 24 soatdan keyin
    python3 scripts/rollout.py --toxtat            # favqulodda: hammasini to'xtatish

Muhitdan o'qiladi:
    CHAQIMCHI_ADMIN_URL        standart https://api.chaqimchi.uz
    CHAQIMCHI_CLOUD_ADMIN_KEY  admin kaliti (majburiy)
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Dict, List

import httpx

DEFAULT_URL = "https://api.chaqimchi.uz"
TIMEOUT_SEC = 30


class RolloutError(RuntimeError):
    """Foydalanuvchiga ko'rsatiladigan xato."""


def _client(base_url: str, admin_key: str) -> httpx.Client:
    return httpx.Client(
        base_url=base_url.rstrip("/"),
        headers={"X-Cloud-Admin-Key": admin_key},
        timeout=TIMEOUT_SEC,
    )


def _sites(client: httpx.Client) -> List[Dict[str, Any]]:
    response = client.get("/api/v1/admin/sites")
    if response.status_code == 401 or response.status_code == 403:
        raise RolloutError("Admin kaliti qabul qilinmadi (CHAQIMCHI_CLOUD_ADMIN_KEY)")
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        raise RolloutError("Kutilmagan javob: saytlar ro'yxati emas")
    return data


def _channel(site: Dict[str, Any]) -> str:
    """Obyektning siyosati ro'yxat javobining o'zida keladi.

    `list_sites` `SELECT * FROM sites` qiladi, `update_channel` esa aynan
    shu jadvalda — ya'ni har sayt uchun alohida so'rov kerak emas.
    Bo'sh bo'lsa `auto` (server ham shunday hisoblaydi).
    """
    return str(site.get("update_channel") or "auto")


def _device_versions(client: httpx.Client, site_id: str) -> str:
    """Qurilmalardagi haqiqiy versiya — tarqatish yetganini shundan bilamiz."""
    try:
        response = client.get(f"/api/v1/admin/sites/{site_id}")
        response.raise_for_status()
        devices = response.json().get("devices") or []
    except (httpx.HTTPError, ValueError):
        return "?"
    versions = sorted({str(d.get("app_version") or "—") for d in devices})
    return ", ".join(versions) if versions else "qurilma yo'q"


def _set_policy(client: httpx.Client, site_id: str, channel: str) -> None:
    response = client.put(
        f"/api/v1/admin/sites/{site_id}/update-policy",
        json={"channel": channel},
    )
    response.raise_for_status()


def _paused(client: httpx.Client) -> bool:
    response = client.get("/api/v1/admin/updates-paused")
    response.raise_for_status()
    return bool(response.json().get("paused"))


def _set_paused(client: httpx.Client, paused: bool) -> None:
    response = client.put("/api/v1/admin/updates-paused", json={"paused": paused})
    response.raise_for_status()


def show_status(client: httpx.Client) -> int:
    sites = _sites(client)
    if _paused(client):
        print("DIQQAT: yangilanish tarqatish GLOBAL to'xtatilgan (--davom bilan yoqiladi)")
    if not sites:
        print("Obyekt yo'q.")
        return 0
    print(f"{'Obyekt':<32} {'Siyosat':<9} {'Qurilma versiyasi':<20} ID")
    for site in sites:
        site_id = str(site.get("id") or site.get("site_id") or "")
        name = str(site.get("name") or site_id)[:30]
        versions = _device_versions(client, site_id)[:18]
        print(f"{name:<32} {_channel(site):<9} {versions:<20} {site_id}")
    return 0


def canary(client: httpx.Client, site_id: str) -> int:
    """Faqat bitta obyekt yangilansin, qolganlari kutsin."""
    sites = _sites(client)
    known = {str(site.get("id") or site.get("site_id")) for site in sites}
    if site_id not in known:
        raise RolloutError(f"Bunday obyekt yo'q: {site_id}")
    held = 0
    for site in sites:
        current = str(site.get("id") or site.get("site_id"))
        channel = "auto" if current == site_id else "hold"
        _set_policy(client, current, channel)
        held += channel == "hold"
    print(f"✓ Sinov obyekti: {site_id} (auto)")
    print(f"✓ Kutayotgan obyektlar: {held} ta (hold)")
    print()
    print("24 soat kuzating: panel ochiladimi, hodisalar kelyaptimi,")
    print("qurilma versiyasi yangilandimi. Muammo bo'lmasa:")
    print("  python3 scripts/rollout.py --hammaga")
    return 0


def everyone(client: httpx.Client) -> int:
    sites = _sites(client)
    for site in sites:
        _set_policy(client, str(site.get("id") or site.get("site_id")), "auto")
    print(f"✓ {len(sites)} ta obyekt 'auto' ga qaytarildi — 15 daqiqada yangilanadi.")
    return 0


def pause(client: httpx.Client, paused: bool) -> int:
    _set_paused(client, paused)
    if paused:
        print("✓ Yangilanish tarqatish TO'XTATILDI — hech bir qurilma yangi paket olmaydi.")
        print("  Qaytarish: python3 scripts/rollout.py --davom")
    else:
        print("✓ Yangilanish tarqatish yoqildi.")
    return 0


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--holat", action="store_true", help="obyektlar va siyosatlari")
    group.add_argument("--sinov", metavar="SITE_ID", help="faqat shu obyekt yangilansin")
    group.add_argument("--hammaga", action="store_true", help="hammasini 'auto' ga qaytarish")
    group.add_argument("--toxtat", action="store_true", help="tarqatishni butunlay to'xtatish")
    group.add_argument("--davom", action="store_true", help="tarqatishni qayta yoqish")
    parser.add_argument("--url", default=os.environ.get("CHAQIMCHI_ADMIN_URL", DEFAULT_URL))
    args = parser.parse_args(argv)

    admin_key = os.environ.get("CHAQIMCHI_CLOUD_ADMIN_KEY", "").strip()
    if not admin_key:
        print("CHAQIMCHI_CLOUD_ADMIN_KEY berilishi shart", file=sys.stderr)
        return 1

    try:
        with _client(args.url, admin_key) as client:
            if args.holat:
                return show_status(client)
            if args.sinov:
                return canary(client, args.sinov)
            if args.hammaga:
                return everyone(client)
            return pause(client, paused=bool(args.toxtat))
    except RolloutError as exc:
        print(f"XATO: {exc}", file=sys.stderr)
        return 1
    except httpx.HTTPError as exc:
        print(f"XATO: cloud bilan aloqa: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
