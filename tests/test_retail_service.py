"""Konfigdan ishga tayyor xizmatgacha: yig'ish, qoidalar va outbox.

Model fayli ham, kamera ham kerak emas: detektor va outbox tashqaridan
beriladi.
"""

from __future__ import annotations

from datetime import time as dt_time
from pathlib import Path
from typing import Any, Dict, List

import pytest

from chaqimchi_ai.event_models import EdgeEvent
from chaqimchi_ai.outbox import EventOutbox
from chaqimchi_ai.retail.service import OutboxSink, build_runner, load_rules
from chaqimchi_ai.settings import AppSettings


class FakeDetector:
    def detect(self, _frame):
        return []


def settings_for(*, vision: Any = None, **retail: Any) -> AppSettings:
    payload: Dict[str, Any] = {
        "scene": {"enabled": True, "model_path": "models/person.onnx"},
        "vision": vision or {"enabled": False},
        "retail": {
            "enabled": True,
            "cameras": [
                {
                    "id": "kassa-01",
                    "stream_url": "rtsp://nvr/kassa/sub",
                    "record_url": "rtsp://nvr/kassa/main",
                    "priority": "security",
                },
                {"id": "zal-01", "stream_url": "rtsp://nvr/zal/sub"},
            ],
            **retail,
        },
    }
    return AppSettings.model_validate(payload)


def runner_for(tmp_path: Path, *, vision: Any = None, **retail: Any):
    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=10 * 1024**2, retention_days=7)
    runner = build_runner(
        settings_for(vision=vision, **retail),
        tmp_path,
        detector=FakeDetector(),
        outbox=outbox,
        on_stats=None,
    )
    return runner, outbox


# ── Yig'ish ──────────────────────────────────────────────────────────────


def test_cameras_get_their_priority_and_buffers(tmp_path: Path) -> None:
    runner, _outbox = runner_for(tmp_path)

    cameras = runner.stats()["broker"]["cameras"]
    assert cameras["kassa-01"]["priority"] == "SECURITY"
    assert cameras["zal-01"]["priority"] == "RETAIL"
    # Faqat `record_url` bor kamera klip yozadi.
    assert runner._streams["kassa-01"].clips is not None
    assert runner._streams["zal-01"].clips is None


def test_disk_quota_is_shared_between_recording_cameras(tmp_path: Path) -> None:
    """8 kamera to'liq kvotani o'ziniki deb bilsa 128 GB disk oldin to'lardi."""
    runner, _outbox = runner_for(tmp_path, buffer_max_bytes=40 * 1024**3)

    buffer = runner._streams["kassa-01"].clips
    assert buffer is not None
    assert buffer.max_bytes == 40 * 1024**3  # yozayotgan bitta kamera


def test_all_cameras_share_one_model(tmp_path: Path) -> None:
    """8 kameraga 8 model yuklash xotira va compile vaqtini bekorga yeydi."""
    detector = FakeDetector()
    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=10 * 1024**2)
    runner = build_runner(settings_for(), tmp_path, detector=detector, outbox=outbox)

    analyzers = [
        runner.pipeline._cameras[camera_id].analyzer for camera_id in ("kassa-01", "zal-01")
    ]
    assert all(analyzer.detector is detector for analyzer in analyzers)


def test_service_refuses_to_start_without_cameras(tmp_path: Path) -> None:
    settings = settings_for(cameras=[])
    with pytest.raises(RuntimeError):
        build_runner(settings, tmp_path, detector=FakeDetector())


def test_disabled_retail_does_not_build(tmp_path: Path) -> None:
    settings = settings_for(enabled=False)
    with pytest.raises(RuntimeError):
        build_runner(settings, tmp_path, detector=FakeDetector())


def test_duplicate_camera_ids_are_rejected() -> None:
    with pytest.raises(ValueError):
        settings_for(
            cameras=[
                {"id": "bir", "stream_url": "rtsp://a"},
                {"id": "bir", "stream_url": "rtsp://b"},
            ]
        )


