#!/usr/bin/env python3
"""Anti-spoof sifatini O‘Z suratlaringizda o‘lchash va chegara tanlash.

Tayyorlash — ikki papka:

    data/antispoof/real/   — tirik odam suratlari (kameraga qarab turgan)
    data/antispoof/spoof/  — hujum suratlari: telefon ekranidagi yuzni
                             kameraga ko‘rsatib olingan kadr, bosma qog‘oz va h.k.

Har ikkalasida kamida 20 tadan surat bo‘lsin va ular **shu obyektning
kamerasi bilan** olingan bo‘lsin — boshqa qurilmada o‘lchangan raqamlar
sizning joyingizga o‘tmaydi.

Ishga tushirish:

    python scripts/validate_antispoof.py
    python scripts/validate_antispoof.py --backend onnx --model models/antispoof.onnx
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Tuple

import cv2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chaqimchi_ai.antispoof import build_checker  # noqa: E402
from chaqimchi_ai.face_engine import FaceEngine  # noqa: E402
from chaqimchi_ai.settings import load_app_settings  # noqa: E402

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def _face_crop(engine: FaceEngine, img, margin: float = 0.2):
    """Rasmdagi eng katta yuzni chekka bilan kesib qaytaradi.

    Diqqat: `analyze_frame` preprocess qilingan (kichraytirilgan) tasvir
    koordinatalarini qaytaradi, shuning uchun kesish ham o‘shanda bajariladi.
    """
    work = engine.preprocess_image(img)
    faces, _ = engine.analyze_frame(img)
    if not faces:
        return None
    face = max(faces, key=lambda f: (f["bbox"][2] - f["bbox"][0]) * (f["bbox"][3] - f["bbox"][1]))
    x1, y1, x2, y2 = face["bbox"]
    pad = int(max(x2 - x1, y2 - y1) * margin)
    h, w = work.shape[:2]
    return work[
        max(0, int(y1) - pad) : min(h, int(y2) + pad),
        max(0, int(x1) - pad) : min(w, int(x2) + pad),
    ]


def _score_dir(engine: FaceEngine, checker, folder: Path) -> Tuple[List[float], int]:
    """Papkadagi har bir suratning tiriklik balli. Qaytaradi: (ballar, o‘tkazilgan)."""
    scores: List[float] = []
    skipped = 0
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        img = cv2.imread(str(path))
        if img is None:
            skipped += 1
            continue
        crop = _face_crop(engine, img)
        if crop is None or crop.size == 0:
            print(f"  yuz topilmadi: {path.name}")
            skipped += 1
            continue
        scores.append(checker.check(crop).score)
    return scores, skipped


def _rates(real: List[float], spoof: List[float], threshold: float) -> Tuple[float, float]:
    """(FRR, FAR): tirikni rad etish va soxtani o‘tkazib yuborish ulushi."""
    frr = sum(1 for s in real if s < threshold) / len(real) if real else 0.0
    far = sum(1 for s in spoof if s >= threshold) / len(spoof) if spoof else 0.0
    return frr, far


def main() -> int:
    parser = argparse.ArgumentParser(description="Anti-spoof sifatini o‘lchash")
    parser.add_argument("--real", default="data/antispoof/real", help="Tirik suratlar papkasi")
    parser.add_argument("--spoof", default="data/antispoof/spoof", help="Hujum suratlari papkasi")
    parser.add_argument("--backend", choices=["heuristic", "onnx"], default=None)
    parser.add_argument("--model", default=None, help="ONNX model yo‘li")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    cfg = load_app_settings(ROOT)
    real_dir, spoof_dir = ROOT / args.real, ROOT / args.spoof

    missing = [str(d) for d in (real_dir, spoof_dir) if not d.is_dir()]
    if missing:
        print("Papka topilmadi: " + ", ".join(missing), file=sys.stderr)
        print("\nTayyorlang:", file=sys.stderr)
        print(f"  mkdir -p {args.real} {args.spoof}", file=sys.stderr)
        print("  real/  → tirik odam suratlari", file=sys.stderr)
        print("  spoof/ → telefon ekrani / bosma qog‘ozdagi yuz suratlari", file=sys.stderr)
        return 1

    checker = build_checker(
        backend=args.backend or cfg.antispoof.backend,
        model_path=Path(args.model) if args.model else None,
        min_score=cfg.antispoof.min_score,
        min_blur_variance=cfg.antispoof.min_blur_variance,
        live_index=cfg.antispoof.live_index,
    )
    engine = FaceEngine(
        model_name=cfg.face.model_name,
        det_size=cfg.face.det_size,
        preprocess_max_side=cfg.face.preprocess_max_side,
    )

    print(f"Backend: {checker.method}\n")
    print("Tirik suratlar:")
    real, real_skip = _score_dir(engine, checker, real_dir)
    print("Hujum suratlari:")
    spoof, spoof_skip = _score_dir(engine, checker, spoof_dir)

    if not real or not spoof:
        print("\nHar ikki papkada ham yuz topilgan surat bo‘lishi kerak.", file=sys.stderr)
        return 1

    # Eng yaxshi chegara: FRR + FAR yig'indisi eng kichik bo'lgan nuqta.
    grid = [i / 100 for i in range(1, 100)]
    best = min(grid, key=lambda t: sum(_rates(real, spoof, t)))
    best_frr, best_far = _rates(real, spoof, best)
    cur_frr, cur_far = _rates(real, spoof, cfg.antispoof.min_score)

    report = {
        "backend": checker.method,
        "real_count": len(real),
        "spoof_count": len(spoof),
        "skipped": real_skip + spoof_skip,
        "real_score_min": round(min(real), 4),
        "real_score_avg": round(sum(real) / len(real), 4),
        "spoof_score_max": round(max(spoof), 4),
        "spoof_score_avg": round(sum(spoof) / len(spoof), 4),
        "separation": round(min(real) - max(spoof), 4),
        "current_min_score": cfg.antispoof.min_score,
        "current_frr": round(cur_frr, 4),
        "current_far": round(cur_far, 4),
        "suggested_min_score": best,
        "suggested_frr": round(best_frr, 4),
        "suggested_far": round(best_far, 4),
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print(
        f"\nTirik  : {len(real)} ta, ball {report['real_score_min']}–"
        f"{round(max(real), 4)} (o‘rtacha {report['real_score_avg']})"
    )
    print(
        f"Hujum  : {len(spoof)} ta, ball {round(min(spoof), 4)}–"
        f"{report['spoof_score_max']} (o‘rtacha {report['spoof_score_avg']})"
    )
    print(f"Ajralish: {report['separation']:+.3f}  (musbat bo‘lsa — to‘liq ajratadi)")
    print()
    print(
        f"Hozirgi chegara {cfg.antispoof.min_score}: "
        f"tirikni rad etish {cur_frr:.1%}, soxtani o‘tkazib yuborish {cur_far:.1%}"
    )
    print(
        f"Tavsiya  chegara {best}: "
        f"tirikni rad etish {best_frr:.1%}, soxtani o‘tkazib yuborish {best_far:.1%}"
    )
    print(f"\nconfig.yaml → antispoof.min_score: {best}")

    if report["separation"] <= 0:
        print(
            "\nDIQQAT: ballar ustma-ust tushyapti — bu backend sizning hujum "
            "turingizni ishonchli ajratmayapti. Kirish nazorati uchun "
            "o‘qitilgan model yoki qo‘shimcha tekshiruv (PIN, karta) kerak."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
