"""Kamera nazorati: 3 kameradan bittasi o‘chsa ham bilinsin.

Bungacha edge har heartbeat'da `active_cameras` yuborardi, lekin cloud uni
faqat javobda qaytarib tashlardi — hech qayerda saqlanmasdi. Natijada 3
kamerali Business mijozda (1 490 000 so‘m/oy) bitta kamera o‘chsa, panelda
hamma narsa yashil turardi.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from cloud.alerts import plan_camera_alerts, run_check
from cloud.store import CloudStore


@pytest.fixture
def store(tmp_path) -> CloudStore:
    return CloudStore(tmp_path / "cloud.db")


def _site_row(
    *,
    cameras_active: int = 3,
    cameras_expected: int = 3,
    connection: str = "online",
    license_status: str = "active",
) -> dict:
    return {
        "id": "s1",
        "name": "Oq Saroy",
        "plan": "business",
        "contact_phone": "+998901112233",
        "license_status": license_status,
        "connection": connection,
        "cameras_active": cameras_active,
        "cameras_expected": cameras_expected,
    }


# ── Kamera sonini saqlash ────────────────────────────────────────────────


def test_heartbeat_stores_camera_count(store: CloudStore) -> None:
    site = store.create_site("Do'kon", "business")
    claimed = store.claim_device(site["pairing_code"])

    store.heartbeat(claimed["site_id"], claimed["device_token"], active_cameras=3)

    row = store.list_sites()[0]
    assert row["cameras_active"] == 3
    assert row["cameras_expected"] == 3
    assert row["cameras_ok"] is True


def test_expected_remembers_the_peak(store: CloudStore) -> None:
    """Bir marta 3 kamera bilan ishlagan bo‘lsa — kutilgani 3 bo‘lib qoladi."""
    site = store.create_site("Do'kon", "business")
    claimed = store.claim_device(site["pairing_code"])

    store.heartbeat(claimed["site_id"], claimed["device_token"], active_cameras=3)
    store.heartbeat(claimed["site_id"], claimed["device_token"], active_cameras=2)

    row = store.list_sites()[0]
    assert row["cameras_active"] == 2
    assert row["cameras_expected"] == 3
    assert row["cameras_ok"] is False


def test_site_without_heartbeat_has_no_expectation(store: CloudStore) -> None:
    """Hali xabar bermagan sayt uchun kamera ogohlantirishi yo‘q."""
    site = store.create_site("Do'kon", "starter")
    store.claim_device(site["pairing_code"])

    row = store.list_sites()[0]
    assert row["cameras_expected"] == 0
    assert row["cameras_ok"] is True


def test_detail_shows_cameras_per_device(store: CloudStore) -> None:
    site = store.create_site("Do'kon", "business")
    claimed = store.claim_device(site["pairing_code"])
    store.heartbeat(claimed["site_id"], claimed["device_token"], active_cameras=2)

    detail = store.site_detail(site["site_id"])
    assert detail["cameras_active"] == 2
    assert detail["devices"][0]["active_cameras"] == 2


def test_admin_can_lower_expectation(store: CloudStore) -> None:
    """Kamera ataylab olib tashlanganda abadiy ogohlantirmasin."""
    site = store.create_site("Do'kon", "business")
    claimed = store.claim_device(site["pairing_code"])
    store.heartbeat(claimed["site_id"], claimed["device_token"], active_cameras=3)
    store.heartbeat(claimed["site_id"], claimed["device_token"], active_cameras=2)
    assert store.list_sites()[0]["cameras_ok"] is False

    store.set_cameras_expected(site["site_id"], 2)

    assert store.list_sites()[0]["cameras_ok"] is True


def test_set_cameras_rejects_unknown_site(store: CloudStore) -> None:
    with pytest.raises(ValueError, match="topilmadi"):
        store.set_cameras_expected("yoq", 2)


# ── plan_camera_alerts ───────────────────────────────────────────────────


def test_missing_camera_triggers_alert() -> None:
    alerts, _ = plan_camera_alerts([_site_row(cameras_active=2)], {})
    assert len(alerts) == 1
    assert alerts[0].kind == "cameras"
    assert "1 ta kamera ishlamayapti" in alerts[0].text
    assert "3 tadan 2 tasi" in alerts[0].text


def test_all_cameras_working_is_quiet() -> None:
    alerts, _ = plan_camera_alerts([_site_row()], {})
    assert alerts == []


def test_camera_alert_not_repeated() -> None:
    sites = [_site_row(cameras_active=2)]
    alerts, _ = plan_camera_alerts(sites, {"s1": "missing:1"})
    assert alerts == []


def test_worsening_sends_new_alert() -> None:
    """1 ta kamera o‘chgan edi, endi 2 ta — bu yangi xabar."""
    alerts, _ = plan_camera_alerts([_site_row(cameras_active=1)], {"s1": "missing:1"})
    assert len(alerts) == 1
    assert "2 ta kamera ishlamayapti" in alerts[0].text


def test_camera_recovery_alert() -> None:
    alerts, _ = plan_camera_alerts([_site_row(cameras_active=3)], {"s1": "missing:1"})
    assert len(alerts) == 1
    assert "kameralar tiklandi" in alerts[0].text
    assert alerts[0].remember is None


def test_offline_site_skips_camera_alert() -> None:
    """Tizim butunlay o‘chgan — aloqa ogohlantirishi allaqachon ketgan."""
    alerts, _ = plan_camera_alerts(
        [_site_row(cameras_active=0, connection="offline")], {}
    )
    assert alerts == []


def test_suspended_site_skips_camera_alert() -> None:
    alerts, forget = plan_camera_alerts(
        [_site_row(cameras_active=0, license_status="suspended")], {"s1": "missing:3"}
    )
    assert alerts == []
    assert forget == ["s1"]


def test_site_without_expectation_is_skipped() -> None:
    alerts, _ = plan_camera_alerts(
        [_site_row(cameras_active=0, cameras_expected=0)], {}
    )
    assert alerts == []


# ── To‘liq oqim ──────────────────────────────────────────────────────────


class FakeSender:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, text: str) -> bool:
        self.sent.append(text)
        return True

    async def aclose(self) -> None:
        pass


def test_end_to_end_camera_failure_and_recovery(store: CloudStore) -> None:
    site = store.create_site("Oq Saroy", "business", contact_phone="+998901112233")
    claimed = store.claim_device(site["pairing_code"])
    hb = dict(site_id=claimed["site_id"], device_token=claimed["device_token"])
    store.heartbeat(**hb, active_cameras=3)
    sender = FakeSender()

    # Hammasi joyida — xabar yo'q.
    assert asyncio.run(run_check(store, sender)).sent == 0

    # Bitta kamera o'chdi.
    store.heartbeat(**hb, active_cameras=2)
    run = asyncio.run(run_check(store, sender))
    assert run.sent == 1
    assert "1 ta kamera ishlamayapti" in sender.sent[-1]

    # Takrorlanmaydi.
    store.heartbeat(**hb, active_cameras=2)
    assert asyncio.run(run_check(store, sender)).sent == 0

    # Tuzatildi.
    store.heartbeat(**hb, active_cameras=3)
    run = asyncio.run(run_check(store, sender))
    assert run.sent == 1
    assert "kameralar tiklandi" in sender.sent[-1]


def test_offline_site_gets_one_alert_not_two(store: CloudStore) -> None:
    """Tizim o‘chganda faqat aloqa xabari ketadi, kamera xabari emas."""
    site = store.create_site("Do'kon", "business")
    claimed = store.claim_device(site["pairing_code"])
    store.heartbeat(claimed["site_id"], claimed["device_token"], active_cameras=3)

    conn = store._connect()
    old = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=72)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    conn.execute(
        "UPDATE devices SET last_seen = ?, active_cameras = 0 WHERE site_id = ?",
        (old, site["site_id"]),
    )
    conn.commit()
    conn.close()

    sender = FakeSender()
    run = asyncio.run(run_check(store, sender))

    assert run.sent == 1
    assert "ishlamayapti" in sender.sent[0]
    assert "kamera" not in sender.sent[0]


# ── Migratsiya ───────────────────────────────────────────────────────────


def test_migration_adds_columns_to_old_db(tmp_path) -> None:
    """Ishlab turgan cloud yangilanganda ustunlar qo‘shiladi."""
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
        CREATE TABLE devices (
            id TEXT PRIMARY KEY, site_id TEXT NOT NULL, label TEXT NOT NULL,
            token_hash TEXT NOT NULL, hardware_id TEXT, last_seen TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE pairing_codes (
            code TEXT PRIMARY KEY, site_id TEXT NOT NULL, expires_at TEXT NOT NULL,
            used INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE alert_state (
            site_id TEXT PRIMARY KEY, connection TEXT NOT NULL, notified_at TEXT NOT NULL
        );
        INSERT INTO alert_state VALUES ('s1', 'offline', '2026-01-01 00:00:00');
        """
    )
    conn.commit()
    conn.close()

    store = CloudStore(db)

    # Eski ogohlantirish holati yo'qolmagan.
    assert store.alert_states("connection") == {"s1": "offline"}
    # Yangi ustunlar ishlaydi.
    site = store.create_site("Yangi", "starter")
    claimed = store.claim_device(site["pairing_code"])
    store.heartbeat(claimed["site_id"], claimed["device_token"], active_cameras=2)
    assert store.list_sites()[0]["cameras_expected"] == 2
