import pytest

from cloud.store import LEAD_DELIVERY_MAX_ATTEMPTS, CloudStore


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


def _lead_with_delivery(store: CloudStore, chat_id: str = "-1001") -> str:
    lead = store.create_lead(
        full_name="Ali Valiyev",
        phone="+998 90 123 45 67",
        company="Pilot",
        city="Toshkent",
        cameras=4,
        message="Maslahat",
        source_hash="ip-hash",
    )
    store.ensure_lead_notification_deliveries(lead["id"], [chat_id])
    return str(lead["id"])


def test_a_hopeless_chat_leaves_the_queue_instead_of_blocking_it(tmp_path) -> None:
    """Bitta nosoz Telegram ID butun sotuv voronkasini o'ldirmasin.

    8 urinishdan keyin yetkazish yopilishi kerak edi, lekin jadval sxemasi
    `abandoned` holatini qabul qilmasdi.  `UPDATE` yiqilar, `updated_at`
    o'zgarmas, ya'ni o'sha qator navbat boshida (`ORDER BY updated_at ASC`)
    qolib ketardi va keyingi har bir aylanish aynan shu yerda yiqilardi —
    saytdan kelgan boshqa hech qaysi ariza yetib bormasdi.
    """
    store = CloudStore(tmp_path / "cloud.db")
    lead_id = _lead_with_delivery(store)

    for _ in range(LEAD_DELIVERY_MAX_ATTEMPTS):
        store.mark_lead_notification_delivery(
            lead_id, "-1001", sent=False, error="chat not found"
        )

    delivery = store.lead_notification_delivery(lead_id, "-1001")
    assert delivery["state"] == "abandoned"
    assert delivery["attempts"] == LEAD_DELIVERY_MAX_ATTEMPTS
    assert store.pending_lead_notification_deliveries() == [], "navbatni to'smasin"


def test_a_blocked_chat_does_not_delay_the_next_lead(tmp_path) -> None:
    """Voronka tirik qolgani — yakuniy tekshiruv."""
    store = CloudStore(tmp_path / "cloud.db")
    dead_lead = _lead_with_delivery(store)
    for _ in range(LEAD_DELIVERY_MAX_ATTEMPTS):
        store.mark_lead_notification_delivery(
            dead_lead, "-1001", sent=False, error="chat not found"
        )

    fresh = store.create_lead(
        full_name="Dilshod Karimov",
        phone="+998 91 000 00 00",
        company="Baraka",
        city="Samarqand",
        cameras=2,
        message=None,
        source_hash="boshqa-ip",
    )
    store.ensure_lead_notification_deliveries(fresh["id"], ["-1001"])

    queue = store.pending_lead_notification_deliveries()
    assert [item["lead_id"] for item in queue] == [fresh["id"]]


def test_an_old_database_learns_the_abandoned_state(tmp_path) -> None:
    """Ishlab turgan serverda jadval eski `CHECK` bilan yaratilgan —
    yangilanish uni qayta qurishi kerak, aks holda tuzatish yetib bormaydi."""
    import sqlite3

    path = tmp_path / "cloud.db"
    CloudStore(path)  # jadvallarni yaratadi
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            DROP TABLE lead_notification_deliveries;
            CREATE TABLE lead_notification_deliveries (
                lead_id TEXT NOT NULL,
                chat_id TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'pending'
                    CHECK(state IN ('pending', 'sent', 'failed')),
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                next_attempt_at TEXT,
                sent_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (lead_id, chat_id)
            );
            """
        )

    store = CloudStore(path)  # migratsiya shu yerda ishlaydi
    lead_id = _lead_with_delivery(store)
    for _ in range(LEAD_DELIVERY_MAX_ATTEMPTS):
        store.mark_lead_notification_delivery(lead_id, "-1001", sent=False, error="xato")

    assert store.lead_notification_delivery(lead_id, "-1001")["state"] == "abandoned"


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


def test_versiya_vaqti_faqat_ozgarganda_yoziladi(tmp_path) -> None:
    """"Qachondan beri bir xil" — yangilanish qotib qolganini shu ko'rsatadi.

    Har heartbeat'da yozilsa bu savolga javob bo'lmasdi: qurilma har
    daqiqada "salom" yuboradi va sana doim hozirgi payt bo'lib qolardi.
    """
    store = CloudStore(tmp_path / "cloud.db")
    site = store.create_site("Do'kon", "lite")
    device = store.claim_device(site["pairing_code"])

    store.record_device_version(device["device_id"], "0.6.8")
    birinchi = store.device_versions()[site["site_id"]]["since"]
    assert birinchi

    conn = store._connect()
    conn.execute("UPDATE devices SET app_version_at = '2020-01-01 00:00:00'")
    conn.commit()
    conn.close()

    store.record_device_version(device["device_id"], "0.6.8")
    assert store.device_versions()[site["site_id"]]["since"] == "2020-01-01 00:00:00"

    store.record_device_version(device["device_id"], "0.6.12")
    yangi = store.device_versions()[site["site_id"]]
    assert yangi["version"] == "0.6.12"
    assert yangi["since"] != "2020-01-01 00:00:00"


def test_eski_qurilmaga_versiya_vaqti_birinchi_salomda_qoyiladi(tmp_path) -> None:
    """Ustun keyinroq qo'shilgan — eski qatorlarda u bo'sh.

    Sanani `created_at` dan olib bo'lmaydi: bir yil oldin ochilgan
    do'kon deploy kuniyoq "qotib qolgan" deb xabar berardi.  Shu sabab
    bo'sh sana birinchi heartbeat'da hozirgi paytga qo'yiladi.
    """
    store = CloudStore(tmp_path / "cloud.db")
    site = store.create_site("Do'kon", "lite")
    device = store.claim_device(site["pairing_code"])
    conn = store._connect()
    conn.execute("UPDATE devices SET app_version = '0.6.8', app_version_at = NULL")
    conn.commit()
    conn.close()
    assert store.device_versions()[site["site_id"]]["since"] is None

    store.record_device_version(device["device_id"], "0.6.8")
    assert store.device_versions()[site["site_id"]]["since"] is not None
