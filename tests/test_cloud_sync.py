import asyncio
from pathlib import Path

import httpx

from chaqimchi_ai.cloud_sync import CloudEventSync
from chaqimchi_ai.event_models import EdgeEvent
from chaqimchi_ai.outbox import EventOutbox
from chaqimchi_ai.settings import CloudSyncSettings


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
        assert await sync.sync_once() == {"sent": 1, "failed": 0}
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
