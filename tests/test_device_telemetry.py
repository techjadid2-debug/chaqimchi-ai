"""Qurilma o'zi haqida rost ma'lumot bersin.

72 soatlik barqarorlik sinovining butun ma'nosi shu raqamlarda: ular
noto'g'ri bo'lsa sinov "o'tdi" deb ko'rinadi-yu, hech narsa isbotlanmaydi.

Bu yerda ikkita haqiqiy xato qo'riqlanadi:

1. `supervisor.status()` `analyzed`, `errors`, `action_errors` ni
   qaytarmasdi.  `cloud_config.send_heartbeat()` esa aynan shu kalitlarni
   o'qiydi — natijada cloudga **doim `0, 0, 0`** ketardi va cloudning
   "qurilma jimgina ishlamay qoldi" detektori Windows yo'lida umuman
   ishlamasdi.
2. Yuborilmagan hodisalar `SELECT COUNT(*) FROM outbox` bilan sanalardi —
   `WHERE sent_at IS NULL` siz.  Yuborilgan yozuvlar ikki kun saqlanadi,
   ya'ni muvaffaqiyatli ketgan hodisalar ham "navbatda" bo'lib ko'rinardi.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any, Dict

import pytest

CLOUD_SYNC = {
    "enabled": True,
    "url": "https://cloud.example.uz",
    "site_id": "site-1",
    "device_id": "dev-1",
    "device_token": "tok-1",
}


@pytest.fixture
def local(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CHAQIMCHI_LOCAL_DIR", str(tmp_path))
    from chaqimchi_ai.local import cloud_config, cloud_link, config_store, counters, paths

    for module in (paths, config_store, counters, cloud_link, cloud_config):
        importlib.reload(module)
    config_store.update("cloud_sync", CLOUD_SYNC)
    return cloud_config


def _write_status(tmp_path: Path, **values: Any) -> None:
    """Retail zanjiri yozadigan holat fayli."""
    import time

    from chaqimchi_ai.local import paths

    payload = {
        "updated_at": time.time(),
        "cameras_configured": 4,
        "cameras_active": 4,
        "cameras": {},
        "analyzed": 0,
        "events": 0,
        "plan_filtered": 0,
        "errors": 0,
        "action_errors": 0,
    }
    payload.update(values)
    paths.status_path().write_text(json.dumps(payload), encoding="utf-8")


def _capture_heartbeat(module, monkeypatch: pytest.MonkeyPatch) -> Dict[str, Any]:
    sent: Dict[str, Any] = {}

    class _Response:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        @staticmethod
        def json() -> Dict[str, Any]:
            return {"ok": True}

    def _post(url, headers=None, json=None, timeout=None):
        sent.update(json or {})
        return _Response()

    monkeypatch.setattr(module.httpx, "post", _post)
    return sent


# ── Tahlil raqamlari cloudga yetsin ─────────────────────────────────────


def test_supervisor_reports_the_numbers_from_the_status_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CHAQIMCHI_LOCAL_DIR", str(tmp_path))
    from chaqimchi_ai.local import config_store, counters, paths, supervisor

    for module in (paths, config_store, counters, supervisor):
        importlib.reload(module)
    _write_status(tmp_path, analyzed=1234, errors=7, action_errors=2)

    status = supervisor.RetailSupervisor().status()

    assert status["analyzed"] == 1234
    assert status["errors"] == 7
    assert status["action_errors"] == 2


def test_heartbeat_carries_the_analysis_numbers(
    local, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Eng muhim tekshiruv: raqam status faylidan cloudgacha yetadimi."""
    sent = _capture_heartbeat(local, monkeypatch)

    assert local.send_heartbeat({"cameras_active": 4, "analyzed": 900, "errors": 5}) is True

    assert sent["analyzed"] == 900
    assert sent["analysis_errors"] == 5, "xatolar cloudga yetmasa nosozlik ko'rinmaydi"


