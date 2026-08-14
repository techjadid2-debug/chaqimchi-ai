#!/usr/bin/env python3
"""Benchmark va 72 soatlik soak hisobotidan sotuv qabul faylini yaratadi."""

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

from chaqimchi_ai.pilot_acceptance import validate_n100_acceptance  # noqa: E402
from chaqimchi_ai.sotqin_profile import HARDWARE_PROFILE  # noqa: E402


def _read(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Sotqin N100 pilotini qabul qilish")
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--soak", type=Path, required=True)
    parser.add_argument("--approved-by", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    payload = {
        "schema_version": 1,
        "hardware_profile": HARDWARE_PROFILE,
        "approved_by": args.approved_by.strip(),
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "benchmark_sha256": _sha256(args.benchmark),
            "soak_sha256": _sha256(args.soak),
        },
        "benchmark": _read(args.benchmark),
        "soak": _read(args.soak),
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
