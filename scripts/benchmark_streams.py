#!/usr/bin/env python3
"""Chaqimchi Lite uchun 8 RTSP scene analytics qabul testi."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import time
from pathlib import Path

import cv2

from chaqimchi_ai.scene_analytics import build_scene_analyzer
from chaqimchi_ai.settings import AppSettings


def run_camera(camera, analyzer, duration: int) -> dict:
    cap = cv2.VideoCapture(camera.source)
    if not cap.isOpened():
        return {"camera_id": camera.id, "ok": False, "error": "stream ochilmadi"}
    deadline = time.monotonic() + duration
    analyzed = frames = events = 0
    started = time.monotonic()
    try:
        while time.monotonic() < deadline:
            ok, frame = cap.read()
            if not ok:
                break
            frames += 1
            before = analyzer._last_analysis
            events += len(analyzer.process(frame))
            if analyzer._last_analysis != before:
                analyzed += 1
    finally:
        cap.release()
    elapsed = max(0.001, time.monotonic() - started)
    fps = analyzed / elapsed
    return {
        "camera_id": camera.id,
        "ok": fps >= 2.0,
        "read_fps": round(frames / elapsed, 2),
        "ai_fps": round(fps, 2),
        "events": events,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("config/lite.yaml"))
    parser.add_argument("--duration", type=int, default=300)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    settings = AppSettings.load(args.config, base_dir=Path.cwd())
    cameras = [camera for camera in settings.cameras if camera.enabled]
    if len(cameras) != 8:
        parser.error("Chaqimchi Lite benchmarki uchun aynan 8 faol kamera kerak")
    analyzers = {
        camera.id: build_scene_analyzer(camera.id, settings.scene, Path.cwd())
        for camera in cameras
    }
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(
                lambda camera: run_camera(
                    camera, analyzers[camera.id], max(30, args.duration)
                ),
                cameras,
            )
        )
    thermal = Path("/sys/class/thermal/thermal_zone0/temp")
    temperature = float(thermal.read_text().strip()) / 1000 if thermal.is_file() else None
    report = {
        "passed": all(item["ok"] for item in results)
        and (temperature is None or temperature < 80),
        "temperature_c": temperature,
        "minimum_ai_fps": 2.0,
        "cameras": results,
        "hardware": os.uname().machine,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
