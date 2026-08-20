#!/usr/bin/env python3
"""Yuz tanish modellarini yuklab o'rnatadi (OpenVINO Open Model Zoo).

`fetch_retail_model.py` bilan bir xil qoida: checksum'siz hech narsa
o'rnatilmaydi.

Bungacha bu skript InsightFace `buffalo_l` arxivini olardi va u faqat
**tadqiqot litsenziyasida** edi — davomatni pulli tarif ichida sotib
bo'lmasdi.  Endi uchala model ham Apache-2.0:

- `face-detection-retail-0005`        — yuzni topish
- `landmarks-regression-retail-0009`  — 5 tayanch nuqta (tekislash uchun)
- `face-reidentification-retail-0095` — 256 o'lchamli embedding

Har bir model IKKI fayldan iborat (.xml — tuzilma, .bin — og'irliklar);
bittasi yetishmasa OpenVINO uni umuman yuklay olmaydi.

Konteynerda (prod):

    docker compose -f docker-compose.chaqimchi.yml --env-file .env.production \
      exec cloud python scripts/fetch_face_models.py

Lokal (test):

    python scripts/fetch_face_models.py --target data/cloud/models/faces

MUHIM: model almashgani uchun MAVJUD xodim embeddinglari (512 o'lchamli,
ArcFace) yaroqsiz.  O'rnatgandan keyin `scripts/reembed_faces.py` ni
ishga tushiring — saqlangan rasmlardan qayta hisoblanadi.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path

MANIFEST_PATH = Path(__file__).resolve().parents[1] / "models" / "faces_manifest.json"

DEFAULT_TARGET = os.environ.get("CHAQIMCHI_FACE_MODEL_ROOT", "data/cloud/models/faces")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest() -> dict:
    if not MANIFEST_PATH.is_file():
        raise SystemExit(f"XATO: manifest topilmadi: {MANIFEST_PATH}")
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if data.get("license") != "Apache-2.0":
        # Bu tekshiruv ataylab: tijoriy sotuvga yaroqsiz model jimgina
        # qaytib kelmasin.
        raise SystemExit(f"XATO: manifestdagi litsenziya kutilmagan: {data.get('license')}")
    return data


def fetch(url: str, destination: Path) -> None:
    with urllib.request.urlopen(url, timeout=300) as response:  # noqa: S310 - HTTPS
        with destination.open("wb") as handle:
            while chunk := response.read(1024 * 1024):
                handle.write(chunk)


def main() -> int:
    parser = argparse.ArgumentParser(description="Yuz modellarini o'rnatadi (Apache-2.0)")
    parser.add_argument("--target", default=DEFAULT_TARGET, help="Model papkasi")
    parser.add_argument(
        "--force", action="store_true", help="Mavjud fayllarni qayta yuklab oladi"
    )
    args = parser.parse_args()

    manifest = load_manifest()
    target = Path(args.target)
    target.mkdir(parents=True, exist_ok=True)

    for name, entry in manifest["files"].items():
        final = target / name
        expected = entry["sha256"]
        if final.is_file() and not args.force:
            actual = sha256_file(final)
            if actual == expected:
                print(f"OK: {name} allaqachon o'rnatilgan")
                continue
            print(f"OGOHLANTIRISH: {name} checksum mos emas — qayta yuklanadi")

        # `.part` orqali: yarim yuklangan fayl hech qachon model nomida
        # qolmaydi, aks holda xizmat uni yuklashga urinib yiqilardi.
        staged = target / f"{name}.part"
        print(f"Yuklanmoqda: {name}")
        fetch(entry["url"], staged)
        actual = sha256_file(staged)
        if actual != expected:
            staged.unlink(missing_ok=True)
            raise SystemExit(f"XATO: {name} checksum mos emas: {actual}")
        staged.replace(final)
        print(f"OK: {name} ({final.stat().st_size // 1024} KB)")

    print(f"Tayyor: {target}")
    print(
        "\nDIQQAT: model almashgan bo'lsa mavjud xodim rasmlarini qayta "
        "hisoblang:\n    python scripts/reembed_faces.py"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
