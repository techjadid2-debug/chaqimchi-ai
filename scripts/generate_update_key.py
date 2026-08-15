#!/usr/bin/env python3
"""OTA relizlarini imzolash uchun Ed25519 kalit juftligini yaratadi.

Ishlatish:

    python scripts/generate_update_key.py

**Maxfiy kalit repo daraxtidan tashqarida** turadi (`~/.chaqimchi/`).  Bu
ataylab: `.gitignore` ga ishonish yetarli emas — `git add -f`, repo
ildizidan olingan `tar`, yoki Docker build konteksti uni baribir ilib
ketishi mumkin.  Fayl tizimida boshqa joyda bo'lsa, bunday yo'l umuman yo'q.

**Ochiq kalit repoga commit qilinadi** (`deploy/update-public.pem`) va reliz
paketi ichida qurilmaga boradi.  `install_sotqin.sh` uni
`/etc/chaqimchi/update-public.pem` ga bir marta yozadi va **almashtirmaydi**.

Nima uchun shunday: birinchi o'rnatish baribir cloudga ishonadi (arxiv
HTTPS + SHA-256 bilan olinadi).  Lekin kalit o'rnatishda qotirilgach,
**keyinchalik cloud buzilsa ham** hujumchi imzo yasay olmaydi va qurilma
eski kodda qolaveradi.  Agar kalit har yangilanishda cloud'dan olinsa, bu
xossa butunlay yo'qoladi va Ed25519 qatlami qimmat checksum'ga aylanadi.

Kalit CI'ga qo'yilmaydi.  Bugungi miqyosda GitHub Actions'ga imzo siri
berish — GitHub mijoz qurilmasiga root kod yubora oladi degani.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
import sys
from pathlib import Path
from typing import Optional, Sequence

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

DEFAULT_PRIVATE = Path.home() / ".chaqimchi" / "sotqin-release-signing.pem"
DEFAULT_PUBLIC = BASE_DIR / "deploy" / "update-public.pem"


def fingerprint(public_pem: bytes) -> str:
    """Kalitni ko'z bilan solishtirish uchun qisqa barmoq izi."""
    return base64.b32encode(hashlib.sha256(public_pem).digest()[:10]).decode("ascii")


def generate(private_path: Path, public_path: Path) -> str:
    if private_path.exists():
        raise FileExistsError(
            f"{private_path} allaqachon bor. Uni almashtirsangiz mavjud qurilmalar "
            "yangilanmay qoladi — avval eskisini zaxiralang va qo'lda o'chiring."
        )
    key = Ed25519PrivateKey.generate()
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        # Parolsiz: demo kechasi parol so'rovi hech narsa bermaydi va uni
        # albatta chetlab o'tishadi.  Himoya — fayl huquqi va zaxira.
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    private_path.parent.mkdir(parents=True, exist_ok=True)
    # Avval huquqni qo'yamiz, keyin yozamiz — oraliqda fayl ochiq turmasin.
    handle = os.open(private_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(handle, "wb") as file:
        file.write(private_pem)

    public_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.write_bytes(public_pem)
    return fingerprint(public_pem)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private", type=Path, default=DEFAULT_PRIVATE)
    parser.add_argument("--public", type=Path, default=DEFAULT_PUBLIC)
    args = parser.parse_args(argv)

    try:
        mark = generate(args.private, args.public)
    except FileExistsError as exc:
        print(f"XATO: {exc}", file=sys.stderr)
        return 1

    print(f"Maxfiy kalit : {args.private}  (0600)")
    print(f"Ochiq kalit  : {args.public}")
    print(f"Barmoq izi   : {mark}")
    print()
    print("Endi darhol:")
    print("  1. Maxfiy kalitni parol menejeriga zaxiralang.")
    print("     Uni yo'qotsangiz mavjud qurilmalarni boshqa yangilay olmaysiz.")
    print(f"  2. Ochiq kalitni commit qiling: git add -f {args.public}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
