"""Oddiy in-memory metrikalar (Prometheus o‘rniga JSON API)."""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional


class MetricsCollector:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.inferences_total = 0
        self.matches_total = 0
        self.errors_total = 0
        self.spoofs_total = 0
        self.purged_events_total = 0
        self.purged_files_total = 0
        self._infer_ms: List[float] = []
        self._max_samples = 200
        self.cameras: Dict[str, Dict[str, Any]] = {}
        self.started_at = time.time()

    def record_inference(
        self,
        camera_id: Optional[str],
        infer_ms: float,
        *,
        faces: int = 0,
    ) -> None:
        with self._lock:
            self.inferences_total += 1
            self._infer_ms.append(float(infer_ms))
            if len(self._infer_ms) > self._max_samples:
                self._infer_ms = self._infer_ms[-self._max_samples :]
            if camera_id:
                cam = self.cameras.setdefault(
                    camera_id,
                    {"inferences": 0, "matches": 0, "spoofs": 0, "last_infer_ms": 0.0},
                )
                cam["inferences"] += 1
                cam["last_infer_ms"] = float(infer_ms)
                cam["last_faces"] = faces

    def record_match(self, camera_id: Optional[str] = None) -> None:
        with self._lock:
            self.matches_total += 1
            if camera_id and camera_id in self.cameras:
                self.cameras[camera_id]["matches"] += 1

    def record_spoof(self, camera_id: Optional[str] = None) -> None:
        """Anti-spoof rad etgan mos kelish."""
        with self._lock:
            self.spoofs_total += 1
            if camera_id and camera_id in self.cameras:
                self.cameras[camera_id]["spoofs"] = self.cameras[camera_id].get("spoofs", 0) + 1

    def record_purge(self, events_deleted: int, files_deleted: int) -> None:
        """Arxiv tozalash natijasi (retention)."""
        with self._lock:
            self.purged_events_total += int(events_deleted)
            self.purged_files_total += int(files_deleted)

    def record_error(self) -> None:
        with self._lock:
            self.errors_total += 1

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            infer = list(self._infer_ms)
            uptime = time.time() - self.started_at
            out: Dict[str, Any] = {
                "uptime_sec": round(uptime, 1),
                "inferences_total": self.inferences_total,
                "matches_total": self.matches_total,
                "spoofs_total": self.spoofs_total,
                "errors_total": self.errors_total,
                "purged_events_total": self.purged_events_total,
                "purged_files_total": self.purged_files_total,
                "inference_ms": {
                    "count": len(infer),
                    "avg": round(sum(infer) / len(infer), 2) if infer else None,
                    "p95": round(float(sorted(infer)[int(len(infer) * 0.95)]), 2)
                    if len(infer) >= 2
                    else (round(infer[-1], 2) if infer else None),
                },
                "cameras": dict(self.cameras),
            }
            return out


_metrics = MetricsCollector()


def get_metrics() -> MetricsCollector:
    return _metrics
