import pytest

from cloud.store import CloudStore


def test_create_site_and_heartbeat(tmp_path) -> None:
    store = CloudStore(tmp_path / "cloud.db")
    site = store.create_site("Test Shop", "starter", subscription_months=1)
    assert site["pairing_code"]
    claimed = store.claim_device(site["pairing_code"], label="pc1")
    hb = store.heartbeat(claimed["site_id"], claimed["device_token"], active_cameras=1)
    assert hb["status"] == "active"
    assert hb["max_cameras"] == 1


def test_extend_subscription(tmp_path) -> None:
    store = CloudStore(tmp_path / "cloud.db")
    site = store.create_site("X", "business", subscription_months=1)
    ext = store.extend_subscription(site["site_id"], 3)
    assert "subscription_until" in ext


def test_list_sites_has_computed_fields(tmp_path) -> None:
    store = CloudStore(tmp_path / "cloud.db")
    site = store.create_site("Do'kon", "business", subscription_months=2)
    store.claim_device(site["pairing_code"])

    rows = store.list_sites()
    assert len(rows) == 1
    row = rows[0]
    assert row["license_status"] == "active"
    assert row["devices"] == 1
    assert row["days_left"] > 0
    assert row["monthly_price_uzs"] == 1_490_000


def test_site_detail_lists_devices_and_codes(tmp_path) -> None:
    store = CloudStore(tmp_path / "cloud.db")
    site = store.create_site("Ombor", "starter", subscription_months=1)
    detail = store.site_detail(site["site_id"])

    # Qurilma juftlanmagan — kod hali faol.
    assert detail["devices"] == []
    assert [c["code"] for c in detail["active_pairing_codes"]] == [site["pairing_code"]]
    assert detail["limits"]["max_cameras"] == 1

    store.claim_device(site["pairing_code"], label="mini-pc")
    detail2 = store.site_detail(site["site_id"])
    assert [d["label"] for d in detail2["devices"]] == ["mini-pc"]
    # Ishlatilgan kod endi ro'yxatda emas.
    assert detail2["active_pairing_codes"] == []


def test_suspend_blocks_heartbeat_then_resume(tmp_path) -> None:
    store = CloudStore(tmp_path / "cloud.db")
    site = store.create_site("To'lovsiz", "starter", subscription_months=1)
    claimed = store.claim_device(site["pairing_code"])

    suspended = store.set_status(site["site_id"], "suspended")
    assert suspended["license_status"] == "suspended"
    hb = store.heartbeat(claimed["site_id"], claimed["device_token"])
    assert hb["status"] == "suspended"

    store.set_status(site["site_id"], "active")
    assert store.heartbeat(claimed["site_id"], claimed["device_token"])["status"] == "active"


def test_set_status_rejects_unknown_values(tmp_path) -> None:
    store = CloudStore(tmp_path / "cloud.db")
    site = store.create_site("X", "starter")
    with pytest.raises(ValueError):
        store.set_status(site["site_id"], "deleted")
    with pytest.raises(ValueError):
        store.set_status("yo'q-sayt", "active")


def test_new_pairing_code_allows_reclaim(tmp_path) -> None:
    store = CloudStore(tmp_path / "cloud.db")
    site = store.create_site("Almashtirilgan PC", "business")
    store.claim_device(site["pairing_code"], label="eski")

    fresh = store.new_pairing_code(site["site_id"])
    assert fresh["pairing_code"] != site["pairing_code"]
    claimed = store.claim_device(fresh["pairing_code"], label="yangi")
    assert claimed["site_id"] == site["site_id"]
    assert len(store.site_detail(site["site_id"])["devices"]) == 2


def test_stats_counts_and_revenue(tmp_path) -> None:
    store = CloudStore(tmp_path / "cloud.db")
    store.create_site("A", "starter", subscription_months=12)
    b = store.create_site("B", "business", subscription_months=12)
    store.set_status(b["site_id"], "suspended")

    stats = store.stats()
    assert stats["total_sites"] == 2
    assert stats["active"] == 1
    assert stats["by_status"]["suspended"] == 1
    # To'xtatilgan mijoz daromadga qo'shilmaydi.
    assert stats["monthly_revenue_uzs"] == 790_000
