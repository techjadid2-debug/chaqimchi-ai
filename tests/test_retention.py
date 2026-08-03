import asyncio
import sqlite3
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from chaqimchi_ai.events import EventLog
from chaqimchi_ai.licensing.models import LicenseState
from chaqimchi_ai.metrics import get_metrics
from chaqimchi_ai.retention import (
    container_retention_days,
    effective_retention_days,
    purge_once,
    purge_summary,
    retention_loop,
    run_purge,
)
from chaqimchi_ai.runtime.container import AppContainer
from chaqimchi_ai.settings import AppSettings
from webapp.main import create_app


def _make_log(tmp_path: Path) -> EventLog:
    return EventLog(tmp_path / "events.db")


def _add_event(log: EventLog, *, days_ago: int, image_path: str | None = None) -> None:
    """Voqeani berilgan yoshda yozadi (timestamp qo‘lda siljitiladi)."""
    log.log_event("p1", "Ali", "cam1", 0.9, image_path=image_path)
    conn = sqlite3.connect(log.db_path)
    conn.execute(
        "UPDATE events SET timestamp = datetime('now', ?) WHERE id = (SELECT MAX(id) FROM events)",
        (f"-{days_ago} days",),
    )
    conn.commit()
    conn.close()


# ── effective_retention_days ─────────────────────────────────────────────


def test_effective_days_takes_the_shorter_one() -> None:
    assert effective_retention_days(30, 90) == 30
    assert effective_retention_days(180, 90) == 90


def test_effective_days_ignores_zero() -> None:
    assert effective_retention_days(0, 90) == 90
    assert effective_retention_days(30, 0) == 30
    assert effective_retention_days(0, None) == 0


# ── EventLog.purge_older_than ────────────────────────────────────────────


def test_purge_removes_only_old_events(tmp_path: Path) -> None:
    log = _make_log(tmp_path)
    _add_event(log, days_ago=100)
    _add_event(log, days_ago=40)
    _add_event(log, days_ago=1)

    deleted, _ = log.purge_older_than(30)

    assert deleted == 2
    assert log.count_all() == 1


def test_purge_zero_days_keeps_everything(tmp_path: Path) -> None:
    log = _make_log(tmp_path)
    _add_event(log, days_ago=1000)

    assert log.purge_older_than(0) == (0, [])
    assert log.count_all() == 1


def test_purge_returns_image_paths(tmp_path: Path) -> None:
    log = _make_log(tmp_path)
    _add_event(log, days_ago=100, image_path="/snap/a.jpg")
    _add_event(log, days_ago=100, image_path=None)

    deleted, paths = log.purge_older_than(30)

    assert deleted == 2
    assert paths == ["/snap/a.jpg"]


def test_oldest_timestamp(tmp_path: Path) -> None:
    log = _make_log(tmp_path)
    assert log.oldest_timestamp() is None
    _add_event(log, days_ago=5)
    _add_event(log, days_ago=50)
    assert log.oldest_timestamp() is not None
    log.purge_older_than(30)
    assert log.oldest_timestamp() is not None


# ── purge_once: baza + fayllar ───────────────────────────────────────────


def test_purge_once_deletes_snapshot_files(tmp_path: Path) -> None:
    snaps = tmp_path / "snapshots"
    snaps.mkdir()
    old = snaps / "cam1_old.jpg"
    fresh = snaps / "cam1_new.jpg"
    old.write_bytes(b"x" * 100)
    fresh.write_bytes(b"y" * 50)

    log = _make_log(tmp_path)
    _add_event(log, days_ago=100, image_path=str(old))
    _add_event(log, days_ago=1, image_path=str(fresh))

    result = purge_once(log, snaps, 30)

    assert result.events_deleted == 1
    assert result.files_deleted == 1
    assert result.bytes_freed == 100
    assert not old.exists()
    assert fresh.exists()


def test_purge_once_disabled_does_nothing(tmp_path: Path) -> None:
    snaps = tmp_path / "snapshots"
    snaps.mkdir()
    f = snaps / "a.jpg"
    f.write_bytes(b"x")

    log = _make_log(tmp_path)
    _add_event(log, days_ago=999, image_path=str(f))

    result = purge_once(log, snaps, 0)

    assert result.events_deleted == 0
    assert result.files_deleted == 0
    assert f.exists()
    assert log.count_all() == 1


