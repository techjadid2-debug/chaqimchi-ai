"""Telegram ogohlantirishlari: kimga, qachon va necha marta xabar ketadi."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from cloud.alerts import (
    PAIRING_GRACE_HOURS,
    SILENT_ALERT_HOURS,
    AlertConfig,
    AlertService,
    TelegramSender,
    plan_alerts,
    plan_camera_alerts,
    run_check,
)
from cloud.store import CloudStore


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _stamp(hours_ago: float = 0) -> str:
    return (_now() - timedelta(hours=hours_ago)).strftime("%Y-%m-%d %H:%M:%S")


def _site(
    site_id: str = "s1",
    *,
    connection: str = "online",
    license_status: str = "active",
    name: str = "Do'kon",
    created_hours_ago: float = 500,
    minutes_since_seen: int = 5,
    phone: str | None = None,
) -> dict:
    return {
        "id": site_id,
        "name": name,
        "plan": "starter",
        "license_status": license_status,
        "connection": connection,
        "minutes_since_seen": minutes_since_seen,
        "created_at": _stamp(created_hours_ago),
        "contact_phone": phone,
    }


def test_alert_config_can_reuse_owner_bot_token(monkeypatch) -> None:
    monkeypatch.delenv("CHAQIMCHI_SALES_TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("CHAQIMCHI_CLOUD_TELEGRAM_TOKEN", raising=False)
    monkeypatch.setenv("CHAQIMCHI_OWNER_TELEGRAM_TOKEN", "owner-token")
    monkeypatch.setenv("CHAQIMCHI_CLOUD_TELEGRAM_CHAT_ID", "123")
    config = AlertConfig.from_env()
    assert config.enabled
    assert config.token == "owner-token"


def test_sales_bot_token_wins_over_the_customer_bot(monkeypatch) -> None:
    """Arizalar va servis xabarlari SOTUV botidan ketadi.

    Ikkalasi bitta botdan kelsa, ega uchun "yangi ariza" va "do'kon
    hisoboti" bir chatda aralashib, ikkalasi ham e'tibordan qolardi.
    """
    monkeypatch.setenv("CHAQIMCHI_SALES_TELEGRAM_TOKEN", "sotuv-token")
    monkeypatch.setenv("CHAQIMCHI_OWNER_TELEGRAM_TOKEN", "mijoz-token")
    monkeypatch.setenv("CHAQIMCHI_CLOUD_TELEGRAM_CHAT_ID", "123")

    assert AlertConfig.from_env().token == "sotuv-token"


# ── plan_alerts: kimga xabar ketadi ──────────────────────────────────────


def test_offline_site_triggers_alert() -> None:
    alerts, _ = plan_alerts([_site(connection="offline")], {})
    assert len(alerts) == 1
    assert "ishlamayapti" in alerts[0].text
    assert alerts[0].remember == "offline"


def test_alert_not_repeated_while_state_unchanged() -> None:
    """Eng muhimi: har 15 daqiqada o‘sha xabar takrorlanmasin."""
    sites = [_site(connection="offline")]
    alerts, _ = plan_alerts(sites, {"s1": "offline"})
    assert alerts == []


def test_recovery_alert_after_offline() -> None:
    alerts, _ = plan_alerts([_site(connection="online")], {"s1": "offline"})
    assert len(alerts) == 1
    assert "qayta ishga tushdi" in alerts[0].text
    assert alerts[0].remember is None


def test_stale_counts_as_recovery() -> None:
    """Tizim yana xabar bera boshlagan — muammo hal bo‘lgan."""
    alerts, _ = plan_alerts([_site(connection="stale")], {"s1": "offline"})
    assert len(alerts) == 1
    assert "qayta ishga tushdi" in alerts[0].text


def test_stale_alone_does_not_alert() -> None:
    """1–24 soatlik uzilish odatiy hol — bezovta qilmaydi."""
    alerts, _ = plan_alerts([_site(connection="stale")], {})
    assert alerts == []


def test_long_silence_alerts_even_while_stale() -> None:
    """Jonli holat: do'kon kompyuteri 10 soat jim, hech kim bilmagan.

    `stale` oralig'i 1 dan 24 soatgacha cho'zilgani uchun 10 soatlik
    jimlik hech qanday xabar bermasdi — do'kon ochiq bo'lsa ham.
    """
    site = _site(connection="stale", minutes_since_seen=10 * 60)
    alerts, _ = plan_alerts([site], {})
    assert len(alerts) == 1
    assert alerts[0].remember == "silent"
    assert "10 soatdan beri jim" in alerts[0].text


def test_short_outage_still_stays_silent() -> None:
    """Chegaradan bir daqiqa berisi — internet uzilishi, xabar yo'q."""
    site = _site(connection="stale", minutes_since_seen=SILENT_ALERT_HOURS * 60 - 1)
    assert plan_alerts([site], {})[0] == []


