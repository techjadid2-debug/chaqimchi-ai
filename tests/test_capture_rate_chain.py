"""Avtomatik konversiya: qurilmadan hisobotgacha.

Nega bu test bor.  Zanjirning qurilma tomoni 0.6.33 da YOZILGAN edi
(`enes/retail/service.py` `capture.enabled` ni o'qiydi va `people_seen`
yuboradi), lekin cloud bu bayroqni HECH QACHON yubormagan — ya'ni kod
abadiy yopiq turgan va hech kim buni sezmagan.

Bayroq ataylab SERVER tomonda: eski cloud `people_seen` turini
tanimaydi va butun batchni rad etadi, qurilma esa rad etilgan hodisani
`permanent=True` bilan o'ldiradi.  Ya'ni qurilma o'zi yoqsa hodisa
qaytarib bo'lmas yo'qolardi.

Zanjir to'rt bo'g'in: darvoza (`/edge/config`) → qabul (`REPORT_EVENT_TYPES`)
→ yig'ish (`traffic.seen`) → foiz (`capture`).  Har bo'g'in alohida
tekshiriladi, chunki bittasini unutish natijani JIMGINA nolga aylantiradi.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from cloud.event_store import REPORT_EVENT_TYPES, TIMELINE_HIDDEN_TYPES


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ENES_CLOUD_ADMIN_KEY", "test-admin")
    monkeypatch.setenv("ENES_OWNER_JWT_SECRET", "o" * 64)
    monkeypatch.setenv("ENES_PORTAL_JWT_SECRET", "p" * 64)
    monkeypatch.setattr("cloud.main.DB_PATH", tmp_path / "cloud.db")
    monkeypatch.setattr("cloud.main._store", None)
    monkeypatch.setattr("cloud.main._event_store", None)
    monkeypatch.setattr("cloud.main._event_store_key", None)
    from cloud.main import app

    return TestClient(app)


@pytest.fixture
def shop(client: TestClient) -> Dict[str, Any]:
    trial = client.post(
        "/api/v1/public/quick-trial",
        json={
            "phone": "+998 90 123 45 67",
            "full_name": "Ega Egayev",
            "company": "Namuna do'kon",
            "username": "dokonchi",
            "password": "parol12345",
            "consent": True,
        },
    ).json()
    claimed = client.post(
        "/api/v1/devices/claim",
        json={"pairing_code": trial["pairing_code"], "label": "KASSA-PC"},
    ).json()
    login = client.post(
        "/api/v1/auth/login", json={"username": "dokonchi", "password": "parol12345"}
    ).json()
    from cloud.main import get_store

    get_store().upsert_camera(
        trial["site_id"], "camera-01", label="Kirish", rtsp_url="rtsp://x/1", role="entrance"
    )
    get_store().upsert_camera(
        trial["site_id"], "camera-02", label="Zal", rtsp_url="rtsp://x/2", role="sales"
    )
    return {
        "site_id": trial["site_id"],
        "owner": {"Authorization": f"Bearer {login['access_token']}"},
        "device": {
            "X-Site-Id": claimed["site_id"],
            "X-Device-Id": claimed["device_id"],
            "X-Device-Token": claimed["device_token"],
        },
    }


# ── 1) Darvoza: qurilma bayroqni OLADI ────────────────────────────────


def test_the_device_is_told_to_count_the_denominator(
    client: TestClient, shop: Dict[str, Any]
) -> None:
    """Bayroqsiz qurilmadagi kod abadiy yopiq turardi."""
    config = client.get("/api/v1/edge/config", headers=shop["device"]).json()

    assert "capture" in config, "darvoza umuman yuborilmayapti"
    assert config["capture"]["enabled"] is True


def test_an_expired_subscription_switches_the_denominator_off(
    client: TestClient, shop: Dict[str, Any]
) -> None:
    """`person_count` sotilmagan yoki obuna tugagan do'konda o'lchov
    ham to'xtaydi — u sotiladigan funksiyaning bir qismi."""
    from cloud.main import get_store

    # Obunani orqaga surib "tugagan" holatga o'tkazamiz — `grace` (14
    # kun) ATAYLAB ishlaydi, shuning uchun undan ham oldinga.
    get_store().reduce_subscription(shop["site_id"], 24)
    config = client.get("/api/v1/edge/config", headers=shop["device"]).json()

    assert config["capture"]["enabled"] is False


