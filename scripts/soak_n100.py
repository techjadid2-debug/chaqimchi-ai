#!/usr/bin/env python3
"""Sotqin R1 uchun 72 soatlik kamera/harorat/outbox soak hisobotini yig'adi."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

SERVICES = (
    "chaqimchi-sotqin.service",
    "chaqimchi-retail.service",
    "chaqimchi-attendance.service",
)


def service_restarts() -> int:
    total = 0
    for service in SERVICES:
        result = subprocess.run(
            ["systemctl", "show", service, "--property=NRestarts", "--value"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            try:
                total += int(result.stdout.strip() or 0)
            except ValueError:
                pass
    return total


def read_health(url: str) -> Dict[str, Any]:
    with urllib.request.urlopen(url, timeout=15) as response:  # noqa: S310 - localhost
        payload = json.load(response)
    return dict(payload.get("device_health") or {})


def summarize_samples(
    samples: List[Dict[str, Any]],
    *,
    duration_hours: float,
    restart_delta: int,
) -> Dict[str, Any]:
    expected = len(samples)
    active = [int(item.get("cameras_active") or 0) for item in samples]
    temperatures = [
        float(item["temperature_c"])
        for item in samples
        if item.get("temperature_c") is not None
    ]
    online_samples = sum(1 for count in active if count >= 4)
    return {
        "duration_hours": round(max(0.0, duration_hours), 3),
        "cameras_min_active": min(active, default=0),
        "unexpected_restarts": max(0, int(restart_delta)),
        "camera_uptime_percent": round(
            online_samples * 100 / expected if expected else 0.0, 3
        ),
        "max_temperature_c": round(max(temperatures), 2) if temperatures else None,
        "undelivered_critical_events": int(
            samples[-1].get("outbox_critical_pending") or 0
        )
        if samples
        else 0,
        "samples": expected,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hours", type=float, default=72.0)
    parser.add_argument("--interval", type=float, default=60.0)
    parser.add_argument("--health-url", default="http://127.0.0.1:8742/health")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.hours <= 0 or args.interval < 1:
        parser.error("hours musbat, interval kamida 1 soniya bo'lishi kerak")

    started_wall = datetime.now(timezone.utc)
    started = time.monotonic()
    restart_baseline = service_restarts()
    samples: List[Dict[str, Any]] = []
    failures = 0
    deadline = started + args.hours * 3600
    try:
        while time.monotonic() < deadline:
            try:
                samples.append(read_health(args.health_url))
            except Exception as exc:  # noqa: BLE001 - uzilish soak natijasining bir qismi
                failures += 1
                samples.append({"cameras_active": 0, "error": str(exc)[:300]})
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(args.interval, remaining))
    except KeyboardInterrupt:
        pass

    duration = (time.monotonic() - started) / 3600
    report = summarize_samples(
        samples,
        duration_hours=duration,
        restart_delta=service_restarts() - restart_baseline,
    )
    report.update(
        {
            "started_at": started_wall.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "poll_failures": failures,
            "complete": duration >= args.hours,
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
