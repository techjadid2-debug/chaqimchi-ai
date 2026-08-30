"""Cloud yukini ushlab turadigan qoidalar.

Har bir test bitta aniq savolga javob beradi: bitta obyekt yoki bitta buzuq
qurilma cloud'ni (yoki Telegram botni) yiqita oladimi?
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cloud import ratelimit
from cloud.notify import throttle
from cloud.snapshots import LocalSnapshotStore

ADMIN = {"X-Cloud-Admin-Key": "test-admin"}


@pytest.fixture
def cloud(tmp_path: Path, monkeypatch):
    import cloud.main as main

    monkeypatch.setenv("CHAQIMCHI_CLOUD_ADMIN_KEY", "test-admin")
    monkeypatch.setenv("CHAQIMCHI_OWNER_JWT_SECRET", "owner-secret-with-more-than-32-characters")
    monkeypatch.setenv("CHAQIMCHI_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("CHAQIMCHI_S3_ENDPOINT", raising=False)
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "cloud.db")
    monkeypatch.setattr(main, "_store", None)
    monkeypatch.setattr(main, "_event_store", None)
    monkeypatch.setattr(main, "_event_store_key", None)
    monkeypatch.setattr(main, "_snapshots", LocalSnapshotStore(tmp_path / "snapshots"))

    sent = []

    async def fake_send(chat_id: str, text: str, *, reply_markup=None) -> None:
        sent.append((chat_id, text))

    monkeypatch.setattr(main, "_send_owner_telegram", fake_send)

    # Fon halqalari o'chiriladi: lifespan `_maintenance_loop` ni yaratishi
    # bilan u ALOHIDA oqimda darhol purge boshlaydi va testdagi
    # `setenv("CHAQIMCHI_CLIP_RETENTION_DAYS", ...)` dan OLDIN standart
    # 7 kunni o'qib muzlatib oladi.  To'liq to'plamda oqim kechikib test
    # yaratgan saytga yetib borar va uning klipini o'chirar edi — shu
    # poyga `test_clip_retention_is_configurable` ning uch haftalik
    # beqarorligi.  Testlar purge'ni baribir sinxron o'zi chaqiradi.
    async def no_background_loop() -> None:
        return None

    monkeypatch.setattr(main, "_maintenance_loop", no_background_loop)
    monkeypatch.setattr(main, "_history_rollup_loop", no_background_loop)

    ratelimit.limiter().reset()
    throttle().reset()
    with TestClient(main.app) as client:
        yield main, client, sent
    ratelimit.limiter().reset()
    throttle().reset()


def _site(client: TestClient, name: str, plan: str = "lite"):
    site = client.post(
        "/api/v1/admin/sites", headers=ADMIN, json={"name": name, "plan": plan}
    ).json()
    device = client.post(
        "/api/v1/devices/claim", json={"pairing_code": site["pairing_code"]}
    ).json()
    headers = {
        "X-Site-Id": device["site_id"],
        "X-Device-Id": device["device_id"],
        "X-Device-Token": device["device_token"],
    }
    return site, headers


def _events(count: int, *, days_ago: int = 0, prefix: str = "evt"):
    occurred = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    return [
        {
            "event_id": f"{prefix}-{index}",
            "event_type": "zone_entered",
            # Minimal rejimda botga faqat critical boradi — bu testlar
            # yuborish MEXANIKASINI tekshiradi, siyosatni emas.
            "severity": "critical",
            "camera_id": "camera-01",
            "occurred_at": occurred,
        }
        for index in range(count)
    ]


# ── Telegram ─────────────────────────────────────────────────────────────


def test_large_batch_sends_one_message_not_one_per_event(cloud) -> None:
    _main, client, sent = cloud
    site, headers = _site(client, "Oq Saroy")
    client.post(
        f"/api/v1/admin/sites/{site['site_id']}/members",
        headers=ADMIN,
        json={"telegram_id": "555", "role": "owner"},
    )

    response = client.post(
        "/api/v1/edge/events/batch", headers=headers, json={"events": _events(500)}
    )

    assert response.status_code == 200
    assert len(sent) == 1
    assert "500 ta ogohlantirish" in sent[0][1]


def test_same_alert_is_not_repeated_every_batch(cloud) -> None:
    _main, client, sent = cloud
    site, headers = _site(client, "Oq Saroy")
    client.post(
        f"/api/v1/admin/sites/{site['site_id']}/members",
        headers=ADMIN,
        json={"telegram_id": "555", "role": "owner"},
    )

    client.post(
        "/api/v1/edge/events/batch", headers=headers, json={"events": _events(3, prefix="a")}
    )
    client.post(
        "/api/v1/edge/events/batch", headers=headers, json={"events": _events(3, prefix="b")}
    )

    assert len(sent) == 1


# ── Tezlik cheklovi ──────────────────────────────────────────────────────


def test_event_ingestion_is_rate_limited_per_device(cloud, monkeypatch) -> None:
    """Chegara rostdan ishlaydi.

    Haqiqiy chegara (600) bilan sinash 600 ta HTTP so'rov demak — test
    o'n daqiqalab ishlardi.  Shuning uchun chegara vaqtincha kichraytiriladi;
    haqiqiy qiymatning yetarliligi quyidagi alohida testda tekshiriladi.
    """
    main, client, _sent = cloud
    _site_row, headers = _site(client, "Do'kon")
    monkeypatch.setattr(main, "EVENT_BATCH_HOURLY_LIMIT", 5)

    codes = [
        client.post(
            "/api/v1/edge/events/batch",
            headers=headers,
            json={"events": _events(1, prefix=f"r{index}")},
        ).status_code
        for index in range(8)
    ]

    assert codes == [200] * 5 + [429] * 3


def test_the_hourly_limit_leaves_room_for_a_real_shop(cloud) -> None:
    """Chegara pilotni buzmasin.

    Bu 1.2-tuzatishning sababi: chegara 120 edi, edge esa har 5 soniyada
    so'rov yubordi (soatiga 720) — ~10 daqiqada 429 va abadiy sikl.
    """
    main, _client, _sent = cloud

    # `cloud_sync.batch_size` standarti 50 ta hodisa.
    assert main.EVENT_BATCH_HOURLY_LIMIT * 50 >= 25_000
    # Edge eng tez rejimda ham (5 soniyada bir) soatiga 720 so'rov qiladi;
    # chegara bundan past bo'lsa navbat to'lgan paytda 429 muqarrar.
    assert main.EVENT_BATCH_HOURLY_LIMIT >= 720 * 0.8


# ── Config polling ───────────────────────────────────────────────────────


def test_heartbeat_tells_the_device_whether_config_changed(cloud) -> None:
    main, client, _sent = cloud
    site, headers = _site(client, "Do'kon")

    first = client.post(
        "/api/v1/sotqin/heartbeat", headers=headers, json={"config_revision": 0}
    ).json()
    assert first["config_revision"] == 0
    assert first["config_changed"] is False

    # Owner sozlamani o'zgartirsa revision oshadi va qurilma buni biladi.
    main.get_event_store().update_site_config(site["site_id"], {"occupancy_limit": 30})
    second = client.post(
        "/api/v1/sotqin/heartbeat", headers=headers, json={"config_revision": 0}
    ).json()
    assert second["config_revision"] == 1
    assert second["config_changed"] is True

    third = client.post(
        "/api/v1/sotqin/heartbeat", headers=headers, json={"config_revision": 1}
    ).json()
    assert third["config_changed"] is False


# ── Arxiv muddati ────────────────────────────────────────────────────────


def test_purge_uses_each_plan_retention_not_a_fixed_30_days(cloud) -> None:
    main, client, _sent = cloud
    lite, lite_headers = _site(client, "Lite do'kon", plan="lite")  # 30 kun
    big, big_headers = _site(client, "Zavod", plan="enterprise")  # 365 kun

    client.post(
        "/api/v1/edge/events/batch",
        headers=lite_headers,
        json={"events": _events(2, days_ago=100, prefix="l")},
    )
    client.post(
        "/api/v1/edge/events/batch",
        headers=big_headers,
        json={"events": _events(2, days_ago=100, prefix="e")},
    )

    store = main.get_event_store()
    assert len(store.list_events(lite["site_id"], limit=50)) == 2

    main._purge_expired_events()

    assert store.list_events(lite["site_id"], limit=50) == []
    # 365 kunlik arxiv uchun to'lagan mijoz 100 kunlik hodisani ko'rib turishi kerak.
    assert len(store.list_events(big["site_id"], limit=50)) == 2


def test_clips_expire_sooner_than_the_archive_the_customer_paid_for(cloud) -> None:
    """Disk sig'imini kliplar belgilaydi — lekin hodisa arxivi tegilmasin.

    Bitta klip 50 MB gacha, snapshot esa ~100 KB: 30 kunlik klip saqlash
    bitta VPS'ni ~10-13 do'konga tushirardi.  Kliplarni 7 kunda o'chirsak
    ~50-80 do'kon sig'adi.  Ammo `retention_days` (30/90/365) mijozga
    SOTILGAN arxiv — statistika va rasm o'z muddatida qolishi shart.
    """
    main, client, _sent = cloud
    site, headers = _site(client, "Klipli do'kon", plan="enterprise")  # arxiv 365 kun

    client.post(
        "/api/v1/edge/events/batch",
        headers=headers,
        json={"events": _events(1, days_ago=20, prefix="c")},
    )
    store = main.get_event_store()
    event_id = store.list_events(site["site_id"], limit=5)[0]["event_id"]
    store.set_clip(site["site_id"], event_id, f"{site['site_id']}/{event_id}.mp4", size_bytes=1024)
    assert store.event(site["site_id"], event_id)["has_clip"] == 1

    main._purge_expired_events()

    event = store.event(site["site_id"], event_id)
    assert event is not None, "hodisaning o'zi 365 kunlik arxivda qolishi kerak"
    assert event["has_clip"] == 0, "20 kunlik klip o'chirilishi kerak edi"
    assert event["clip_key"] is None


def test_media_retention_is_configurable(cloud, monkeypatch) -> None:
    """Muddatni env bilan uzaytirib bo'lsin — aks holda orqaga qaytish yo'li yo'q."""
    main, client, _sent = cloud
    monkeypatch.setenv("CHAQIMCHI_MEDIA_RETENTION_HOURS", str(60 * 24))
    site, headers = _site(client, "Uzoq klip", plan="enterprise")

    client.post(
        "/api/v1/edge/events/batch",
        headers=headers,
        json={"events": _events(1, days_ago=20, prefix="k")},
    )
    store = main.get_event_store()
    event_id = store.list_events(site["site_id"], limit=5)[0]["event_id"]
    store.set_clip(site["site_id"], event_id, f"{site['site_id']}/{event_id}.mp4", size_bytes=1024)

    main._purge_expired_events()

    assert store.event(site["site_id"], event_id)["has_clip"] == 1


