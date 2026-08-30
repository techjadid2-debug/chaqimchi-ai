import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from chaqimchi_ai.event_models import EdgeEvent
from cloud.event_store import EventStore
from cloud.vision_agent import (
    MAX_JOB_ATTEMPTS,
    _time_window,
    parse_query,
    process_next_job,
)


def test_uzbek_query_parser_finds_time_camera_and_event_type() -> None:
    parsed = parse_query(
        "Bugun soat 14:00 dan 16:00 gacha Kirish kamerada kimdir kirdimi?",
        [{"camera_id": "cam-1", "label": "Kirish"}],
    )
    assert parsed["camera_id"] == "cam-1"
    assert parsed["event_types"] == ["line_crossed"]
    assert parsed["direction"] == "in"
    # Chegaralar UTC'da: 14:00 Toshkent = 09:00 UTC.  `occurred_at` bazada
    # UTC-satr va SATR sifatida taqqoslanadi — lokal TZ'li chegara mavjud
    # eventlarni ham "topilmadi" qilib yuborardi.
    assert parsed["start_at"].startswith(
        datetime.now(ZoneInfo("Asia/Tashkent")).date().isoformat()
    ) or "T09:00:00" in parsed["start_at"]
    assert "+00:00" in parsed["start_at"]
    assert "+00:00" in parsed["end_at"]
    assert "T09:00:00" in parsed["start_at"]
    assert "T11:00:00" in parsed["end_at"]


def test_time_window_is_utc_and_survives_bad_hours() -> None:
    now = datetime(2026, 8, 25, 12, 0, tzinfo=ZoneInfo("Asia/Tashkent"))
    start, end = _time_window("kecha 14 dan 16 gacha nima bo'ldi?", now=now)
    assert start == "2026-08-24T09:00:00+00:00"
    assert end == "2026-08-24T11:00:00+00:00"
    # "3 dan 26 gacha" — soat emas.  Avval bu yerda ValueError xom holida
    # jobni yiqitardi; endi butun kun olinadi.
    start, end = _time_window("3 dan 26 gacha bo'lgan orders", now=now)
    assert start == "2026-08-24T19:00:00+00:00"  # kun boshi Toshkentda
    assert end == "2026-08-25T19:00:00+00:00"


def test_vision_job_uses_structured_events_without_external_vlm(tmp_path: Path) -> None:
    store = EventStore(sqlite_path=tmp_path / "events.db")
    store.ingest(
        "site-a", "device-a", [
            EdgeEvent(event_id="evt-a", event_type="line_crossed", camera_id="entry", direction="in")
        ],
    )
    job = store.create_vision_job(
        "site-a", requester_id="owner-a", requester_kind="owner", question="Bugun kimdir kirdimi?"
    )

    async def missing_media(_: str) -> bytes:
        raise FileNotFoundError

    async def ignored_delete(_: str) -> None:
        return None

    worked = asyncio.run(
        process_next_job(
            store,
            cameras_for_site=lambda _: [{"camera_id": "entry", "label": "Kirish"}],
            media_get=missing_media,
            media_delete=ignored_delete,
        )
    )
    assert worked is True
    result = store.vision_job("site-a", job["id"])
    assert result and result["status"] == "completed"
    assert result["result"]["sources"][0]["event_id"] == "evt-a"


class FakeS3Error(Exception):
    """MinIO S3Error kabi: FileNotFoundError EMAS."""