def test_purge_once_sweeps_orphan_files(tmp_path: Path) -> None:
    """Bazada yozuvi yo‘q, lekin muddati o‘tgan fayl ham o‘chadi."""
    snaps = tmp_path / "snapshots"
    snaps.mkdir()
    orphan = snaps / "orphan.jpg"
    orphan.write_bytes(b"z" * 10)
    old_ts = time.time() - 60 * 86400
    import os

    os.utime(orphan, (old_ts, old_ts))

    log = _make_log(tmp_path)
    result = purge_once(log, snaps, 30)

    assert result.files_deleted == 1
    assert not orphan.exists()


def test_purge_once_ignores_non_image_files(tmp_path: Path) -> None:
    snaps = tmp_path / "snapshots"
    snaps.mkdir()
    keep = snaps / "notes.txt"
    keep.write_text("muhim")
    old_ts = time.time() - 60 * 86400
    import os

    os.utime(keep, (old_ts, old_ts))

    log = _make_log(tmp_path)
    purge_once(log, snaps, 30)

    assert keep.exists()


def test_purge_once_refuses_paths_outside_snapshots_dir(tmp_path: Path) -> None:
    """Bazadagi yo‘l papkadan tashqarida bo‘lsa — fayl o‘chirilmaydi."""
    snaps = tmp_path / "snapshots"
    snaps.mkdir()
    outside = tmp_path / "muhim.jpg"
    outside.write_bytes(b"q" * 5)

    log = _make_log(tmp_path)
    _add_event(log, days_ago=100, image_path=str(outside))

    result = purge_once(log, snaps, 30)

    assert result.events_deleted == 1
    assert result.files_deleted == 0
    assert outside.exists()


def test_purge_once_missing_snapshots_dir(tmp_path: Path) -> None:
    log = _make_log(tmp_path)
    _add_event(log, days_ago=100)

    result = purge_once(log, tmp_path / "yoq", 30)

    assert result.events_deleted == 1
    assert result.files_deleted == 0


# ── Konteyner + litsenziya ───────────────────────────────────────────────


def _license(retention_days: int) -> LicenseState:
    return LicenseState(
        site_id="s1",
        plan="starter",
        status="active",
        subscription_until="2030-01-01",
        max_cameras=1,
        max_persons=50,
        retention_days=retention_days,
        telegram_allowed=True,
    )


@pytest.fixture
def container(tmp_path: Path) -> AppContainer:
    return AppContainer(
        tmp_path,
        settings=AppSettings(),
        events=EventLog(tmp_path / "events.db"),
    )


def test_container_days_from_license(container: AppContainer) -> None:
    """Konfigda ko‘rsatilmasa — tarif muddati ishlaydi."""
    assert container_retention_days(container) == 0
    container.license_state = _license(90)
    assert container_retention_days(container) == 90


def test_container_config_cannot_exceed_plan(container: AppContainer) -> None:
    container.settings.events.retention_days = 365
    container.license_state = _license(30)
    assert container_retention_days(container) == 30


def test_container_config_can_be_stricter(container: AppContainer) -> None:
    container.settings.events.retention_days = 7
    container.license_state = _license(365)
    assert container_retention_days(container) == 7


def test_summary_reports_both_sources(container: AppContainer) -> None:
    container.settings.events.retention_days = 60
    container.license_state = _license(90)
    _add_event(container.events, days_ago=3)

    out = purge_summary(container)

    assert out["enabled"] is True
    assert out["retention_days"] == 60
    assert out["config_days"] == 60
    assert out["license_days"] == 90
    assert out["events_total"] == 1
    assert out["last_purge"] is None


# ── Fon vazifasi ─────────────────────────────────────────────────────────


