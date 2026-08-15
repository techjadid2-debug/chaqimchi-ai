from pathlib import Path

from chaqimchi_ai.event_models import EdgeEvent
from chaqimchi_ai.outbox import (
    BASE_RETRY_DELAY_SEC,
    MAX_ATTEMPTS,
    MAX_RETRY_DELAY_SEC,
    EventOutbox,
    retry_delay,
)


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


def test_outbox_attaches_clip_after_initial_event(tmp_path: Path) -> None:
    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=100_000)
    event = EdgeEvent(
        event_id="event-with-late-clip",
        event_type="after_hours_presence",
        severity="critical",
        camera_id="cam",
    )
    outbox.enqueue(event)
    clip = tmp_path / "event.mp4"
    clip.write_bytes(b"video")
    event.clip_path = str(clip)
    outbox.enqueue(event)

    row = outbox.pending()[0]
    assert row["clip_path"] == str(clip)
    assert row["payload"]["has_clip"] is True
    assert "clip_path" not in row["payload"]
    assert outbox.clip_path(event.event_id) == str(clip)


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


# ── Backoff va umidsiz hodisalar ─────────────────────────────────────────


def _event(event_id: str = "evt-1", **kwargs) -> EdgeEvent:
    return EdgeEvent(event_id=event_id, event_type="line_crossed", camera_id="camera-01", **kwargs)


def test_a_rejected_event_stops_blocking_the_batch(tmp_path: Path) -> None:
    """Butun tuzatishning sababi.

    Cloud biror hodisani doimiy rad etsa (eski sxema, buzuq maydon), u
    har 5 soniyada qayta yuborilar va batch o'rnini egallab turardi —
    ortidagi yaxshi hodisalar esa kutib qolardi.
    """
    from datetime import datetime, timedelta, timezone

    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=10**7)
    outbox.enqueue(_event("yomon"))
    outbox.enqueue(_event("yaxshi"))
    moment = datetime.now(timezone.utc)

    outbox.fail("yomon", "cloud rad etdi", now=moment)

    # Yomoni navbatdan chiqdi, yaxshisi qoldi.
    assert [row["event_id"] for row in outbox.pending(now=moment)] == ["yaxshi"]
    assert outbox.stats()["waiting"] == 1
    # Kutish tugagach yana urinib ko'riladi.
    later = moment + timedelta(seconds=retry_delay(1) + 1)
    assert sorted(row["event_id"] for row in outbox.pending(now=later)) == ["yaxshi", "yomon"]


def test_the_delay_doubles_and_stops_at_the_ceiling() -> None:
    assert retry_delay(1) == BASE_RETRY_DELAY_SEC
    assert retry_delay(2) == BASE_RETRY_DELAY_SEC * 2
    assert retry_delay(3) == BASE_RETRY_DELAY_SEC * 4
    # Shiftga tegib to'xtaydi: cloud tiklanishi 5 daqiqadan uzoq
    # kutishga arzimaydi.
    assert retry_delay(50) == MAX_RETRY_DELAY_SEC
    # Nol yoki manfiy urinish ham xato bermasin.
    assert retry_delay(0) == BASE_RETRY_DELAY_SEC


def test_a_hopeless_event_is_dropped_but_not_lost(tmp_path: Path) -> None:
    """Nima uchun rad etilganini keyin ko'rish mumkin bo'lsin."""
    from datetime import datetime, timedelta, timezone

    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=10**7)
    outbox.enqueue(_event("umidsiz"))
    moment = datetime.now(timezone.utc)

    for attempt in range(MAX_ATTEMPTS):
        outbox.fail("umidsiz", f"{attempt}-urinish rad etildi", now=moment)
        moment += timedelta(seconds=MAX_RETRY_DELAY_SEC + 1)

    assert outbox.pending(now=moment) == []
    stats = outbox.stats()
    assert stats["pending"] == 0
    assert stats["poisoned"] == 1

    dropped = outbox.dead_letters()
    assert len(dropped) == 1
    assert dropped[0]["event_id"] == "umidsiz"
    assert dropped[0]["attempts"] == MAX_ATTEMPTS
    assert "rad etildi" in dropped[0]["last_error"]


def test_failing_an_unknown_event_is_harmless(tmp_path: Path) -> None:
    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=10**7)
    outbox.fail("yo-q", "xato")  # xato bermasligi kerak
    assert outbox.stats()["poisoned"] == 0


def test_a_new_payload_gets_a_fresh_chance(tmp_path: Path) -> None:
    """Klip tayyor bo'lganda hodisa qayta yoziladi — bu yangi imkoniyat.

    Lekin `attempts` saqlanadi: umidsiz hodisa klip orqali cheksiz qayta
    urinaverishi mumkin bo'lmasin.
    """
    from datetime import datetime, timezone

    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=10**7)
    clip = tmp_path / "klip.mp4"
    clip.write_bytes(b"mp4")
    outbox.enqueue(_event("evt-1"))
    moment = datetime.now(timezone.utc)
    outbox.fail("evt-1", "tarmoq yo'q", now=moment)
    assert outbox.pending(now=moment) == []

    outbox.enqueue(_event("evt-1", clip_path=str(clip)))

    row = outbox.pending(now=moment)[0]
    assert row["event_id"] == "evt-1"
    assert row["attempts"] == 1  # hisob nolga tushmadi
    assert row["clip_path"] == str(clip)


def test_successful_delivery_clears_everything(tmp_path: Path) -> None:
    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=10**7)
    outbox.enqueue(_event("evt-1"))
    outbox.fail("evt-1", "vaqtincha xato")

    assert outbox.acknowledge(["evt-1"]) == 1
    assert outbox.stats() == {"pending": 0, "bytes": 0, "waiting": 0, "poisoned": 0}


def test_dead_letters_do_not_pile_up_forever(tmp_path: Path) -> None:
    """Ular diagnostika uchun, arxiv uchun emas."""
    from datetime import datetime, timedelta, timezone

    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=10**7, retention_days=1)
    outbox.enqueue(_event("eski"))
    old = datetime.now(timezone.utc) - timedelta(days=5)
    for _ in range(MAX_ATTEMPTS):
        outbox.fail("eski", "rad etildi", now=old)

    assert outbox.stats()["poisoned"] == 1
    outbox.prune()
    assert outbox.stats()["poisoned"] == 0


def test_the_schema_upgrades_an_existing_database(tmp_path: Path) -> None:
    """Ishlab turgan qurilmada baza allaqachon bor — yangi ustun
    qo'shilganda u yiqilmasligi kerak."""
    import sqlite3

    path = tmp_path / "outbox.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE outbox (event_id TEXT PRIMARY KEY, payload TEXT NOT NULL,"
            "snapshot_path TEXT, snapshot_size INTEGER NOT NULL DEFAULT 0,"
            "created_at TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT)"
        )
        conn.execute(
            "INSERT INTO outbox(event_id,payload,created_at) VALUES('eski','{}','2026-01-01T00:00:00+00:00')"
        )

    outbox = EventOutbox(path, max_bytes=10**7)

    assert outbox.stats()["pending"] == 1
    assert outbox.pending()[0]["event_id"] == "eski"
    outbox.fail("eski", "xato")
    assert outbox.stats()["waiting"] == 1
