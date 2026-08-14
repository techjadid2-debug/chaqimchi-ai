#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from chaqimchi_ai.model_bundle import verify_model_manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    errors = verify_model_manifest(args.manifest)
    if errors:
        parser.error("; ".join(errors))
    print(f"Model bundle tasdiqlandi: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
