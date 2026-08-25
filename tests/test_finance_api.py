"""Moliya paneli: xarajatlar REAL manbalardan hisoblanadi.

Gemini — Google `usageMetadata`sidan yozilgan token sarfi; infra — env'dagi
summalar.  Bu testlar hisob matematikasi va taqsimotni qulflaydi.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import cloud.main as main
from cloud.snapshots import LocalSnapshotStore
from cloud.vision_agent import _job_usage, record_usage


@pytest.fixture
def finance_client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CHAQIMCHI_CLOUD_ADMIN_KEY", "test-admin")
    monkeypatch.setenv("CHAQIMCHI_OWNER_JWT_SECRET", "owner-secret-with-more-than-32-characters")
    monkeypatch.setenv("CHAQIMCHI_ENV", "test")
    monkeypatch.setenv("CHAQIMCHI_USD_RATE_UZS", "13000")
    monkeypatch.setenv("CHAQIMCHI_COST_SERVER_MONTHLY_USD", "10")
    monkeypatch.setenv("CHAQIMCHI_COST_DOMAIN_YEARLY_UZS", "27000")
    monkeypatch.setenv("CHAQIMCHI_GEMINI_INPUT_USD_PER_M", "0.30")
    monkeypatch.setenv("CHAQIMCHI_GEMINI_OUTPUT_USD_PER_M", "2.50")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("CHAQIMCHI_S3_ENDPOINT", raising=False)
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "cloud.db")
    monkeypatch.setattr(main, "_store", None)
    monkeypatch.setattr(main, "_event_store", None)
    monkeypatch.setattr(main, "_event_store_key", None)
    monkeypatch.setattr(main, "_snapshots", LocalSnapshotStore(tmp_path / "snapshots"))
    with TestClient(main.app) as client:
        yield client


ADMIN = {"X-Cloud-Admin-Key": "test-admin"}


def _make_site(client: TestClient, name: str, *, pair: bool) -> str:
    site = client.post(
        "/api/v1/admin/sites", headers=ADMIN, json={"name": name, "plan": "biznes"}
    ).json()
    if pair:
        client.post("/api/v1/devices/claim", json={"pairing_code": site["pairing_code"]})
    return str(site["site_id"])


def test_fixed_costs_come_from_env_and_domain_splits_monthly(finance_client) -> None:
    client = finance_client
    _make_site(client, "Do'kon A", pair=True)

    data = client.get("/api/v1/admin/finance", headers=ADMIN).json()
    fixed = data["fixed"]
    assert fixed["server_monthly_usd"] == 10
    assert fixed["server_monthly_uzs"] == 130_000  # 10 $ × 13 000
    assert fixed["server_configured"] is True
    assert fixed["domain_yearly_uzs"] == 27_000
    assert fixed["domain_monthly_uzs"] == 2_250  # 27 000 / 12
    assert fixed["total_monthly_uzs"] == 132_250


def test_infra_is_split_only_between_paired_sites(finance_client) -> None:
    """Stub-sayt (qurilmasiz) haqiqiy mijoz ulushini shishirmasin."""
    client = finance_client
    paired = _make_site(client, "Ulangan", pair=True)
    stub = _make_site(client, "Stub", pair=False)

    data = client.get("/api/v1/admin/finance", headers=ADMIN).json()
    assert data["fixed"]["split_between"] == 1
    rows = {row["site_id"]: row for row in data["sites"]}
    assert rows[paired]["billable"] is True
    assert rows[paired]["shared_cost_uzs"] == data["fixed"]["total_monthly_uzs"]
    assert rows[stub]["billable"] is False
    assert rows[stub]["shared_cost_uzs"] == 0
    assert rows[stub]["revenue_uzs"] == 0, "ulanmagan sayt daromad sifatida sanalmasin"


def test_gemini_cost_uses_real_recorded_tokens(finance_client) -> None:
    """1M kirish × $0.30 + 1M chiqish × $2.50 — kurs 13 000 bilan."""
    client = finance_client
    site_id = _make_site(client, "Baraka", pair=True)
    store = main.get_event_store()
    job = store.create_vision_job(
        site_id, requester_id="owner", requester_kind="owner", question="Savol?"
    )
    store.claim_vision_job()
    store.finish_vision_job(
        site_id, str(job["id"]), result={"answer": "ok"},
        input_tokens=1_000_000, output_tokens=1_000_000,
    )

    month = datetime.now(timezone.utc).strftime("%Y-%m")
    data = client.get(f"/api/v1/admin/finance?month={month}", headers=ADMIN).json()
    gem = data["gemini"]
    assert gem["input_tokens"] == 1_000_000
    assert gem["output_tokens"] == 1_000_000
    # (0.30 + 2.50) $ × 13 000 = 36 400 so'm
    assert gem["cost_uzs"] == 36_400
    assert gem["untracked_jobs"] == 0
    row = next(r for r in data["sites"] if r["site_id"] == site_id)
    assert row["gemini_cost_uzs"] == 36_400
    assert row["total_cost_uzs"] == 36_400 + row["shared_cost_uzs"]
    assert row["margin_uzs"] == row["revenue_uzs"] - row["total_cost_uzs"]
    assert data["totals"]["cost_uzs"] == data["fixed"]["total_monthly_uzs"] + 36_400


def test_untracked_jobs_are_reported_not_hidden(finance_client) -> None:
    client = finance_client
    site_id = _make_site(client, "Eski", pair=True)
    store = main.get_event_store()
    job = store.create_vision_job(
        site_id, requester_id="owner", requester_kind="owner", question="Savol?"
    )
    store.claim_vision_job()
    # Token yozilmagan (eski yozuv formati).
    store.finish_vision_job(site_id, str(job["id"]), result={"answer": "ok"})

    data = client.get("/api/v1/admin/finance", headers=ADMIN).json()
    assert data["gemini"]["untracked_jobs"] == 1


def test_month_param_is_validated(finance_client) -> None:
    assert finance_client.get(
        "/api/v1/admin/finance?month=2026-13", headers=ADMIN
    ).status_code == 422
    assert finance_client.get(
        "/api/v1/admin/finance?month=bugun", headers=ADMIN
    ).status_code == 422


def test_record_usage_accumulates_including_thinking_tokens() -> None:
    """`thoughtsTokenCount` ham chiqishga kiradi — Google shuni billing qiladi."""
    usage = {"input": 0, "output": 0, "calls": 0}
    token = _job_usage.set(usage)
    try:
        record_usage(
            {"usageMetadata": {"promptTokenCount": 1200, "candidatesTokenCount": 80, "thoughtsTokenCount": 40}}
        )
        record_usage({"usageMetadata": {"promptTokenCount": 300, "candidatesTokenCount": 20}})
        record_usage({})  # usageMetadata yo'q — yiqilmaydi
    finally:
        _job_usage.reset(token)
    assert usage == {"input": 1500, "output": 140, "calls": 2}


def test_completed_job_stores_zero_tokens_as_tracked(tmp_path: Path) -> None:
    """Gemini chaqirilmagan job ham `0` bilan yoziladi (NULL emas) —
    Moliya uni "kuzatilmagan" deb adashtirmasin."""
    import asyncio

    from chaqimchi_ai.event_models import EdgeEvent
    from cloud.event_store import EventStore
    from cloud.vision_agent import process_next_job

    store = EventStore(sqlite_path=tmp_path / "events.db")
    store.ingest(
        "site-a", "device-a",
        [EdgeEvent(event_id="evt-a", event_type="line_crossed", camera_id="cam", direction="in")],
    )
    store.create_vision_job(
        "site-a", requester_id="owner", requester_kind="owner", question="Kirdimi?"
    )

    async def missing(_: str) -> bytes:
        raise FileNotFoundError

    async def noop(_: str) -> None:
        return None

    asyncio.run(
        process_next_job(store, cameras_for_site=lambda _: [], media_get=missing, media_delete=noop)
    )
    usage = store.vision_usage_by_site("2000-01-01T00:00:00+00:00", "2100-01-01T00:00:00+00:00")
    assert usage == [
        {"site_id": "site-a", "jobs": 1, "input_tokens": 0, "output_tokens": 0, "untracked_jobs": 0}
    ]
