"""Edge outbox'ini HTTPS orqali cloudga uzatish."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Callable, Dict, Optional

import httpx

from chaqimchi_ai.outbox import EventOutbox
from chaqimchi_ai.settings import CloudSyncSettings

logger = logging.getLogger(__name__)


class CloudEventSync:
    def __init__(
        self,
        settings: CloudSyncSettings,
        outbox: EventOutbox,
        *,
        client: Optional[httpx.AsyncClient] = None,
        health_provider: Optional[Callable[[], Dict[str, object]]] = None,
        config_applier: Optional[Callable[[Dict[str, object]], None]] = None,
    ) -> None:
        self.settings = settings
        self.outbox = outbox
        self.client = client
        self._owns_client = client is None
        self.health_provider = health_provider
        self.config_applier = config_applier
        self._last_heartbeat = 0.0

    @property
    def headers(self) -> Dict[str, str]:
        return {
            "X-Site-Id": self.settings.site_id or "",
            "X-Device-Id": self.settings.device_id or "",
            "X-Device-Token": self.settings.device_token or "",
        }

    async def _get_client(self) -> httpx.AsyncClient:
        if self.client is None:
            self.client = httpx.AsyncClient(timeout=30)
        return self.client

    async def sync_once(self) -> Dict[str, int]:
        rows = self.outbox.pending(self.settings.batch_size)
        if not rows:
            return {"sent": 0, "failed": 0}
        client = await self._get_client()
        base = self.settings.url.rstrip("/")
        try:
            response = await client.post(
                f"{base}/api/v1/edge/events/batch",
                headers=self.headers,
                json={"events": [row["payload"] for row in rows]},
            )
            response.raise_for_status()
            accepted = set(response.json().get("accepted", []))
        except Exception as exc:  # noqa: BLE001 - navbat keyingi siklda qayta urinadi
            for row in rows:
                self.outbox.fail(row["event_id"], str(exc))
            logger.warning("Cloud event sync muvaffaqiyatsiz: %s", exc)
            return {"sent": 0, "failed": len(rows)}

        completed = []
        failed = 0
        for row in rows:
            event_id = row["event_id"]
            if event_id not in accepted:
                self.outbox.fail(event_id, "cloud eventni qabul qilmadi")
                failed += 1
                continue
            snapshot = row.get("snapshot_path")
            if snapshot and Path(snapshot).is_file():
                try:
                    with Path(snapshot).open("rb") as handle:
                        upload = await client.put(
                            f"{base}/api/v1/edge/events/{event_id}/snapshot",
                            headers={**self.headers, "Content-Type": "image/jpeg"},
                            content=handle.read(),
                        )
                    upload.raise_for_status()
                except Exception as exc:  # noqa: BLE001
                    self.outbox.fail(event_id, str(exc))
                    failed += 1
                    continue
            clip = row.get("clip_path")
            if clip and Path(clip).is_file():
                try:
                    with Path(clip).open("rb") as handle:
                        upload = await client.put(
                            f"{base}/api/v1/edge/events/{event_id}/clip",
                            headers={**self.headers, "Content-Type": "video/mp4"},
                            content=handle.read(),
                        )
                    upload.raise_for_status()
                except Exception as exc:  # noqa: BLE001
                    self.outbox.fail(event_id, str(exc))
                    failed += 1
                    continue
            completed.append(event_id)
        self.outbox.acknowledge(completed)
        return {"sent": len(completed), "failed": failed}

    async def heartbeat_once(self) -> None:
        if self.health_provider is None:
            return
        client = await self._get_client()
        response = await client.post(
            f"{self.settings.url.rstrip('/')}/api/v1/edge/heartbeat",
            headers=self.headers,
            json=self.health_provider(),
        )
        response.raise_for_status()

    async def config_once(self) -> None:
        if self.config_applier is None:
            return
        client = await self._get_client()
        response = await client.get(
            f"{self.settings.url.rstrip('/')}/api/v1/edge/config", headers=self.headers
        )
        response.raise_for_status()
        self.config_applier(response.json())

    async def run(self, stop_requested: Optional[Callable[[], bool]] = None) -> None:
        try:
            while not (stop_requested and stop_requested()):
                try:
                    await self.sync_once()
                    now = time.monotonic()
                    if now - self._last_heartbeat >= self.settings.heartbeat_interval_sec:
                        await self.heartbeat_once()
                        await self.config_once()
                        self._last_heartbeat = now
                except asyncio.CancelledError:
                    break
                except Exception:  # pragma: no cover - mustaqil fon sikli
                    logger.exception("Cloud sync siklida kutilmagan xato")
                await asyncio.sleep(self.settings.interval_sec)
        finally:
            await self.close()

    async def close(self) -> None:
        if self._owns_client and self.client is not None:
            await self.client.aclose()
        self.client = None
