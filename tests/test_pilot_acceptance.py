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


def test_production_feature_gate_requires_valid_acceptance(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CHAQIMCHI_ENV", "production")
    monkeypatch.setenv("CHAQIMCHI_AVAILABLE_FEATURES", "person_count,unknown")
    monkeypatch.delenv("CHAQIMCHI_N100_ACCEPTANCE_FILE", raising=False)
    assert available_feature_codes() == frozenset()

    path = tmp_path / "acceptance.json"
    path.write_text(json.dumps(valid_acceptance()), encoding="utf-8")
    monkeypatch.setenv("CHAQIMCHI_N100_ACCEPTANCE_FILE", str(path))
    assert available_feature_codes() == frozenset({"person_count"})


# ── Windows yo'li (asosiy mahsulot) ─────────────────────────────────────
#
# Bungacha faqat N100 mezoni bor edi: Windows sinovi `device_in_use="CPU"`
# va `max_temperature_c=null` bilan kelib **hech qachon o'ta olmasdi**.
# Ya'ni asosiy mahsulotni sotuvga ochishning texnik yo'li yo'q edi.
#
# Yumshatilgani faqat ikkitasi (GPU va harorat).  Qolgan hamma narsa bir
# xil, chunki mijozga beriladigan va'da bir xil.

from chaqimchi_ai.pilot_acceptance import WINDOWS_PROFILE  # noqa: E402


def valid_windows_acceptance() -> dict:
    return {
        "schema_version": 1,
        "hardware_profile": WINDOWS_PROFILE,
        "approved_by": "Abdulvosit",
        "approved_at": "2026-08-24T12:00:00+00:00",
        "benchmark": {
            "device_in_use": "CPU",
            "frame_source": "rtsp://nvr/kanal-1",
            "warnings": [],
            "detector": {"elapsed_sec": 300.0},
            "verdict": {"cameras": 4, "ok": True, "warnings": []},
        },
        "soak": {
            "duration_hours": 72.4,
            "cameras_min_active": 4,
            "unexpected_restarts": 0,
            "camera_uptime_percent": 99.6,
            "max_temperature_c": None,
            "undelivered_critical_events": 0,
        },
        "field_checks": {
            "daily_count_delta_percent": 4.2,
            "clip_delivered": True,
            "ota_update_ok": True,
        },
    }


def test_windows_passes_on_cpu_without_a_temperature_sensor() -> None:
    result = validate_n100_acceptance(valid_windows_acceptance())

    assert result["ok"] is True, result["reasons"]


def test_n100_still_requires_the_gpu_and_a_temperature() -> None:
    """Windows uchun yumshatish Box mezonini pasaytirmasin."""
    payload = valid_acceptance()
    payload["benchmark"]["device_in_use"] = "CPU"
    assert "benchmark Intel GPU'da bajarilmagan" in validate_n100_acceptance(payload)["reasons"]

    payload = valid_acceptance()
    payload["soak"]["max_temperature_c"] = None
    assert "harorat o'lchanmagan" in validate_n100_acceptance(payload)["reasons"]


def test_windows_still_needs_the_full_72_hours_and_four_cameras() -> None:
    payload = valid_windows_acceptance()
    payload["soak"]["duration_hours"] = 40.0
    payload["soak"]["cameras_min_active"] = 2
    reasons = validate_n100_acceptance(payload)["reasons"]

    assert any("72 soat" in reason for reason in reasons)
    assert any("kamera uzluksiz faol" in reason for reason in reasons)


def test_a_restart_fails_windows_too() -> None:
    payload = valid_windows_acceptance()
    payload["soak"]["unexpected_restarts"] = 1

    assert "soak testda kutilmagan restart bo'lgan" in validate_n100_acceptance(payload)["reasons"]


def test_an_overheating_windows_machine_is_still_refused() -> None:
    """Harorat o'lchanmasligi mumkin, lekin o'lchangani yuqori bo'lsa —
    bu baribir nuqson."""
    payload = valid_windows_acceptance()
    payload["soak"]["max_temperature_c"] = 92.0

    assert any("harorat" in reason for reason in validate_n100_acceptance(payload)["reasons"])


def test_the_manual_count_comparison_is_mandatory_on_windows() -> None:
    """`docs/DOKON_MVP.md` mezoni: kunlik son qo'lda sanash bilan ±10%."""
    payload = valid_windows_acceptance()
    payload["field_checks"]["daily_count_delta_percent"] = None
    assert "kunlik son qo'lda sanash bilan solishtirilmagan" in (
        validate_n100_acceptance(payload)["reasons"]
    )

    payload = valid_windows_acceptance()
    payload["field_checks"]["daily_count_delta_percent"] = 18.0
    assert any("farq qiladi" in reason for reason in validate_n100_acceptance(payload)["reasons"])


def test_clip_delivery_and_ota_must_be_confirmed() -> None:
    payload = valid_windows_acceptance()
    payload["field_checks"] = {}
    reasons = validate_n100_acceptance(payload)["reasons"]

    assert "hodisa klipi cloudga yetib borgani tasdiqlanmagan" in reasons
    assert "masofadan yangilanish sinovdan o'tmagan" in reasons


def test_an_unknown_hardware_profile_is_refused() -> None:
    payload = valid_windows_acceptance()
    payload["hardware_profile"] = "MENING-KOMPYUTERIM"
    result = validate_n100_acceptance(payload)

    assert result["ok"] is False
    assert any("hardware_profile" in reason for reason in result["reasons"])