def test_impossible_budget_is_rejected() -> None:
    with pytest.raises(ValueError):
        settings_for(target_fps=1.0, min_fps=5.0, max_fps=10.0)


# ── Kamera buzilishi va ish vaqti ────────────────────────────────────────


def test_tamper_check_is_on_by_default(tmp_path: Path) -> None:
    """O'g'ri birinchi navbatda kamerani yopadi — bu standart yoqiq bo'lsin."""
    runner, _outbox = runner_for(tmp_path)

    assert runner.pipeline._cameras["kassa-01"].tamper is not None


def test_tamper_check_can_be_turned_off(tmp_path: Path) -> None:
    runner, _outbox = runner_for(tmp_path, tamper_enabled=False)

    assert runner.pipeline._cameras["kassa-01"].tamper is None


def test_business_hours_reach_the_pipeline(tmp_path: Path) -> None:
    runner, _outbox = runner_for(tmp_path, open_from="09:00", open_to="21:00")

    hours = runner.pipeline.business_hours
    assert hours is not None
    assert hours.contains(dt_time(hour=12)) is True
    assert hours.contains(dt_time(hour=23)) is False


def test_without_business_hours_the_night_event_is_off(tmp_path: Path) -> None:
    """Vaqt berilmasa hodisa umuman chiqmaydi — noto'g'ri vaqt yolg'on
    signal bergandan ko'ra yaxshiroq."""
    runner, _outbox = runner_for(tmp_path)

    assert runner.pipeline.business_hours is None


def test_half_written_business_hours_are_rejected() -> None:
    with pytest.raises(ValueError):
        settings_for(open_from="09:00")


def test_a_wrong_time_format_is_rejected() -> None:
    with pytest.raises(ValueError):
        settings_for(open_from="9 tong", open_to="21:00")
    with pytest.raises(ValueError):
        settings_for(open_from="09:00", open_to="25:00")


# ── Qoidalar ─────────────────────────────────────────────────────────────


def test_rules_are_read_from_yaml(tmp_path: Path) -> None:
    path = tmp_path / "rules.yaml"
    path.write_text(
        """
schedules:
  ish-vaqti: {start: "09:00", end: "21:00"}
rules:
  - name: Kassada uzun navbat
    event_type: queue_threshold_exceeded
    conditions: {min_queue_length: 5}
    schedule: ish-vaqti
    severity: warning
    actions: [save_clip, telegram_alert]
""",
        encoding="utf-8",
    )

    engine = load_rules(path)

    assert [rule.name for rule in engine.rules] == ["Kassada uzun navbat"]
    assert engine.rules[0].actions == ("save_clip", "telegram_alert")


def test_a_broken_rules_file_stops_the_service(tmp_path: Path) -> None:
    """Jimgina bo'sh qoida bilan davom etish yomonroq: sotuvchi qoidani
    yozdim deb yuradi, tizim esa hech qachon ogohlantirmaydi."""
    path = tmp_path / "rules.yaml"
    path.write_text("rules:\n  - name: yomon\n    event_type: line_crossed\n    actions: [ucha]\n")

    with pytest.raises(ValueError):
        load_rules(path)


def test_missing_rules_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_rules(tmp_path / "yo-q.yaml")


def test_no_rules_path_means_everything_goes_to_cloud(tmp_path: Path) -> None:
    assert load_rules(None).rules == []


def test_rules_path_is_wired_into_the_pipeline(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "rules.yaml").write_text(
        "rules:\n  - name: bostirish\n    event_type: person_detected\n    suppress: true\n"
    )

    runner, _outbox = runner_for(tmp_path, rules_path="config/rules.yaml")

    assert [rule.name for rule in runner.pipeline.rules.rules] == ["bostirish"]


# ── Outbox ───────────────────────────────────────────────────────────────


