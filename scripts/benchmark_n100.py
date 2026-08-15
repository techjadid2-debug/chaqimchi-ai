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
import statistics
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:  # skript sifatida ishga tushirilganda
    sys.path.insert(0, str(BASE_DIR))

from chaqimchi_ai.sotqin_profile import GUARANTEED_CAMERAS  # noqa: E402

DEFAULT_MODEL = BASE_DIR / "models" / "retail" / "person-detection-retail-0013.xml"

#: Substream o'lchami — tahlil aynan shunda ketadi.
FRAME_WIDTH = 640
FRAME_HEIGHT = 360

#: Aylanib turadigan kadrlar soni.  Bitta kadrni takrorlash kesh tufayli
#: haqiqatdan tez chiqadi.
FRAME_POOL = 60

#: Byudjet o'lchangan p95 ning shuncha ulushini target qilib oladi
#: (`InferenceBudget._adapt`).  Xulosa aynan shu songa asoslanadi.
BUDGET_SAFETY = 0.8

#: Barqarorlik: oxirgi uchdan bir qism shundan ko'p pasaysa — issiqlik cheklovi.
THERMAL_DROP_WARN = 0.15


def percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(round(fraction * (len(ordered) - 1)))
    return ordered[index]


# ── Kadrlar ──────────────────────────────────────────────────────────────


def synthetic_frames(count: int = FRAME_POOL) -> List[Any]:
    """Turli-tuman sun'iy kadrlar.

    Bir xil kadrni takrorlash noto'g'ri natija beradi; shu sabab har kadr
    boshqacha shovqin va bloklardan iborat.
    """
    import numpy as np

    rng = np.random.default_rng(20260813)
    frames = []
    for index in range(count):
        frame = rng.integers(30, 220, size=(FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8)
        top = (index * 7) % (FRAME_HEIGHT - 80)
        left = (index * 11) % (FRAME_WIDTH - 40)
        frame[top : top + 80, left : left + 40] = 90  # odamga o'xshash blok
        frames.append(frame)
    return frames


def frames_from_source(source: str, count: int = FRAME_POOL) -> List[Any]:
    """Haqiqiy oqimdan yoki fayldan kadr to'plash."""
    import cv2

    capture = cv2.VideoCapture(int(source) if source.isdigit() else source)
    if not capture.isOpened():
        raise SystemExit(f"Manba ochilmadi: {source}")
    frames = []
    try:
        while len(frames) < count:
            ok, frame = capture.read()
            if not ok:
                break
            frames.append(cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT)))
    finally:
        capture.release()
    if not frames:
        raise SystemExit(f"Manbadan kadr o'qilmadi: {source}")
    return frames


# ── O'lchovlar ───────────────────────────────────────────────────────────


@dataclass
class Samples:
    latencies: List[float] = field(default_factory=list)
    stamps: List[float] = field(default_factory=list)

    def add(self, latency: float, at: float) -> None:
        self.latencies.append(latency)
        self.stamps.append(at)

    def summary(self, elapsed: float, *, workers: int) -> Dict[str, Any]:
        if not self.latencies:
            return {"samples": 0}
        p95 = percentile(self.latencies, 0.95)
        return {
            "samples": len(self.latencies),
            "elapsed_sec": round(elapsed, 2),
            "throughput_fps": round(len(self.latencies) / max(elapsed, 1e-6), 2),
            "p50_ms": round(percentile(self.latencies, 0.50) * 1000, 2),
            "p95_ms": round(p95 * 1000, 2),
            "p99_ms": round(percentile(self.latencies, 0.99) * 1000, 2),
            "mean_ms": round(statistics.fmean(self.latencies) * 1000, 2),
            # Byudjet aynan shu formula bilan ishlaydi: workers / p95, keyin
            # 0.8 zaxira.  Ishlash paytida target shu son atrofida turadi.
            "budget_target_fps": round(BUDGET_SAFETY * workers / max(p95, 1e-6), 2),
            "stability": self._stability(),
        }

    def _stability(self) -> Dict[str, Any]:
        """Birinchi va oxirgi uchdan bir qism tezligi.

        Qurilma qizib sekinlashsa qisqa o'lchov 8 soatlik smena uchun yolg'on
        bo'ladi.
        """
        if len(self.latencies) < 30:
            return {"enough_data": False}
        third = len(self.latencies) // 3
        first = statistics.fmean(self.latencies[:third])
        last = statistics.fmean(self.latencies[-third:])
        drop = 1.0 - (first / last) if last > 0 else 0.0
        return {
            "enough_data": True,
            "first_third_ms": round(first * 1000, 2),
            "last_third_ms": round(last * 1000, 2),
            "slowdown_percent": round(max(0.0, drop) * 100, 1),
        }


def measure_detector(
    detector: Any, frames: List[Any], *, seconds: float, warmup: float, workers: int
) -> Dict[str, Any]:
    """Detektorni to'liq yuklab o'lchaydi."""
    deadline = time.monotonic() + warmup
    index = 0
    while time.monotonic() < deadline:
        detector.detect(frames[index % len(frames)])
        index += 1

    samples = Samples()
    lock = threading.Lock()
    stop_at = time.monotonic() + seconds
    started = time.monotonic()

    def worker(offset: int) -> None:
        position = offset
        while time.monotonic() < stop_at:
            frame = frames[position % len(frames)]
            position += 1
            before = time.perf_counter()
            detector.detect(frame)
            latency = time.perf_counter() - before
            with lock:
                samples.add(latency, time.monotonic())

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    elapsed = time.monotonic() - started
    result = samples.summary(elapsed, workers=workers)
    result["workers"] = workers
    return result


