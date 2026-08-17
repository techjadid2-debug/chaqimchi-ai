#!/usr/bin/env python3
"""Yuz tanish modellarini (buffalo_l: SCRFD + ArcFace) yuklab o'rnatadi.

`fetch_retail_model.py` bilan bir xil qoida: checksum'siz hech narsa
o'rnatilmaydi.  Farqi — manifest alohida faylda emas, shu yerda qattiq
yozilgan: skript konteyner ichida yolg'iz ishlaydi va tashqi faylga
bog'lanmasin.

Arxivdan faqat 2 ta model olinadi (det_10g + w600k_r50) — qolgan uchtasi
(yosh-jins, landmark) davomatga kerak emas, ~90 MB joy tejaladi.

Konteynerda (prod):

    docker compose -f docker-compose.contabo.yml --env-file .env.production \
      exec cloud python scripts/fetch_face_models.py

Lokal (test):

    python scripts/fetch_face_models.py --target data/cloud/models/faces

MUHIM: buffalo_l modellari faqat tadqiqot litsenziyasida (InsightFace) —
sotuvga chiqarishdan oldin tijoriy litsenziyali model kerak.  Bu skript
faqat yopiq pilot uchun.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import urllib.request
import zipfile
from pathlib import Path

ARCHIVE_URL = "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip"
ARCHIVE_SHA256 = "80ffe37d8a5940d59a7384c201a2a38d4741f2f3c51eef46ebb28218a7b0ca2f"

#: Arxiv ichidan olinadigan fayllar va ularning sha256 lari.
WANTED = {
    "det_10g.onnx": "5838f7fe053675b1c7a08b633df49e7af5495cee0493c7dcf6697200b85b5b91",
    "w600k_r50.onnx": "4c06341c33c2ca1f86781dab0e829f88ad5b64be9fba56e56bc9ebdefc619e43",
}

DEFAULT_TARGET = os.environ.get("CHAQIMCHI_FACE_MODEL_ROOT", "data/cloud/models/faces")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="buffalo_l modellarini o'rnatadi")
    parser.add_argument("--target", default=DEFAULT_TARGET, help="Model papkasi")
    args = parser.parse_args()

    target = Path(args.target)
    target.mkdir(parents=True, exist_ok=True)

    missing = [name for name in WANTED if not (target / name).is_file()]
    if not missing:
        for name, expected in WANTED.items():
            actual = sha256_file(target / name)
            if actual != expected:
                raise SystemExit(f"XATO: {name} checksum mos emas ({actual})")
        print(f"OK: modellar allaqachon o'rnatilgan: {target}")
        return 0

    # Zip target papkaning o'zida saqlanadi: konteynerda /tmp kichik (64 MB),
    # arxiv esa ~280 MB — faqat volume yoziladi.
    archive = target / "buffalo_l.zip.part"
    print(f"Yuklanmoqda: {ARCHIVE_URL}")
    with urllib.request.urlopen(ARCHIVE_URL, timeout=300) as response:  # noqa: S310 - HTTPS
        with archive.open("wb") as handle:
            while chunk := response.read(1024 * 1024):
                handle.write(chunk)

    actual = sha256_file(archive)
    if actual != ARCHIVE_SHA256:
        archive.unlink(missing_ok=True)
        raise SystemExit(f"XATO: arxiv checksum mos emas: {actual}")

    with zipfile.ZipFile(archive) as bundle:
        for name, expected in WANTED.items():
            staged = target / f"{name}.part"
            with bundle.open(name) as source, staged.open("wb") as sink:
                while chunk := source.read(1024 * 1024):
                    sink.write(chunk)
            digest = sha256_file(staged)
            if digest != expected:
                staged.unlink(missing_ok=True)
                archive.unlink(missing_ok=True)
                raise SystemExit(f"XATO: {name} checksum mos emas: {digest}")
            staged.replace(target / name)
            print(f"OK: {name} ({(target / name).stat().st_size // (1024 * 1024)} MB)")

    archive.unlink(missing_ok=True)
    print(f"Tayyor: {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
