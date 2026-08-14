"""Sotqin `/config` ni faqat rostdan o'zgarganda tortadi.

Bungacha har heartbeat'da (standart 60 s) to'liq config so'ralardi — kuniga
1440 ta og'ir so'rov: cloud har safar funksiya narxini qayta hisoblab, har
kameraning RTSP parolini deshifrlardi. Javob esa deyarli har doim bir xil.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest

from chaqimchi_ai.event_models import EdgeEvent
from chaqimchi_ai.outbox import EventOutbox
from chaqimchi_ai.sotqin_agent import SotqinAgent


class FakeResponse:
    def __init__(self, payload: Dict[str, Any]) -> None:
        self._payload = payload

    def json(self) -> Dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        return None


class FakeClient:
    """Agent qaysi marshrutlarni chaqirganini yozib boradi."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.calls: List[str] = []
        self.heartbeat_reply: Dict[str, Any] = {}

    async def post(self, url: str, **_kwargs) -> FakeResponse:
        self.calls.append(url)
        if url.endswith("/heartbeat"):
            return FakeResponse(self.heartbeat_reply)
        return FakeResponse({"ok": True})

    async def get(self, url: str, **_kwargs) -> FakeResponse:
        self.calls.append(url)
        return FakeResponse(self.config)


def config_payload(revision: int) -> Dict[str, Any]:
    return {
        "revision": revision,
        "product": {"name": "Sotqin", "max_cameras": 8},
        "buffer_policy": {"max_days": 3, "max_bytes": 40 * 1024**3},
        "cameras": [],
        "cloud_features": [],
    }


@pytest.fixture
def agent(tmp_path: Path, monkeypatch) -> SotqinAgent:
    monkeypatch.setenv("CHAQIMCHI_CLOUD_URL", "https://cloud.example.uz")
    monkeypatch.setenv("CHAQIMCHI_SITE_ID", "site-1")
    monkeypatch.setenv("CHAQIMCHI_DEVICE_ID", "device-1")
    monkeypatch.setenv("CHAQIMCHI_DEVICE_TOKEN", "token-1")
    monkeypatch.setenv("CHAQIMCHI_SOTQIN_CONFIG_CACHE", str(tmp_path / "sotqin-config.json"))
    return SotqinAgent()


def config_calls(client: FakeClient) -> int:
    return sum(1 for url in client.calls if url.endswith("/sotqin/config"))


@pytest.mark.asyncio
async def test_first_heartbeat_pulls_config_then_stops_pulling(agent) -> None:
    client = FakeClient(config_payload(4))
    agent.client = client

    # Birinchi marta qurilmada config yo'q — cloud "o'zgardi" deydi.
    client.heartbeat_reply = {"ok": True, "config_revision": 4, "config_changed": True}
    await agent.heartbeat_once()
    assert config_calls(client) == 1
    assert agent.remote_config_revision == 4
    assert agent.config_status == "applied"

    # Keyingi 10 heartbeat — bitta ham config so'rovi yo'q.
    client.heartbeat_reply = {"ok": True, "config_revision": 4, "config_changed": False}
    for _ in range(10):
        await agent.heartbeat_once()
    assert config_calls(client) == 1
    assert agent.last_error is None


@pytest.mark.asyncio
async def test_revision_change_pulls_config_again(agent) -> None:
    client = FakeClient(config_payload(4))
    agent.client = client
    client.heartbeat_reply = {"ok": True, "config_revision": 4, "config_changed": True}
    await agent.heartbeat_once()

    client.config = config_payload(5)
    client.heartbeat_reply = {"ok": True, "config_revision": 5, "config_changed": True}
    await agent.heartbeat_once()

    assert config_calls(client) == 2
    assert agent.remote_config_revision == 5


@pytest.mark.asyncio
async def test_old_cloud_without_the_flag_still_works(agent) -> None:
    """Cloud yangilanmagan bo'lsa agent eski yo'l bilan ishlayveradi."""
    client = FakeClient(config_payload(2))
    agent.client = client
    client.heartbeat_reply = {"ok": True}

    await agent.heartbeat_once()

    assert config_calls(client) == 1
    assert agent.remote_config_revision == 2


@pytest.mark.asyncio
async def test_unapplied_config_is_retried_even_when_unchanged(agent) -> None:
    """ACK yuborilmay qolgan bo'lsa qurilma config'ni qayta oladi."""
    client = FakeClient(config_payload(7))
    agent.client = client
    agent.remote_config_revision = 7
    agent.config_status = "rejected"
    client.heartbeat_reply = {"ok": True, "config_revision": 7, "config_changed": False}

    await agent.heartbeat_once()

    assert config_calls(client) == 1
    assert agent.config_status == "applied"


@pytest.mark.asyncio
async def test_unchanged_config_still_reprobes_camera_health(agent, monkeypatch) -> None:
    client = FakeClient(config_payload(4))
    agent.client = client
    agent.remote_config_revision = 4
    agent.config_status = "applied"
    agent.probe_interval = 60
    client.heartbeat_reply = {"ok": True, "config_revision": 4, "config_changed": False}
    moments = iter([100.0, 120.0, 161.0])
    monkeypatch.setattr(agent, "monotonic", lambda: next(moments))
    probes = 0

    async def report() -> None:
        nonlocal probes
        probes += 1

    monkeypatch.setattr(agent, "report_camera_probes", report)

    await agent.heartbeat_once()
    await agent.heartbeat_once()
    await agent.heartbeat_once()

    assert probes == 2
    assert config_calls(client) == 0


def test_control_health_sums_retail_and_attendance_outboxes(agent, tmp_path) -> None:
    retail = EventOutbox(tmp_path / "retail.db", max_bytes=100_000)
    attendance = EventOutbox(tmp_path / "attendance.db", max_bytes=100_000)
    retail.enqueue(
        EdgeEvent(
            event_type="camera_tampered",
            severity="critical",
            camera_id="camera-01",
        )
    )
    attendance.enqueue(EdgeEvent(event_type="employee_seen", camera_id="camera-02"))
    agent.outbox_paths = (retail.db_path, attendance.db_path)

    health = agent.health_payload()

    assert health["outbox_pending"] == 2
    assert health["outbox_bytes"] > 0
    assert health["outbox_critical_pending"] == 1
