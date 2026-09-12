"""`releases/` papkasining avtomatik tozalanishi.

Papka hech qachon tozalanmasdi: har nashr ~100 MB `.exe` qoldirardi va
serverda 19 ta eski reliz bilan 1,9 GB ga o'sdi.  Diskning to'lishi bu
yerda faqat "joy tugadi" degani emas — Postgres va MinIO o'sha diskda.

Bu yerdagi eng muhim test bitta: **qurilma hali so'rayotgan versiya
o'chmasin.**  O'chsa yangilanish zanjiri uziladi (qurilma o'z joriy
versiyasini rollback nishoni qilib serverdan yuklab oladi) va buni
masofadan tuzatib bo'lmaydi — tuzatma yetib boradigan kanalning o'zi
shu zanjir.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import cloud.main as main
from cloud.event_store import EventStore
from cloud.store import CloudStore

DATABASE_URL = os.environ.get("ENES_TEST_DATABASE_URL", "").strip()
needs_postgres = pytest.mark.skipif(
    not DATABASE_URL, reason="ENES_TEST_DATABASE_URL qo'yilmagan"
)


def _pair(directory: Path, name: str, *, size: int = 32) -> tuple[Path, Path]:
    """Reliz juftligi: `.exe` va yonidagi manifest."""
    exe = directory / f"{name}.exe"
    exe.write_bytes(b"M" * size)
    manifest = directory / f"{name}.json"
    manifest.write_text("{}", encoding="utf-8")
    return exe, manifest


@pytest.fixture
def releases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Bo'sh reliz papkasi + bo'sh bazalar.

    Papka `_release_dirs()` orqali beriladi — production'da ikkita yo'l
    bor (`BASE_DIR/releases` va `/app/releases`) va ular konteynerda
    BITTA papka.
    """
    directory = tmp_path / "releases"
    directory.mkdir()
    monkeypatch.setattr(main, "_release_dirs", lambda: [directory])

    events = EventStore(sqlite_path=tmp_path / "events.db")
    control = CloudStore(tmp_path / "cloud.db")
    monkeypatch.setattr(main, "get_event_store", lambda: events)
    monkeypatch.setattr(main, "get_store", lambda: control)
    return directory


def _names(directory: Path) -> set[str]:
    return {path.name for path in directory.iterdir()}


# ── Eng muhimi: ishlatilayotgan versiya o'chmaydi ────────────────────────


def test_a_version_a_device_still_reports_is_never_deleted(
    releases: Path, tmp_path: Path
) -> None:
    """Pilot 0.6.25 da turgan bo'lsa, o'sha fayl saqlanadi.

    Qurilma yangilanishdan oldin O'Z joriy versiyasining o'rnatuvchisini
    reliz serveridan rollback nishoni qilib yuklab oladi
    (`enes/local/updater.py: _ensure_rollback_target`).  Fayl o'chirilgan
    bo'lsa buzuq reliz chiqqanda do'kon qo'lda tiklanishni kutib qoladi.
    """
    for version in ("0.6.25", "0.6.30", "0.6.31", "0.6.32", "0.6.33"):
        _pair(releases, f"enes-windows-{version}")

    main.get_event_store().record_health(
        "site-1", "device-1", {"app_version": "0.6.25", "cameras_active": 2}
    )

    report = main.prune_windows_releases(keep=3)

    assert "enes-windows-0.6.25.exe" in _names(releases), (
        "qurilma hali shu versiyada — fayl qolishi shart"
    )
    assert "enes-windows-0.6.25.json" in _names(releases)
    # Oxirgi uchtasi + himoyalangani = to'rt juftlik.
    assert "enes-windows-0.6.30.exe" not in _names(releases)
    assert report["deleted"] == [
        "enes-windows-0.6.30.exe",
        "enes-windows-0.6.30.json",
    ]


def test_the_control_database_copy_of_the_version_also_protects(
    releases: Path,
) -> None:
    """Versiya ikki BOSHQA bazada yozilgan va ikkalasi ham o'qiladi.

    Heartbeat uni hodisa bazasiga (`device_health`) ham, boshqaruv
    bazasiga (`devices.app_version`) ham yozadi.  Bittasi ko'chirish
    oynasida bo'shab turgan bo'lsa ikkinchisi himoyani ushlab turadi —
    bo'sh ro'yxat bu yerda "hech kim ishlatmayapti" degani emas.
    """
    for version in ("0.6.20", "0.6.30", "0.6.31", "0.6.32"):
        _pair(releases, f"enes-windows-{version}")

    store = main.get_store()
    site = store.create_site("Sinov", "starter", subscription_months=1)
    device = store.claim_device(site["pairing_code"], label="pc1")
    store.record_device_version(device["device_id"], "0.6.20")

    main.prune_windows_releases(keep=3)

    assert "enes-windows-0.6.20.exe" in _names(releases)


