"""Deklarativ qoida dvigateli.

Asosiy talab: do'kon qoidasini o'zgartirish uchun kod tegilmasin va yangi
reliz chiqarilmasin — config yetarli bo'lsin.
"""

from __future__ import annotations

from datetime import time as clock_time

import pytest

from chaqimchi_ai.event_models import EdgeEvent
from chaqimchi_ai.retail.rules import Rule, RuleEngine, Schedule


def queue_event(**overrides) -> EdgeEvent:
    defaults = dict(
        event_type="queue_threshold_exceeded",
        camera_id="kassa-01",
        zone="kassa",
        queue_length=5,
        severity="info",
    )
    defaults.update(overrides)
    return EdgeEvent(**defaults)  # type: ignore[arg-type]


# ── Config'dan yuklash ───────────────────────────────────────────────────


def test_rules_load_from_plain_config() -> None:
    engine = RuleEngine.from_config(
        {
            "schedules": {"ish-vaqti": {"start": "09:00", "end": "21:00"}},
            "rules": [
                {
                    "name": "Kassada uzun navbat",
                    "event_type": "queue_threshold_exceeded",
                    "camera_id": "kassa-01",
                    "zone": "kassa",
                    "conditions": {"min_queue_length": 5},
                    "schedule": "ish-vaqti",
                    "severity": "warning",
                    "cooldown_sec": 300,
                    "actions": ["save_clip", "telegram_alert"],
                }
            ],
        }
    )

    decision = engine.evaluate(queue_event(), now=0.0, local_time=clock_time(12, 0))

    assert decision.rule_name == "Kassada uzun navbat"
    assert decision.event.severity == "warning"
    assert decision.actions == ("save_clip", "telegram_alert")


def test_config_errors_are_loud_not_silent() -> None:
    with pytest.raises(ValueError, match="noma'lum harakat"):
        Rule(name="r", event_type="loitering", actions=["send_sms"])
    with pytest.raises(ValueError, match="noma'lum severity"):
        Rule(name="r", event_type="loitering", severity="juda-muhim")
    with pytest.raises(ValueError, match="noma'lum shart"):
        Rule(name="r", event_type="loitering", conditions={"min_temperature": 5})
    with pytest.raises(ValueError, match="jadvali topilmadi"):
        RuleEngine([Rule(name="r", event_type="loitering", schedule="yo'q")])


# ── Moslik ───────────────────────────────────────────────────────────────


def test_event_without_a_matching_rule_passes_through_unchanged() -> None:
    engine = RuleEngine()
    decision = engine.evaluate(queue_event(), now=0.0)
    assert decision.rule_name is None
    assert decision.actions == ("cloud_sync",)
    assert decision.event.severity == "info"


def test_rule_only_applies_to_its_own_camera_and_zone() -> None:
    engine = RuleEngine([
        Rule(name="faqat-kassa-01", event_type="queue_threshold_exceeded",
             camera_id="kassa-01", zone="kassa", severity="critical")
    ])

    assert engine.evaluate(queue_event(), now=0.0).event.severity == "critical"
    assert engine.evaluate(queue_event(camera_id="kassa-02"), now=1.0).rule_name is None
    assert engine.evaluate(queue_event(zone="zal"), now=2.0).rule_name is None


def test_conditions_filter_by_measured_value() -> None:
    engine = RuleEngine([
        Rule(name="juda-uzun", event_type="queue_threshold_exceeded",
             conditions={"min_queue_length": 8}, severity="critical")
    ])

    assert engine.evaluate(queue_event(queue_length=5), now=0.0).rule_name is None
    assert engine.evaluate(queue_event(queue_length=9), now=1.0).rule_name == "juda-uzun"


def test_direction_condition_separates_entry_from_exit() -> None:
    engine = RuleEngine([
        Rule(name="faqat-kirish", event_type="line_crossed",
             conditions={"direction": "in"}, actions=["cloud_sync"])
    ])
    inside = EdgeEvent(event_type="line_crossed", camera_id="kirish", direction="in")
    outside = EdgeEvent(event_type="line_crossed", camera_id="kirish", direction="out")

    assert engine.evaluate(inside, now=0.0).rule_name == "faqat-kirish"
    assert engine.evaluate(outside, now=1.0).rule_name is None


def test_first_matching_rule_wins() -> None:
    engine = RuleEngine([
        Rule(name="birinchi", event_type="queue_threshold_exceeded", severity="warning"),
        Rule(name="ikkinchi", event_type="queue_threshold_exceeded", severity="critical"),
    ])
    assert engine.evaluate(queue_event(), now=0.0).rule_name == "birinchi"


# ── Jadval ───────────────────────────────────────────────────────────────


