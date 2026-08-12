from pathlib import Path

from chaqimchi_ai.event_models import EdgeEvent
from chaqimchi_ai.outbox import EventOutbox


def test_outbox_roundtrip_and_idempotency(tmp_path: Path) -> None:
    image = tmp_path / "event.jpg"
    image.write_bytes(b"jpeg")
    event = EdgeEvent(
        event_type="zone_entered",
        severity="warning",
        camera_id="cam-1",
        zone="ombor",
        snapshot_path=str(image),
    )
    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=10_000)
    outbox.enqueue(event)
    outbox.enqueue(event)

    rows = outbox.pending()
    assert len(rows) == 1
    assert rows[0]["payload"]["event_id"] == event.event_id
    assert rows[0]["payload"]["has_snapshot"] is True
    assert outbox.stats()["pending"] == 1
    assert outbox.acknowledge([event.event_id]) == 1
    assert outbox.pending() == []


def test_outbox_enforces_size_limit(tmp_path: Path) -> None:
    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=800)
    for number in range(10):
        outbox.enqueue(
            EdgeEvent(
                event_type="person_detected",
                camera_id="cam",
                metadata={"padding": "x" * 200, "number": number},
            )
        )
    assert outbox.stats()["bytes"] <= 800
    assert outbox.stats()["pending"] < 10


def test_outbox_keeps_critical_events_before_batch_events_when_disk_is_full(tmp_path: Path) -> None:
    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=700)
    for number in range(3):
        outbox.enqueue(
            EdgeEvent(
                event_type="person_detected",
                severity="info",
                camera_id="cam",
                metadata={"padding": "x" * 180, "number": number},
            )
        )
    critical = EdgeEvent(
        event_type="zone_entered",
        severity="critical",
        camera_id="cam",
        metadata={"padding": "x" * 180},
    )
    outbox.enqueue(critical)

    rows = outbox.pending()
    assert rows[0]["event_id"] == critical.event_id
    assert any(row["event_id"] == critical.event_id for row in rows)