def test_a_pinned_version_is_never_deleted(releases: Path) -> None:
    """`pin` kanalidagi obyektning versiyasi ham "hali so'ralayotgan".

    Fayli o'chsa `/api/v1/edge/update` o'sha do'konga "qotirilgan versiya
    topilmadi" deb javob beradi va do'kon yangilanishdan ABADIY tushib
    qoladi — panelda bu ogohlantirish bo'lib chiqmaydi.
    """
    for version in ("0.6.20", "0.6.30", "0.6.31", "0.6.32"):
        _pair(releases, f"enes-windows-{version}")

    site = main.get_store().create_site("Sinov", "starter", subscription_months=1)
    main.get_store().set_update_policy(site["site_id"], channel="pin", version="0.6.20")

    main.prune_windows_releases(keep=3)

    assert "enes-windows-0.6.20.exe" in _names(releases)


def test_nothing_is_deleted_when_the_device_versions_cannot_be_read(
    releases: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Baza o'qilmasa tozalash BEKOR qilinadi.

    Ortiqcha fayl faqat joy yeydi; kerakli faylning o'chishi esa
    do'konni masofadan tuzatib bo'lmaydigan holga soladi.  Ya'ni
    shubhada tanlov har doim "o'chirmaslik" tomonda.
    """
    for version in ("0.6.20", "0.6.30", "0.6.31", "0.6.32"):
        _pair(releases, f"enes-windows-{version}")

    class _Sinmoq:
        def reported_app_versions(self):
            raise RuntimeError("baza yo'q")

    monkeypatch.setattr(main, "get_event_store", _Sinmoq)
    report = main.prune_windows_releases(keep=1)

    assert report["skipped"] is True
    assert len(_names(releases)) == 8, "hech narsa o'chmasin"


# ── Juftlik hisobi ──────────────────────────────────────────────────────


def test_each_prefix_keeps_its_own_newest_pairs(releases: Path) -> None:
    """Eski prefiks ataylab qoldirilgan ko'prik (`tests/test_brand.py`).

    Ikkala nom bir ro'yxatda sanalsa o'tish davrida eski nomdagi
    relizlar yangilari tomonidan siqib chiqarilardi — daladagi 0.6.25
    qurilmasi esa aynan eski nomni so'raydi.
    """
    for version in ("0.6.23", "0.6.24", "0.6.25", "0.6.26"):
        _pair(releases, f"chaqimchi-windows-{version}")
    for version in ("0.6.30", "0.6.31", "0.6.32", "0.6.33"):
        _pair(releases, f"enes-windows-{version}")

    main.prune_windows_releases(keep=2)

    assert _names(releases) == {
        "chaqimchi-windows-0.6.25.exe",
        "chaqimchi-windows-0.6.25.json",
        "chaqimchi-windows-0.6.26.exe",
        "chaqimchi-windows-0.6.26.json",
        "enes-windows-0.6.32.exe",
        "enes-windows-0.6.32.json",
        "enes-windows-0.6.33.exe",
        "enes-windows-0.6.33.json",
    }


def test_the_newest_release_survives_even_with_keep_zero(releases: Path) -> None:
    """`keep=0` bilan chaqirilsa JONLI reliz o'chib ketardi va hech bir
    qurilma boshqa yangilanmasdi.  Chegara kamida bitta juftlik."""
    _pair(releases, "enes-windows-0.6.33")

    main.prune_windows_releases(keep=0)

    assert "enes-windows-0.6.33.exe" in _names(releases)


def test_two_digit_minor_is_not_compared_as_text(releases: Path) -> None:
    """`"0.10" < "0.9"` matn taqqoslashida — ya'ni eng yangi reliz
    "eski" deb o'chib ketardi (`_version_key` bilan bir sabab)."""
    for version in ("0.9.0", "0.10.0", "0.11.0"):
        _pair(releases, f"enes-windows-{version}")

    main.prune_windows_releases(keep=2)

    assert _names(releases) == {
        "enes-windows-0.10.0.exe",
        "enes-windows-0.10.0.json",
        "enes-windows-0.11.0.exe",
        "enes-windows-0.11.0.json",
    }


# ── "Tanimadim" holati ──────────────────────────────────────────────────


def test_an_exe_without_a_manifest_is_cleaned_up(releases: Path) -> None:
    """Yolg'iz `.exe` na relizga, na tozalashga ko'rinmasdi.

    `latest_windows_release()` uni ataylab e'tiborsiz qoldiradi (imzosiz
    paketni qurilma rad etadi), ya'ni fayl papkada ABADIY qolar edi —
    `prune()` faqat o'zi taniydigan nomni o'chirish tuzog'ining aynan
    o'zi.
    """
    (releases / "enes-windows-0.6.28.exe").write_bytes(b"MZ")
    (releases / "enes-windows-0.6.29.json").write_text("{}", encoding="utf-8")
    _pair(releases, "enes-windows-0.6.33")

    report = main.prune_windows_releases(keep=3)

    assert _names(releases) == {"enes-windows-0.6.33.exe", "enes-windows-0.6.33.json"}
    assert "enes-windows-0.6.28.exe" in report["deleted"], "juftsiz `.exe`"
    assert "enes-windows-0.6.29.json" in report["deleted"], "yetim manifest"


def test_a_file_with_an_unknown_name_is_cleaned_up_too(releases: Path) -> None:
    """Nomda kelishmovchilik faylni ko'rinmas qilib qo'yardi.

    Yozuvchi bilan o'quvchi nomda ajralib qolsa fayl na retentionga, na
    kvotaga ko'rinmaydi va papka disk to'lguncha o'sadi.  Shu sabab
    tozalash ro'yxatida "tanimadim" holati ham bor.
    """
    (releases / "ENES_Setup-0.6.31.exe").write_bytes(b"MZ")
    _pair(releases, "enes-windows-0.6.33")

    main.prune_windows_releases(keep=3)

    assert "ENES_Setup-0.6.31.exe" not in _names(releases)


def test_the_versionless_installer_and_the_box_line_are_left_alone(
    releases: Path,
) -> None:
    """Papkada bizning ishimiz bo'lmagan fayllar ham turadi.

    `ENES_Setup.exe` — relizlar topilmaganda saytga beriladigan zaxira
    (`_windows_installer_file`), `enes-sotqin-*` va `enes-lite-*` esa
    Box/R1 yo'lining arxiv va manifestlari.  "Tanimadim" qoidasiga
    qo'shib o'chirilsa yuklab olish 503, Box yangilanishi esa 404
    berardi.
    """
    (releases / "ENES_Setup.exe").write_bytes(b"MZ")
    (releases / "Chaqimchi_AI_Setup.exe").write_bytes(b"MZ")
    (releases / "enes-sotqin-0.6.0.tar.gz").write_bytes(b"gz")
    (releases / "enes-sotqin-0.6.0.json").write_text("{}", encoding="utf-8")
    _pair(releases, "enes-windows-0.6.33")

    main.prune_windows_releases(keep=1)

    assert _names(releases) == {
        "ENES_Setup.exe",
        "Chaqimchi_AI_Setup.exe",
        "enes-sotqin-0.6.0.tar.gz",
        "enes-sotqin-0.6.0.json",
        "enes-windows-0.6.33.exe",
        "enes-windows-0.6.33.json",
    }


# ── Rejani ko'rsatish (host tomonda o'chirish uchun) ────────────────────


def test_the_plan_mode_deletes_nothing(releases: Path) -> None:
    """Production'da papka konteynerga `:ro` bilan ulangan, ya'ni qaror
    konteynerda, o'chirish esa hostda bajariladi
    (`scripts/publish_windows_release.sh`)."""
    for version in ("0.6.30", "0.6.33"):
        _pair(releases, f"enes-windows-{version}")

    report = main.prune_windows_releases(keep=1, dry_run=True)

    assert report["planned"] == [
        "enes-windows-0.6.30.exe",
        "enes-windows-0.6.30.json",
    ]
    assert report["deleted"] == []
    assert "enes-windows-0.6.30.exe" in _names(releases)


def test_the_freed_space_is_reported(releases: Path) -> None:
    """Hisobot jurnalga tushadi: "tozalandi" degani "joy bo'shadi"
    degani emas — juftlikning faqat manifesti o'chishi mumkin."""
    _pair(releases, "enes-windows-0.6.30", size=3 * 1024 * 1024)
    _pair(releases, "enes-windows-0.6.33", size=3 * 1024 * 1024)

    report = main.prune_windows_releases(keep=1)

    assert report["freed_bytes"] > 3 * 1024 * 1024


def test_the_release_the_cloud_offers_is_still_the_newest_after_pruning(
    releases: Path,
) -> None:
    """Tozalashdan keyin qurilma so'raydigan javob buzilmasin."""
    for version in ("0.6.28", "0.6.30", "0.6.33"):
        _pair(releases, f"enes-windows-{version}")

    main.prune_windows_releases(keep=1)
    release = main.latest_windows_release()

    assert release is not None and release["version"] == "0.6.33"


# ── Chaqiruv joylari ────────────────────────────────────────────────────


def test_the_background_loop_prunes_behind_the_leader_gate() -> None:
    """Fon vazifasi FAQAT yetakchida ishlashi kerak.

    `_maintenance_loop` har worker'da ochiladi.  Tozalash yetakchi
    darvozasidan o'tmasa ikki worker bir vaqtda o'chirishga urinadi va
    ikkinchisi `FileNotFoundError` ni xato deb jurnalga yozadi.
    """
    source = Path(main.__file__).read_text(encoding="utf-8")
    loop = source[source.index("async def _maintenance_loop") : source.index("async def _lead_notification_loop")]

    assert "if not _is_leader():" in loop, "yetakchi darvozasi yo'q"
    gate = loop.index("if not _is_leader():")
    assert "prune_windows_releases" in loop[gate:], "tozalash darvozadan KEYIN chaqirilsin"


def test_the_daily_step_really_is_daily() -> None:
    """Kuniga bir marta: halqa qadami 30 daqiqa, ya'ni 48 qadam."""
    assert main._MAINTENANCE_STEP_SEC * main._PRUNE_RELEASES_EVERY_STEPS == 24 * 3600


def test_the_first_prune_is_not_at_startup() -> None:
    """Ilova ko'tarilgan zahoti o'chirmaydi.

    Startup paytida "qaysi versiya hali kerak" ro'yxati bo'sh bo'lishi
    mumkin (yangi yoki ko'chirilgan baza — qurilmalar hali heartbeat
    yubormagan) va tozalash aynan shu ro'yxatga tayanadi.  Qurilma har
    daqiqada aloqa qiladi, ya'ni birinchi tozalashgacha 30 daqiqa
    kutiladi.
    """
    assert main._PRUNE_RELEASES_AT_STEP > 0
    assert main._PRUNE_RELEASES_AT_STEP < main._PRUNE_RELEASES_EVERY_STEPS


@needs_postgres
def test_the_reported_versions_query_works_on_postgres() -> None:
    """Himoya qaysi versiya o'chmasligini shu so'rovdan biladi.

    `cloud/event_store.py` ikki dialektli va bu qismi jimgina buziladi:
    xato faqat PostgreSQL'da, ya'ni faqat productionda ko'rinadi.
    Ishga tushirish:

        createdb enes_test
        ENES_TEST_DATABASE_URL=postgresql://$USER@localhost:5432/enes_test \\
            python -m pytest tests/test_release_prune.py
    """
    import psycopg

    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
    store = EventStore(database_url=DATABASE_URL)
    store.record_health("site-1", "device-1", {"app_version": "0.6.25"})
    # `unknown` — `EdgeHeartbeatBody` standarti: versiya aytilmagan.
    store.record_health("site-1", "device-2", {"app_version": "unknown"})

    assert store.reported_app_versions() == ["0.6.25"]


def test_the_publish_script_prunes_after_shipping() -> None:
    """Nashrdan KEYIN: yangi juftlik joyida turganda "eng yangi uchta"
    hisobi to'g'ri chiqadi.  Tozalash yiqilsa nashr buzilmasin —
    reliz allaqachon jonli."""
    script = (Path(main.__file__).resolve().parents[1] / "scripts" / "publish_windows_release.sh").read_text(
        encoding="utf-8"
    )

    assert "prune_releases.py --reja" in script
    assert script.index("curl -fsS \"$dl_url/releases/") < script.index("prune_remote"), (
        "tozalash tashqi tekshiruvdan keyin bo'lsin"
    )
    assert "if ! prune_remote; then" in script, "tozalash nashrni yiqitmasin"
