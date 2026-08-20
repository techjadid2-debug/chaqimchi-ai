"""Aloqa holati: qaysi mijozning tizimi ishlamayotganini bilish."""

from datetime import datetime, timedelta, timezone

import pytest

from cloud.store import (
    OFFLINE_HOURS,
    ONLINE_MINUTES,
    CloudStore,
    _connection_state,
)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _seen(minutes_ago: int) -> str:
    return (_now() - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%d %H:%M:%S")


# ── _connection_state ────────────────────────────────────────────────────


def test_recent_heartbeat_is_online() -> None:
    state = _connection_state(_seen(5), devices=1)
    assert state["connection"] == "online"
    assert state["minutes_since_seen"] == 5


def test_within_one_hour_still_online() -> None:
    """Bitta heartbeat o‘tkazib yuborilishi normal (interval 30 daq)."""
    assert _connection_state(_seen(ONLINE_MINUTES - 1), 1)["connection"] == "online"


def test_a_few_hours_is_stale() -> None:
    assert _connection_state(_seen(ONLINE_MINUTES + 10), 1)["connection"] == "stale"
    assert _connection_state(_seen(OFFLINE_HOURS * 60 - 10), 1)["connection"] == "stale"


def test_over_a_day_is_offline() -> None:
    assert _connection_state(_seen(OFFLINE_HOURS * 60 + 10), 1)["connection"] == "offline"


def test_no_device_is_not_paired() -> None:
    """Kod berilgan, lekin o‘rnatuvchi ishni tugatmagan."""
    state = _connection_state(None, devices=0)
    assert state["connection"] == "not_paired"
    assert state["minutes_since_seen"] is None


def test_device_without_last_seen_is_offline() -> None:
    assert _connection_state(None, devices=1)["connection"] == "offline"


def test_broken_timestamp_does_not_crash() -> None:
    assert _connection_state("axlat", 1)["connection"] == "offline"


def test_future_timestamp_clamped_to_zero() -> None:
    """Soatlar farq qilsa manfiy daqiqa chiqmasin."""
    future = (_now() + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    state = _connection_state(future, 1)
    assert state["minutes_since_seen"] == 0
    assert state["connection"] == "online"


# ── list_sites / site_detail ─────────────────────────────────────────────


@pytest.fixture
def store(tmp_path) -> CloudStore:
    return CloudStore(tmp_path / "cloud.db")


def _age_device(store: CloudStore, site_id: str, minutes: int) -> None:
    conn = store._connect()
    conn.execute("UPDATE devices SET last_seen = ? WHERE site_id = ?", (_seen(minutes), site_id))
    conn.commit()
    conn.close()


def test_new_site_without_device_is_not_paired(store: CloudStore) -> None:
    store.create_site("Yangi do'kon", "starter")
    row = store.list_sites()[0]
    assert row["connection"] == "not_paired"
    assert row["last_seen"] is None


def test_paired_site_is_online(store: CloudStore) -> None:
    site = store.create_site("Do'kon", "starter")
    store.claim_device(site["pairing_code"])

    row = store.list_sites()[0]
    assert row["connection"] == "online"
    assert row["last_seen"]


def test_silent_site_becomes_offline(store: CloudStore) -> None:
    site = store.create_site("Do'kon", "starter")
    store.claim_device(site["pairing_code"])
    _age_device(store, site["site_id"], OFFLINE_HOURS * 60 + 60)

    row = store.list_sites()[0]
    assert row["connection"] == "offline"
    assert row["minutes_since_seen"] > OFFLINE_HOURS * 60


def test_heartbeat_brings_site_back_online(store: CloudStore) -> None:
    site = store.create_site("Do'kon", "starter")
    claimed = store.claim_device(site["pairing_code"])
    _age_device(store, site["site_id"], 3000)
    assert store.list_sites()[0]["connection"] == "offline"

    store.heartbeat(claimed["site_id"], claimed["device_token"], active_cameras=1)

    assert store.list_sites()[0]["connection"] == "online"


def test_site_uses_most_recent_device(store: CloudStore) -> None:
    """Ikki qurilmadan bittasi ishlayotgan bo‘lsa — sayt ishlayapti."""
    site = store.create_site("Do'kon", "business")
    store.claim_device(site["pairing_code"])
    _age_device(store, site["site_id"], 5000)
    second = store.new_pairing_code(site["site_id"])
    store.claim_device(second["pairing_code"])

    row = store.list_sites()[0]
    assert row["devices"] == 2
    assert row["connection"] == "online"


def test_site_detail_marks_each_device(store: CloudStore) -> None:
    site = store.create_site("Do'kon", "starter")
    store.claim_device(site["pairing_code"])

    detail = store.site_detail(site["site_id"])
    assert detail["connection"] == "online"
    assert detail["devices"][0]["connection"] == "online"
    assert detail["devices"][0]["minutes_since_seen"] is not None


def test_site_detail_without_devices(store: CloudStore) -> None:
    site = store.create_site("Do'kon", "starter")
    detail = store.site_detail(site["site_id"])
    assert detail["connection"] == "not_paired"
    assert detail["last_seen"] is None


# ── stats ────────────────────────────────────────────────────────────────


def test_stats_counts_offline_sites(store: CloudStore) -> None:
    ok = store.create_site("Ishlayapti", "starter")
    store.claim_device(ok["pairing_code"])

    broken = store.create_site("Buzuq", "starter")
    store.claim_device(broken["pairing_code"])
    _age_device(store, broken["site_id"], OFFLINE_HOURS * 60 + 120)

    store.create_site("O'rnatilmagan", "starter")

    s = store.stats()
    assert s["by_connection"]["online"] == 1
    assert s["offline"] == 1
    assert s["not_paired"] == 1


def test_suspended_site_not_counted_as_broken(store: CloudStore) -> None:
    """O‘zimiz to‘xtatgan mijoz jim turishi — normal, qizil raqamga tushmaydi."""
    site = store.create_site("To'xtatilgan", "starter")
    store.claim_device(site["pairing_code"])
    _age_device(store, site["site_id"], OFFLINE_HOURS * 60 + 120)
    store.set_status(site["site_id"], "suspended")

    s = store.stats()
    assert s["offline"] == 0
    assert s["by_connection"] == {}


def test_stats_empty_store(store: CloudStore) -> None:
    s = store.stats()
    assert s["offline"] == 0
    assert s["not_paired"] == 0
    assert s["by_connection"] == {}
