from __future__ import annotations

import json
from pathlib import Path

from chaqimchi_ai.pilot_acceptance import (
    pilot_acceptance_status,
    validate_n100_acceptance,
)
from chaqimchi_ai.sotqin_profile import HARDWARE_PROFILE
from cloud.store import available_feature_codes


def valid_acceptance() -> dict:
    return {
        "schema_version": 1,
        "hardware_profile": HARDWARE_PROFILE,
        "approved_by": "Pilot komissiyasi",
        "approved_at": "2026-08-13T12:00:00+00:00",
        "benchmark": {
            "device_in_use": "GPU",
            "frame_source": "pilot-store.mp4",
            "warnings": [],
            "detector": {"elapsed_sec": 60.1},
            "verdict": {"cameras": 4, "ok": True, "warnings": []},
        },
        "soak": {
            "duration_hours": 72.1,
            "cameras_min_active": 4,
            "unexpected_restarts": 0,
            "camera_uptime_percent": 99.5,
            "max_temperature_c": 78.0,
            "undelivered_critical_events": 0,
        },
    }


def test_real_benchmark_and_soak_open_acceptance(tmp_path: Path) -> None:
    path = tmp_path / "acceptance.json"
    path.write_text(json.dumps(valid_acceptance()), encoding="utf-8")

    assert validate_n100_acceptance(valid_acceptance())["ok"] is True
    assert pilot_acceptance_status(path)["ok"] is True


def test_synthetic_or_short_measurement_is_rejected() -> None:
    payload = valid_acceptance()
    payload["benchmark"]["frame_source"] = "sun'iy kadrlar"
    payload["soak"]["duration_hours"] = 12

    result = validate_n100_acceptance(payload)

    assert result["ok"] is False
    assert any("haqiqiy" in reason for reason in result["reasons"])
    assert any("72" in reason for reason in result["reasons"])


def test_production_feature_gate_requires_valid_acceptance(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("CHAQIMCHI_ENV", "production")
    monkeypatch.setenv("CHAQIMCHI_AVAILABLE_FEATURES", "person_count,unknown")
    monkeypatch.delenv("CHAQIMCHI_N100_ACCEPTANCE_FILE", raising=False)
    assert available_feature_codes() == frozenset()

    path = tmp_path / "acceptance.json"
    path.write_text(json.dumps(valid_acceptance()), encoding="utf-8")
    monkeypatch.setenv("CHAQIMCHI_N100_ACCEPTANCE_FILE", str(path))
    assert available_feature_codes() == frozenset({"person_count"})
