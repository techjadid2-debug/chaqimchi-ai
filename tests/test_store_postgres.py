"""`cloud/store.py` ning PostgreSQL yo'li.

Production `--workers 1` da ishlab kelgan edi va sababi shu fayl:
SQLite bitta faylga ko'p jarayondan yozishga yaramaydi.

Bu yerdagi testlarning ko'pi bazasiz yuradi — ular SQL tarjimasini
tekshiradi va aynan shu qism jimgina buziladi: xato faqat PostgreSQL'da
ko'rinadi, ya'ni faqat productionda.  Haqiqiy bazaga tegadigan testlar
`ENES_TEST_DATABASE_URL` qo'yilganda ishlaydi:

    createdb enes_test
    ENES_TEST_DATABASE_URL=postgresql://$USER@localhost:5432/enes_test \
        python -m pytest tests/test_store_postgres.py
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from cloud.store import CloudStore, _split_statements, _to_postgres

DATABASE_URL = os.environ.get("ENES_TEST_DATABASE_URL", "").strip()
needs_postgres = pytest.mark.skipif(
    not DATABASE_URL, reason="ENES_TEST_DATABASE_URL qo'yilmagan"
)


# ── SQL tarjimasi (bazasiz) ──────────────────────────────────────────────


def test_placeholders_become_postgres_style() -> None:
    assert _to_postgres("SELECT * FROM sites WHERE id=?") == "SELECT * FROM sites WHERE id=%s"


def test_a_literal_percent_survives_the_translation() -> None:
    """`LIKE 'ENES Windows%'` — haqiqiy so'rov va u tarjimani buzardi.

    Foiz `%s` o'rin egasidan KEYIN himoyalansa, psycopg uni o'rin
    egasining bir qismi deb o'qib "yetishmayapti" derdi.  Xato faqat
    PostgreSQL'da ko'rinardi.
    """
    translated = _to_postgres("SELECT ? WHERE product_name LIKE 'ENES Windows%'")

    assert translated == "SELECT %s WHERE product_name LIKE 'ENES Windows%%'"


def test_sqlite_only_insert_becomes_on_conflict() -> None:
    """`INSERT OR IGNORE` SQLite sintaksisi; ma'no oxirida beriladi."""
    translated = _to_postgres("INSERT OR IGNORE INTO t(a) VALUES (?)")

    assert translated == "INSERT INTO t(a) VALUES (%s) ON CONFLICT DO NOTHING"


def test_autoincrement_becomes_a_sequence() -> None:
    assert "BIGSERIAL PRIMARY KEY" in _to_postgres("id INTEGER PRIMARY KEY AUTOINCREMENT")


# ── Skriptni bo'laklash ──────────────────────────────────────────────────


def test_a_semicolon_inside_a_comment_does_not_split_the_script() -> None:
    """Haqiqiy baza aynan shu yerda yiqilgan.

    `_init_db` dagi izohlardan birida nuqta-vergul bor
    (`... yoziladi; haqiqiy qurilma ...`) va oddiy `split(";")` izoh
    matnini "so'rov" qilib yuborardi: «syntax error at or near
    "haqiqiy"».
    """
    script = """
        CREATE TABLE a (id TEXT);
        -- Izoh: bu yerda ; bor va u bo'linish nuqtasi EMAS
        CREATE TABLE b (id TEXT);
    """

    statements = _split_statements(script)

    assert len(statements) == 2
    assert statements[0].startswith("CREATE TABLE a")
    assert statements[1].startswith("CREATE TABLE b")


def test_a_semicolon_inside_a_string_does_not_split_the_script() -> None:
    statements = _split_statements("INSERT INTO t(a) VALUES ('bir; ikki'); SELECT 1;")

    assert len(statements) == 2
    assert "bir; ikki" in statements[0]


def test_an_escaped_quote_keeps_the_string_open() -> None:
    """SQL'da qo'shtirnoq `''` bilan qochiriladi — satr davom etadi."""
    statements = _split_statements("SELECT 'o''zbek; tili'; SELECT 2;")

    assert len(statements) == 2
    assert statements[0] == "SELECT 'o''zbek; tili'"


# ── Haqiqiy PostgreSQL ───────────────────────────────────────────────────


@pytest.fixture
def pg_store(tmp_path: Path):
    import psycopg

    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
    return CloudStore(tmp_path / "unused.db", database_url=DATABASE_URL)


