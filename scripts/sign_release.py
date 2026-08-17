#!/usr/bin/env python3
"""Reliz arxivini imzolaydi va qurilma kutgan manifestni yozadi.

    python scripts/sign_release.py releases/chaqimchi-sotqin-0.6.0.tar.gz

Uchta narsa ataylab shunday:

1. **Imzolovchi tekshiruvchining o'z funksiyasini import qiladi**
   (`canonical_manifest_payload`).  Bayt tartibi butun tizimda bitta joyda
   yozilgan va bu yerda `json.dumps` umuman yo'q.  Aks holda `sort_keys`
   yoki `separators` ni sal boshqacha yozib qo'yish yetardi va qurilma
   `"Release imzosi yaroqsiz"` deb rad etardi — sababini aytmasdan.
2. **Versiya arxiv ichidan tekshiriladi.**  Fayl nomi `0.6.0` bo'lib,
   ichidagi kod `0.5.0` bo'lishi mumkin — diskda aynan shunday tarball
   topilgan va u mijozga ketardi.
3. **Yozgandan keyin o'zini tekshiradi** — aynan qurilmadagi ochiq kalit
   bilan.  Noto'g'ri kalit bilan imzolangani noutbukda ma'lum bo'ladi,
   obyektda emas.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import tarfile
from pathlib import Path
from typing import Optional, Sequence

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from chaqimchi_ai.signed_update import (
    UpdateVerificationError,
    canonical_manifest_payload,
    sha256_file,
    verify_release_manifest,
)

DEFAULT_PRIVATE = Path.home() / ".chaqimchi" / "sotqin-release-signing.pem"
DEFAULT_PUBLIC = BASE_DIR / "deploy" / "update-public.pem"

#: `signed_update.verify_release_manifest` qabul qiladigan belgilar.
VERSION_PATTERN = re.compile(r"^[A-Za-z0-9.\-_]+$")

#: `chaqimchi-sotqin-0.6.0.tar.gz` va `chaqimchi-windows-0.7.0.exe`.
#: Windows o'rnatuvchisi ham xuddi shu imzo yo'lidan o'tadi: u mijoz
#: kompyuterida **administrator huquqi** bilan bajariladi, ya'ni
#: tekshirilmagan fayl qurilmani butunlay topshirish demak.
ARCHIVE_PATTERN = re.compile(
    r"^chaqimchi-(sotqin|lite|windows)-(?P<version>.+)\.(?:tar\.gz|exe)$"
)

VERSION_IN_SOURCE = re.compile(r"^__version__\s*=\s*[\"'](?P<version>[^\"']+)[\"']", re.M)


def version_from_name(archive: Path) -> str:
    match = ARCHIVE_PATTERN.match(archive.name)
    if not match:
        raise ValueError(f"Arxiv nomi kutilgan shaklda emas: {archive.name}")
    return match.group("version")


def version_inside(archive: Path) -> Optional[str]:
    """Arxiv ichidagi `chaqimchi_ai/__init__.py` dagi versiya.

    Topilmasa `None` — bu xato emas, `chaqimchi-lite` paketida boshqacha
    tuzilma bo'lishi mumkin.  `.exe` ham `None` qaytaradi: u tar arxiv
    emas, ichini ochib bo'lmaydi.  Bunday holda nomdagi versiyaga
    ishoniladi va uni `build_windows_payload.py` `__version__` dan qo'yadi.
    """
    if archive.suffix.lower() == ".exe":
        return None
    with tarfile.open(archive, "r:gz") as package:
        for member in package.getmembers():
            if not member.isfile():
                continue
            parts = Path(member.name).parts
            if parts[-2:] != ("chaqimchi_ai", "__init__.py"):
                continue
            handle = package.extractfile(member)
            if handle is None:
                return None
            found = VERSION_IN_SOURCE.search(handle.read().decode("utf-8", "replace"))
            return found.group("version") if found else None
    return None


def build_manifest(
    archive: Path,
    *,
    version: str,
    product: str,
    target_arch: str,
    private_key: Ed25519PrivateKey,
) -> dict:
    manifest = {
        "schema_version": 2,
        "product": product,
        "target_arch": target_arch,
        "version": version,
        "sha256": sha256_file(archive),
    }
    signature = private_key.sign(canonical_manifest_payload(manifest))
    manifest["signature"] = base64.b64encode(signature).decode("ascii")
    return manifest


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--private-key", type=Path, default=DEFAULT_PRIVATE)
    parser.add_argument("--public-key", type=Path, default=DEFAULT_PUBLIC)
    # Standart qiymat YO'Q — mahsulot fayl nomidan aniqlanadi.  Ilgari
    # default "chaqimchi-sotqin" edi va Windows relizi bir marta noto'g'ri
    # mahsulot bilan imzolanib ketgan (2026-08-17, ushlab qolindi).
    parser.add_argument("--product", default=None)
    parser.add_argument("--target-arch", default="x86_64")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.product is None:
        name = args.archive.name
        args.product = next(
            (prefix for prefix in ("chaqimchi-windows", "chaqimchi-sotqin", "chaqimchi-lite")
             if name.startswith(prefix + "-")),
            None,
        )
        if args.product is None:
            print(
                f"XATO: fayl nomidan mahsulot aniqlanmadi: {name}\n"
                "Nom chaqimchi-windows-X.Y.Z.exe yoki chaqimchi-sotqin-X.Y.Z.tar.gz "
                "ko'rinishida bo'lsin, yoki --product bering.",
                file=sys.stderr,
            )
            return 1

    if not args.archive.is_file():
        print(f"XATO: arxiv topilmadi: {args.archive}", file=sys.stderr)
        return 1
    if not args.private_key.is_file():
        print(
            f"XATO: maxfiy kalit topilmadi: {args.private_key}\n"
            "Avval: python scripts/generate_update_key.py",
            file=sys.stderr,
        )
        return 1

    try:
        version = version_from_name(args.archive)
    except ValueError as exc:
        print(f"XATO: {exc}", file=sys.stderr)
        return 1
    if not VERSION_PATTERN.match(version):
        print(f"XATO: versiya qurilma qabul qilmaydigan belgilar bilan: {version}", file=sys.stderr)
        return 1

    inside = version_inside(args.archive)
    if inside is not None and inside != version:
        print(
            f"XATO: arxiv nomi {version}, ichidagi kod esa {inside}.\n"
            "Paketni qayta quring: scripts/build_sotqin_release.sh",
            file=sys.stderr,
        )
        return 1

    private_key = serialization.load_pem_private_key(args.private_key.read_bytes(), password=None)
    if not isinstance(private_key, Ed25519PrivateKey):
        print("XATO: maxfiy kalit Ed25519 emas", file=sys.stderr)
        return 1

    manifest = build_manifest(
        args.archive,
        version=version,
        product=args.product,
        target_arch=args.target_arch,
        private_key=private_key,
    )
    # `with_suffix()` ishlatib bo'lmaydi: `chaqimchi-windows-0.7.0.exe` da
    # oxirgi "suffix" — `.0`, ya'ni natija `chaqimchi-windows-0.7.json`
    # bo'lib ketardi va qurilma manifestni topolmasdi.  Kengaytmani
    # nomdan aniq kesamiz.
    output = args.output
    if output is None:
        stem = re.sub(r"\.(?:tar\.gz|exe)$", "", args.archive.name)
        output = args.archive.with_name(f"{stem}.json")
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # O'z-o'zini tekshirish: aynan qurilmadagi ochiq kalit bilan.
    try:
        verify_release_manifest(args.archive, output, args.public_key)
    except UpdateVerificationError as exc:
        output.unlink(missing_ok=True)
        print(
            f"XATO: imzolangan manifest tekshiruvdan o'tmadi: {exc}\n"
            f"Maxfiy kalit {args.public_key} ga mos kelmasligi mumkin.",
            file=sys.stderr,
        )
        return 1

    print(f"Manifest : {output}")
    print(f"Versiya  : {version}  ({args.product}, {args.target_arch})")
    print(f"SHA-256  : {manifest['sha256']}")
    print()
    print("Serverga ikkala faylni ham qo'ying:")
    print(f"  scp {args.archive} {output} <server>:<deploy-dir>/releases/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
