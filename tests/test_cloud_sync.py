import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx
import pytest

from chaqimchi_ai.cloud_sync import (
    DEFAULT_RETRY_AFTER_SEC,
    MAX_RETRY_AFTER_SEC,
    CloudEventSync,
    parse_retry_after,
)
from chaqimchi_ai.event_models import EdgeEvent
from chaqimchi_ai.outbox import EventOutbox
from chaqimchi_ai.settings import CloudSyncSettings


class Clock:
    """Qo'lda suriladigan monoton soat."""

    def __init__(self) -> None:
        self.value = 1000.0

    def __call__(self) -> float:
        return self.value


def sync_for(
    tmp_path: Path,
    *,
    handler=None,
    clock: Optional[Clock] = None,
    **settings,
) -> tuple[CloudEventSync, EventOutbox, Clock]:
    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=100_000)
    clock = clock or Clock()
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler)) if handler else None
    sync = CloudEventSync(
        CloudSyncSettings(
            enabled=True,
            url="https://cloud.test",
            site_id="site",
            device_id="device",
            device_token="token",
            **settings,
        ),
        outbox,
        client=client,
        clock=clock,
    )
    return sync, outbox, clock


def test_cloud_sync_uploads_snapshot_heartbeat_and_config(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot.jpg"
    snapshot.write_bytes(b"jpeg")
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"mp4")
    event = EdgeEvent(
        event_id="evt-sync",
        event_type="zone_entered",
        severity="warning",
        camera_id="camera-01",
        snapshot_path=str(snapshot),
        clip_path=str(clip),
    )
    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=100_000)
    outbox.enqueue(event)
    called = []

    def handler(request: httpx.Request) -> httpx.Response:
        called.append(request.url.path)
        if request.url.path.endswith("/events/batch"):
            return httpx.Response(200, json={"accepted": ["evt-sync"]})
        if request.url.path.endswith("/config"):
            return httpx.Response(200, json={"revision": 1, "config": {"zones": []}})
        return httpx.Response(200, json={"ok": True})

    applied = []
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    sync = CloudEventSync(
        CloudSyncSettings(
            enabled=True,
            url="https://cloud.test",
            site_id="site",
            device_id="device",
            device_token="token",
        ),
        outbox,
        client=client,
        health_provider=lambda: {"cameras_active": 8},
        config_applier=applied.append,
    )

    async def exercise() -> None:
        assert await sync.sync_once() == {"sent": 1, "failed": 0, "pending": 1}
        await sync.heartbeat_once()
        await sync.config_once()
        await client.aclose()

    asyncio.run(exercise())
    assert outbox.pending() == []
    assert "/api/v1/edge/events/evt-sync/snapshot" in called
    assert "/api/v1/edge/events/evt-sync/clip" in called
    assert "/api/v1/edge/heartbeat" in called
    assert applied[0]["revision"] == 1


def test_sync_worker_can_stop_without_consuming_the_outbox(tmp_path: Path) -> None:
    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=100_000)
    outbox.enqueue(EdgeEvent(event_type="line_crossed", camera_id="camera-01"))
    sync = CloudEventSync(
        CloudSyncSettings(
            enabled=True,
            url="https://cloud.test",
            site_id="site",
            device_id="device",
            device_token="token",
        ),
        outbox,
    )

    asyncio.run(sync.run(stop_requested=lambda: True))

    assert len(outbox.pending()) == 1
    assert sync.client is None


# ── 429: cloud "sekinla" desa ────────────────────────────────────────────


def test_rate_limit_does_not_blame_the_events(tmp_path: Path) -> None:
    """Butun tuzatishning sababi shu.

    Cloud chegarani oshirdi desa, eski kod har bir eventni "muvaffaqiyatsiz"
    deb belgilardi va 5 soniyadan keyin yana urinardi — abadiy sikl.  Endi
    eventlar tegilmaydi va sikl `Retry-After` gacha to'xtaydi.
    """
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(429, headers={"Retry-After": "120"}, json={"detail": "ko'p"})

    sync, outbox, clock = sync_for(tmp_path, handler=handler)
    outbox.enqueue(EdgeEvent(event_id="evt-1", event_type="line_crossed", camera_id="camera-01"))

    async def exercise() -> None:
        result = await sync.sync_once()
        assert result["throttled"] == 1
        assert result["sent"] == 0 and result["failed"] == 0
        # Blok davomida umuman so'rov yubormaydi.
        assert await sync.sync_once() == {"sent": 0, "failed": 0, "pending": 1}
        await sync.close()

    asyncio.run(exercise())

    assert calls == ["/api/v1/edge/events/batch"]  # ikkinchi urinish bo'lmadi
    assert sync.blocked_for == 120.0
    # Eng muhimi: hodisa hali navbatda va urinishlar hisobiga tegilmagan.
    pending = outbox.pending()
    assert len(pending) == 1
    assert pending[0]["attempts"] == 0
    assert pending[0]["last_error"] is None