def test_events_land_in_the_outbox(tmp_path: Path) -> None:
    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=10 * 1024**2)
    sink = OutboxSink(outbox)
    event = EdgeEvent(event_type="line_crossed", camera_id="kassa-01", direction="in")

    sink("cloud_sync", event)

    pending: List[Dict[str, Any]] = outbox.pending()
    assert [row["event_id"] for row in pending] == [event.event_id]


def test_telegram_action_also_goes_through_the_outbox(tmp_path: Path) -> None:
    """Cloud allaqachon Telegramga yozadi — edge'da ikkinchi mijoz takror
    xabar va shovqin bo'lardi."""
    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=10 * 1024**2)
    sink = OutboxSink(outbox)

    sink(
        "telegram_alert",
        EdgeEvent(event_type="camera_tampered", camera_id="kassa-01", severity="critical"),
    )

    assert len(outbox.pending()) == 1


def test_ignore_action_writes_nothing(tmp_path: Path) -> None:
    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=10 * 1024**2)
    sink = OutboxSink(outbox)

    sink("ignore", EdgeEvent(event_type="person_detected", camera_id="kassa-01"))

    assert outbox.pending() == []


def test_the_important_event_is_uploaded_first(tmp_path: Path) -> None:
    """Internet tiklanganda navbat xavfsizlik hodisasidan boshlanishi kerak."""
    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=10 * 1024**2)
    sink = OutboxSink(outbox)

    sink("cloud_sync", EdgeEvent(event_type="person_detected", camera_id="cam"))
    tampered = EdgeEvent(
        event_type="camera_tampered", camera_id="cam", severity="critical"
    )
    sink("cloud_sync", tampered)

    assert outbox.pending()[0]["event_id"] == tampered.event_id


# ── Ko'rish agentiga ulanish (8.3) ───────────────────────────────────────


def test_vision_is_off_by_default(tmp_path: Path) -> None:
    """Pul sarflaydigan modul o'z-o'zidan yoqilib qolmasin."""
    runner, _outbox = runner_for(tmp_path)

    assert runner.reviewer is None
    assert runner.pipeline.on_review is None
    assert "vision" not in runner.stats()


def test_enabled_vision_is_wired_into_the_pipeline(tmp_path: Path) -> None:
    """`vision.enabled: true` — zanjir kadrni ko'rikchiga uzata oladi."""
    runner, _outbox = runner_for(
        tmp_path, vision={"enabled": True, "min_interval_sec": 60, "max_calls_per_day": 5}
    )

    assert runner.reviewer is not None
    assert runner.pipeline.on_review == runner.reviewer.submit
    # Sozlama yo'lda yo'qolmagan — narx aynan shu raqamlarga bog'liq.
    assert runner.reviewer.agent.config.min_interval_sec == 60
    assert runner.reviewer.agent.config.max_calls_per_day == 5
    assert runner.stats()["vision"]["completed"] == 0


def test_usage_is_shared_with_the_face_service(tmp_path: Path) -> None:
    """Kunlik limit umumiy: ikkala xizmat bitta hisobga yozadi.

    Alohida bo'lsa "kuniga 100 ta" aslida 200 ta bo'lib chiqardi.
    """
    runner, _outbox = runner_for(tmp_path, vision={"enabled": True})

    assert runner.reviewer is not None
    assert runner.reviewer.agent.usage.db_path == tmp_path / "data" / "vision_usage.db"


def test_ai_review_rule_loads(tmp_path: Path) -> None:
    """Namunadagi qoida rostdan yuklanadi (config/rules.yaml sinovi)."""
    path = tmp_path / "rules.yaml"
    path.write_text(
        "rules:\n"
        "  - name: Buzilish\n"
        "    event_type: camera_tampered\n"
        "    actions: [cloud_sync, ai_review]\n",
        encoding="utf-8",
    )

    engine = load_rules(path)

    assert engine.rules[0].actions == ("cloud_sync", "ai_review")