# ── 2) Qabul: tur uchta ro'yxatda to'g'ri joyda ───────────────────────


def test_the_denominator_event_reaches_the_report_but_not_the_timeline() -> None:
    """Ikkisi BIRGA bo'lishi shart.

    `REPORT_EVENT_TYPES` — RUXSAT ro'yxati: tur unga yozilmasa hisobot
    maxrajni umuman ko'rmaydi.  `TIMELINE_HIDDEN_TYPES` — TAQIQ
    ro'yxati: yozilmasa lenta har 10 daqiqada bitta yozuv bilan
    axlatlanadi (kuniga ~150 qator) va haqiqiy hodisalar ko'rinmaydi.
    Biri yolg'iz qo'shilsa ikkinchi nuqson chiqadi.
    """
    assert "people_seen" in REPORT_EVENT_TYPES
    assert "people_seen" in TIMELINE_HIDDEN_TYPES


def test_no_snapshot_is_expected_for_a_counter() -> None:
    """Yig'ma son — ko'rinadigan voqea emas.  Rasm so'ralsa panel
    «rasm bor» deb ko'rsatib, mijoz bosganda 404 olardi."""
    from cloud.main import MEDIALESS_EVENTS

    assert "people_seen" in MEDIALESS_EVENTS


# ── 3) Yig'ish: faqat KIRISH kamerasi ─────────────────────────────────


def _send(client: TestClient, shop: Dict[str, Any], events: list) -> None:
    response = client.post(
        "/api/v1/edge/events/batch", headers=shop["device"], json={"events": events}
    )
    assert response.status_code == 200, response.text


def _event(index: int, kind: str, camera: str, **extra: Any) -> Dict[str, Any]:
    return {
        "event_id": f"e{index}",
        "event_type": kind,
        "camera_id": camera,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "severity": "info",
        **extra,
    }


def test_only_the_entrance_camera_feeds_the_denominator(
    client: TestClient, shop: Dict[str, Any]
) -> None:
    """Hamma kameraning «yaqinlashdi» sonini qo'shish maxrajni
    shishiradi va foiz SUN'IY pasayadi — nol emas, lekin YOLG'ON,
    ya'ni mahsulotning eng qattiq taqig'i."""
    _send(
        client,
        shop,
        [
            _event(1, "people_seen", "camera-01", metadata={"seen": 200}),
            # Savdo zali kamerasi ham odam ko'radi — maxrajga KIRMASIN.
            _event(2, "people_seen", "camera-02", metadata={"seen": 500}),
            *[_event(10 + n, "line_crossed", "camera-01", direction="in") for n in range(50)],
        ],
    )

    report = client.get("/api/v1/owner/report", headers=shop["owner"]).json()

    assert report["traffic"]["seen"]["total"] == 700, "yig'indi hamma kameradan"
    assert report["capture"]["passed"] == 200, "maxraj FAQAT kirish kamerasidan"
    assert report["capture"]["entered"] == 50
    assert report["capture"]["percent"] == 25


def test_a_day_without_the_signal_has_no_capture_key(
    client: TestClient, shop: Dict[str, Any]
) -> None:
    """Bo'shlik va nol BOSHQA javoblar.

    `0` — «hech kim yaqinlashmadi», kalit yo'qligi — «o'lchov yo'q»
    (eski kun, funksiya yoqilmagan, qurilma hali yubormagan).  Nol
    bilan to'ldirish yolg'on javob bo'lardi.
    """
    _send(client, shop, [_event(1, "line_crossed", "camera-01", direction="in")])

    report = client.get("/api/v1/owner/report", headers=shop["owner"]).json()

    assert "seen" not in report["traffic"]
    assert "capture" not in report


def test_a_broken_count_shows_numbers_without_a_percent(
    client: TestClient, shop: Dict[str, Any]
) -> None:
    """Kirgan «o'tgan»dan ko'p — sanoq buzuq (chiziq noto'g'ri yoki
    kamera eshik oldini ko'rmaydi).  «130%» butun hisobga ishonchni
    yo'q qiladi, shuning uchun foiz ko'rsatilmaydi."""
    _send(
        client,
        shop,
        [
            _event(1, "people_seen", "camera-01", metadata={"seen": 30}),
            *[_event(10 + n, "line_crossed", "camera-01", direction="in") for n in range(45)],
        ],
    )

    report = client.get("/api/v1/owner/report", headers=shop["owner"]).json()

    assert report["capture"]["percent"] is None
    assert report["capture"]["passed"] == 30 and report["capture"]["entered"] == 45


