#!/usr/bin/env python3
"""
Laptopda tez sinov: namuna rasmdan yuz + embedding + cosine tekshiruvi.

  .venv/bin/python scripts/quick_face_test.py

O‘z rasmingiz:
  .venv/bin/python scripts/quick_face_test.py /yo'l/sizning.jpg
"""

from __future__ import annotations

import argparse
import logging
import sys
import urllib.request
from pathlib import Path

import cv2
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(message)s")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "image",
        nargs="?",
        default=None,
        help="BGR rasm fayli; berilmasa OpenCV lena yuklanadi",
    )
    args = parser.parse_args()

    from chaqimchi_ai.face_engine import FaceEngine

    if args.image:
        path = Path(args.image)
        if not path.is_file():
            logging.error("Fayl topilmadi: %s", path)
            return 1
        img = cv2.imread(str(path))
    else:
        path = Path(__file__).resolve().parent.parent / "test_data_lena.jpg"
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            url = "https://raw.githubusercontent.com/opencv/opencv/4.x/samples/data/lena.jpg"
            logging.info("Yuklanmoqda: %s", url)
            urllib.request.urlretrieve(url, path)
        img = cv2.imread(str(path))

    if img is None:
        logging.error("Rasm o‘qilmadi.")
        return 1

    logging.info("FaceEngine yuklanmoqda (birinchida modellar ~/.insightface ga tushadi)...")
    eng = FaceEngine()
    emb = eng.extract_primary_embedding(img)
    if emb is None:
        logging.error("Yuz topilmadi.")
        return 2

    logging.info("Embedding: %s", emb.shape)
    res = eng.compare_faces(emb, [emb], threshold=0.4)
    logging.info("O‘z-o‘ziga cosine: %.4f | mos: %s", float(res.scores[0]), bool(res.matched_mask[0]))
    rng = np.random.randn(512).astype(np.float32)
    rng /= np.linalg.norm(rng) + 1e-8
    res2 = eng.compare_faces(emb, [rng], threshold=0.4)
    logging.info("Tasodifiy vektor cosine: %.4f | mos: %s", float(res2.scores[0]), bool(res2.matched_mask[0]))
    logging.info("OK — yuz tanish yadrosi ishlayapti.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
