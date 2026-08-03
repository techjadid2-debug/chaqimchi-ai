"""Prometheus matn formatiga eksport."""

from __future__ import annotations

from typing import Any, Dict


def _line(name: str, value: Any, labels: Dict[str, str] | None = None) -> str:
    if labels:
        lbl = ",".join(f'{k}="{v}"' for k, v in labels.items())
        return f"{name}{{{lbl}}} {value}"
    return f"{name} {value}"


def format_prometheus(snapshot: Dict[str, Any]) -> str:
    lines = [
        "# HELP chaqimchi_inferences_total Jami inferenslar",
        "# TYPE chaqimchi_inferences_total counter",
        _line("chaqimchi_inferences_total", snapshot.get("inferences_total", 0)),
        "# HELP chaqimchi_matches_total Jami mos kelishlar",
        "# TYPE chaqimchi_matches_total counter",
        _line("chaqimchi_matches_total", snapshot.get("matches_total", 0)),
        "# HELP chaqimchi_spoofs_total Anti-spoof rad etgan mos kelishlar",
        "# TYPE chaqimchi_spoofs_total counter",
        _line("chaqimchi_spoofs_total", snapshot.get("spoofs_total", 0)),
        "# HELP chaqimchi_purged_events_total Arxivdan o‘chirilgan voqealar",
        "# TYPE chaqimchi_purged_events_total counter",
        _line("chaqimchi_purged_events_total", snapshot.get("purged_events_total", 0)),
        "# HELP chaqimchi_purged_files_total Arxivdan o‘chirilgan snapshot fayllar",
        "# TYPE chaqimchi_purged_files_total counter",
        _line("chaqimchi_purged_files_total", snapshot.get("purged_files_total", 0)),
        "# HELP chaqimchi_errors_total Jami xatolar",
        "# TYPE chaqimchi_errors_total counter",
        _line("chaqimchi_errors_total", snapshot.get("errors_total", 0)),
        "# HELP chaqimchi_uptime_seconds Server uptime",
        "# TYPE chaqimchi_uptime_seconds gauge",
        _line("chaqimchi_uptime_seconds", snapshot.get("uptime_sec", 0)),
        "# HELP chaqimchi_ws_clients WebSocket mijozlar",
        "# TYPE chaqimchi_ws_clients gauge",
        _line("chaqimchi_ws_clients", snapshot.get("ws_clients", 0)),
    ]

    infer = snapshot.get("inference_ms") or {}
    if infer.get("avg") is not None:
        lines.extend([
            "# HELP chaqimchi_inference_ms_avg O‘rtacha inferens (ms)",
            "# TYPE chaqimchi_inference_ms_avg gauge",
            _line("chaqimchi_inference_ms_avg", infer["avg"]),
        ])
    if infer.get("p95") is not None:
        lines.extend([
            "# HELP chaqimchi_inference_ms_p95 95-percentil inferens (ms)",
            "# TYPE chaqimchi_inference_ms_p95 gauge",
            _line("chaqimchi_inference_ms_p95", infer["p95"]),
        ])

    for cam_id, cam in (snapshot.get("cameras") or {}).items():
        lines.append(
            _line(
                "chaqimchi_camera_inferences_total",
                cam.get("inferences", 0),
                {"camera_id": str(cam_id)},
            )
        )

    return "\n".join(lines) + "\n"
