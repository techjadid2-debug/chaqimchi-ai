#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    data = json.loads(args.manifest.read_text(encoding="utf-8"))
    if data.get("licensed_for_commercial_use") is not True:
        parser.error("Commercial litsenziya manifestda tasdiqlanmagan")
    if not data.get("license_reference") or "REQUIRED" in data["license_reference"]:
        parser.error("License reference berilmagan")
    for name, expected in data.get("files", {}).items():
        path = args.manifest.parent / name
        if not path.is_file():
            parser.error(f"Model topilmadi: {name}")
        if sha256(path) != str(expected).lower():
            parser.error(f"SHA-256 mos emas: {name}")
    print(f"Model bundle tasdiqlandi: {data.get('bundle')} {data.get('version')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