def test_missing_snapshot_in_object_store_does_not_fail_the_job(tmp_path: Path) -> None:
    """Prod'da media_get MinIO S3Error tashlaydi — bitta yo'q rasm butun
    jobni yiqitmasligi kerak."""
    store = EventStore(sqlite_path=tmp_path / "events.db")
    store.ingest(
        "site-a", "device-a", [
            EdgeEvent(
                event_id="evt-b", event_type="after_hours_presence", camera_id="entry",
                has_snapshot=True,
            )
        ],
    )
    store.set_snapshot("site-a", "evt-b", "site-a/evt-b.jpg", size_bytes=10)
    job = store.create_vision_job(
        "site-a", requester_id="owner-a", requester_kind="owner", question="Kecha harakat bo'ldimi?"
    )

    async def s3_error(_: str) -> bytes:
        raise FakeS3Error("NoSuchKey")

    async def ignored_delete(_: str) -> None:
        return None

    asyncio.run(
        process_next_job(
            store,
            cameras_for_site=lambda _: [],
            media_get=s3_error,
            media_delete=ignored_delete,
        )
    )
    result = store.vision_job("site-a", job["id"])
    assert result and result["status"] == "completed", result and result.get("error_text")


def test_face_capture_events_never_reach_the_agent(tmp_path: Path) -> None:
    """Yuz kadrlari agent javobiga manba bo'lmaydi — panel rol-guardini
    agent chetlab o'tmasin."""
    store = EventStore(sqlite_path=tmp_path / "events.db")
    store.ingest(
        "site-a", "device-a", [
            EdgeEvent(event_id="evt-face", event_type="face_captured", camera_id="entry"),
            EdgeEvent(event_id="evt-line", event_type="line_crossed", camera_id="entry", direction="in"),
        ],
    )
    job = store.create_vision_job(
        "site-a", requester_id="owner-a", requester_kind="owner", question="Bugun nima bo'ldi?"
    )

    async def missing_media(_: str) -> bytes:
        raise FileNotFoundError

    async def ignored_delete(_: str) -> None:
        return None

    asyncio.run(
        process_next_job(
            store,
            cameras_for_site=lambda _: [],
            media_get=missing_media,
            media_delete=ignored_delete,
        )
    )
    result = store.vision_job("site-a", job["id"])
    ids = [item["event_id"] for item in result["result"]["sources"]]
    assert "evt-line" in ids
    assert "evt-face" not in ids


def test_stale_running_jobs_are_requeued_then_failed(tmp_path: Path) -> None:
    """Worker qulasa job abadiy `running` qolmasin: avval requeue,
    urinishlar tugagach aniq xato bilan yopiladi."""
    store = EventStore(sqlite_path=tmp_path / "events.db")
    job = store.create_vision_job(
        "site-a", requester_id="owner-a", requester_kind="owner", question="Savol?"
    )
    claimed = store.claim_vision_job()
    assert claimed and str(claimed["id"]) == str(job["id"])
    # started_at ni eski qilib qo'yamiz — "worker o'lgan" holati.
    old = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    with store._connect() as conn:  # noqa: SLF001 — test to'g'ridan-to'g'ri holat quradi
        conn.execute(store._sql("UPDATE vision_jobs SET started_at=?"), (old,))

    assert store.requeue_stale_vision_jobs(older_than_sec=300, max_attempts=MAX_JOB_ATTEMPTS) == 1
    requeued = store.vision_job("site-a", str(job["id"]))
    assert requeued["status"] == "queued"

    # Urinishlar tugagan job endi failed bo'ladi.
    with store._connect() as conn:  # noqa: SLF001
        conn.execute(
            store._sql("UPDATE vision_jobs SET status='running',started_at=?,attempts=?"),
            (old, MAX_JOB_ATTEMPTS),
        )
    store.requeue_stale_vision_jobs(older_than_sec=300, max_attempts=MAX_JOB_ATTEMPTS)
    failed = store.vision_job("site-a", str(job["id"]))
    assert failed["status"] == "failed"
    assert "qayta yuboring" in (failed["error_text"] or "")


def test_daily_job_count_comes_from_the_database(tmp_path: Path) -> None:
    """Kunlik pul limiti DB'dan sanaladi — restart uni nolga tushirmaydi."""
    store = EventStore(sqlite_path=tmp_path / "events.db")
    for _ in range(3):
        store.create_vision_job(
            "site-a", requester_id="owner-a", requester_kind="owner", question="Savol?"
        )
    since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    assert store.count_vision_jobs_since("site-a", since) == 3
    assert store.count_vision_jobs_since("site-b", since) == 0