def test_sync_resumes_after_the_block_expires(tmp_path: Path) -> None:
    responses = [httpx.Response(429, headers={"Retry-After": "30"})]

    def handler(request: httpx.Request) -> httpx.Response:
        if responses:
            return responses.pop(0)
        return httpx.Response(200, json={"accepted": ["evt-1"]})

    sync, outbox, clock = sync_for(tmp_path, handler=handler)
    outbox.enqueue(EdgeEvent(event_id="evt-1", event_type="line_crossed", camera_id="camera-01"))

    async def exercise() -> None:
        await sync.sync_once()
        clock.value += 31.0
        assert (await sync.sync_once())["sent"] == 1
        await sync.close()

    asyncio.run(exercise())
    assert outbox.pending() == []


def test_a_real_failure_still_counts_against_the_event(tmp_path: Path) -> None:
    """429 istisno; 500 esa eventning muammosi bo'lishi mumkin va sanaladi."""
    from datetime import datetime, timedelta, timezone

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="server xatosi")

    sync, outbox, _clock = sync_for(tmp_path, handler=handler)
    outbox.enqueue(EdgeEvent(event_id="evt-1", event_type="line_crossed", camera_id="camera-01"))

    async def exercise() -> None:
        assert (await sync.sync_once())["failed"] == 1
        await sync.close()

    asyncio.run(exercise())

    # Hodisa navbatda qoladi, lekin darhol qayta yuborilmaydi — aks holda
    # doimiy rad etiladigan hodisa batch o'rnini egallab turardi.
    assert outbox.pending() == []
    assert outbox.stats()["waiting"] == 1
    later = datetime.now(timezone.utc) + timedelta(seconds=30)
    assert outbox.pending(now=later)[0]["attempts"] == 1


@pytest.mark.parametrize(
    "header,expected",
    [
        ("120", 120.0),
        ("  45  ", 45.0),
        (None, DEFAULT_RETRY_AFTER_SEC),
        ("", DEFAULT_RETRY_AFTER_SEC),
        ("0", DEFAULT_RETRY_AFTER_SEC),
        ("-5", DEFAULT_RETRY_AFTER_SEC),
        ("Wed, 21 Oct 2026 07:28:00 GMT", DEFAULT_RETRY_AFTER_SEC),
        ("999999", MAX_RETRY_AFTER_SEC),  # noto'g'ri sarlavha qurilmani jim qilmasin
    ],
)
def test_retry_after_is_parsed_defensively(header, expected) -> None:
    assert parse_retry_after(header) == expected


# ── Adaptiv oraliq ───────────────────────────────────────────────────────


def test_idle_queue_backs_off_but_busy_queue_stays_fast(tmp_path: Path) -> None:
    """Tinch do'kon cloudni har 5 soniyada bezovta qilmasin, lekin
    birinchi hodisada darhol tez oraliqqa qaytsin."""
    sync, _outbox, _clock = sync_for(tmp_path, interval_sec=5, max_interval_sec=60)

    empty = {"sent": 0, "failed": 0, "pending": 0}
    assert sync.next_interval(empty) == 10.0
    assert sync.next_interval(empty) == 20.0
    assert sync.next_interval(empty) == 40.0
    assert sync.next_interval(empty) == 60.0
    assert sync.next_interval(empty) == 60.0  # shiftda to'xtaydi

    assert sync.next_interval({"sent": 1, "failed": 0, "pending": 1}) == 5.0


def test_block_wins_over_the_idle_interval(tmp_path: Path) -> None:
    sync, _outbox, clock = sync_for(tmp_path, interval_sec=5, max_interval_sec=60)
    sync._blocked_until = clock.value + 300.0

    assert sync.next_interval({"sent": 0, "failed": 0, "pending": 3}) == 300.0


def test_max_interval_cannot_be_below_the_floor() -> None:
    with pytest.raises(ValueError, match="max_interval_sec"):
        CloudSyncSettings(interval_sec=30, max_interval_sec=10)


def _event_with_snapshot(tmp_path: Path, event_id: str = "evt-media") -> EdgeEvent:
    snapshot = tmp_path / f"{event_id}.jpg"
    snapshot.write_bytes(b"jpeg")
    return EdgeEvent(
        event_id=event_id,
        event_type="zone_entered",
        severity="critical",
        camera_id="camera-01",
        snapshot_path=str(snapshot),
    )


