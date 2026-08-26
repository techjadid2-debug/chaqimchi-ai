"""Moliya paneli: xarajatlar REAL manbalardan hisoblanadi.

Gemini — Google `usageMetadata`sidan yozilgan token sarfi; infra — env'dagi
summalar.  Bu testlar hisob matematikasi va taqsimotni qulflaydi.
"""

from datetime import datetime, timedelta, timezone
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
    monkeypatch.setenv("CHAQIMCHI_COST_KWH_UZS", "1000")
    monkeypatch.setenv("CHAQIMCHI_DEVICE_WATTS_WINDOWS", "65")
    monkeypatch.setenv("CHAQIMCHI_DEVICE_WATTS_BOX", "12")
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


# ── Elektr sarfi ─────────────────────────────────────────────────────────
#
# Elektr O'LCHANGAN ish vaqtidan hisoblanadi: `device_metrics` daqiqalik
# bucket yozadi, ya'ni bucket sanog'i — kompyuter necha daqiqa ishlagani.
# Taxminiy "24/7" bilan hisoblash kechasi o'chiriladigan do'kon
# kompyuterining tannarxini ikki barobar oshirib yuborardi.


def _add_uptime(site_id: str, minutes: int, *, device_id: str = "dev-1") -> None:
    """Sayt uchun `minutes` ta daqiqalik bucket yozadi (joriy oyning boshidan)."""
    import json

    store = main.get_event_store()
    now = datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    payload = json.dumps({"cameras_active": 2})
    with store._connect() as conn:
        for i in range(minutes):
            bucket = (start + timedelta(minutes=i)).isoformat()
            conn.execute(
                store._sql(
                    "INSERT INTO device_metrics (device_id,site_id,bucket_at,payload_json,received_at)"
                    " VALUES (?,?,?,?,?)"
                ),
                (device_id, site_id, bucket, payload, bucket),
            )


def _windows_site(client: TestClient, name: str) -> str:
    """Do'kon kompyuteri ulangan sayt.

    `devices/claim` standart holda qurilmani "Sotqin" (Box) deb yozadi —
    elektr hisobida bu Box vattini beradi.  Windows yo'lini sinash uchun
    tur ANIQ ko'rsatiladi.
    """
    site = client.post(
        "/api/v1/admin/sites", headers=ADMIN, json={"name": name, "plan": "biznes"}
    ).json()
    client.post(
        "/api/v1/devices/claim",
        json={"pairing_code": site["pairing_code"], "product_name": "Chaqimchi Windows"},
    )
    return str(site["site_id"])


def _site_row(client: TestClient, site_id: str) -> dict:
    body = client.get("/api/v1/admin/finance", headers=ADMIN).json()
    return next(row for row in body["sites"] if row["site_id"] == site_id)


def test_energy_is_computed_from_measured_uptime(finance_client) -> None:
    """720 soat × 65 Vt × 1000 so'm/kVt·soat = 46 800 so'm."""
    site_id = _windows_site(finance_client, "Elektr")
    _add_uptime(site_id, 720 * 60)

    row = _site_row(finance_client, site_id)

    assert row["energy_measured"] is True
    assert row["energy_uptime_hours"] == 720.0
    assert row["energy_kwh"] == 46.8
    assert row["energy_cost_uzs"] == 46_800


def test_a_computer_switched_off_half_the_month_costs_half(finance_client) -> None:
    """O'lchov haqiqatan ishlatilsin — aks holda bu son shunchaki
    konstantaga ko'paytirilgan taxmin bo'lardi."""
    site_id = _windows_site(finance_client, "Yarim oy")
    _add_uptime(site_id, 360 * 60)

    row = _site_row(finance_client, site_id)

    assert row["energy_uptime_hours"] == 360.0
    assert row["energy_cost_uzs"] == 23_400


def test_no_measurement_is_not_the_same_as_zero(finance_client) -> None:
    """`device_metrics` 30 kun saqlanadi — eski oyda bucket bo'lmaydi.

    O'shanda "elektr 0 so'm" deb ko'rsatish "bepul edi" degan yolg'on
    xulosaga olib borardi.  Panel `energy_measured` ni ko'rib `—` chizadi.
    """
    site_id = _make_site(finance_client, "O'lchovsiz", pair=True)

    row = _site_row(finance_client, site_id)

    assert row["energy_measured"] is False
    assert row["energy_cost_uzs"] == 0
    assert row["energy_uptime_hours"] == 0.0