def test_silence_alert_is_not_repeated() -> None:
    site = _site(connection="stale", minutes_since_seen=10 * 60)
    assert plan_alerts([site], {"s1": "silent"})[0] == []


def test_silence_escalates_to_offline() -> None:
    """24 soatdan keyin ikkinchi, jiddiyroq xabar ketadi."""
    site = _site(connection="offline", minutes_since_seen=30 * 60)
    alerts, _ = plan_alerts([site], {"s1": "silent"})
    assert len(alerts) == 1
    assert alerts[0].remember == "offline"


def test_recovery_after_silence() -> None:
    alerts, _ = plan_alerts([_site(connection="online")], {"s1": "silent"})
    assert len(alerts) == 1
    assert "qayta ishga tushdi" in alerts[0].text
    assert alerts[0].remember is None


def test_silent_site_does_not_also_raise_camera_alert() -> None:
    """Bitta muammo — bitta xabar.

    Kompyuter o'chganda kameralar ham yo'qoladi; aloqa xabari ustiga
    kamera xabarini qo'shish shovqin.
    """
    site = _site(connection="stale", minutes_since_seen=10 * 60)
    site.update({"cameras_expected": 4, "cameras_active": 0})
    assert plan_camera_alerts([site], {})[0] == []

    site["minutes_since_seen"] = 30
    assert len(plan_camera_alerts([site], {})[0]) == 1


def test_online_site_is_quiet() -> None:
    alerts, forget = plan_alerts([_site(connection="online")], {})
    assert alerts == []
    assert forget == []


# ── Juftlanmagan mijozlar ────────────────────────────────────────────────


def test_new_site_not_alerted_during_pairing_grace() -> None:
    """Yangi mijoz — o‘rnatuvchi hali bormagan bo‘lishi mumkin."""
    site = _site(connection="not_paired", created_hours_ago=PAIRING_GRACE_HOURS - 1)
    alerts, _ = plan_alerts([site], {})
    assert alerts == []


def test_old_unpaired_site_is_alerted() -> None:
    site = _site(connection="not_paired", created_hours_ago=PAIRING_GRACE_HOURS + 1)
    alerts, _ = plan_alerts([site], {})
    assert len(alerts) == 1
    assert "o‘rnatish tugallanmagan" in alerts[0].text


def test_missing_created_at_still_alerts() -> None:
    site = _site(connection="not_paired")
    site["created_at"] = None
    alerts, _ = plan_alerts([site], {})
    assert len(alerts) == 1


# ── To‘lovi joyida bo‘lmagan mijozlar ────────────────────────────────────


@pytest.mark.parametrize("status", ["suspended", "expired"])
def test_non_operational_sites_are_ignored(status: str) -> None:
    """O‘zimiz to‘xtatgan mijoz jim turishi — normal, xabar shart emas."""
    alerts, _ = plan_alerts([_site(connection="offline", license_status=status)], {})
    assert alerts == []