def test_vision_data_purge_returns_audio_keys(tmp_path: Path) -> None:
    store = EventStore(sqlite_path=tmp_path / "events.db")
    job = store.create_vision_job(
        "site-a", requester_id="owner-a", requester_kind="owner", question="Savol?"
    )
    store.finish_vision_job(
        "site-a", str(job["id"]), result={"answer": "ok"},
        audio_reply_key="agent/replies/site-a/x.bin",
    )
    old = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
    with store._connect() as conn:  # noqa: SLF001
        conn.execute(store._sql("UPDATE vision_jobs SET created_at=?"), (old,))
    keys = store.purge_vision_data(retention_days=90)
    assert keys == ["agent/replies/site-a/x.bin"]
    assert store.vision_job("site-a", str(job["id"])) is None


def test_vision_settings_are_per_site(tmp_path: Path) -> None:
    store = EventStore(sqlite_path=tmp_path / "events.db")
    store.set_vision_consent("site-a", consented=True, actor_id="owner-a")
    assert store.vision_settings("site-a")["consented"] is True
    assert store.vision_settings("site-b")["consented"] is False


def test_a_recently_failed_job_gets_another_try(tmp_path: Path) -> None:
    """`MAX_JOB_ATTEMPTS` va'dasi `failed` yo'lida ham bajarilsin.

    2026-08-29 da eganing "bugun nimalar bo'ldi?" savoli bitta
    "Gemini javob bermadi" bilan o'ldi: qayta urinish faqat `running`
    da qotib qolgan jobga tegishli edi.
    """
    store = EventStore(sqlite_path=tmp_path / "events.db")
    job = store.create_vision_job(
        "site-a", requester_id="owner-a", requester_kind="owner", question="Bugun nimalar bo'ldi?"
    )
    store.finish_vision_job("site-a", str(job["id"]), error="Gemini javob bermadi")

    assert store.requeue_failed_vision_jobs(within_sec=300, max_attempts=MAX_JOB_ATTEMPTS) == 1

    retried = store.vision_job("site-a", str(job["id"]))
    assert retried["status"] == "queued"
    assert not retried["error_text"], "eski xato matni yangi urinishga o'tmasin"


def test_an_old_failure_is_left_alone(tmp_path: Path) -> None:
    """Kechagi savolga bugun javob berish javob bermaslikdan yomonroq."""
    store = EventStore(sqlite_path=tmp_path / "events.db")
    job = store.create_vision_job(
        "site-a", requester_id="owner-a", requester_kind="owner", question="Savol?"
    )
    store.finish_vision_job("site-a", str(job["id"]), error="Gemini javob bermadi")
    old = (datetime.now(timezone.utc) - timedelta(hours=20)).isoformat()
    with store._connect() as conn:  # noqa: SLF001 — test to'g'ridan-to'g'ri holat quradi
        conn.execute(store._sql("UPDATE vision_jobs SET completed_at=?"), (old,))

    assert store.requeue_failed_vision_jobs(within_sec=300, max_attempts=MAX_JOB_ATTEMPTS) == 0
    assert store.vision_job("site-a", str(job["id"]))["status"] == "failed"


def test_a_job_out_of_attempts_stays_failed(tmp_path: Path) -> None:
    store = EventStore(sqlite_path=tmp_path / "events.db")
    job = store.create_vision_job(
        "site-a", requester_id="owner-a", requester_kind="owner", question="Savol?"
    )
    store.finish_vision_job("site-a", str(job["id"]), error="Gemini javob bermadi")
    with store._connect() as conn:  # noqa: SLF001
        conn.execute(store._sql("UPDATE vision_jobs SET attempts=?"), (MAX_JOB_ATTEMPTS,))

    assert store.requeue_failed_vision_jobs(within_sec=300, max_attempts=MAX_JOB_ATTEMPTS) == 0