def test_schedule_limits_a_rule_to_working_hours() -> None:
    engine = RuleEngine(
        [Rule(name="ish-vaqtida", event_type="queue_threshold_exceeded",
              schedule="ish", severity="warning")],
        schedules={"ish": Schedule.parse("09:00", "21:00")},
    )

    assert engine.evaluate(queue_event(), now=0.0, local_time=clock_time(12, 0)).rule_name
    assert engine.evaluate(queue_event(), now=1.0, local_time=clock_time(23, 0)).rule_name is None


def test_outside_schedule_covers_after_hours_without_a_second_window() -> None:
    engine = RuleEngine(
        [Rule(name="ish-vaqtidan-tashqari", event_type="person_detected",
              schedule="ish", outside_schedule=True, severity="critical")],
        schedules={"ish": Schedule.parse("09:00", "21:00")},
    )
    event = EdgeEvent(event_type="person_detected", camera_id="zal")

    assert engine.evaluate(event, now=0.0, local_time=clock_time(2, 30)).event.severity == "critical"
    assert engine.evaluate(event, now=1.0, local_time=clock_time(12, 0)).rule_name is None


def test_schedule_can_span_midnight() -> None:
    night = Schedule.parse("22:00", "06:00")
    assert night.contains(clock_time(23, 30)) is True
    assert night.contains(clock_time(3, 0)) is True
    assert night.contains(clock_time(12, 0)) is False


def test_scheduled_rule_does_not_fire_when_time_is_unknown() -> None:
    """Vaqt berilmasa jadvalli qoida ishlamaydi — jim xato bo'lmasin."""
    engine = RuleEngine(
        [Rule(name="ish-vaqtida", event_type="queue_threshold_exceeded", schedule="ish")],
        schedules={"ish": Schedule.parse("09:00", "21:00")},
    )
    assert engine.evaluate(queue_event(), now=0.0, local_time=None).rule_name is None


def test_invalid_time_format_is_rejected() -> None:
    with pytest.raises(ValueError):
        Schedule.parse("9", "21:00")
    with pytest.raises(ValueError):
        Schedule.parse("25:00", "21:00")


# ── Cooldown va bostirish ────────────────────────────────────────────────


def test_cooldown_stops_the_same_alert_repeating() -> None:
    engine = RuleEngine([
        Rule(name="navbat", event_type="queue_threshold_exceeded",
             cooldown_sec=300, actions=["telegram_alert"])
    ])

    assert engine.evaluate(queue_event(), now=0.0).actions == ("telegram_alert",)
    assert engine.evaluate(queue_event(), now=120.0).suppressed is True
    assert engine.evaluate(queue_event(), now=400.0).actions == ("telegram_alert",)


def test_cooldown_is_per_camera_and_zone() -> None:
    engine = RuleEngine([
        Rule(name="navbat", event_type="queue_threshold_exceeded",
             cooldown_sec=300, actions=["telegram_alert"])
    ])
    engine.evaluate(queue_event(camera_id="kassa-01"), now=0.0)

    # Boshqa kassadagi navbat mustaqil.
    assert engine.evaluate(queue_event(camera_id="kassa-02"), now=1.0).suppressed is False


def test_suppress_rule_drops_the_event_entirely() -> None:
    engine = RuleEngine([
        Rule(name="xodimlar-zonasi", event_type="person_detected",
             zone="xodimlar", suppress=True)
    ])
    event = EdgeEvent(event_type="person_detected", camera_id="ombor", zone="xodimlar")

    assert engine.evaluate(event, now=0.0).suppressed is True


def test_decisions_filters_out_suppressed_events() -> None:
    engine = RuleEngine([
        Rule(name="xodimlar", event_type="person_detected", zone="xodimlar", suppress=True)
    ])
    events = [
        EdgeEvent(event_type="person_detected", camera_id="c", zone="xodimlar"),
        EdgeEvent(event_type="person_detected", camera_id="c", zone="zal"),
    ]

    kept = engine.decisions(events, now=0.0)
    assert len(kept) == 1
    assert kept[0].event.zone == "zal"


def test_rule_does_not_mutate_the_original_event() -> None:
    engine = RuleEngine([
        Rule(name="ko'tar", event_type="queue_threshold_exceeded", severity="critical")
    ])
    original = queue_event()

    decision = engine.evaluate(original, now=0.0)

    assert decision.event.severity == "critical"
    assert original.severity == "info"  # asl nusxa tegilmagan


def test_ai_review_is_an_allowed_action() -> None:
    """Qoida kadrni AI ga yubora olishi kerak (8.3)."""
    rule = Rule(name="AI", event_type="camera_tampered", actions=("ai_review",))
    assert "ai_review" in rule.actions


def test_ai_review_is_not_a_default_action() -> None:
    """Pul sarflaydigan harakat o'z-o'zidan yoqilib qolmasin.

    Qoida yozilmagan hodisa standart yo'ldan ketadi; agar `ai_review` shu
    yerda bo'lsa, har bir hodisa uchun chaqiruv bo'lardi.
    """
    from chaqimchi_ai.retail.rules import DEFAULT_ACTIONS

    assert "ai_review" not in DEFAULT_ACTIONS