# ── 4) Deploydan keyin revision ko'tarilsin ───────────────────────────


def test_the_revision_bump_is_shared_by_the_endpoint_and_the_script() -> None:
    """Qurilma konfigni keshlaydi va faqat revision o'zgarganda qayta
    tortadi — bayroq qo'shilishi o'zi yetarli emas.

    Mantiq ilgari faqat endpoint ichida edi; skript uni takrorlasa
    ikkisi vaqt o'tib ajralib ketardi.
    """
    from cloud import main

    assert callable(main.bump_feature_revision)
    script = (Path(__file__).resolve().parents[1] / "scripts" / "bump_feature_revision.py").read_text(
        encoding="utf-8"
    )
    assert "bump_feature_revision" in script
    assert "--dry-run" in script, "xavfsiz ko'rish rejimi yo'q"


def test_the_bump_raises_the_revision(client: TestClient, shop: Dict[str, Any]) -> None:
    from cloud.main import bump_feature_revision, get_event_store

    before = int(get_event_store().get_site_config(shop["site_id"])["revision"])
    after = bump_feature_revision(shop["site_id"])

    assert int(after["revision"]) > before


# ── 5) Sayt va'da BERMAYDI ────────────────────────────────────────────


def test_the_site_does_not_sell_automatic_conversion_yet() -> None:
    """Pilotda kalibrlanmagan: `SEEN_LINE_BAND` (0,15) boshlang'ich
    taxmin va haqiqiy do'konda o'lchanmagan.  Panel va Telegramda
    ko'rsatiladi, SOTUV va'dasi sifatida emas
    (`docs/DOKON_MVP.md` bilan solishtirilgan)."""
    static = Path(__file__).resolve().parents[1] / "cloud" / "static"
    for name in ("site.html", "site.ru.html", "site.en.html"):
        page = (static / name).read_text(encoding="utf-8").lower()
        assert "avtomatik konversiya" not in page
        assert "автоматическая конверсия" not in page
        assert "automatic conversion" not in page


# ── 6) Kunlik xabar: faqat FOIZ chiqqanda ─────────────────────────────


def test_the_digest_shows_the_percent_line(client: TestClient, shop: Dict[str, Any]) -> None:
    from cloud import value

    line = value.capture_rate_line(entered=50, passed=200, lang="uz")

    assert line and "25%" in line


def test_the_digest_stays_silent_when_the_percent_is_missing() -> None:
    """Sokin kun xabari qisqa qolsin.

    Har qo'shilgan qator xabarni kamroq o'qiladigan qiladi
    (`test_a_calm_day_message_stays_short`), shuning uchun foiz
    chiqmagan holatda (kichik namuna yoki buzuq sanoq) ikki son
    yolg'iz qo'shilmaydi — `cloud/digest.py` shartini tekshiradi.
    """
    digest = (Path(__file__).resolve().parents[1] / "cloud" / "digest.py").read_text(
        encoding="utf-8"
    )
    block = digest[digest.index('capture = report.get("capture")'):]
    block = block[: block.index("# Demografiya")]

    assert 'capture.get("percent") is not None' in block, (
        "foizsiz holat ham xabarga qo'shilyapti"
    )


def test_the_panel_row_disappears_without_the_measurement() -> None:
    """Nol bilan to'ldirish «hech kim yaqinlashmadi» degan yolg'on
    javob bo'lardi."""
    numbers = (
        Path(__file__).resolve().parents[1] / "frontend" / "src" / "Numbers.tsx"
    ).read_text(encoding="utf-8")

    assert "dashboard.today.capture || null" in numbers
    assert "{capture ? <>" in numbers, "blok shartsiz chizilyapti"
    # Foizni panel HISOBLAMAYDI — qoida serverda bitta joyda.
    assert "capture.percent == null" in numbers
    assert "/ capture.passed" not in numbers, "panel foizni o'zi hisoblayapti"