def test_media_dies_in_48_hours_but_the_event_stays(cloud) -> None:
    """Ega qarori (2026-08-30): bulutda rasm 48 soat, keyin faqat raqam.

    Hodisa qatorining O'ZI qolishi SHART — narx sahifasida «aniqlangan
    hodisalar va kunlik raqamlar 30 kun saqlanadi» deb sotilgan.  Media
    bilan birga hodisani ham o'chirish mijoz to'lagan narsani olib
    qo'yish bo'lardi.
    """
    main, client, _sent = cloud
    site, headers = _site(client, "Ikki kunlik media", plan="biznes")

    client.post(
        "/api/v1/edge/events/batch",
        headers=headers,
        json={"events": _events(1, days_ago=3, prefix="m")},
    )
    store = main.get_event_store()
    event_id = store.list_events(site["site_id"], limit=5)[0]["event_id"]
    store.set_clip(site["site_id"], event_id, f"{site['site_id']}/{event_id}.mp4", size_bytes=1024)

    main._purge_expired_events()

    event = store.event(site["site_id"], event_id)
    assert event is not None, "hodisa 30 kunlik arxivda qolishi kerak"
    assert event["has_clip"] == 0, "48 soatdan eski klip o'chsin"
    assert event["clip_key"] is None
    assert event["has_snapshot"] == 0, "48 soatdan eski rasm ham o'chsin"