def test_suspended_site_state_is_forgotten() -> None:
    """Qayta yoqilganda yolg‘on «tiklandi» xabari ketmasligi uchun."""
    alerts, forget = plan_alerts(
        [_site(connection="offline", license_status="suspended")], {"s1": "offline"}
    )
    assert alerts == []
    assert forget == ["s1"]


def test_grace_site_is_still_watched() -> None:
    """To‘lov kechikkan, lekin tizim ishlashi kerak — kuzatuvda qoladi."""
    alerts, _ = plan_alerts([_site(connection="offline", license_status="grace")], {})
    assert len(alerts) == 1


# ── Xabar mazmuni ────────────────────────────────────────────────────────


def test_message_includes_name_and_phone() -> None:
    site = _site(connection="offline", name="Chorsu Market", phone="+998901234567")
    alerts, _ = plan_alerts([site], {})
    assert "Chorsu Market" in alerts[0].text
    assert "+998901234567" in alerts[0].text


def test_message_shows_how_long_offline() -> None:
    site = _site(connection="offline", minutes_since_seen=3 * 24 * 60)
    alerts, _ = plan_alerts([site], {})
    assert "3 kun oldin" in alerts[0].text


def test_message_handles_unknown_last_seen() -> None:
    site = _site(connection="offline", minutes_since_seen=None)
    alerts, _ = plan_alerts([site], {})
    assert "hech qachon" in alerts[0].text


# ── run_check: baza bilan birga ──────────────────────────────────────────


class FakeSender:
    """Tarmoqqa chiqmaydi — nima yuborilgani ro‘yxatda qoladi."""

    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.sent: list[str] = []

    async def send(self, text: str) -> bool:
        self.sent.append(text)
        return self.ok

    async def aclose(self) -> None:
        pass


@pytest.fixture
def store(tmp_path) -> CloudStore:
    return CloudStore(tmp_path / "cloud.db")


def _make_offline_site(store: CloudStore, name: str = "Do'kon") -> str:
    site = store.create_site(name, "starter")
    store.claim_device(site["pairing_code"])
    conn = store._connect()
    conn.execute(
        "UPDATE devices SET last_seen = ? WHERE site_id = ?",
        (_stamp(72), site["site_id"]),
    )
    conn.commit()
    conn.close()
    return site["site_id"]


def test_run_check_sends_and_remembers(store: CloudStore) -> None:
    site_id = _make_offline_site(store)
    sender = FakeSender()

    run = asyncio.run(run_check(store, sender))

    assert run.sent == 1
    assert store.alert_states() == {site_id: "offline"}

    # Ikkinchi tekshiruvda takrorlanmaydi.
    run2 = asyncio.run(run_check(store, sender))
    assert run2.sent == 0
    assert len(sender.sent) == 1


def _make_silent_site(store: CloudStore, hours: float) -> str:
    site = store.create_site("Do'kon", "starter")
    store.claim_device(site["pairing_code"])
    conn = store._connect()
    conn.execute(
        "UPDATE devices SET last_seen = ? WHERE site_id = ?",
        (_stamp(hours), site["site_id"]),
    )
    conn.commit()
    conn.close()
    return site["site_id"]


def test_owner_is_told_when_the_system_stops(store: CloudStore) -> None:
    """Egasi kuzatuv to'xtaganini BILISHI kerak.

    `camera_offline` ni qurilmaning o'zi yuboradi — kompyuter o'chganda
    uni yuboradigan hech kim qolmaydi.  Ya'ni eng yomon holatda egasi
    hech narsa eshitmasdi.
    """
    site_id = _make_silent_site(store, hours=10)
    sender = FakeSender()
    to_owner: list[tuple[str, str]] = []

    async def owner_notify(sid: str, text: str) -> None:
        to_owner.append((sid, text))

    run = asyncio.run(run_check(store, sender, owner_notify))

    assert run.sent == 1
    assert len(to_owner) == 1
    assert to_owner[0][0] == site_id
    assert "Kuzatuv to'xtadi" in to_owner[0][1]
    # Egasiga tarif, telefon yoki ichki atamalar yozilmaydi.
    assert "tarif" not in to_owner[0][1].lower()


