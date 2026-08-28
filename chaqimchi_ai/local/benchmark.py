"""Qurilma sig'imini O'LCHAYDI — taxmin qilmaydi.

Bu yadro ilgari `scripts/benchmark_n100.py` ichida turardi va aynan shu
uni ishlatib bo'lmas qilardi: Windows payload'iga faqat `chaqimchi_ai`
paketi ko'chiriladi (`scripts/build_windows_payload.py: CODE_DIRS`),
ya'ni do'kon kompyuterida `scripts/` YO'Q.  Natijada "avval o'lchang"
degan tavsiya bajarib bo'lmaydigan bo'lib qolgan edi: o'lchov mumkin
bo'lgan yagona joy — mijozning kompyuteri — skriptga ega emas.

Endi yadro paket ichida va uni ikki joydan chaqirish mumkin:

* `scripts/benchmark_n100.py` — qo'lda, terminaldan;
* `local/cloud_jobs.py: _run_benchmark` — admin paneldagi tugmadan,
  masofadan, mijozni bezovta qilmasdan.

Nima o'lchanadi va o'lchov qachon YOLG'ON bo'lishi — skript
docstringida (u foydalanuvchiga ko'rinadigan hujjat).
"""

from __future__ import annotations

import statistics
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

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
    """Oqimdan kadr olish narxi: `grab()` (dekodsiz) va `retrieve()` (dekod).

    Kadrning HAQIQIY o'lchamini ham qaytaradi (`native_width`/`height`).

    Nega shu yerda: tahlil yo'li kadrni doim 640x360 ga keltiradi
    (`frames_from_source`), ya'ni o'lchov natijasidagi `frame_size`
    kamerada nima turganini AYTMAYDI.  2026-08-29 da bu sezildi:
    "kamerani 720p ga o'tkazdim" degandan keyin o'zgarish ishlaganini
    tekshirishning yagona yo'li 24 soat kutib `face_crops.written` ga
    qarash edi.  Bu metod oqimni allaqachon ochadi — qo'shimcha ulanish
    kerak emas.

    O'lcham `CAP_PROP` dan emas, KADRNING O'ZIDAN olinadi: RTSP'da
    property'lar ba'zi kameralarda nol yoki eskirgan qiymat qaytaradi,
    dekodlangan kadr esa har doim rost.
    """
    import cv2

    capture = cv2.VideoCapture(int(source) if source.isdigit() else source)
    if not capture.isOpened():
        return {"ok": False, "error": "manba ochilmadi"}
    grabs: List[float] = []
    decodes: List[float] = []
    native: Optional[tuple] = None
    stop_at = time.monotonic() + seconds
    try:
        while time.monotonic() < stop_at:
            before = time.perf_counter()
            if not capture.grab():
                break
            grabs.append(time.perf_counter() - before)
            before = time.perf_counter()
            ok, frame = capture.retrieve()
            if not ok:
                break
            decodes.append(time.perf_counter() - before)
            if native is None and frame is not None:
                height, width = frame.shape[:2]
                native = (int(width), int(height))
    finally:
        capture.release()
    if not decodes:
        return {"ok": False, "error": "kadr o'qilmadi"}
    return {
        "ok": True,
        "grab_ms": round(statistics.fmean(grabs) * 1000, 3),
        "decode_ms": round(statistics.fmean(decodes) * 1000, 3),
        "stream_fps": round(len(decodes) / max(sum(grabs) + sum(decodes), 1e-6), 1),
        "native_width": native[0] if native else None,
        "native_height": native[1] if native else None,
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
