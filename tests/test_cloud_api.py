import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def cloud_client(tmp_path, monkeypatch):
    monkeypatch.setenv("CHAQIMCHI_CLOUD_ADMIN_KEY", "test-admin")
    db = tmp_path / "c.db"
    monkeypatch.setattr("cloud.main.DB_PATH", db)
    monkeypatch.setattr("cloud.main._store", None)
    from cloud.main import app

    return TestClient(app)


def test_cloud_plans_and_site(cloud_client) -> None:
    r = cloud_client.get("/api/v1/plans")
    assert r.status_code == 200
    assert r.json()["plans"]["lite"]["monthly_price_usd"] == 20
    assert "starter" in r.json()["plans"]

    r2 = cloud_client.post(
        "/api/v1/admin/sites",
        headers={"X-Cloud-Admin-Key": "test-admin"},
        json={"name": "API Test", "plan": "starter", "subscription_months": 1},
    )
    assert r2.status_code == 200
    data = r2.json()
    assert data["pairing_code"]


def test_new_site_defaults_to_biznes(cloud_client) -> None:
    """Tarif berilmasa — asosiy tarif, cheklangani emas.

    Standart `boshlangich` bo'lsa, tarif ko'rsatilmagan yo'ldan
    (masalan ariza konvertatsiyasi) kelgan mijoz 2 kamera chegarasiga
    tushib qolardi va sababi hech qayerda yozilmasdi.
    """
    response = cloud_client.post(
        "/api/v1/admin/sites",
        headers={"X-Cloud-Admin-Key": "test-admin"},
        json={"name": "Biznes Pilot", "subscription_months": 1},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["plan"] == "biznes"
    assert body["limits"]["monthly_price_usd"] == 23


def test_feature_catalog_draft_quote_and_approval(cloud_client) -> None:
    site = _make_site(cloud_client, "Feature API", "lite")
    catalog = cloud_client.get("/api/v1/admin/features", headers=ADMIN)
    assert catalog.status_code == 200
    assert catalog.json()["price_book"]["base_fee_usd_cents"] == 2_000
    assert cloud_client.get("/api/v1/admin/business-templates", headers=ADMIN).status_code == 200

    payload = {"selections": [{"feature_code": "person_count", "camera_count": 2}]}
    quote = cloud_client.post(
        f"/api/v1/admin/sites/{site['site_id']}/features/quote", headers=ADMIN, json=payload
    )
    assert quote.status_code == 200
    assert quote.json()["monthly_usd_cents"] == 2_600

    draft = cloud_client.put(
        f"/api/v1/admin/sites/{site['site_id']}/features/draft", headers=ADMIN, json=payload
    )
    assert draft.status_code == 200
    assert draft.json()["drafts"][0]["feature_code"] == "person_count"
    approved = cloud_client.post(
        f"/api/v1/admin/sites/{site['site_id']}/features/approve", headers=ADMIN
    )
    assert approved.status_code == 200
    assert approved.json()["assignments"][0]["status"] == "active"
    claim = cloud_client.post(
        "/api/v1/sotqin/claim",
        json={
            "pairing_code": site["pairing_code"],
            "hardware_model": "Intel N100",
            "hardware_revision": "R1",
            "serial_number": "SQN-R1-TEST",
        },
    )
    assert claim.status_code == 200
    device = claim.json()
    edge_config = cloud_client.get(
        "/api/v1/sotqin/config",
        headers={
            "X-Site-Id": device["site_id"],
            "X-Device-Id": device["device_id"],
            "X-Device-Token": device["device_token"],
        },
    )
    assert edge_config.status_code == 200
    assert edge_config.json()["cloud_features"] == [
        {"code": "person_count", "camera_count": 2, "queue_kind": "batch"}
    ]
    assert edge_config.json()["product"]["hardware_profile"] == "SOTQIN-N100-8-128-R1"
    assert edge_config.json()["product"]["guaranteed_cameras"] == 4
    assert edge_config.json()["buffer_policy"]["max_bytes"] == 40 * 1024**3
    ack = cloud_client.post(
        "/api/v1/sotqin/config/ack",
        headers={
            "X-Site-Id": device["site_id"],
            "X-Device-Id": device["device_id"],
            "X-Device-Token": device["device_token"],
        },
        json={"revision": edge_config.json()["revision"], "status": "applied"},
    )
    assert ack.status_code == 200
    detail = cloud_client.get(f"/api/v1/admin/sites/{site['site_id']}", headers=ADMIN).json()
    assert detail["devices"][0]["product_name"] == "Sotqin"
    assert detail["devices"][0]["hardware_model"] == "Intel N100"
    assert detail["devices"][0]["config_status"] == "applied"


def test_camera_inventory_is_encrypted_for_admin_and_sent_only_to_paired_sotqin(
    cloud_client,
) -> None:
    site = _make_site(cloud_client, "Camera inventory", "lite")
    saved = cloud_client.put(
        f"/api/v1/admin/sites/{site['site_id']}/camera-inventory/camera-01",
        headers=ADMIN,
        json={
            "label": "Asosiy kirish",
            "rtsp_url": "rtsp://admin:camera-password@10.0.0.10:554/sub",
            "enabled": True,
        },
    )
    assert saved.status_code == 200
    assert saved.json()["camera"]["probe_status"] == "pending"
    inventory = cloud_client.get(
        f"/api/v1/admin/sites/{site['site_id']}/camera-inventory", headers=ADMIN
    )
    assert inventory.status_code == 200
    assert "rtsp_ciphertext" not in inventory.text
    assert "camera-password" not in inventory.text

    claim = cloud_client.post("/api/v1/sotqin/claim", json={"pairing_code": site["pairing_code"]})
    device = claim.json()
    headers = {
        "X-Site-Id": device["site_id"],
        "X-Device-Id": device["device_id"],
        "X-Device-Token": device["device_token"],
    }
    config = cloud_client.get("/api/v1/sotqin/config", headers=headers)
    assert config.status_code == 200
    assert config.json()["cameras"][0]["source"].startswith("rtsp://admin:")
    probes = cloud_client.post(
        "/api/v1/sotqin/camera-probes",
        headers=headers,
        json=[
            {
                "camera_id": "camera-01",
                "status": "online",
                "codec": "h264",
                "width": 1280,
                "height": 720,
                "fps": 10,
            }
        ],
    )
    assert probes.status_code == 200
    listed = cloud_client.get(
        f"/api/v1/admin/sites/{site['site_id']}/camera-inventory", headers=ADMIN
    ).json()
    assert listed["cameras"][0]["probe_status"] == "online"
    assert listed["cameras"][0]["codec"] == "h264"


ADMIN = {"X-Cloud-Admin-Key": "test-admin"}


def _make_site(client, name: str = "Panel Test", plan: str = "business") -> dict:
    r = client.post(
        "/api/v1/admin/sites",
        headers=ADMIN,
        json={"name": name, "plan": plan, "subscription_months": 6},
    )
    assert r.status_code == 200
    return r.json()


def test_admin_endpoints_require_key(cloud_client) -> None:
    site = _make_site(cloud_client)
    paths = [
        ("get", "/api/v1/admin/stats", None),
        ("get", f"/api/v1/admin/sites/{site['site_id']}", None),
        ("post", f"/api/v1/admin/sites/{site['site_id']}/status", {"status": "suspended"}),
        ("post", f"/api/v1/admin/sites/{site['site_id']}/pairing", None),
    ]
    for method, path, body in paths:
        call = getattr(cloud_client, method)
        r = call(path, json=body) if body else call(path)
        assert r.status_code == 401, path


def test_admin_stats(cloud_client) -> None:
    _make_site(cloud_client, "Stats", "starter")
    stats = cloud_client.get("/api/v1/admin/stats", headers=ADMIN).json()
    assert stats["total_sites"] == 1
    assert stats["active"] == 1
    assert stats["monthly_revenue_uzs"] == 790_000


def test_admin_site_detail_and_status_flow(cloud_client) -> None:
    site = _make_site(cloud_client)
    site_id = site["site_id"]

    detail = cloud_client.get(f"/api/v1/admin/sites/{site_id}", headers=ADMIN).json()
    assert detail["license_status"] == "active"
    assert detail["limits"]["max_cameras"] == 3

    r = cloud_client.post(
        f"/api/v1/admin/sites/{site_id}/status", headers=ADMIN, json={"status": "suspended"}
    )
    assert r.status_code == 200
    assert r.json()["license_status"] == "suspended"

    # Noto'g'ri holat — pydantic rad etadi.
    bad = cloud_client.post(
        f"/api/v1/admin/sites/{site_id}/status", headers=ADMIN, json={"status": "o'chirilgan"}
    )
    assert bad.status_code == 422


def test_admin_new_pairing_code(cloud_client) -> None:
    site = _make_site(cloud_client)
    r = cloud_client.post(f"/api/v1/admin/sites/{site['site_id']}/pairing", headers=ADMIN)
    assert r.status_code == 200
    code = r.json()["pairing_code"]
    assert code != site["pairing_code"]

    claimed = cloud_client.post("/api/v1/devices/claim", json={"pairing_code": code})
    assert claimed.status_code == 200
    assert claimed.json()["site_id"] == site["site_id"]


def test_admin_unknown_site_is_404(cloud_client) -> None:
    assert cloud_client.get("/api/v1/admin/sites/yo-q", headers=ADMIN).status_code == 404
    r = cloud_client.post(
        "/api/v1/admin/sites/yo-q/status", headers=ADMIN, json={"status": "active"}
    )
    assert r.status_code == 404


def test_admin_panel_page_is_served(cloud_client) -> None:
    r = cloud_client.get("/admin")
    assert r.status_code == 200
    assert "Chaqimchi Cloud" in r.text
    # Panel ikkita uslub faylida keladi: umumiy dizayn tizimi (owner.css) va
    # admin qismlari (panel.css).  Biri yetib bormasa panel uslubsiz ochiladi.
    assert cloud_client.get("/assets/owner.css").status_code == 200
    assert cloud_client.get("/assets/panel.css").status_code == 200


def test_sotqin_bootstrap_is_only_served_for_a_published_hashed_release(
    cloud_client, monkeypatch
) -> None:
    assert cloud_client.get("/downloads/sotqin-installer.sh").status_code == 503
    monkeypatch.setenv("CHAQIMCHI_SOTQIN_RELEASE_URL", "https://releases.example.uz/sotqin.tar.gz")
    monkeypatch.setenv("CHAQIMCHI_SOTQIN_RELEASE_SHA256", "a" * 64)
    response = cloud_client.get("/downloads/sotqin-installer.sh")
    assert response.status_code == 200
    assert "https://releases.example.uz/sotqin.tar.gz" in response.text
    assert "--code" in response.text
    assert "__RELEASE_URL__" not in response.text


def test_official_site_and_public_lead_to_customer_flow(cloud_client) -> None:
    assert cloud_client.get("/").status_code == 200
    assert "Do‘koningiz" in cloud_client.get("/").text
    # "4 kameragacha", "4 kamera" EMAS: arzon tarifda ikkita kamera va
    # hero shuni yashirmasligi kerak (`plans.py: boshlangich.max_cameras`).
    assert "4 kameragacha qabul profili" in cloud_client.get("/").text
    assert cloud_client.get("/connect").status_code == 200
    assert cloud_client.get("/privacy").status_code == 200
    assert cloud_client.get("/status").status_code == 200

    rejected = cloud_client.post(
        "/api/v1/public/leads",
        json={"full_name": "Ali Valiyev", "phone": "+998901234567", "consent": False},
    )
    assert rejected.status_code == 422

    response = cloud_client.post(
        "/api/v1/public/leads",
        json={
            "full_name": "Ali Valiyev",
            "phone": "+998901234567",
            "company": "Pilot Savdo",
            "city": "Toshkent",
            "cameras": 4,
            "consent": True,
        },
    )
    assert response.status_code == 200
    lead_id = response.json()["lead_id"]

    leads = cloud_client.get("/api/v1/admin/leads", headers=ADMIN)
    assert leads.status_code == 200
    assert leads.json()[0]["id"] == lead_id
    assert "source_hash" not in leads.json()[0]

    converted = cloud_client.post(
        f"/api/v1/admin/leads/{lead_id}/convert",
        headers=ADMIN,
        json={"subscription_months": 1},
    )
    assert converted.status_code == 200
    site = converted.json()
    assert site["plan"] == "biznes"
    assert site["name"] == "Pilot Savdo"

    onboarding = cloud_client.get(
        f"/api/v1/admin/sites/{site['site_id']}/onboarding", headers=ADMIN
    )
    assert onboarding.status_code == 200
    assert onboarding.json()["steps"][0] == {
        "key": "customer",
        "label": "Mijoz ochildi",
        "done": True,
    }
    assert onboarding.json()["pairing"]["code"] == site["pairing_code"]


def test_lead_notification_reaches_only_explicit_personal_ids_once(
    cloud_client, monkeypatch
) -> None:
    import cloud.main as cm

    sent = []

    class Sender:
        async def send_to(self, chat_id, text):
            sent.append((chat_id, text))
            return True

    class Config:
        token = "123:test"
        chat_id = "-100111"

    class Alerts:
        config = Config()
        sender = Sender()

    monkeypatch.setenv(
        "CHAQIMCHI_TELEGRAM_LEAD_CHAT_IDS",
        "5476913898,5476913898",
    )
    monkeypatch.setattr(cm, "get_alerts", lambda: Alerts())
    cm.get_store().upsert_telegram_lead_destination(
        "-100333", chat_type="supergroup", title="Sales"
    )
    payload = {
        "full_name": "Vali Valiyev",
        "phone": "+998909876543",
        "consent": True,
    }

    first = cloud_client.post("/api/v1/public/leads", json=payload)
    repeated = cloud_client.post("/api/v1/public/leads", json=payload)

    assert first.status_code == repeated.status_code == 200
    assert first.json()["duplicate"] is False
    assert repeated.json()["duplicate"] is True
    # Takroriy ariza (bir xil telefon) qayta xabar TUG'DIRMAYDI: tugmani
    # 5 marta bosgan mehmon adminga 5 ta xabar bo'lib tushar edi.
    assert [chat_id for chat_id, _ in sent] == ["5476913898"]
    assert "Yangi Chaqimchi AI" in sent[0][1]


def test_public_registration_opens_bot_and_start_returns_role_buttons(
    cloud_client, monkeypatch
) -> None:
    import cloud.main as cm

    monkeypatch.setenv("CHAQIMCHI_TELEGRAM_BOT_USERNAME", "chaqimchi_bot")
    monkeypatch.setenv("CHAQIMCHI_TELEGRAM_WEBHOOK_SECRET", "webhook-test")
    monkeypatch.setenv("CHAQIMCHI_PUBLIC_URL", "https://chaqimchi.example")
    sent = []

    async def fake_send(chat_id, text, *, reply_markup=None):
        sent.append((chat_id, text, reply_markup))

    monkeypatch.setattr(cm, "_send_owner_telegram", fake_send)
    page = cloud_client.get("/")
    assert "https://t.me/chaqimchi_bot?start=register" in page.text
    assert "__TELEGRAM_REGISTER_URL__" not in page.text

    webhook = cloud_client.post(
        "/api/v1/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "webhook-test"},
        json={
            "message": {
                "chat": {"id": 5476913898, "type": "private"},
                "text": "/start register",
            }
        },
    )
    assert webhook.status_code == 200
    assert sent[0][0] == "5476913898"
    buttons = sent[0][2]["inline_keyboard"]
    assert buttons[0][0]["web_app"]["url"] == "https://chaqimchi.example/owner"
    assert buttons[1][0]["url"] == "https://chaqimchi.example/installer"
    assert buttons[2][0]["url"] == "https://chaqimchi.example/#narx"
    # Ichki kod nomi mijozga ko'rinmasin.
    assert "Sotqin" not in sent[0][1]
    assert cloud_client.post("/api/v1/telegram/webhook", json={"message": {}}).status_code == 404


def test_admin_readiness_requires_admin_key(cloud_client) -> None:
    assert cloud_client.get("/api/v1/admin/readiness").status_code == 401
    response = cloud_client.get("/api/v1/admin/readiness", headers=ADMIN)
    assert response.status_code == 200
    assert any(item["key"] == "database" for item in response.json()["items"])
    lead_item = next(
        item for item in response.json()["items"] if item["key"] == "lead_notifications"
    )
    assert lead_item["ok"] is False
    assert lead_item["required"] is True


QUICK_TRIAL = {
    "phone": "+998 90 123 45 67",
    "company": "Test Market",
    "consent": True,
    "username": "testmarket",
    "password": "mening-parolim1",
}


def test_quick_trial_creates_a_site(cloud_client) -> None:
    res = cloud_client.post("/api/v1/public/quick-trial", json=QUICK_TRIAL)
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["site_id"]
    assert data["pairing_code"]
    assert data["owner_url"]


# ── Mijoz o'zi ro'yxatdan o'tadi ────────────────────────────────────────
#
# Bungacha login va parolni admin qo'lda yaratib, qo'lda yuborardi.  Ya'ni
# har bir mijoz operatorning ish vaqtini kutardi va saytdan o'z-o'zidan
# ulanishning yo'li yo'q edi.


def test_the_customer_can_log_in_with_the_password_they_chose(cloud_client, monkeypatch) -> None:
    """Butun ma'no shu: ro'yxatdan o'tdi — darrov panelga kira oladi."""
    monkeypatch.setenv("CHAQIMCHI_PORTAL_JWT_SECRET", "portal-secret-with-more-than-32-chars")
    created = cloud_client.post("/api/v1/public/quick-trial", json=QUICK_TRIAL).json()
    assert created["username"] == "testmarket"
    assert created["login_error"] is None

    login = cloud_client.post(
        "/api/v1/auth/login",
        json={"username": "testmarket", "password": "mening-parolim1"},
    )

    assert login.status_code == 200, login.text
    assert login.json()["account"]["site_id"] == created["site_id"]


def test_the_password_never_comes_back_in_the_response(cloud_client) -> None:
    body = cloud_client.post("/api/v1/public/quick-trial", json=QUICK_TRIAL).text

    assert "mening-parolim1" not in body


def test_a_taken_login_does_not_leave_an_orphan_shop(cloud_client) -> None:
    """`create_site` ni orqaga qaytarib bo'lmaydi (o'chirish funksiyasi
    yo'q), shuning uchun login band ekani DO'KON YARATILISHIDAN OLDIN
    tekshirilishi kerak."""
    from cloud import ratelimit

    ratelimit.limiter().reset()
    assert cloud_client.post("/api/v1/public/quick-trial", json=QUICK_TRIAL).status_code == 200
    before = len(cloud_client.get("/api/v1/admin/sites", headers=ADMIN).json())

    second = cloud_client.post(
        "/api/v1/public/quick-trial", json={**QUICK_TRIAL, "phone": "+998 90 999 88 77"}
    )

    assert second.status_code == 409
    after = len(cloud_client.get("/api/v1/admin/sites", headers=ADMIN).json())
    assert after == before, "xato ketgan so'rovdan egasiz do'kon qolmasin"


def test_a_weak_password_is_refused_with_a_readable_reason(cloud_client) -> None:
    res = cloud_client.post(
        "/api/v1/public/quick-trial", json={**QUICK_TRIAL, "password": "parolparol"}
    )

    assert res.status_code == 422
    assert "raqam" in res.json()["detail"], res.text


def test_the_trial_seats_are_limited(cloud_client, monkeypatch) -> None:
    """Mahsulot hali 72 soatlik qabul sinovidan o'tmagan — nosozlik
    chiqsa u o'nlab do'konga tarqalmasligi kerak."""
    from cloud import ratelimit

    ratelimit.limiter().reset()
    monkeypatch.setenv("CHAQIMCHI_SELF_SERVICE_LIMIT", "1")

    first = cloud_client.post("/api/v1/public/quick-trial", json=QUICK_TRIAL)
    second = cloud_client.post(
        "/api/v1/public/quick-trial",
        json={**QUICK_TRIAL, "username": "boshqadokon", "phone": "+998 90 222 33 44"},
    )

    assert first.status_code == 200
    assert second.status_code == 503
    assert "raqamingizni qoldiring" in second.json()["detail"], "berk ko'cha bo'lmasin"


def test_self_service_trial_is_fourteen_days(cloud_client) -> None:
    """Sinov qiymatni ko'rishga yetadi, ammo pullik mahsulotni uch oy
    bepul qilib qo'ymaydi."""
    data = cloud_client.post("/api/v1/public/quick-trial", json=QUICK_TRIAL).json()

    assert data["trial_days"] == 14


def test_windows_release_is_honest_about_availability(cloud_client, monkeypatch) -> None:
    """Sayt tugmani shu javobga qarab ko'rsatadi.

    Ilgari sahifada "115 MB bundle yuklab olish" tugmasi turardi, endpoint
    esa fayl yo'qligi uchun 503 qaytarardi.  Endi mavjudlik bitta joydan
    o'qiladi va hajm o'lchanadi.
    """
    monkeypatch.delenv("CHAQIMCHI_WINDOWS_INSTALLER_URL", raising=False)
    monkeypatch.setattr("cloud.main.WINDOWS_INSTALLER_PATHS", ())
    monkeypatch.setattr("cloud.main._release_dirs", list)

    body = cloud_client.get("/api/v1/public/windows-release").json()
    assert body["available"] is False
    assert body["size_mb"] is None
    assert cloud_client.get("/api/v1/public/download-installer").status_code == 503


def test_windows_installer_is_served_from_disk(cloud_client, monkeypatch, tmp_path) -> None:
    installer = tmp_path / "Chaqimchi_AI_Setup.exe"
    installer.write_bytes(b"MZ" + b"\0" * 2_000_000)
    monkeypatch.delenv("CHAQIMCHI_WINDOWS_INSTALLER_URL", raising=False)
    monkeypatch.setattr("cloud.main.WINDOWS_INSTALLER_PATHS", (installer,))
    monkeypatch.setattr("cloud.main._release_dirs", list)

    body = cloud_client.get("/api/v1/public/windows-release").json()
    assert body["available"] is True
    assert body["size_mb"] == 2

    response = cloud_client.get("/api/v1/public/download-installer")
    assert response.status_code == 200
    assert response.content.startswith(b"MZ")
    # Fayl nomida versiya bo'lishi shart: usiz har yuklab olishda bir xil
    # nom va deyarli bir xil hajm tushardi va mijoz yangi versiyani
    # olganini ko'ra olmasdi.
    disposition = response.headers.get("content-disposition", "")
    assert "Chaqimchi_AI_Setup-" in disposition
    assert disposition.endswith('.exe"')


def test_download_filename_carries_version_and_pairing_code(
    cloud_client, monkeypatch, tmp_path
) -> None:
    """Nomdagi kod o'rnatuvchi tomonidan o'qiladi va dastur o'zi ulanadi.

    Versiya qo'shilgach kod nomning **oxirida** qolishi shart — NSIS
    aynan oxirgi `-XXXXXX` ni o'qiydi.
    """
    installer = tmp_path / "Chaqimchi_AI_Setup.exe"
    installer.write_bytes(b"MZ")
    monkeypatch.delenv("CHAQIMCHI_WINDOWS_INSTALLER_URL", raising=False)
    monkeypatch.setattr("cloud.main.WINDOWS_INSTALLER_PATHS", (installer,))
    monkeypatch.setattr("cloud.main._release_dirs", list)

    disposition = cloud_client.get("/api/v1/public/download-installer?code=13204e").headers[
        "content-disposition"
    ]
    assert disposition.endswith('-13204E.exe"'), disposition


def test_windows_installer_redirects_when_published_externally(cloud_client, monkeypatch) -> None:
    """~70 MB binarni Docker image ichida tashish shart emas — u GitHub
    Releases'da turadi va cloud faqat yo'naltiradi."""
    monkeypatch.setenv(
        "CHAQIMCHI_WINDOWS_INSTALLER_URL",
        "https://github.com/example/releases/Chaqimchi_AI_Setup.exe",
    )
    monkeypatch.setenv("CHAQIMCHI_WINDOWS_INSTALLER_SIZE_MB", "71")

    body = cloud_client.get("/api/v1/public/windows-release").json()
    assert body["available"] is True
    assert body["size_mb"] == 71

    response = cloud_client.get("/api/v1/public/download-installer", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"].startswith("https://github.com/")


def test_windows_installer_url_must_be_https(cloud_client, monkeypatch) -> None:
    """HTTP havola o'rnatuvchini yo'lda almashtirishga imkon berardi."""
    monkeypatch.setenv("CHAQIMCHI_WINDOWS_INSTALLER_URL", "http://example.com/setup.exe")
    monkeypatch.setattr("cloud.main.WINDOWS_INSTALLER_PATHS", ())
    monkeypatch.setattr("cloud.main._release_dirs", list)
    assert cloud_client.get("/api/v1/public/windows-release").json()["available"] is False


def test_quick_trial_requires_consent(cloud_client) -> None:
    """Rozilik katagisiz do'kon yozuvi va telefon raqami saqlanmasin.

    Oldin `consent` maydonining standart qiymati `True` edi — ya'ni forma
    katagi belgilanmasa ham ma'lumot bazaga tushardi.  `/public/leads` esa
    doim rozilik talab qilgan; ikki endpoint bir xil qoidada bo'lishi kerak.
    """
    res = cloud_client.post(
        "/api/v1/public/quick-trial",
        json={
            "phone": "+998 90 123 45 67",
            "company": "Rozilik yo'q",
            "username": "dokonchi",
            "password": "parol12345",
        },
    )
    assert res.status_code == 422


def test_quick_trial_is_rate_limited(cloud_client) -> None:
    """Bu endpoint har chaqiruvda haqiqiy `site` yaratadi — cheksiz bo'lmasin."""
    from cloud import ratelimit

    ratelimit.limiter().reset()
    codes = [
        cloud_client.post(
            "/api/v1/public/quick-trial",
            json={
                "phone": "+998 90 111 22 33",
                "consent": True,
                # Har so'rovda boshqa login: aks holda ikkinchisi 409
                # ("login band") bo'lib, cheklov sinovi ma'nosini yo'qotardi.
                "username": f"dokon{index}",
                "password": "parol12345",
            },
        ).status_code
        for index in range(5)
    ]
    assert codes.count(200) == 3, codes
    assert codes[-1] == 429


def test_windows_release_version_comes_from_the_file_not_the_server(tmp_path, monkeypatch):
    """Sayt ko'rsatgan versiya yuklab olinadigan fayl bilan bir xil bo'lsin.

    Haqiqiy xato: bu yerda serverning o'z `__version__` i qaytarilardi.
    Yangi o'rnatuvchi yuklangach sayt hamon eski raqamni ko'rsatardi,
    fayl nomi esa yangisini — "yangisi chiqdimi?" degan savolga javob
    berib bo'lmasdi.
    """
    from cloud import main as cloud_main

    releases = tmp_path / "releases"
    releases.mkdir()
    exe = releases / "chaqimchi-windows-9.9.9.exe"
    exe.write_bytes(b"x" * 2048)
    exe.with_suffix(".json").write_text('{"version": "9.9.9"}', encoding="utf-8")

    monkeypatch.setattr(cloud_main, "_release_dirs", lambda: [releases])
    monkeypatch.setattr(cloud_main, "_windows_installer_url", lambda: "")
    monkeypatch.setattr(cloud_main, "_windows_installer_file", lambda: exe)

    with TestClient(cloud_main.app) as client:
        body = client.get("/api/v1/public/windows-release").json()

    assert body["available"] is True
    assert body["version"] == "9.9.9", "versiya relizdan olinishi kerak"
    assert body["version"] != cloud_main.__version__


# ── Faqat telefon bilan ariza → tasdiqlash → panelga kirish ─────────────
#
# Mijoz saytda ISM yozmaydi: har bir qo'shimcha maydon formani tashlab
# ketadiganlar sonini oshiradi va ism baribir qo'ng'iroqda aniqlanadi.
# Admin arizani tasdiqlaganda do'kon HAM, panelga kirish ma'lumoti HAM
# yaratiladi — aks holda mijozning paneliga kirish yo'li qolmasdi.


def test_a_phone_number_alone_is_enough_to_apply(cloud_client) -> None:
    response = cloud_client.post(
        "/api/v1/public/leads", json={"phone": "+998 93 222 50 70", "consent": True}
    )

    assert response.status_code == 200, response.text
    lead = cloud_client.get("/api/v1/admin/leads", headers=ADMIN).json()[0]
    assert lead["phone"] == "+998 93 222 50 70"
    assert not lead["full_name"], "yo'q ismni o'ylab topmaymiz"


def test_the_site_form_asks_only_for_name_and_phone(cloud_client) -> None:
    """CTA faqat bog'lanish uchun zarur ism va telefonni ko'rsatadi."""
    page = cloud_client.get("/").text
    form = page[page.index('id="leadForm"') : page.index("</form>", page.index('id="leadForm"'))]

    visible = [
        line for line in form.splitlines()
        if "<input" in line and 'type="hidden"' not in line and 'name="website"' not in line
    ]
    assert len(visible) == 2, visible  # ism va telefon
    assert 'name="full_name"' in form and 'name="phone"' in form
    assert 'name="username"' not in form and 'name="password"' not in form


def test_the_form_sends_a_lead_request(cloud_client) -> None:
    """CTA self-service emas, oddiy lead endpointiga ariza yuboradi."""
    js = cloud_client.get("/assets/site.js").text

    assert 'fetch("/api/v1/public/leads"' in js


def test_the_lead_cta_has_no_self_service_trial_flow(cloud_client) -> None:
    """Minimal CTA o'zidan login/parol yoki trial yaratishni talab qilmaydi."""
    js = cloud_client.get("/assets/site.js").text

    assert "/api/v1/public/quick-trial" not in js
    assert "startTrial" not in js


def test_approving_an_application_hands_over_a_working_login(
    cloud_client, monkeypatch
) -> None:
    monkeypatch.setenv("CHAQIMCHI_PORTAL_JWT_SECRET", "portal-secret-with-more-than-32-chars")
    lead_id = cloud_client.post(
        "/api/v1/public/leads", json={"phone": "+998901112233", "consent": True}
    ).json()["lead_id"]

    site = cloud_client.post(
        f"/api/v1/admin/leads/{lead_id}/convert", headers=ADMIN, json={"subscription_months": 1}
    ).json()

    assert site["login"]["username"] == "998901112233", "login — o'z telefon raqami"
    signed_in = cloud_client.post(
        "/api/v1/auth/login",
        json={"username": site["login"]["username"], "password": site["login"]["password"]},
    )
    assert signed_in.status_code == 200, signed_in.text
    assert signed_in.json()["account"]["role"] == "customer"
    assert signed_in.json()["account"]["site_id"] == site["site_id"]


def test_the_password_can_be_read_out_over_the_phone(cloud_client) -> None:
    """Parol mijozga TELEFONDA aytiladi — SMS shlyuzi yo'q.
    `k7Qm2xW9pL` ni aytib bo'lmaydi, "olma anor 4821" ni bo'ladi."""
    lead_id = cloud_client.post(
        "/api/v1/public/leads", json={"phone": "+998901112244", "consent": True}
    ).json()["lead_id"]

    password = cloud_client.post(
        f"/api/v1/admin/leads/{lead_id}/convert", headers=ADMIN, json={"subscription_months": 1}
    ).json()["login"]["password"]

    assert password.isascii() and password.isalnum(), password
    assert password[-4:].isdigit() and password[:-4].isalpha(), password


def test_two_shops_on_one_phone_get_different_logins(cloud_client) -> None:
    """Bitta odam ikkinchi do'kon ochsa login to'qnashadi va ikkinchi
    do'kon panelsiz qolardi."""
    logins = []
    for index in range(2):
        site = cloud_client.post(
            "/api/v1/admin/sites",
            headers=ADMIN,
            json={"name": f"Do'kon {index}", "contact_phone": "+998900000001"},
        ).json()
        created = cloud_client.post(
            f"/api/v1/admin/sites/{site['site_id']}/login", headers=ADMIN
        )
        assert created.status_code == 200, created.text
        logins.append(created.json()["username"])

    assert logins[0] != logins[1], logins


def test_a_shop_cannot_end_up_with_two_logins(cloud_client) -> None:
    site = cloud_client.post(
        "/api/v1/admin/sites", headers=ADMIN, json={"name": "Yagona", "contact_phone": "+998900000002"}
    ).json()
    cloud_client.post(f"/api/v1/admin/sites/{site['site_id']}/login", headers=ADMIN)

    again = cloud_client.post(f"/api/v1/admin/sites/{site['site_id']}/login", headers=ADMIN)

    assert again.status_code == 409
    assert "998900000002" in again.json()["detail"], "mavjud login aytilsin"


def test_a_lead_without_a_name_still_gets_a_readable_shop_name(cloud_client) -> None:
    """Do'kon nomi `lead["full_name"]` dan olinardi — ism yo'q bo'lgach
    nomi bo'sh do'kon ochilardi."""
    lead_id = cloud_client.post(
        "/api/v1/public/leads", json={"phone": "+998905550505", "consent": True}
    ).json()["lead_id"]

    site = cloud_client.post(
        f"/api/v1/admin/leads/{lead_id}/convert", headers=ADMIN, json={"subscription_months": 1}
    ).json()

    assert site["name"].strip()
    assert "998905550505" in site["name"]


def test_a_coded_link_keeps_the_code_even_when_a_public_url_is_set(
    cloud_client, tmp_path, monkeypatch
) -> None:
    """Serverga `CHAQIMCHI_WINDOWS_INSTALLER_URL` qo'yilgach kodli havola
    JIMGINA buzilgan edi.

    Redirect brauzerga manzildagi nomni saqlatadi
    (`chaqimchi-windows-0.6.8.exe`) — kod yo'qoladi va mijoz sehrgarda
    6 ta belgini qo'lda kiritishga majbur bo'ladi.  Ya'ni "bir bosishda
    ulanish" va'dasi bitta env o'zgaruvchisi bilan o'chib qolardi.
    """
    installer = tmp_path / "Chaqimchi_AI_Setup.exe"
    installer.write_bytes(b"MZ")
    monkeypatch.setenv(
        "CHAQIMCHI_WINDOWS_INSTALLER_URL",
        "https://dl.example.uz/releases/chaqimchi-windows-0.6.8.exe",
    )
    monkeypatch.setattr("cloud.main.WINDOWS_INSTALLER_PATHS", (installer,))
    monkeypatch.setattr("cloud.main._release_dirs", list)

    response = cloud_client.get(
        "/api/v1/public/download-installer?code=13204e", follow_redirects=False
    )

    assert response.status_code == 200, "kodli havola redirect bo'lmasin"
    assert response.headers["content-disposition"].endswith('-13204E.exe"')


def test_a_coded_link_still_works_when_the_file_is_only_remote(
    cloud_client, monkeypatch
) -> None:
    """Fayl faqat tashqarida bo'lsa kodni saqlab qololmaymiz — lekin
    yuklab olish baribir ishlashi kerak (sehrgar kodni so'raydi)."""
    monkeypatch.setenv(
        "CHAQIMCHI_WINDOWS_INSTALLER_URL",
        "https://github.com/example/releases/Chaqimchi_AI_Setup.exe",
    )
    monkeypatch.setattr("cloud.main.WINDOWS_INSTALLER_PATHS", ())
    monkeypatch.setattr("cloud.main._release_dirs", list)

    response = cloud_client.get(
        "/api/v1/public/download-installer?code=13204e", follow_redirects=False
    )

    assert response.status_code == 307


# ── Sog'liq tekshiruvi ───────────────────────────────────────────────────


def test_liveness_stays_cheap_and_always_ok(cloud_client) -> None:
    """`/health` ni Docker chaqiradi — u bog'liqlikka bog'lanmasligi kerak."""
    response = cloud_client.get("/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert "checks" not in response.json()


def test_deep_health_actually_touches_dependencies(cloud_client) -> None:
    """Bungacha `/health` bazani ochmasdan ham 'ok' derdi."""
    response = cloud_client.get("/health/deep", headers=ADMIN)
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    names = {item["name"] for item in body["checks"]}
    assert names == {"control_db", "event_db", "media", "disk"}
    assert all(item["ok"] for item in body["checks"])


def test_deep_health_tells_a_stranger_nothing_about_the_business(cloud_client) -> None:
    """Monitoring 503 ni ko'rsin, begona esa mijozlar sonini BILMASIN.

    2026-08-25 auditi: bu endpoint ochiq turardi va `{"sites": 4}`
    qaytarardi — raqobatchi bitta `curl` bilan nechta mijozimiz borligini
    bilib olardi.  Bucket nomi, disk hajmi va versiya ham chiqardi.
    """
    body = cloud_client.get("/health/deep").json()

    assert body["ok"] is True
    assert {item["name"] for item in body["checks"]} == {
        "control_db",
        "event_db",
        "media",
        "disk",
    }
    for item in body["checks"]:
        assert set(item) <= {"name", "ok", "ms"}, item
    text = str(body)
    for leak in ("sites", "bucket", "free_gb", "used_percent", "version", "postgres"):
        assert leak not in text, leak


def test_deep_health_reports_503_when_a_dependency_is_down(cloud_client, monkeypatch) -> None:
    """Nosozlik 200 bilan yashirilsa, tashqi monitoring uni hech qachon ko'rmaydi."""
    import cloud.main as main

    def broken() -> None:
        raise RuntimeError("baza yiqildi")

    original = main._probe
    monkeypatch.setattr(main, "_probe", lambda name, check: original(name, broken))

    # Begona ham 503 ni ko'radi — monitoring shu bilan ishlaydi.
    anonymous = cloud_client.get("/health/deep")
    assert anonymous.status_code == 503
    assert anonymous.json()["ok"] is False
    assert "error" not in anonymous.json()["checks"][0], "sabab begonaga aytilmaydi"

    # Sababni esa faqat admin o'qiydi.
    response = cloud_client.get("/health/deep", headers=ADMIN)
    assert response.status_code == 503
    body = response.json()
    assert body["ok"] is False
    assert "baza yiqildi" in body["checks"][0]["error"]


def test_deep_health_warns_before_the_disk_is_full(cloud_client, monkeypatch) -> None:
    """Disk to'lgach SQLite yozuvi ham yiqiladi — oldindan bilish kerak."""
    import cloud.main as main

    monkeypatch.setattr(main, "HEALTH_MIN_FREE_GB", 10**9)
    response = cloud_client.get("/health/deep", headers=ADMIN)
    assert response.status_code == 503
    disk = next(item for item in response.json()["checks"] if item["name"] == "disk")
    assert disk["ok"] is False
    assert "GB qoldi" in disk["error"]


# ── Audit jurnali ────────────────────────────────────────────────────────
#
# 2026-08-25 auditi (YUQORI-9): jurnal bor edi, lekin eng xavfli
# amallarni yozmasdi — kirish havolasi yaratish (bu credential), naqd
# to'lovni tasdiqlash, obunani uzaytirish, tarifni almashtirish, a'zo
# qo'shish/o'chirish va biometrik rasmni o'chirish.  Ya'ni pul yoki
# kirish huquqi bilan bog'liq bahsda ko'rsatadigan dalil yo'q edi.


def _audit_actions(client) -> dict:
    rows = client.get("/api/v1/admin/portal-audit", headers=ADMIN).json()
    entries = rows["events"]
    return {str(row["action"]): row for row in entries}


def test_money_and_access_changes_leave_a_trace(cloud_client, monkeypatch) -> None:
    """Pul va kirish huquqiga tegadigan har bir amal yozilsin."""
    # Kirish havolasi owner tokenini imzolaydi — kalitsiz 503 qaytaradi.
    monkeypatch.setenv("CHAQIMCHI_OWNER_JWT_SECRET", "owner-secret-with-more-than-32-chars")
    site = _make_site(cloud_client, "Audit", "biznes")
    site_id = site["site_id"]

    cloud_client.post(
        f"/api/v1/admin/sites/{site_id}/members",
        headers=ADMIN,
        json={"telegram_id": "777", "role": "owner"},
    )
    cloud_client.post(
        f"/api/v1/admin/sites/{site_id}/members/777/login-link", headers=ADMIN
    )
    cloud_client.post(
        f"/api/v1/admin/sites/{site_id}/extend", headers=ADMIN, json={"months": 3}
    )
    cloud_client.post(
        f"/api/v1/admin/sites/{site_id}/plan", headers=ADMIN, json={"plan": "boshlangich"}
    )

    actions = _audit_actions(cloud_client)
    for expected in (
        "site.member.added",
        "owner.login_link.created",
        "site.subscription.extended",
        "site.plan.changed",
    ):
        assert expected in actions, f"{expected} jurnalga tushmadi"


def test_the_login_link_token_never_reaches_the_log(cloud_client, monkeypatch) -> None:
    """Havolaning o'zi parol.  Jurnal uni saqlab qolsa, jurnalni o'qiy
    oladigan har kim mijoz paneliga kira olardi."""
    monkeypatch.setenv("CHAQIMCHI_OWNER_JWT_SECRET", "owner-secret-with-more-than-32-chars")
    site = _make_site(cloud_client, "Audit token", "biznes")
    site_id = site["site_id"]
    cloud_client.post(
        f"/api/v1/admin/sites/{site_id}/members",
        headers=ADMIN,
        json={"telegram_id": "778", "role": "owner"},
    )
    created = cloud_client.post(
        f"/api/v1/admin/sites/{site_id}/members/778/login-link", headers=ADMIN
    ).json()
    token = created["url"].split("key=")[1]

    rows = cloud_client.get("/api/v1/admin/portal-audit", headers=ADMIN).text

    assert token not in rows, "token jurnalga oqib ketdi"


def test_the_master_key_is_not_an_anonymous_actor(cloud_client) -> None:
    """`X-Cloud-Admin-Key` bilan qilingan amal `actor_id=NULL` bo'lib
    qolsa, u boshqa har qanday bo'sh yozuvdan farq qilmasdi.  Kimligini
    aytmasa ham, USULI ko'rinishi kerak."""
    site = _make_site(cloud_client, "Audit master", "biznes")
    cloud_client.post(
        f"/api/v1/admin/sites/{site['site_id']}/plan",
        headers=ADMIN,
        json={"plan": "boshlangich"},
    )

    entry = _audit_actions(cloud_client)["site.plan.changed"]

    assert entry["actor_id"] == "cloud-admin-key"


# ── Chegara ogohlantirishi platforma adminiga yetsin ─────────────────────


def test_rate_limited_site_notifies_the_platform_admin(cloud_client, monkeypatch) -> None:
    """Media chegarasi urilsa admin XABAR OLADI — kuniga bir marta.

    2026-08-26 nosozligining eng qimmat qismi: do'kon 3 soat rasmsiz
    ishladi va bu hech kimga bildirilmadi.  Yagona izi `INFO` access
    logdagi 6 315 ta 429 qatori edi.
    """
    import asyncio

    import cloud.main as main
    from cloud import ratelimit

    monkeypatch.setenv("CHAQIMCHI_TELEGRAM_LEAD_CHAT_IDS", "555")
    site = cloud_client.post(
        "/api/v1/admin/sites",
        headers={"X-Cloud-Admin-Key": "test-admin"},
        json={"name": "Chegara do'koni", "plan": "lite"},
    ).json()
    site_id = site["site_id"]

    sent: list = []

    class FakeSender:
        async def send_to(self, chat_id, text):
            sent.append((chat_id, text))
            return True

    monkeypatch.setattr(main.get_alerts(), "sender", FakeSender())
    main._rate_limit_notified.clear()

    # Hali hech narsa rad etilmagan — xabar ham yo'q.
    asyncio.run(main._notify_rate_limited_sites())
    assert sent == [], "sog'lom obyekt uchun xabar yuborilmasin"

    # Chegara uriladi.
    for _ in range(4):
        ratelimit.limiter().hit("snapshots", site_id, limit=1, window_sec=3600)

    asyncio.run(main._notify_rate_limited_sites())
    assert len(sent) == 1
    chat_id, text = sent[0]
    assert chat_id == "555"
    assert "Chegara do'koni" in text
    assert "3" in text, "saqlanmagan rasm soni xabarda bo'lsin"

    # Ikkinchi chaqiruv — takror xabar YO'Q (kuniga bir marta).
    asyncio.run(main._notify_rate_limited_sites())
    assert len(sent) == 1, "6 315 ta rad etish 6 315 ta xabar bo'lmasin"