def test_the_shop_computer_is_costlier_than_a_box(finance_client) -> None:
    """Windows desktop N100 qutisidan bir necha barobar ko'p tok yeydi —
    bir xil ish vaqtida tannarx ham shunga yarasha farq qilsin."""
    windows = _windows_site(finance_client, "Windows do'kon")
    box = _make_site(finance_client, "Box do'kon", pair=True)
    _add_uptime(windows, 100 * 60, device_id="dev-win")
    _add_uptime(box, 100 * 60, device_id="dev-box")

    win_row = _site_row(finance_client, windows)
    box_row = _site_row(finance_client, box)

    assert win_row["energy_uptime_hours"] == box_row["energy_uptime_hours"] == 100.0
    assert win_row["energy_watts"] == 65
    assert box_row["energy_watts"] == 12
    assert win_row["energy_cost_uzs"] == 6_500
    assert box_row["energy_cost_uzs"] == 1_200


def test_electricity_is_the_customers_bill_not_ours(finance_client) -> None:
    """Elektr bizning tannarxga KIRMAYDI.

    Windows yo'lida dastur mijozning o'z kompyuterida ishlaydi va tokni
    u to'laydi.  Uni bizning xarajatga qo'shish foydani soxta
    kamaytirardi.  Raqam esa yo'qolmaydi — u mijozning JAMI xarajatini
    ko'rsatadi va sotuvda aynan shu savolga javob beradi.
    """
    site_id = _windows_site(finance_client, "Kim to'laydi")
    _add_uptime(site_id, 100 * 60)

    row = _site_row(finance_client, site_id)

    assert row["energy_cost_uzs"] == 6_500
    # Bizning tannarx: faqat Gemini + infra.
    assert row["total_cost_uzs"] == row["gemini_cost_uzs"] + row["shared_cost_uzs"]
    assert row["margin_uzs"] == row["revenue_uzs"] - row["total_cost_uzs"]
    # Mijozga jami: obuna + o'z toki.
    assert row["customer_total_uzs"] == row["revenue_uzs"] + row["energy_cost_uzs"]


def test_energy_does_not_shrink_our_profit(finance_client) -> None:
    """Elektr o'ssa ham foydamiz o'zgarmasin — u bizning cho'ntagimizdan
    chiqmaydi.  Bu testsiz kelajakda uni yana tannarxga qo'shib
    yuborish oson."""
    quiet = _windows_site(finance_client, "Kam ishlagan")
    _add_uptime(quiet, 10 * 60, device_id="dev-quiet")
    busy = _windows_site(finance_client, "Ko'p ishlagan")
    _add_uptime(busy, 700 * 60, device_id="dev-busy")

    quiet_row = _site_row(finance_client, quiet)
    busy_row = _site_row(finance_client, busy)

    assert busy_row["energy_cost_uzs"] > quiet_row["energy_cost_uzs"] * 50
    # Elektr 70 barobar farq qiladi, foyda esa bir xil.
    assert busy_row["margin_uzs"] == quiet_row["margin_uzs"]


def test_totals_keep_our_cost_and_the_customer_bill_apart(finance_client) -> None:
    site_id = _windows_site(finance_client, "Jami")
    _add_uptime(site_id, 100 * 60)

    body = finance_client.get("/api/v1/admin/finance", headers=ADMIN).json()
    totals = body["totals"]

    # Bizning tannarx — elektrsiz.
    assert totals["cost_uzs"] == totals["fixed_cost_uzs"] + totals["gemini_cost_uzs"]
    assert totals["margin_uzs"] == totals["revenue_uzs"] - totals["cost_uzs"]
    assert totals["margin_percent"] is not None
    # Mijozlar to'laydigan elektr alohida turadi.
    assert totals["energy_cost_uzs"] > 0
    assert totals["customer_total_uzs"] == totals["revenue_uzs"] + totals["energy_cost_uzs"]
    assert body["energy"]["paid_by"] == "customer"


def test_a_customer_who_stopped_paying_is_not_counted_as_revenue(finance_client) -> None:
    """Obunasi to'xtatilgan do'kon daromad bo'lib turmasin.

    Ilgari daromad faqat "qurilma ulanganmi" shartiga bog'liq edi va
    `license_status` umuman tekshirilmasdi.  Natijada Moliya sahifasi
    to'xtatilgan mijozni ham sanardi, "Boshqaruv" esa sanamasdi
    (`cloud/store.py: stats()` faqat active/grace) — bir xil savolga
    ikki xil javob.
    """
    site_id = _windows_site(finance_client, "To'xtatilgan")
    _add_uptime(site_id, 100 * 60)

    before = _site_row(finance_client, site_id)
    assert before["revenue_uzs"] > 0

    finance_client.post(
        f"/api/v1/admin/sites/{site_id}/status", headers=ADMIN, json={"status": "suspended"}
    )
    after = _site_row(finance_client, site_id)

    assert after["revenue_uzs"] == 0
    assert after["license_status"] == "suspended"
    # Bizning xarajat esa QOLADI: to'lamayapti, lekin server joyini
    # egallab turibdi.  Aynan shu — zarar keltiruvchi mijoz.
    assert after["margin_uzs"] < 0
