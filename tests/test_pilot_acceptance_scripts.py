"""Qabul (Acceptance) va Soak skriptlari uchun testlar."""

from chaqimchi_ai.pilot_acceptance import validate_n100_acceptance
from chaqimchi_ai.sotqin_profile import HARDWARE_PROFILE
from scripts.soak_n100 import service_restarts, summarize_samples


def test_service_restarts_does_not_crash_on_non_systemd():
    # macOS yoki systemd bo'lmagan tizimda xato bermasdan 0 qaytarishi kerak
    count = service_restarts()
    assert isinstance(count, int)
    assert count >= 0


def test_summarize_samples_computes_metrics_correctly():
    samples = [
        {"cameras_active": 4, "temperature_c": 65.0, "outbox_critical_pending": 0},
        {"cameras_active": 4, "temperature_c": 72.5, "outbox_critical_pending": 0},
        {"cameras_active": 4, "temperature_c": 78.0, "outbox_critical_pending": 0},
        {"cameras_active": 4, "temperature_c": 70.0, "outbox_critical_pending": 0},
    ]
    summary = summarize_samples(samples, duration_hours=72.1, restart_delta=0)
    assert summary["duration_hours"] == 72.1
    assert summary["cameras_min_active"] == 4
    assert summary["camera_uptime_percent"] == 100.0
    assert summary["max_temperature_c"] == 78.0
    assert summary["unexpected_restarts"] == 0
    assert summary["undelivered_critical_events"] == 0


def test_validate_n100_acceptance_success():
    payload = {
        "schema_version": 1,
        "hardware_profile": HARDWARE_PROFILE,
        "approved_by": "Qabul Komissiyasi",
        "approved_at": "2026-08-15T12:00:00Z",
        "sources": {
            "benchmark_sha256": "abcdef1234567890",
            "soak_sha256": "123456abcdef7890",
        },
        "benchmark": {
            "device_in_use": "GPU",
            "frame_source": "pilot-store-4cam.mp4",
            "detector": {"elapsed_sec": 65.0},
            "verdict": {"cameras": 4, "ok": True, "warnings": []},
            "warnings": [],
        },
        "soak": {
            "duration_hours": 72.5,
            "cameras_min_active": 4,
            "unexpected_restarts": 0,
            "camera_uptime_percent": 99.8,
            "max_temperature_c": 77.5,
            "undelivered_critical_events": 0,
        },
    }
    result = validate_n100_acceptance(payload)
    assert result["ok"] is True
    assert len(result["reasons"]) == 0
