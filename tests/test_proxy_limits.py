"""Proxy (Caddy) limitlari app limitlaridan katta ekanini tekshiradi.

Bu sinf testlar umuman yo'q edi va aynan shu tirqishdan jiddiy xato
o'tib ketgan: `cloud/main.py` 50 MB gacha klip qabul qiladi, lekin
`deploy/Caddyfile` `max_size 10MB` bilan turgan.  Haqiqiy hodisa kliplari
15-22 MB chiqadi — Caddy ularni app'gacha yetkazmay 413 qaytarar,
edge 20 urinishdan keyin klipni dead_letter'ga tashlar va "hodisa videosi"
funksiyasi productionda jimgina ishlamas edi.  FastAPI darajasidagi
testlar buni ko'rmaydi, chunki ular proxy'siz ishlaydi — shuning uchun
bu fayl Caddyfile matnini o'zini tekshiradi.
"""

from __future__ import annotations

import re
from pathlib import Path

from cloud.main import CLIP_MAX_BYTES, SNAPSHOT_MAX_BYTES

ROOT = Path(__file__).resolve().parents[1]
CADDYFILE = ROOT / "deploy" / "Caddyfile"

_UNITS = {"KB": 1024, "MB": 1024**2, "GB": 1024**3}


def caddy_max_body_bytes() -> int:
    text = CADDYFILE.read_text(encoding="utf-8")
    match = re.search(r"max_size\s+(\d+)\s*(KB|MB|GB)", text)
    assert match, "Caddyfile'da request_body max_size topilmadi"
    return int(match.group(1)) * _UNITS[match.group(2)]


def test_caddy_limit_klip_limitidan_katta() -> None:
    # Teng bo'lishi ham xato: Content-Length'dan tashqari header/overhead bor.
    assert caddy_max_body_bytes() > CLIP_MAX_BYTES, (
        "deploy/Caddyfile max_size cloud klip limitidan kichik — kliplar "
        "proxy'da 413 bilan qaytadi va hech qachon cloudga yetmaydi"
    )


def test_klip_limiti_snapshot_limitidan_katta() -> None:
    # Sanity: konstantalar chalkashtirilmaganini ushlab turadi.
    assert CLIP_MAX_BYTES > SNAPSHOT_MAX_BYTES