def test_owner_is_told_when_it_comes_back(store: CloudStore) -> None:
    site_id = _make_silent_site(store, hours=10)
    sender = FakeSender()
    to_owner: list[tuple[str, str]] = []

    async def owner_notify(sid: str, text: str) -> None:
        to_owner.append((sid, text))

    asyncio.run(run_check(store, sender, owner_notify))
    conn = store._connect()
    conn.execute("UPDATE devices SET last_seen = ? WHERE site_id = ?", (_stamp(0), site_id))
    conn.commit()
    conn.close()

    asyncio.run(run_check(store, sender, owner_notify))

    assert len(to_owner) == 2
    assert "tiklandi" in to_owner[1][1]


def test_owner_send_failure_does_not_replay_the_internal_alert(store: CloudStore) -> None:
    """Mijozga yetmasa ham ichki holat yozilsin.

    Aks holda muammo har tekshiruvda "yangi" bo'lib, ichki chatga har
    15 daqiqada bir xil xabar ketardi.
    """
    _make_silent_site(store, hours=10)
    sender = FakeSender()

    async def broken(_sid: str, _text: str) -> None:
        raise RuntimeError("Telegram javob bermadi")

    asyncio.run(run_check(store, sender, broken))
    run2 = asyncio.run(run_check(store, sender, broken))

    assert run2.sent == 0
    assert len(sender.sent) == 1


def test_unpaired_site_does_not_bother_the_owner(store: CloudStore) -> None:
    """Juftlanmagan sayt — bizning o'rnatish ishimiz, mijozniki emas."""
    site = store.create_site("Yangi do'kon", "starter")
    conn = store._connect()
    conn.execute("UPDATE sites SET created_at = ? WHERE id = ?", (_stamp(500), site["site_id"]))
    conn.commit()
    conn.close()
    sender = FakeSender()
    to_owner: list[tuple[str, str]] = []

    async def owner_notify(sid: str, text: str) -> None:
        to_owner.append((sid, text))

    run = asyncio.run(run_check(store, sender, owner_notify))

    assert run.sent == 1  # ichki chatga ketdi
    assert to_owner == []  # mijozga yo'q


def test_run_check_reports_a_stuck_update(store: CloudStore, monkeypatch) -> None:
    """Ulash tekshiruvi: `run_check` yangilanish holatini ham ko'radi.

    Planer sof funksiya, lekin u chaqirilmasa foydasi yo'q — jonli
    do'konda aynan shunday bo'lgan edi (mexanizm bor, chaqiruv yo'q).
    """
    import cloud.alerts as alerts_module

    site = store.create_site("Do'kon", "starter")
    device = store.claim_device(site["pairing_code"])
    store.heartbeat(device["site_id"], device["device_token"], active_cameras=1)
    store.record_device_version(device["device_id"], "0.6.8")
    conn = store._connect()
    conn.execute("UPDATE devices SET app_version_at = ?", (_stamp(24 * 5),))
    conn.commit()
    conn.close()

    monkeypatch.setattr(alerts_module, "_latest_release_version", lambda: "0.6.12")
    sender = FakeSender()
    run = asyncio.run(run_check(store, sender))

    assert run.sent == 1, sender.sent
    assert "0.6.12" in sender.sent[0]
    assert store.alert_states("update") == {site["site_id"]: "stuck"}

    # Ikkinchi tekshiruvda takrorlanmaydi.
    assert asyncio.run(run_check(store, sender)).sent == 0


def test_failed_send_is_retried_next_time(store: CloudStore) -> None:
    """Telegram javob bermasa holat yozilmaydi — xabar butunlay yo‘qolmaydi."""
    _make_offline_site(store)
    failing = FakeSender(ok=False)

    run = asyncio.run(run_check(store, failing))

    assert run.failed == 1
    assert store.alert_states() == {}

    ok_sender = FakeSender()
    assert asyncio.run(run_check(store, ok_sender)).sent == 1


