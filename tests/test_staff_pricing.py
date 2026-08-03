"""Xodim bo‘yicha narx modeli.

Kamera tariflari (do‘kon) va xodim tariflari (davomat) yonma-yon ishlaydi —
hozirgi mijozlarning narxi o‘zgarmasligi kerak.
"""

import pytest
from fastapi.testclient import TestClient

from chaqimchi_ai.licensing.plans import PLANS, cheapest_plan_for, get_plan
from cloud.payments import PaymentStore
from cloud.store import CloudStore

ADMIN = {"X-Cloud-Admin-Key": "test-admin"}


@pytest.fixture
def store(tmp_path) -> CloudStore:
    return CloudStore(tmp_path / "cloud.db")


# ── Narx formulasi ───────────────────────────────────────────────────────


def test_camera_plans_ignore_person_count() -> None:
    """Eski mijozlarning narxi o‘zgarmaydi — bu eng muhim kafolat."""
    for plan in ("starter", "business", "enterprise"):
        limits = get_plan(plan)
        assert limits.is_per_person is False
        assert limits.monthly_price(0) == limits.monthly_price_uzs
        assert limits.monthly_price(500) == limits.monthly_price_uzs


def test_staff_plan_charges_per_person() -> None:
    limits = get_plan("staff_business")
    assert limits.monthly_price(100) == 1_200_000  # eng kam narx ushlab turadi
    assert limits.monthly_price(200) == 2_400_000  # 200 × 12 000
    assert limits.monthly_price(300) == 3_600_000


def test_minimum_price_protects_small_customer() -> None:
    """10 xodimli mijoz ham eng kam narxni to‘laydi."""
    assert get_plan("staff_starter").monthly_price(10) == 500_000
    assert get_plan("staff_starter").monthly_price(0) == 500_000


def test_bigger_plan_is_cheaper_per_person() -> None:
    """Mijoz o‘sganda ko‘tarilishni o‘zi so‘rashi uchun."""
    assert (
        PLANS["staff_enterprise"].price_per_person_uzs
        < PLANS["staff_business"].price_per_person_uzs
        < PLANS["staff_starter"].price_per_person_uzs
    )


@pytest.mark.parametrize(
    "persons,expected_plan,expected_price",
    [
        (20, "staff_starter", 500_000),
        (50, "staff_starter", 750_000),
        (100, "staff_business", 1_200_000),
        (200, "staff_business", 2_400_000),
        (300, "staff_enterprise", 2_700_000),
        (500, "staff_enterprise", 4_500_000),
    ],
)
def test_cheapest_plan_ladder(persons, expected_plan, expected_price) -> None:
    plan, price = cheapest_plan_for(persons)
    assert plan == expected_plan
    assert price == expected_price


def test_huge_customer_falls_back_to_enterprise() -> None:
    plan, price = cheapest_plan_for(5000)
    assert plan == "staff_enterprise"
    assert price == 45_000_000


# ── Baza cheklovi tijorat bilan mos ──────────────────────────────────────


def test_person_limit_matches_what_customer_pays_for() -> None:
    """100 xodim uchun to‘lasa, bazaga 100 kishi sig‘adi — 101-chisi yo‘q."""
    limits = get_plan("staff_business")
    assert limits.effective_max_persons(100) == 100
    assert limits.effective_max_persons(250) == 250


def test_camera_plan_limit_unchanged() -> None:
    assert get_plan("business").effective_max_persons(999) == 200


# ── Cloud store ──────────────────────────────────────────────────────────


def test_site_price_follows_person_count(store: CloudStore) -> None:
    site = store.create_site("Zavod", "staff_business", billable_persons=200)

    assert site["limits"]["monthly_price_uzs"] == 2_400_000

    row = store.list_sites()[0]
    assert row["billable_persons"] == 200
    assert row["monthly_price_uzs"] == 2_400_000
    assert row["max_persons"] == 200


def test_changing_person_count_changes_price(store: CloudStore) -> None:
    """Mijoz o‘sdi — narx ham o‘sadi, qayta sotuvsiz."""
    site = store.create_site("Zavod", "staff_business", billable_persons=100)
    assert store.list_sites()[0]["monthly_price_uzs"] == 1_200_000

    store.set_billable_persons(site["site_id"], 250)

    assert store.list_sites()[0]["monthly_price_uzs"] == 3_000_000


def test_camera_site_price_unaffected_by_persons(store: CloudStore) -> None:
    site = store.create_site("Do'kon", "business", billable_persons=500)
    assert store.list_sites()[0]["monthly_price_uzs"] == 1_490_000
    detail = store.site_detail(site["site_id"])
    assert detail["limits"]["monthly_price_uzs"] == 1_490_000


def test_heartbeat_reports_paid_person_limit(store: CloudStore) -> None:
    """Edge shu limitni oladi — 100 xodimlik mijoz 101-chisini qo‘sha olmaydi."""
    site = store.create_site("Zavod", "staff_starter", billable_persons=80)
    claimed = store.claim_device(site["pairing_code"])

    hb = store.heartbeat(claimed["site_id"], claimed["device_token"])

    assert hb["max_persons"] == 80


def test_revenue_uses_actual_price(store: CloudStore) -> None:
    store.create_site("Zavod", "staff_business", billable_persons=300)
    store.create_site("Do'kon", "business")

    stats = store.stats()

    assert stats["monthly_revenue_uzs"] == 3_600_000 + 1_490_000


