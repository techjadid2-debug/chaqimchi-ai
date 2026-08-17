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


def test_public_lead_pipeline_and_duplicate_guard(tmp_path) -> None:
    store = CloudStore(tmp_path / "cloud.db")
    lead = store.create_lead(
        full_name="Ali Valiyev",
        phone="+998 90 123 45 67",
        company="Pilot Do'kon",
        city="Toshkent",
        cameras=4,
        message="Ulanish kerak",
        source_hash="ip-hash",
    )
    assert lead["status"] == "new"
    assert store.lead_stats()["new_leads"] == 1

    duplicate = store.create_lead(
        full_name="Ali Valiyev",
        phone="+998 90 123 45 67",
        company=None,
        city=None,
        cameras=1,
        message=None,
        source_hash="ip-hash",
    )
    assert duplicate["id"] == lead["id"]
    assert duplicate["duplicate"] is True
    assert len(store.list_leads()) == 1

    qualified = store.update_lead(lead["id"], status="qualified", admin_note="Mos")
    assert qualified["status"] == "qualified"
    site = store.create_site("Pilot Do'kon", "lite")
    linked = store.link_lead_site(lead["id"], site["site_id"])
    assert linked["status"] == "converted"
    assert linked["site_id"] == site["site_id"]


def test_lead_notification_delivery_is_persistent_and_retryable(tmp_path) -> None:
    store = CloudStore(tmp_path / "cloud.db")
    created = store.create_lead(
        full_name="Ali Valiyev",
        phone="+998 90 123 45 67",
        company="Pilot",
        city="Toshkent",
        cameras=4,
        message="Maslahat",
        source_hash="ip-hash",
    )
    store.ensure_lead_notification_deliveries(created["id"], ["5476913898", "-1001", "5476913898"])

    assert [item["chat_id"] for item in store.pending_lead_notification_deliveries()] == [
        "5476913898",
        "-1001",
    ]
    store.mark_lead_notification_delivery(created["id"], "5476913898", sent=True)
    store.mark_lead_notification_delivery(created["id"], "-1001", sent=False, error="temporary")

    assert store.lead_notification_delivery(created["id"], "5476913898")["state"] == "sent"
    failed = store.lead_notification_delivery(created["id"], "-1001")
    assert failed["state"] == "failed"
    assert failed["attempts"] == 1
    assert failed["next_attempt_at"] is not None
    assert store.recent_leads_without_notifications() == []


def test_cloud_sqlite_directory_is_private(tmp_path) -> None:
    db_dir = tmp_path / "cloud-state"
    store = CloudStore(db_dir / "cloud.db")

    assert store.db_path.stat().st_mode & 0o777 == 0o600
    assert db_dir.stat().st_mode & 0o777 == 0o700


def test_feature_catalog_quote_and_draft_activation(tmp_path) -> None:
    store = CloudStore(tmp_path / "cloud.db")
    catalog = store.list_feature_catalog()
    assert catalog["price_book"]["base_fee_usd_cents"] == 2_000
    assert {item["code"] for item in catalog["features"]} == {
        "person_count",
        "queue_length",
        "store_security",
        # Davomat katalogda bor (admin narxlaydi), lekin public sotuvda yo'q
        # — test_public_pricing shuni qo'riqlaydi.
        "davomat",
    }
    assert any(item["code"] == "retail" for item in store.list_business_templates())

    site = store.create_site("Cloud do'kon", "lite")
    quote = store.feature_quote(
        [
            {"feature_code": "person_count", "camera_count": 2},
            {"feature_code": "queue_length", "camera_count": 1},
        ]
    )
    assert quote["monthly_usd_cents"] == 3_100  # $20 + 2×$3 + $5
    assert quote["gross_margin_percent"] >= 65
    with pytest.raises(ValueError, match="1–4"):
        store.feature_quote([{"feature_code": "person_count", "camera_count": 5}])

    draft = store.replace_feature_draft(site["site_id"], quote["features"])
    assert len(draft["drafts"]) == 2
    assert draft["assignments"] == []
    active = store.approve_feature_draft(site["site_id"])
    assert {item["feature_code"] for item in active["assignments"]} == {
        "person_count",
        "queue_length",
    }
    assert active["drafts"] == []