def test_recovery_clears_state(store: CloudStore) -> None:
    site_id = _make_offline_site(store)
    sender = FakeSender()
    asyncio.run(run_check(store, sender))
    assert store.alert_states()

    # Qurilma yana xabar berdi.
    conn = store._connect()
    conn.execute("UPDATE devices SET last_seen = ? WHERE site_id = ?", (_stamp(0), site_id))
    conn.commit()
    conn.close()

    run = asyncio.run(run_check(store, sender))

    assert run.sent == 1
    assert "qayta ishga tushdi" in sender.sent[-1]
    assert store.alert_states() == {}


def test_run_check_on_empty_store(store: CloudStore) -> None:
    run = asyncio.run(run_check(store, FakeSender()))
    assert run.checked == 0
    assert run.sent == 0


# ── Sozlama ──────────────────────────────────────────────────────────────


def test_config_disabled_without_env(monkeypatch) -> None:
    monkeypatch.delenv("CHAQIMCHI_CLOUD_TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("CHAQIMCHI_CLOUD_TELEGRAM_CHAT_ID", raising=False)
    assert AlertConfig.from_env().enabled is False


def test_config_enabled_with_both_values(monkeypatch) -> None:
    monkeypatch.setenv("CHAQIMCHI_CLOUD_TELEGRAM_TOKEN", "123:abc")
    monkeypatch.setenv("CHAQIMCHI_CLOUD_TELEGRAM_CHAT_ID", "-100")
    cfg = AlertConfig.from_env()
    assert cfg.enabled is True
    assert cfg.interval_sec == 900


def test_config_rejects_too_short_interval(monkeypatch) -> None:
    monkeypatch.setenv("CHAQIMCHI_CLOUD_ALERT_INTERVAL_SEC", "5")
    assert AlertConfig.from_env().interval_sec == 60


def test_config_ignores_broken_interval(monkeypatch) -> None:
    monkeypatch.setenv("CHAQIMCHI_CLOUD_ALERT_INTERVAL_SEC", "tez-tez")
    assert AlertConfig.from_env().interval_sec == 900


def test_service_does_not_start_when_disabled(store: CloudStore) -> None:
    service = AlertService(store, AlertConfig())

    async def scenario() -> None:
        service.start()
        assert service.status()["running"] is False
        await service.stop()

    asyncio.run(scenario())


def test_service_status_shape(store: CloudStore) -> None:
    service = AlertService(store, AlertConfig(token="t", chat_id="c"))
    status = service.status()
    assert status["enabled"] is True
    assert status["last_run"] is None
    assert status["pairing_grace_hours"] == PAIRING_GRACE_HOURS


# ── Telegramga yuborish (tarmoqsiz) ──────────────────────────────────────


def _mock_sender(handler) -> TelegramSender:
    import httpx

    sender = TelegramSender(AlertConfig(token="123:abc", chat_id="-100"))
    sender._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return sender


def test_sender_posts_expected_payload() -> None:
    seen = {}

    def handler(request):
        import json

        import httpx

        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True})

    sender = _mock_sender(handler)
    assert asyncio.run(sender.send("<b>salom</b>")) is True
    assert seen["url"] == "https://api.telegram.org/bot123:abc/sendMessage"
    assert seen["body"]["chat_id"] == "-100"
    assert seen["body"]["text"] == "<b>salom</b>"
    assert seen["body"]["parse_mode"] == "HTML"


def test_sender_reports_failure_on_bad_status() -> None:
    import httpx

    sender = _mock_sender(lambda r: httpx.Response(401, text="Unauthorized"))
    assert asyncio.run(sender.send("x")) is False


def test_sender_survives_network_error() -> None:
    """Telegram yiqilsa cloud ishlashda davom etadi."""
    import httpx

    def handler(request):
        raise httpx.ConnectError("tarmoq yo'q")

    sender = _mock_sender(handler)
    assert asyncio.run(sender.send("x")) is False


