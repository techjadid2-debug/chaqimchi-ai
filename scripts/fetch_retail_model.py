#!/usr/bin/env python3
"""Retail detektor modelini yuklaydi va checksum bo'yicha tekshiradi.

Model repoda saqlanmaydi (ikkilik fayl, litsenziya matni bilan birga keladi),
lekin **tekshirilmagan** model ham o'rnatilmaydi: manifestda sha256 bo'lmasa
skript ishlamaydi.  Bu `signed_update` bilan bir xil qoida — qurilmaga faqat
kim va nima ekani ma'lum bo'lgan fayl tushadi.

Birinchi marta:

    python scripts/fetch_retail_model.py --print-checksums   # yuklab, sha256 chiqaradi
    # chiqqan qiymatlarni models/retail_manifest.json ga yozing va commit qiling
    python scripts/fetch_retail_model.py                     # endi tekshirib o'rnatadi

Model: person-detection-retail-0013, OpenVINO Open Model Zoo, Apache 2.0.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Dict

BASE_DIR = Path(__file__).resolve().parent.parent
MANIFEST = BASE_DIR / "models" / "retail_manifest.json"
TARGET_DIR = BASE_DIR / "models" / "retail"


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def download(url: str) -> bytes:
    if not url.startswith("https://"):
        raise SystemExit(f"Faqat HTTPS: {url}")
    with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310 - HTTPS tekshirildi
        return response.read()


def load_manifest() -> Dict[str, Dict[str, str]]:
    if not MANIFEST.is_file():
        raise SystemExit(f"Manifest topilmadi: {MANIFEST}")
    return json.loads(MANIFEST.read_text(encoding="utf-8"))["files"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--print-checksums",
        action="store_true",
        help="Yuklab, sha256 ni chiqaradi va hech narsa o'rnatmaydi",
    )
    args = parser.parse_args()

    files = load_manifest()
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    failures = []
    verified: Dict[str, bytes] = {}

    for name, entry in files.items():
        print(f"→ {name}", flush=True)
        payload = download(entry["url"])
        digest = sha256(payload)

        if args.print_checksums:
            print(f"   sha256: {digest}")
            continue

        expected = str(entry.get("sha256", "")).strip().lower()
        if not expected:
            failures.append(f"{name}: manifestda sha256 yo'q")
            continue
        if digest != expected:
            failures.append(
                f"{name}: sha256 mos kelmadi\n  kutilgan: {expected}\n  olingan: {digest}"
            )
            continue
        verified[name] = payload
        print(f"   ✓ {len(payload) / 1024:.0f} KB tekshirildi")

    if failures:
        print("\nXATO:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        print("\nModel o'rnatilmadi.", file=sys.stderr)
        return 1
    if not args.print_checksums:
        # Barcha fayl tekshirilmaguncha bittasi ham amaldagi model ustiga
        # yozilmaydi. XML yangi, BIN eski bo'lgan yarim bundle ishlamasin.
        temporary: Dict[str, Path] = {}
        try:
            for name, payload in verified.items():
                path = TARGET_DIR / name
                tmp = path.with_name(f".{path.name}.tmp")
                tmp.write_bytes(payload)
                temporary[name] = tmp
            for name, tmp in temporary.items():
                os.replace(tmp, TARGET_DIR / name)
                print(f"   ✓ {len(verified[name]) / 1024:.0f} KB → models/retail/{name}")
        finally:
            for tmp in temporary.values():
                tmp.unlink(missing_ok=True)
        print(
            f"\nTayyor. config: scene.backend=openvino, scene.model_path=models/retail/{next(iter(files))}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