@needs_postgres
def test_the_schema_is_created_on_postgres(pg_store) -> None:
    site = pg_store.create_site("PG do'kon", plan="lite")

    assert pg_store.get_site(site["site_id"])["name"] == "PG do'kon"
    # Katalog urug'i `INSERT OR IGNORE` bilan yoziladi.
    assert pg_store.list_feature_catalog()["features"]


@needs_postgres
def test_seeding_twice_does_not_duplicate_the_catalogue(pg_store, tmp_path: Path) -> None:
    """`INSERT OR IGNORE` → `ON CONFLICT DO NOTHING` ishlashi shart:
    aks holda har restart katalogni takrorlardi."""
    first = len(pg_store.list_feature_catalog()["features"])

    again = CloudStore(tmp_path / "unused.db", database_url=DATABASE_URL)

    assert len(again.list_feature_catalog()["features"]) == first


@needs_postgres
def test_a_taken_login_is_reported_not_crashed(pg_store) -> None:
    """psycopg `UniqueViolation` beradi, `sqlite3.IntegrityError` emas —
    tutilmasa mijoz "Bu login band" o'rniga 500 ko'rardi."""
    site = pg_store.create_site("PG do'kon", plan="lite")
    pg_store.create_account(
        username="birinchi", password="parol12345", role="customer",
        full_name="Birinchi Odam", site_id=site["site_id"],
    )

    with pytest.raises(ValueError, match="band"):
        pg_store.create_account(
            username="birinchi", password="parol12345", role="customer",
            full_name="Ikkinchi Odam", site_id=site["site_id"],
        )


@needs_postgres
def test_the_latest_job_is_the_last_one_written(pg_store) -> None:
    """`created_at` bir soniya aniqligida: bir soniyada ikki topshiriq
    yozilsa tartib `seq` bilan hal bo'ladi.  SQLite `rowid` iga
    tayanib bo'lmaydi — PostgreSQL'da u YO'Q."""
    site = pg_store.create_site("PG do'kon", plan="lite")
    sid = site["site_id"]
    pg_store.create_job(sid, kind="benchmark", params={"n": 1}, requested_by="t")
    second = pg_store.create_job(sid, kind="benchmark", params={"n": 2}, requested_by="t")

    latest = pg_store.latest_job_of_kind(sid, "benchmark")

    assert latest["job_id"] == second["job_id"]


# ── Pul jadvallari ───────────────────────────────────────────────────────
#
# Bu qism eng ehtiyot bo'linadigani: `payments/store.py` ilgari O'Z
# `sqlite3.connect` iga ega edi.  Cloud PostgreSQL'ga o'tganda u
# jimgina eski SQLite fayliga yozib turaverardi — obuna bir bazada,
# hisob-faktura boshqasida, ya'ni to'lov obunani UZAYTIRMAY qolardi.


@needs_postgres
def test_the_payment_store_follows_the_cloud_database(pg_store) -> None:
    from cloud.payments.store import PaymentStore

    payments = PaymentStore(pg_store)
    site = pg_store.create_site("PG do'kon", plan="lite")
    invoice = payments.create_invoice(site["site_id"], 1)

    assert invoice["state"] == "pending"
    # Hisob-faktura CLOUD bazasidagi saytga bog'landi — ya'ni ikkalasi
    # bitta bazada.
    assert invoice["site_name"] == "PG do'kon"


@needs_postgres
def test_paying_extends_the_subscription_exactly_once(pg_store) -> None:
    """Takroriy `mark_paid` obunani ikki marta surmasin.

    Darvoza — `UPDATE ... WHERE state='pending'` ning `rowcount` i.
    Payme va Click bir vaqtda javob qaytarsa (yoki provayder qayta
    urinsa) ikkalasi ham `pending` ni o'qiydi.
    """
    from cloud.payments.store import PaymentStore

    payments = PaymentStore(pg_store)
    site = pg_store.create_site("PG do'kon", plan="lite")
    sid = site["site_id"]
    invoice = payments.create_invoice(sid, 1)
    before = pg_store.get_site(sid)["subscription_until"]

    payments.mark_paid(invoice["id"], "naqd")
    after = pg_store.get_site(sid)["subscription_until"]
    payments.mark_paid(invoice["id"], "naqd")

    assert after > before, "to'lov obunani uzaytirsin"
    assert pg_store.get_site(sid)["subscription_until"] == after, "ikkinchi marta surmasin"