def test_sender_silent_when_not_configured() -> None:
    sender = TelegramSender(AlertConfig())
    assert asyncio.run(sender.send("x")) is False


# ── API ──────────────────────────────────────────────────────────────────

ADMIN = {"X-Cloud-Admin-Key": "test-admin"}


@pytest.fixture
def cloud_client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("CHAQIMCHI_CLOUD_ADMIN_KEY", "test-admin")
    monkeypatch.delenv("CHAQIMCHI_CLOUD_TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("CHAQIMCHI_CLOUD_TELEGRAM_CHAT_ID", raising=False)
    import cloud.main as cm

    monkeypatch.setattr(cm, "DB_PATH", tmp_path / "c.db")
    monkeypatch.setattr(cm, "_store", None)
    monkeypatch.setattr(cm, "_alerts", None)
    return TestClient(cm.app)


def test_api_alerts_status_disabled_by_default(cloud_client) -> None:
    r = cloud_client.get("/api/v1/admin/alerts", headers=ADMIN)
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False
    assert body["token_set"] is False


def test_api_alerts_requires_admin_key(cloud_client) -> None:
    assert cloud_client.get("/api/v1/admin/alerts").status_code == 401
    assert cloud_client.post("/api/v1/admin/alerts/check").status_code == 401


def test_api_test_message_rejected_when_not_configured(cloud_client) -> None:
    r = cloud_client.post("/api/v1/admin/alerts/test", headers=ADMIN)
    assert r.status_code == 400
    assert "TELEGRAM_TOKEN" in r.json()["detail"]


# ── Server diski ─────────────────────────────────────────────────────────
#
# Qurilma monitoringi mijoz tomonini qo'riqlaydi; bu VPS'ning o'zini.
# Disk to'lsa PostgreSQL o'qish rejimiga tushadi va media yuklash 500
# qaytara boshlaydi — buni mijozdan oldin bilish kerak.


def test_full_disk_raises_an_alert_once() -> None:
    from cloud.alerts import SERVER_SITE_ID, plan_disk_alert

    alerts, _ = plan_disk_alert(91.0, {})
    assert len(alerts) == 1
    assert alerts[0].site_id == SERVER_SITE_ID
    assert alerts[0].kind == "disk"
    assert alerts[0].remember == "full"

    # Holat yozilgach o'sha xabar takrorlanmaydi.
    repeat, _ = plan_disk_alert(92.0, {SERVER_SITE_ID: "full"})
    assert repeat == []


def test_disk_recovery_uses_hysteresis() -> None:
    """84.9/85.1 atrofidagi tebranish xabar bo'roniga aylanmasin."""
    from cloud.alerts import SERVER_SITE_ID, plan_disk_alert

    # 85 dan tushdi, lekin hali 80 dan baland — jim.
    between, _ = plan_disk_alert(83.0, {SERVER_SITE_ID: "full"})
    assert between == []

    # 80 dan pastga tushgach "tiklandi" ketadi.
    recovered, _ = plan_disk_alert(70.0, {SERVER_SITE_ID: "full"})
    assert len(recovered) == 1 and recovered[0].remember is None


def test_unknown_disk_usage_is_silent() -> None:
    from cloud.alerts import plan_disk_alert

    alerts, forget = plan_disk_alert(None, {})
    assert alerts == [] and forget == []


def test_api_manual_check_runs(cloud_client) -> None:
    cloud_client.post(
        "/api/v1/admin/sites",
        headers=ADMIN,
        json={"name": "Do'kon", "plan": "starter", "subscription_months": 1},
    )

    r = cloud_client.post("/api/v1/admin/alerts/check", headers=ADMIN)

    assert r.status_code == 200
    body = r.json()
    assert body["checked"] == 1
    # Telegram sozlanmagan — xabar ketmaydi, lekin tekshiruv ishlaydi.
    assert body["sent"] == 0
    assert cloud_client.get("/api/v1/admin/alerts", headers=ADMIN).json()["last_run"]
