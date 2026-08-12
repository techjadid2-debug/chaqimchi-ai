"""Ogohlantirish yig'ish va tormozlash.

Asosiy talab: 500 talik batch bitta xabarga aylanadi. Bungacha har event
alohida ketardi va bot Telegram limitiga urilib, xabar umuman yetib bormasdi.
"""

from __future__ import annotations

from chaqimchi_ai.event_models import EdgeEvent
from cloud.notify import AlertThrottle, build_alert, summarize


def event(event_type: str, camera: str, severity: str = "warning") -> EdgeEvent:
    return EdgeEvent(event_type=event_type, camera_id=camera, severity=severity)


def test_info_events_never_alert() -> None:
    events = [event("person_detected", "camera-01", severity="info") for _ in range(50)]
    assert build_alert("site-1", events, throttle_service=AlertThrottle()) is None


def test_batch_becomes_one_grouped_message() -> None:
    events = [event("zone_entered", "camera-01") for _ in range(500)]
    events += [event("loitering", "camera-02") for _ in range(3)]

    message = build_alert("site-1", events, throttle_service=AlertThrottle())

    assert message is not None
    assert "503 ta ogohlantirish" in message
    # Eng ko'p takrorlangani birinchi turadi va o'zbekcha nomlanadi.
    lines = message.splitlines()
    assert lines[1] == "• Taqiqlangan zonaga kirish — camera-01 ×500"
    assert lines[2] == "• Uzoq turish — camera-02 ×3"


def test_critical_event_changes_the_marker() -> None:
    assert summarize([event("loitering", "camera-01")]).startswith("⚠️")
    assert summarize([event("loitering", "camera-01", severity="critical")]).startswith("🔴")


def test_repeat_within_window_is_suppressed() -> None:
    throttle = AlertThrottle(window_sec=600)
    assert build_alert("site-1", [event("loitering", "camera-01")], throttle_service=throttle)
    # Xuddi shu kamera, xuddi shu tur — mijoz telefonini o'chirib qo'ymasin.
    assert build_alert("site-1", [event("loitering", "camera-01")], throttle_service=throttle) is None
    # Boshqa kamera yoki boshqa obyekt mustaqil.
    assert build_alert("site-1", [event("loitering", "camera-02")], throttle_service=throttle)
    assert build_alert("site-2", [event("loitering", "camera-01")], throttle_service=throttle)


def test_throttled_type_drops_out_but_others_still_send() -> None:
    throttle = AlertThrottle(window_sec=600)
    build_alert("site-1", [event("loitering", "camera-01")], throttle_service=throttle)

    message = build_alert(
        "site-1",
        [event("loitering", "camera-01"), event("zone_entered", "camera-01")],
        throttle_service=throttle,
    )

    assert message is not None
    assert "Uzoq turish" not in message
    assert "Taqiqlangan zonaga kirish" in message


def test_many_types_are_capped_with_a_tail_line() -> None:
    events = [event("zone_entered", f"camera-{index:02d}") for index in range(1, 10)]
    message = summarize(events)
    assert "va yana 3 ta turdagi hodisa" in message