@needs_postgres
def test_click_gets_an_integer_prepare_id(pg_store) -> None:
    """Click `merchant_prepare_id` ni BUTUN SON deb talab qiladi.

    SQLite'da uni `AUTOINCREMENT` berardi; PostgreSQL'da o'rnini
    `BIGSERIAL` bosadi.  Tarjima ishlamasa bu yerda matn qaytardi va
    Click callback'i rad etilardi.
    """
    from cloud.payments.store import PaymentStore

    payments = PaymentStore(pg_store)
    site = pg_store.create_site("PG do'kon", plan="lite")
    invoice = payments.create_invoice(site["site_id"], 1)

    prepared = payments.click_prepare("clk-1", invoice["id"], invoice["amount_uzs"])

    assert isinstance(prepared["merchant_prepare_id"], int)


# ── `rowid` qaytib kelmasin ──────────────────────────────────────────────


@pytest.mark.parametrize("module", ("store.py", "payments/store.py", "event_store.py"))
def test_no_query_orders_by_rowid(module: str) -> None:
    """`rowid` PostgreSQL'da YO'Q.

    U ikki joyda ishlatilgan edi va ikkalasi ham "oxirgi yozuv" ni
    topish uchun (`latest_job_of_kind`, `list_invoices`).  PostgreSQL'da
    so'rov `UndefinedColumn` bilan yiqilardi — ya'ni admin paneli va
    hisob-faktura ro'yxati ishlamay qolardi.  `ctid` o'rnini bosmaydi:
    u `UPDATE` dan keyin o'zgaradi.  O'rniga `seq` ustuni.
    """
    source = (Path(__file__).resolve().parents[1] / "cloud" / module).read_text(encoding="utf-8")
    offenders = [
        line.strip()
        for line in source.splitlines()
        if "rowid" in line.lower() and "--" not in line and not line.strip().startswith("#")
    ]

    assert offenders == [], f"{module}: `rowid` PostgreSQL'da yo'q: " + "; ".join(offenders)


@needs_postgres
def test_invoices_are_listed_newest_first(pg_store) -> None:
    """Tartib `seq` bilan: `created_at` bir soniya aniqligida va bitta
    saytga bir soniyada ikki hisob ochilishi mumkin."""
    from cloud.payments.store import PaymentStore

    payments = PaymentStore(pg_store)
    site = pg_store.create_site("PG do'kon", plan="lite")
    first = payments.create_invoice(site["site_id"], 1)
    second = payments.create_invoice(site["site_id"], 2)

    listed = payments.list_invoices(site["site_id"])

    assert [item["id"] for item in listed] == [second["id"], first["id"]]


# ── Ko'chirish skripti ───────────────────────────────────────────────────


@needs_postgres
def test_the_migration_keeps_an_edited_catalogue(tmp_path: Path) -> None:
    """Eng jim yo'qotish: sxema yaratilganda katalog STANDART qiymatlar
    bilan urug'lanadi va manbadagi tahrirlangan narx `ON CONFLICT DO
    NOTHING` sabab o'tkazib yuborilardi.  Qatorlar soni esa baribir mos
    kelardi, ya'ni tekshiruv ham buni ko'rmasdi."""
    import subprocess
    import sys

    from cloud.payments.store import PaymentStore

    sqlite_path = tmp_path / "cloud.db"
    source = CloudStore(sqlite_path)
    PaymentStore(source)
    site = source.create_site("Ko'chadigan do'kon", plan="lite")
    source.create_account(
        username="kochgan", password="parol12345", role="customer",
        full_name="Ko'chgan Mijoz", site_id=site["site_id"],
    )
    connection = source._connect()
    connection.execute(
        "UPDATE feature_prices SET monthly_usd_cents=777 WHERE feature_code='person_count'"
    )
    connection.commit()
    connection.close()

    import psycopg

    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")

    result = subprocess.run(
        [sys.executable, "scripts/migrate_control_db.py",
         "--sqlite", str(sqlite_path), "--postgres", DATABASE_URL],
        capture_output=True, text=True, timeout=180,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert result.returncode == 0, result.stderr

    migrated = CloudStore(tmp_path / "unused.db", database_url=DATABASE_URL)
    quote = migrated.feature_quote([{"feature_code": "person_count", "camera_count": 1}])

    assert quote["features"][0]["monthly_usd_cents"] == 777, "tahrirlangan narx yo'qoldi"
    assert migrated.get_site(site["site_id"])["name"] == "Ko'chadigan do'kon"
    # Parol ham ko'chsin: hash ustuni bo'lgani uchun u "shunchaki matn",
    # lekin ko'chirish uni buzsa mijoz panelga kira olmasdi.
    assert migrated.authenticate_account("kochgan", "parol12345")