def measure_frame_overhead(frames: List[Any], *, seconds: float) -> Dict[str, Any]:
    """Harakat filtri va buzilish tekshiruvining har kadrga narxi.

    Bular inferensdan oldin, **har kadrda** ishlaydi.  8 kamera × 5 FPS =
    sekundiga 40 marta, ya'ni arzon ko'ringan ish ham sezilarli bo'lishi
    mumkin.
    """
    from chaqimchi_ai.retail.tamper import TamperDetector
    from chaqimchi_ai.scene_analytics import MotionGate

    gate = MotionGate()
    tamper = TamperDetector()
    motion: List[float] = []
    check: List[float] = []
    stop_at = time.monotonic() + seconds
    index = 0
    while time.monotonic() < stop_at:
        frame = frames[index % len(frames)]
        index += 1
        before = time.perf_counter()
        gate.motion_ratio(frame)
        motion.append(time.perf_counter() - before)
        before = time.perf_counter()
        tamper.update(frame, now=float(index) * 0.2)
        check.append(time.perf_counter() - before)
    return {
        "motion_ms": round(statistics.fmean(motion) * 1000, 3),
        "tamper_ms": round(statistics.fmean(check) * 1000, 3),
        "total_ms": round((statistics.fmean(motion) + statistics.fmean(check)) * 1000, 3),
    }


def measure_decode(source: str, *, seconds: float) -> Dict[str, Any]:
    """Oqimdan kadr olish narxi: `grab()` (dekodsiz) va `retrieve()` (dekod)."""
    import cv2

    capture = cv2.VideoCapture(int(source) if source.isdigit() else source)
    if not capture.isOpened():
        return {"ok": False, "error": "manba ochilmadi"}
    grabs: List[float] = []
    decodes: List[float] = []
    stop_at = time.monotonic() + seconds
    try:
        while time.monotonic() < stop_at:
            before = time.perf_counter()
            if not capture.grab():
                break
            grabs.append(time.perf_counter() - before)
            before = time.perf_counter()
            ok, _frame = capture.retrieve()
            if not ok:
                break
            decodes.append(time.perf_counter() - before)
    finally:
        capture.release()
    if not decodes:
        return {"ok": False, "error": "kadr o'qilmadi"}
    return {
        "ok": True,
        "grab_ms": round(statistics.fmean(grabs) * 1000, 3),
        "decode_ms": round(statistics.fmean(decodes) * 1000, 3),
        "stream_fps": round(len(decodes) / max(sum(grabs) + sum(decodes), 1e-6), 1),
    }


# ── Xulosa ───────────────────────────────────────────────────────────────


def capacity_verdict(
    *,
    budget_target_fps: float,
    cameras: int,
    per_camera_fps: float,
    sample_fps: float,
    overhead_ms: float,
    decode_ms: float = 0.0,
    cores: int = 4,
) -> Dict[str, Any]:
    """O'lchangan raqamlardan "nechta kamera sotish mumkin" degan javob.

    Hisob **byudjet qabul qiladigan** tezlikka asoslanadi (`workers / p95`
    ning 0.8 ulushi), xom o'rtacha tezlikka emas: ishlash paytida target
    aynan shu son atrofida turadi.
    """
    needed = cameras * per_camera_fps
    supported = int(budget_target_fps // per_camera_fps) if per_camera_fps > 0 else 0
    headroom = (budget_target_fps - needed) / needed if needed > 0 else 0.0
    # Kadr yuki inferensdan alohida yadrolarda ketadi (kamera oqimlari), lekin
    # u ham cheklangan resurs.
    capture_load = cameras * sample_fps * (overhead_ms + decode_ms) / 1000.0

    warnings: List[str] = []
    if supported < cameras:
        warnings.append(
            f"Byudjet {cameras} kamerani {per_camera_fps} FPS bilan ko'tarmaydi "
            f"(faqat {supported} tasi)"
        )
    elif headroom < 0.25:
        warnings.append(
            "Zaxira 25% dan kam — issiq kunda yoki og'irroq kadrda byudjet "
            "tushadi va kafolat buziladi"
        )
    if capture_load > cores * 0.5:
        warnings.append(f"Kadr yuki {capture_load:.1f} yadro — {cores} yadroli qurilmada juda ko'p")
    # Broker kafolati: har kamera hech bo'lmasa shu tezlikda ko'rilishi kerak.
    floors = cameras * 0.5
    if budget_target_fps < floors:
        warnings.append(
            f"Kafolatlangan minimum ({floors:.1f} FPS) byudjetdan katta — kamera soni tushirilsin"
        )
    return {
        "cameras": cameras,
        "per_camera_fps": per_camera_fps,
        "needed_fps": round(needed, 2),
        "available_fps": round(budget_target_fps, 2),
        "supported_cameras": supported,
        "headroom_percent": round(headroom * 100, 1),
        "capture_load_cores": round(capture_load, 2),
        "ok": supported >= cameras and not warnings,
        "warnings": warnings,
    }


# ── Hisobot ──────────────────────────────────────────────────────────────


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