def test_set_persons_rejects_negative(store: CloudStore) -> None:
    site = store.create_site("Zavod", "staff_starter", billable_persons=10)
    with pytest.raises(ValueError, match="manfiy"):
        store.set_billable_persons(site["site_id"], -5)


def test_set_persons_unknown_site(store: CloudStore) -> None:
    with pytest.raises(ValueError, match="topilmadi"):
        store.set_billable_persons("yoq", 10)


def test_migration_adds_billable_persons(tmp_path) -> None:
    """Ishlab turgan cloud yangilanganda ustun qo‘shiladi."""
    import sqlite3

    db = tmp_path / "eski.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE sites (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, plan TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active', subscription_until TEXT NOT NULL,
            contact_phone TEXT, address TEXT, created_at TEXT NOT NULL
        );
        INSERT INTO sites VALUES ('s1','Eski mijoz','business','active',
            '2030-01-01 00:00:00', NULL, NULL, '2026-01-01 00:00:00');
        CREATE TABLE devices (
            id TEXT PRIMARY KEY, site_id TEXT NOT NULL, label TEXT NOT NULL,
            token_hash TEXT NOT NULL, hardware_id TEXT, last_seen TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE pairing_codes (
            code TEXT PRIMARY KEY, site_id TEXT NOT NULL, expires_at TEXT NOT NULL,
            used INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    conn.commit()
    conn.close()

    store = CloudStore(db)

    row = store.list_sites()[0]
    assert row["billable_persons"] == 0
    assert row["monthly_price_uzs"] == 1_490_000  # eski narx o'zgarmagan


# ── Hisob-faktura ────────────────────────────────────────────────────────


def test_invoice_uses_person_based_price(store: CloudStore, tmp_path) -> None:
    payments = PaymentStore(store)
    site = store.create_site("Zavod", "staff_business", billable_persons=200)

    inv = payments.create_invoice(site["site_id"], months=1)

    assert inv["amount_uzs"] == 2_400_000


def test_yearly_invoice_gives_two_months_free(store: CloudStore) -> None:
    payments = PaymentStore(store)
    site = store.create_site("Zavod", "staff_business", billable_persons=200)

    inv = payments.create_invoice(site["site_id"], months=12)

    assert inv["amount_uzs"] == 2_400_000 * 10


def test_camera_plan_invoice_unchanged(store: CloudStore) -> None:
    payments = PaymentStore(store)
    site = store.create_site("Do'kon", "business")

    inv = payments.create_invoice(site["site_id"], months=1)

    assert inv["amount_uzs"] == 1_490_000


# ── API ──────────────────────────────────────────────────────────────────


@pytest.fixture
def cloud_client(tmp_path, monkeypatch):
    monkeypatch.setenv("CHAQIMCHI_CLOUD_ADMIN_KEY", "test-admin")
    import cloud.main as cm

    monkeypatch.setattr(cm, "DB_PATH", tmp_path / "c.db")
    monkeypatch.setattr(cm, "_store", None)
    monkeypatch.setattr(cm, "_payments", None)
    monkeypatch.setattr(cm, "_alerts", None)
    return TestClient(cm.app)


def test_api_quote_recommends_plan(cloud_client) -> None:
    """Sotuvchi qo‘lda hisoblamasin."""
    body = cloud_client.get("/api/v1/quote?persons=100").json()

    assert body["plan"] == "staff_business"
    assert body["monthly_uzs"] == 1_200_000
    assert body["yearly_uzs"] == 12_000_000  # 2 oy tekin
    assert body["first_payment_uzs"] == 9_500_000 + 12_000_000


def test_api_quote_is_public(cloud_client) -> None:
    """Narx hisoblagichi admin kalitsiz ishlaydi — sotuvchi telefonda ochadi."""
    assert cloud_client.get("/api/v1/quote?persons=50").status_code == 200


def test_api_create_site_with_persons(cloud_client) -> None:
    r = cloud_client.post(
        "/api/v1/admin/sites",
        headers=ADMIN,
        json={"name": "Zavod", "plan": "staff_business", "billable_persons": 200},
    )

    assert r.status_code == 200, r.text
    assert r.json()["limits"]["monthly_price_uzs"] == 2_400_000


def test_api_change_person_count(cloud_client) -> None:
    site = cloud_client.post(
        "/api/v1/admin/sites",
        headers=ADMIN,
        json={"name": "Zavod", "plan": "staff_starter", "billable_persons": 30},
    ).json()

    r = cloud_client.post(
        f"/api/v1/admin/sites/{site['site_id']}/persons", headers=ADMIN, json={"persons": 90}
    )

    assert r.status_code == 200
    assert r.json()["limits"]["monthly_price_uzs"] == 90 * 15_000


def test_api_persons_requires_admin(cloud_client) -> None:
    assert (
        cloud_client.post("/api/v1/admin/sites/x/persons", json={"persons": 10}).status_code
        == 401
    )


def test_api_plans_marks_billing_type(cloud_client) -> None:
    plans = cloud_client.get("/api/v1/plans").json()["plans"]
    assert plans["business"]["billing"] == "flat"
    assert plans["staff_business"]["billing"] == "per_person"
    assert plans["staff_business"]["per_person_uzs"] == 12_000