def test_rate_limited_snapshot_does_not_kill_the_event(tmp_path: Path) -> None:
    """429 rasmni yo'qotadi, HODISANI emas.

    2026-08-26 jonli nosozligi: kunlik snapshot byudjeti tugagach har
    yuklash 429 qaytardi, `outbox.fail()` esa butun hodisani navbatga
    qaytarardi.  Cloud hodisani qayta qabul qilib rasmni yana rad etardi —
    3 soatda 6 315 ta bekor so'rov va do'konning hamma rasmi yo'q.
    """
    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=100_000)
    outbox.enqueue(_event_with_snapshot(tmp_path))
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request.url.path)
        if request.url.path.endswith("/events/batch"):
            return httpx.Response(200, json={"accepted": ["evt-media"]})
        return httpx.Response(429, json={"detail": "Kunlik snapshot chegarasi oshdi"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    sync = CloudEventSync(
        CloudSyncSettings(
            enabled=True,
            url="https://cloud.test",
            site_id="site",
            device_id="device",
            device_token="token",
        ),
        outbox,
        client=client,
    )

    async def exercise() -> dict:
        result = await sync.sync_once()
        await client.aclose()
        return result

    result = asyncio.run(exercise())

    # Hodisa yuborilgan deb hisoblanadi va navbatdan chiqadi.
    assert result["sent"] == 1
    assert result["failed"] == 0
    assert outbox.pending() == []
    assert sync.media_dropped == 1

    # Ikkinchi sikl umuman so'rov yubormasin — halqa yopilgan.
    attempts.clear()

    async def again() -> None:
        client2 = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        sync.client = client2
        await sync.sync_once()
        await client2.aclose()

    asyncio.run(again())
    assert attempts == []


def test_server_error_on_snapshot_still_retries_the_event(tmp_path: Path) -> None:
    """5xx — vaqtinchalik: hodisa navbatda qolsin va qayta urinsin."""
    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=100_000)
    outbox.enqueue(_event_with_snapshot(tmp_path, "evt-5xx"))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/events/batch"):
            return httpx.Response(200, json={"accepted": ["evt-5xx"]})
        return httpx.Response(503, json={"detail": "server band"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    sync = CloudEventSync(
        CloudSyncSettings(
            enabled=True,
            url="https://cloud.test",
            site_id="site",
            device_id="device",
            device_token="token",
        ),
        outbox,
        client=client,
    )

    async def exercise() -> dict:
        result = await sync.sync_once()
        await client.aclose()
        return result

    result = asyncio.run(exercise())
    assert result["sent"] == 0
    assert result["failed"] == 1
    assert sync.media_dropped == 0
    # Navbatda qoldi: backoff o'tgach hodisa yana yuborishga tayyor bo'ladi.
    assert outbox.pending() == []  # hozir — backoff kutmoqda
    later = datetime.now(timezone.utc) + timedelta(hours=1)
    assert [row["event_id"] for row in outbox.pending(now=later)] == ["evt-5xx"]


# ── Uzoq uzilish navbatni yo'q qilmasin ──────────────────────────────────
#
# 2026-08-27 da sinov do'konida 3 375 ta hodisa butunlay yo'qolgan edi va
# eng ko'p uchragan sabab "All connection attempts failed" — ya'ni
# internet uzilishi.  Har muvaffaqiyatsizlik `MAX_ATTEMPTS` ni yeb
# borardi, 20 urinish esa eksponensial kutish bilan ~3 soat: yarim
# kunlik nosozlik navbatning hammasini o'ldirardi.


def test_a_long_outage_does_not_empty_the_queue(tmp_path: Path) -> None:
    from chaqimchi_ai.outbox import MAX_ATTEMPTS

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("All connection attempts failed", request=request)

    sync, outbox, _clock = sync_for(tmp_path, handler=handler)
    outbox.enqueue(EdgeEvent(event_id="evt-1", event_type="line_crossed", camera_id="camera-01"))

    async def exercise() -> None:
        for _ in range(MAX_ATTEMPTS + 5):
            await sync.sync_once()
        await sync.close()

    asyncio.run(exercise())

    assert outbox.stats()["poisoned"] == 0
    later = datetime.now(timezone.utc) + timedelta(days=1)
    assert [row["event_id"] for row in outbox.pending(now=later)] == ["evt-1"]


def test_an_event_the_cloud_refuses_counts_against_itself(tmp_path: Path) -> None:
    """Ayb hodisada bo'lsa u navbatni abadiy to'sib turmasligi kerak.

    Cloud batchni qabul qildi-yu shu hodisani `accepted` ga qo'shmadi:
    sxema yoki maydon buzuq va qayta urinish uni tuzatmaydi.  Tarmoq
    xatosidan farqi shu — bu urinishlar hisobiga KIRADI.
    """
    import sqlite3

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"accepted": []})

    sync, outbox, _clock = sync_for(tmp_path, handler=handler)
    outbox.enqueue(EdgeEvent(event_id="evt-1", event_type="line_crossed", camera_id="camera-01"))

    async def exercise() -> None:
        assert (await sync.sync_once())["failed"] == 1
        await sync.close()

    asyncio.run(exercise())

    with sqlite3.connect(tmp_path / "outbox.db") as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT attempts,hard_failures FROM outbox").fetchone()
    assert row["attempts"] == 1
    assert row["hard_failures"] == 1
