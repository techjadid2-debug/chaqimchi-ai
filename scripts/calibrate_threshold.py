#!/usr/bin/env python3
"""Threshold kalibrlash CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chaqimchi_ai.database import FaceDatabase
from chaqimchi_ai.face_engine import FaceEngine
from chaqimchi_ai.settings import load_app_settings
from chaqimchi_ai.threshold_calibration import calibrate_from_gallery, calibrate_from_image_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Chaqimchi AI — threshold kalibrlash")
    parser.add_argument(
        "--dir",
        action="store_true",
        help="data/calibration/ papkasidan (har bir shaxs alohida papka)",
    )
    parser.add_argument("--json", action="store_true", help="JSON chiqish")
    args = parser.parse_args()

    cfg = load_app_settings(ROOT)
    cal_dir = ROOT / cfg.paths.calibration_dir

    if args.dir or (cal_dir.is_dir() and any(cal_dir.iterdir())):
        engine = FaceEngine(
            model_name=cfg.face.model_name,
            det_size=cfg.face.det_size,
            preprocess_max_side=cfg.face.preprocess_max_side,
        )
        report = calibrate_from_image_dir(
            engine, cal_dir, current_threshold=cfg.face.compare_threshold
        )
    else:
        db = FaceDatabase(ROOT / cfg.paths.db_path)
        emb = db.embeddings
        import numpy as np

        report = calibrate_from_gallery(
            emb if emb is not None else np.empty((0, 512)),
            current_threshold=cfg.face.compare_threshold,
        )

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        d = report.to_dict()
        print(f"Tavsiya etilgan threshold: {d['suggested_threshold']}")
        print(f"Hozirgi: {d['current_threshold']}")
        print(f"Usul: {d['method']}")
        print(f"Izoh: {d['notes']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