def test_monthly_receipt_is_silent_without_the_owners_revenue(cloud) -> None:
    """Savdo aytilmagan bo'lsa yo'qotishni hisoblab bo'lmaydi — xabar ketmasin."""
    import asyncio
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo

    main, client, sent = cloud
    site, headers = _site(client, "Cheksiz do'kon", plan="biznes")
    client.post(
        "/api/v1/edge/events/batch",
        headers=headers,
        json={"events": _events(1, days_ago=5, prefix="q")},
    )
    from cloud.digest import DailyDigestService

    digest = DailyDigestService(
        main.get_event_store(), main.get_store().list_sites, lambda *a, **k: None
    )
    first_of_month = _dt(2026, 9, 1, 11, 0, tzinfo=ZoneInfo("Asia/Tashkent"))
    assert asyncio.run(digest._monthly_value_once(first_of_month)) == 0


def test_monthly_receipt_uses_the_owners_own_numbers(cloud) -> None:
    """Savdo aytilgan va uzun navbat bo'lgan do'kon chekni oladi."""
    import asyncio
    from datetime import datetime as _dt
    from datetime import timedelta, timezone
    from zoneinfo import ZoneInfo

    from cloud.digest import DailyDigestService

    main, client, _sent = cloud
    site, headers = _site(client, "Navbatli do'kon", plan="biznes")
    site_id = site["site_id"]
    # Raqamlar HAQIQIY nisbatda bo'lishi kerak: oyiga 100 tashrif va
    # kuniga 4.5 mln savdo — bu "har tashrif 1.4 mln" degani va
    # `value.py` uni ataylab rad etadi (sanoq buzuq deb).
    # Kichik do'kon: kuniga 200 000 so'm, oyiga 100 tashrif.
    main.get_store().set_avg_daily_revenue(site_id, 200_000)

    # O'tgan oyda tashriflar va uchta uzun navbat epizodi.
    august = _dt(2026, 8, 15, 12, 0, tzinfo=timezone.utc)
    events = [
        {
            "event_id": f"in-{i}",
            "event_type": "line_crossed",
            "severity": "info",
            "camera_id": "camera-01",
            "occurred_at": (august + timedelta(minutes=i)).isoformat(),
            "direction": "in",
            "edge_version": "0.6.12",
        }
        for i in range(100)
    ] + [
        {
            "event_id": f"q-{i}",
            "event_type": "queue_threshold_exceeded",
            "severity": "warning",
            "camera_id": "camera-01",
            "occurred_at": (august + timedelta(hours=i)).isoformat(),
            "queue_length": 7,
            "edge_version": "0.6.12",
        }
        for i in range(3)
    ]
    client.post("/api/v1/edge/events/batch", headers=headers, json={"events": events})

    messages = []

    async def capture(chat_id, text, **kwargs):
        messages.append(text)

    client.post(
        f"/api/v1/admin/sites/{site_id}/members",
        headers=ADMIN,
        json={"telegram_id": "777", "role": "owner", "display_name": "Egasi"},
    )
    digest = DailyDigestService(main.get_event_store(), main.get_store().list_sites, capture)
    sent = asyncio.run(
        digest._monthly_value_once(_dt(2026, 9, 1, 11, 0, tzinfo=ZoneInfo("Asia/Tashkent")))
    )
    assert sent == 1
    assert "hisob-kitobi" in messages[0]
    assert "taxminiy" in messages[0], "taxmin ekani har doim aytilishi kerak"
