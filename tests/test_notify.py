"""Ogohlantirish yig'ish va tormozlash.

Asosiy talab: 500 talik batch bitta xabarga aylanadi. Bungacha har event
alohida ketardi va bot Telegram limitiga urilib, xabar umuman yetib bormasdi.
"""

from __future__ import annotations

from chaqimchi_ai.event_models import EdgeEvent
from cloud.notify import (
    MAX_NOTE_CHARS,
    AlertThrottle,
    build_alert,
    event_note,
    summarize,
)


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


# ── AI xulosasi (8.4) ────────────────────────────────────────────────────


def ai_review(camera: str, sabab: str, *, tavsif: str = "", severity: str = "warning") -> EdgeEvent:
    return EdgeEvent(
        event_type="ai_review",
        camera_id=camera,
        severity=severity,
        metadata={"sabab": sabab, "tavsif": tavsif},
    )


def test_ai_conclusion_is_written_into_the_message() -> None:
    """Butun modulning ma'nosi shu matnda.

    Usiz xabar "AI ko'rdi — kassa-01" bo'lardi va do'kon egasiga hech narsa
    aytmasdi — u baribir kamerani ochib ko'rishi kerak bo'lardi.
    """
    message = summarize([ai_review("kassa-01", "Ikki kishi janjallashmoqda")])

    assert message.splitlines() == [
        "⚠️ 1 ta ogohlantirish",
        "• AI ko'rdi — kassa-01",
        "   ↳ Ikki kishi janjallashmoqda",
    ]


def test_description_is_used_when_there_is_no_reason() -> None:
    message = summarize([ai_review("kassa-01", "", tavsif="Kadr qorong'i")])
    assert "   ↳ Kadr qorong'i" in message


def test_long_conclusion_is_shortened() -> None:
    """Telefonda bir qarashda o'qilsin — devor bo'lib ketmasin."""
    message = summarize([ai_review("kassa-01", "juda uzun izoh " * 40)])

    note = [line for line in message.splitlines() if line.startswith("   ↳")][0]
    assert len(note) <= MAX_NOTE_CHARS + 8
    assert note.endswith("…")


def test_other_event_types_get_no_note() -> None:
    """Qolgan turlar uchun tur nomi va kamera yetarli."""
    assert event_note(event("loitering", "camera-01")) is None


def test_repeated_conclusions_keep_the_first() -> None:
    """Takrorlangan hodisada eng eskisi muammoning boshlanishini ko'rsatadi."""
    message = summarize(
        [
            ai_review("kassa-01", "Birinchi"),
            ai_review("kassa-01", "Ikkinchi"),
        ]
    )

    assert "   ↳ Birinchi" in message
    assert "Ikkinchi" not in message
    assert "×2" in message
