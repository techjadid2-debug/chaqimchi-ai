#!/usr/bin/env python3
"""Benchmark va 72 soatlik soak hisobotidan sotuv qabul faylini yaratadi.

Ikki apparat yo'li uchun ishlaydi:

    # Chaqimchi Box (N100)
    python scripts/accept_n100_pilot.py --benchmark b.json --soak s.json \
        --approved-by "Ism" --output acceptance.json

    # Mijozning Windows kompyuteri (asosiy mahsulot)
    python scripts/accept_n100_pilot.py --platform windows \
        --benchmark benchmark-windows.json --soak soak-windows.json \
        --daily-count-delta 4.2 --clip-delivered --ota-ok \
        --approved-by "Ism" --output acceptance-windows.json

Windows yo'lida uchta mezonni skript o'lchay olmaydi — ularni do'konda
odam tekshiradi va shu bayroqlar bilan tasdiqlaydi (`docs/DOKON_MVP.md`):
kunlik sonning qo'lda sanash bilan farqi, hodisa klipi cloudga yetib
borgani va masofadan yangilanish o'tgani.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from chaqimchi_ai.pilot_acceptance import WINDOWS_PROFILE, validate_n100_acceptance  # noqa: E402
from chaqimchi_ai.sotqin_profile import HARDWARE_PROFILE  # noqa: E402


def _read(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Pilotni sotuvga qabul qilish")
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--soak", type=Path, required=True)
    parser.add_argument("--approved-by", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--platform",
        choices=("n100", "windows"),
        default="n100",
        help="qaysi apparat yo'li sinalgan",
    )
    parser.add_argument(
        "--daily-count-delta",
        type=float,
        default=None,
        help="kunlik kirish soni qo'lda sanashdan necha foiz farq qildi (windows)",
    )
    parser.add_argument(
        "--clip-delivered",
        action="store_true",
        help="hodisa klipi cloudga yetib bordi va owner panelda ochildi (windows)",
    )
    parser.add_argument(
        "--ota-ok",
        action="store_true",
        help="masofadan yangilanish sinovdan o'tdi (windows)",
    )
    args = parser.parse_args(argv)

    payload = {
        "schema_version": 1,
        "hardware_profile": WINDOWS_PROFILE if args.platform == "windows" else HARDWARE_PROFILE,
        "approved_by": args.approved_by.strip(),
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "benchmark_sha256": _sha256(args.benchmark),
            "soak_sha256": _sha256(args.soak),
        },
        "benchmark": _read(args.benchmark),
        "soak": _read(args.soak),
    }
    if args.platform == "windows":
        # Ochiq yozib qoldiriladi: keyin "bu tekshirilganmi?" degan savol
        # tug'ilmasin va qabul faylining o'zi javob bersin.
        payload["field_checks"] = {
            "daily_count_delta_percent": args.daily_count_delta,
            "clip_delivered": bool(args.clip_delivered),
            "ota_update_ok": bool(args.ota_ok),
        }
    result = validate_n100_acceptance(payload)
    if not result["ok"]:
        for reason in result["reasons"]:
            print(f"XATO: {reason}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Qabul qilindi: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