def test_heartbeat_is_not_silently_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Butun zanjir: status fayli → supervisor → heartbeat.

    Aynan shu joyda uzilish bor edi va uni hech qanday test ushlamasdi.
    """
    monkeypatch.setenv("CHAQIMCHI_LOCAL_DIR", str(tmp_path))
    from chaqimchi_ai.local import cloud_config, cloud_link, config_store, counters, paths
    from chaqimchi_ai.local import supervisor as supervisor_module

    for module in (paths, config_store, counters, cloud_link, cloud_config, supervisor_module):
        importlib.reload(module)
    config_store.update("cloud_sync", CLOUD_SYNC)
    _write_status(tmp_path, analyzed=500, errors=3, action_errors=1)
    sent = _capture_heartbeat(cloud_config, monkeypatch)

    status = supervisor_module.RetailSupervisor().status()
    assert cloud_config.send_heartbeat(status) is True

    assert sent["analyzed"] == 500
    assert sent["analysis_errors"] == 3
    assert sent["queue_errors"] == 1


# ── Kutilmagan qayta ishga tushishlar ───────────────────────────────────


def test_crash_counter_survives_a_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hisoblagich xotirada bo'lsa, aynan restart paytida yo'qolardi."""
    monkeypatch.setenv("CHAQIMCHI_LOCAL_DIR", str(tmp_path))
    from chaqimchi_ai.local import counters, paths

    for module in (paths, counters):
        importlib.reload(module)

    counters.bump("chain_crashes")
    counters.bump("chain_crashes")
    # "Jarayon qayta ishga tushdi" — modul toza holatda qayta yuklanadi.
    importlib.reload(counters)

    assert counters.read()["chain_crashes"] == 2


def test_deliberate_restarts_are_counted_separately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mijoz sozlamani o'zgartirib qayta ishga tushirsa — bu nosozlik emas."""
    monkeypatch.setenv("CHAQIMCHI_LOCAL_DIR", str(tmp_path))
    from chaqimchi_ai.local import counters, paths

    for module in (paths, counters):
        importlib.reload(module)

    counters.bump("chain_starts")
    counters.bump("chain_starts")

    data = counters.read()
    assert data["chain_starts"] == 2
    assert data["chain_crashes"] == 0, "qabul mezoni faqat kutilmaganlarini sanaydi"


def test_supervisor_exposes_the_crash_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CHAQIMCHI_LOCAL_DIR", str(tmp_path))
    from chaqimchi_ai.local import config_store, counters, paths, supervisor

    for module in (paths, config_store, counters, supervisor):
        importlib.reload(module)
    _write_status(tmp_path)
    counters.bump("chain_crashes")

    assert supervisor.RetailSupervisor().status()["restart_count"] == 1


# ── Navbat sanog'i ──────────────────────────────────────────────────────


def _outbox_with(tmp_path: Path, *, severity: str = "info", acknowledge: bool = False):
    from chaqimchi_ai.event_models import EdgeEvent
    from chaqimchi_ai.local import paths
    from chaqimchi_ai.outbox import EventOutbox

    outbox = EventOutbox(paths.outbox_path(), max_bytes=1_000_000)
    event = EdgeEvent(event_type="line_crossed", severity=severity, camera_id="cam-1")
    outbox.enqueue(event)
    if acknowledge:
        outbox.acknowledge([event.event_id])
    return outbox


def test_sent_events_are_not_counted_as_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Yuborilgan yozuv ikki kun saqlanadi — u navbat emas."""
    monkeypatch.setenv("CHAQIMCHI_LOCAL_DIR", str(tmp_path))
    from chaqimchi_ai.local import cloud_link, paths

    for module in (paths, cloud_link):
        importlib.reload(module)
    _outbox_with(tmp_path, acknowledge=True)

    assert cloud_link.pending_events() == 0, (
        "panel bekordan 'hodisa yuborilmagan' deb qo'rqitmasin"
    )


def test_pending_and_critical_are_counted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CHAQIMCHI_LOCAL_DIR", str(tmp_path))
    from chaqimchi_ai.local import cloud_link, paths

    for module in (paths, cloud_link):
        importlib.reload(module)
    _outbox_with(tmp_path, severity="critical")

    stats = cloud_link.outbox_stats()
    assert stats["pending"] == 1
    assert stats["critical"] == 1, "kritik hodisa navbatda qolgani alohida ko'rinsin"
    assert stats["poisoned"] == 0


def test_the_queue_numbers_reach_the_cloud(
    local, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cloud modeli bu maydonlarni allaqachon kutadi — Windows yo'li
    ularni yubormasdi."""
    _outbox_with(tmp_path, severity="critical")
    sent = _capture_heartbeat(local, monkeypatch)

    assert local.send_heartbeat({"cameras_active": 4}) is True

    assert sent["outbox_pending"] == 1
    assert sent["outbox_critical_pending"] == 1
    assert "outbox_poisoned" in sent


def test_a_missing_outbox_is_not_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Yangi o'rnatilgan kompyuterda baza hali yo'q."""
    monkeypatch.setenv("CHAQIMCHI_LOCAL_DIR", str(tmp_path))
    from chaqimchi_ai.local import cloud_link, paths

    for module in (paths, cloud_link):
        importlib.reload(module)

    assert cloud_link.outbox_stats() == {"pending": 0, "critical": 0, "poisoned": 0}
