#!/usr/bin/env python3
"""N100 haqiqatan nechta kamerani ko'taradi — o'lchov, taxmin emas.

Hozirgi "sekundiga 30 inferens" raqami boshqa modeldan miqyoslangan taxmin.
Unga suyanib mijozga 8 kamera va'da qilish xavfli: qurilma ulgurmasa navbat
o'sadi, hodisa kech keladi va tizim ishlayotgandek ko'rinib, aslida foydasiz
bo'ladi.  Bu skript o'sha raqamni **shu qurilmada** o'lchaydi.

    python scripts/benchmark_n100.py --seconds 60 --cameras 4 --source sample.mp4

Nima o'lchanadi:

1. **Detektor** — bitta inferens qancha vaqt oladi (p50/p95/p99) va sekundiga
   nechta ulguradi.
2. **Barqarorlik** — birinchi va oxirgi uchdan bir qismdagi tezlik farqi.
   Qurilma qizib sekinlashsa 5 soniyalik o'lchov 8 soatlik smena uchun yolg'on.
3. **Kadr yuki** — harakat filtri va buzilish tekshiruvi har kadrda ishlaydi
   (8 kamera × 5 FPS = sekundiga 40 marta), shuning uchun ular ham hisobga
   olinadi.
4. **Dekodlash** — `--source` berilsa haqiqiy oqimdan kadr olish narxi.
5. **Xulosa** — shu raqamlar bilan nechta kamera sotish mumkin.

## O'lchov qachon yolg'on bo'ladi

- **Sun'iy kadrda.**  Bo'sh kadrda detektor hech kim topmaydi va natijani
  dekodlash eng qisqa yo'ldan o'tadi.  Haqiqiy do'kon kadri sekinroq —
  shuning uchun `--source` bilan haqiqiy oqimdan o'lchash afzal.
- **CPU'ga tushib qolganda.**  iGPU drayveri yo'q bo'lsa OpenVINO CPU'da
  ishlaydi va raqam butunlay boshqa ma'no kasb etadi.  Skript buni qattiq
  ogohlantiradi.
- **Qisqa ishlaganda.**  Issiqlik cheklovi bir necha daqiqadan keyin
  ko'rinadi; `--seconds 60` eng kami.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:  # skript sifatida ishga tushirilganda
    sys.path.insert(0, str(BASE_DIR))

from chaqimchi_ai.sotqin_profile import GUARANTEED_CAMERAS  # noqa: E402

DEFAULT_MODEL = BASE_DIR / "models" / "retail" / "person-detection-retail-0013.xml"

from chaqimchi_ai.local.benchmark import (  # noqa: E402
    THERMAL_DROP_WARN,
    capacity_verdict,
    frames_from_source,
    measure_decode,
    measure_detector,
    measure_frame_overhead,
    synthetic_frames,
)


def print_report(result: Dict[str, Any]) -> None:
    detector = result["detector"]
    verdict = result["verdict"]
    print()
    print("═" * 66)
    print("  Chaqimchi Retail AI — qurilma sig'imi")
    print("═" * 66)
    print(f"  Qurilma      : {result['host']['machine']} / {result['host']['system']}")
    print(f"  Inferens     : {result['device_in_use']}")
    print(f"  Kadr manbasi : {result['frame_source']}")
    print()
    print("  Detektor")
    print(f"    o'lchov      : {detector['samples']} ta, {detector['elapsed_sec']} soniya")
    print(f"    p50 / p95    : {detector['p50_ms']} / {detector['p95_ms']} ms")
    print(f"    xom tezlik   : {detector['throughput_fps']} inferens/sekund")
    print(f"    byudjet oladi: {detector['budget_target_fps']} inferens/sekund")
    stability = detector["stability"]
    if stability.get("enough_data"):
        print(
            f"    barqarorlik  : {stability['first_third_ms']} → "
            f"{stability['last_third_ms']} ms ({stability['slowdown_percent']}% sekinlashuv)"
        )
    print()
    overhead = result["overhead"]
    print("  Har kadr yuki")
    print(f"    harakat filtri : {overhead['motion_ms']} ms")
    print(f"    buzilish tekshiruvi: {overhead['tamper_ms']} ms")
    if result.get("decode", {}).get("ok"):
        print(f"    dekodlash      : {result['decode']['decode_ms']} ms")
    print()
    print("  Xulosa")
    print(
        f"    {verdict['cameras']} kamera × {verdict['per_camera_fps']} FPS = "
        f"{verdict['needed_fps']} kerak, {verdict['available_fps']} bor"
    )
    print(f"    ko'tara oladi  : {verdict['supported_cameras']} kamera")
    print(f"    zaxira         : {verdict['headroom_percent']}%")
    print(f"    kadr yuki      : {verdict['capture_load_cores']} yadro")
    print()
    for warning in result["warnings"] + verdict["warnings"]:
        print(f"  ⚠  {warning}")
    print()
    print("  " + ("✅ Bu konfiguratsiya sotilishi mumkin" if verdict["ok"] else "❌ Sotilmasin"))
    print("═" * 66)
    print()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="N100 sig'imini o'lchash")
    parser.add_argument("--model", default=str(DEFAULT_MODEL))
    parser.add_argument("--device", default="GPU", help="GPU | CPU")
    parser.add_argument("--seconds", type=float, default=60.0, help="o'lchov davomiyligi")
    parser.add_argument("--warmup", type=float, default=5.0)
    parser.add_argument("--workers", type=int, default=1, help="parallel inferens oqimlari")
    parser.add_argument(
        "--cameras", type=int, default=GUARANTEED_CAMERAS, help="xulosa uchun kamera soni"
    )
    parser.add_argument("--per-camera-fps", type=float, default=2.0)
    parser.add_argument("--sample-fps", type=float, default=5.0)
    parser.add_argument("--cores", type=int, default=4)
    parser.add_argument("--source", default=None, help="RTSP/fayl — haqiqiy kadr uchun")
    parser.add_argument("--json", default=None, help="natijani shu faylga yozish")
    args = parser.parse_args(argv)

    from chaqimchi_ai.retail.detector_ov import OpenVINOPersonDetector

    model_path = Path(args.model)
    if not model_path.is_file():
        raise SystemExit(
            f"Model topilmadi: {model_path}\nAvval: python scripts/fetch_retail_model.py"
        )

    warnings: List[str] = []
    if args.source:
        frames = frames_from_source(args.source)
        frame_source = args.source
    else:
        frames = synthetic_frames()
        frame_source = "sun'iy kadrlar"
        warnings.append(
            "Sun'iy kadrda o'lchandi — haqiqiy do'kon kadri sekinroq bo'ladi. "
            "Aniq raqam uchun: --source rtsp://..."
        )

    detector = OpenVINOPersonDetector(model_path, device=args.device)
    if detector.device_in_use != "GPU":
        warnings.append(
            f"Inferens {detector.device_in_use} da ketyapti, iGPU'da emas — "
            "drayver o'rnatilganini tekshiring, aks holda bu raqam boshqa narsa"
        )
    if args.seconds < 60:
        warnings.append("60 soniyadan qisqa o'lchov issiqlik cheklovini ko'rsatmaydi")

    print(f"O'lchov ketmoqda: {args.seconds:.0f} soniya ({detector.device_in_use})...")
    detector_result = measure_detector(
        detector, frames, seconds=args.seconds, warmup=args.warmup, workers=args.workers
    )
    overhead = measure_frame_overhead(frames, seconds=min(5.0, args.seconds))
    decode = measure_decode(args.source, seconds=5.0) if args.source else {"ok": False}

    verdict = capacity_verdict(
        budget_target_fps=detector_result["budget_target_fps"],
        cameras=args.cameras,
        per_camera_fps=args.per_camera_fps,
        sample_fps=args.sample_fps,
        overhead_ms=overhead["total_ms"],
        decode_ms=decode.get("decode_ms", 0.0) if decode.get("ok") else 0.0,
        cores=args.cores,
    )
    stability = detector_result.get("stability", {})
    if stability.get("enough_data") and stability["slowdown_percent"] > THERMAL_DROP_WARN * 100:
        warnings.append(
            f"Qurilma o'lchov davomida {stability['slowdown_percent']}% sekinlashdi — "
            "issiqlik cheklovi; sovutishni tekshiring"
        )

    result: Dict[str, Any] = {
        "measured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "host": {"machine": platform.machine(), "system": platform.system()},
        "model": str(model_path),
        "device_in_use": detector.device_in_use,
        "frame_source": frame_source,
        "detector": detector_result,
        "overhead": overhead,
        "decode": decode,
        "verdict": verdict,
        "warnings": warnings,
    }
    print_report(result)
    if args.json:
        Path(args.json).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Natija saqlandi: {args.json}")
    return 0 if verdict["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