def test_loop_purges_immediately_on_start(container: AppContainer) -> None:
    """Server o‘chib turganda arxiv eskirgani uchun birinchi tozalash kutmaydi."""
    container.settings.events.retention_days = 30
    container.settings.events.retention_interval_sec = 3600
    _add_event(container.events, days_ago=100)

    async def scenario() -> None:
        task = asyncio.create_task(retention_loop(container))
        for _ in range(200):
            await asyncio.sleep(0.01)
            if container.last_purge is not None:
                break
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(scenario())

    assert container.last_purge is not None
    assert container.last_purge.events_deleted == 1
    assert container.events.count_all() == 0


def test_loop_waits_when_retention_disabled(container: AppContainer) -> None:
    """Muddat berilmagan bo‘lsa (litsenziya hali kelmagan) — hech narsa o‘chmaydi."""
    container.settings.events.retention_days = 0
    container.settings.events.retention_interval_sec = 3600
    _add_event(container.events, days_ago=1000)

    async def scenario() -> None:
        task = asyncio.create_task(retention_loop(container))
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(scenario())

    assert container.last_purge is None
    assert container.events.count_all() == 1


def test_run_purge_updates_metrics(container: AppContainer) -> None:
    container.settings.events.retention_days = 30
    _add_event(container.events, days_ago=100)
    before = get_metrics().snapshot()["purged_events_total"]

    result = asyncio.run(run_purge(container))

    assert result.events_deleted == 1
    assert get_metrics().snapshot()["purged_events_total"] == before + 1


# ── API ──────────────────────────────────────────────────────────────────


@pytest.fixture
def client(container: AppContainer) -> TestClient:
    # `with` yo'q — lifespan ishga tushmasin (kameralar, litsenziya).
    return TestClient(create_app(container))


def test_api_retention_status(client: TestClient, container: AppContainer) -> None:
    container.settings.events.retention_days = 30
    r = client.get("/api/retention")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True
    assert body["retention_days"] == 30


def test_api_retention_purge_runs(client: TestClient, container: AppContainer) -> None:
    container.settings.events.retention_days = 30
    _add_event(container.events, days_ago=100)
    _add_event(container.events, days_ago=2)

    r = client.post("/api/retention/purge")

    assert r.status_code == 200, r.text
    assert r.json()["events_deleted"] == 1
    assert container.events.count_all() == 1
    # Holat endi oxirgi tozalashni ko'rsatadi.
    assert client.get("/api/retention").json()["last_purge"]["events_deleted"] == 1


def test_lifespan_starts_and_stops_retention_task(tmp_path: Path) -> None:
    """Server ko‘tarilganda tozalash fon vazifasi rostdan ishga tushadi."""

    class FakeEngine:
        model_name = "fake"
        det_size = (640, 640)
        recognition_ready = True
        providers = ["CPUExecutionProvider"]

    settings = AppSettings()
    settings.events.retention_days = 30
    settings.events.retention_interval_sec = 3600
    events = EventLog(tmp_path / "events.db")
    _add_event(events, days_ago=100)

    from chaqimchi_ai.audit import AuditLog
    from chaqimchi_ai.database import FaceDatabase

    c = AppContainer(
        tmp_path,
        settings=settings,
        engine=FakeEngine(),
        db=FaceDatabase(tmp_path / "db"),
        events=events,
        audit=AuditLog(tmp_path / "audit.db"),
    )

    with TestClient(create_app(c)) as client:
        assert c.retention_task is not None
        for _ in range(200):
            if c.last_purge is not None:
                break
            time.sleep(0.01)
        assert client.get("/api/retention").json()["retention_days"] == 30

    assert c.last_purge is not None
    assert events.count_all() == 0
    # `aclose` fon vazifasini to'xtatgan bo'lishi kerak.
    assert c.retention_task is None


def test_api_retention_purge_requires_key_when_enabled(
    client: TestClient, container: AppContainer
) -> None:
    sec = container.settings.security
    sec.api_key_enabled = True
    sec.api_key = "maxfiy"
    try:
        assert client.post("/api/retention/purge").status_code == 401
        ok = client.post("/api/retention/purge", headers={"X-API-Key": "maxfiy"})
        assert ok.status_code == 200
    finally:
        sec.api_key_enabled = False
        sec.api_key = None
