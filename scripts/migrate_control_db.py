#!/usr/bin/env python3
"""Boshqaruv bazasini SQLite'dan PostgreSQL'ga ko'chiradi.

Nega kerak: `cloud/store.py` da litsenziya, tarif, narx kitobi, portal
parollari, audit jurnali va hisob-fakturalar turadi.  SQLite bitta
faylga ko'p jarayondan yozishga yaramaydi, shuning uchun
`Dockerfile.cloud` da `--workers 1` — ya'ni butun cloud bitta CPU
yadrosi bilan cheklangan.

Skript **hech narsani o'chirmaydi**: manba SQLite fayli tegilmasdan
qoladi va nimadir noto'g'ri ketsa `ENES_CONTROL_DATABASE_URL` ni
olib tashlash yetadi — cloud eski bazaga qaytadi.

Ishlatish:

    python scripts/migrate_control_db.py \\
        --sqlite data/cloud/cloud.db \\
        --postgres "$ENES_CONTROL_DATABASE_URL"

    # Faqat sanab chiqish (yozmasdan):
    python scripts/migrate_control_db.py ... --dry-run
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloud.payments.store import PaymentStore  # noqa: E402
from cloud.store import CloudStore  # noqa: E402


def sqlite_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name"
    ).fetchall()
    return [str(row[0]) for row in rows]


def copy_table(source: sqlite3.Connection, target, table: str) -> int:
    """Bitta jadvalni ko'chiradi; ko'chirilgan qatorlar sonini qaytaradi.

    Ustunlar MANBADAN olinadi va aniq sanaladi.  `SELECT *` ikki
    sxema ustunlari bir xil tartibda bo'lishiga tayanardi va yangi
    ustun qo'shilishi bilan jimgina qulardi — bu tuzoq loyihada
    allaqachon bir marta yeyilgan (`device_jobs has 15 columns but
    16 values`).
    """
    rows = source.execute(f"SELECT * FROM {table}").fetchall()
    if not rows:
        return 0
    columns = [str(key) for key in rows[0].keys()]
    names = ",".join(columns)
    holders = ",".join("?" for _ in columns)
    # `ON CONFLICT DO NOTHING`: skriptni qayta yuritish xavfsiz bo'lsin —
    # yarim ko'chgan holatdan davom ettirish kerak bo'lishi mumkin.
    target.executemany(
        f"INSERT INTO {table} ({names}) VALUES ({holders}) ON CONFLICT DO NOTHING",
        [tuple(row[column] for column in columns) for row in rows],
    )
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", required=True, type=Path)
    parser.add_argument("--postgres", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.sqlite.is_file():
        print(f"SQLite fayli topilmadi: {args.sqlite}", file=sys.stderr)
        return 2

    source = sqlite3.connect(args.sqlite)
    source.row_factory = sqlite3.Row
    tables = sqlite_tables(source)
    counts = {table: source.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}

    print(f"Manba: {args.sqlite}  ({len(tables)} jadval)")
    for table in tables:
        print(f"  {table:<34} {counts[table]:>7}")
    if args.dry_run:
        print("\n--dry-run: hech narsa yozilmadi")
        return 0

    # Sxema `CloudStore`/`PaymentStore` ning o'zi tomonidan yaratiladi —
    # ikkinchi nusxa DDL saqlanmasin, u vaqt o'tib manbadan ajralib
    # ketardi.
    target_store = CloudStore(args.sqlite, database_url=args.postgres)
    PaymentStore(target_store)
    print("\nSxema PostgreSQL'da tayyor.")

    # Sxema yaratilganda `_init_db` katalogni STANDART qiymatlar bilan
    # urug'laydi.  Ular ko'chirishdan oldin olib tashlanmasa, manbadagi
    # HAQIQIY qatorlar `ON CONFLICT DO NOTHING` sabab o'tkazib
    # yuborilardi va admin tahrirlagan narxlar jimgina standartga
    # qaytardi — qatorlar soni esa BARIBIR mos kelardi, ya'ni
    # tekshiruv ham buni ko'rmasdi.
    connection = target_store._connect()
    try:
        for table in ("feature_prices", "feature_definitions", "business_templates", "price_books"):
            connection.execute(f"DELETE FROM {table}")
        connection.commit()
    finally:
        connection.close()
    print("Standart katalog urug'i tozalandi — manbadagisi ko'chiriladi.")

    # Tartib: chet kalitlar sabab urinish TAKRORLANADI.  Qaysi jadval
    # qaysisiga bog'liqligini qo'lda yozish o'rniga oddiy qat'iy nuqta:
    # har aylanishda o'tganlari olib tashlanadi va yangi o'tish
    # bo'lmaguncha davom etadi.  Yangi jadval qo'shilganda ro'yxatni
    # yangilash kerak bo'lmaydi.
    pending = [table for table in tables if counts[table]]
    moved: dict[str, int] = {}
    while pending:
        progressed = []
        for table in list(pending):
            connection = target_store._connect()
            try:
                moved[table] = copy_table(source, connection, table)
                connection.commit()
                progressed.append(table)
            except Exception as exc:  # chet kalit hali tayyor emas
                connection.rollback()
                last_error = exc
            finally:
                connection.close()
        if not progressed:
            print(f"\nKo'chirib bo'lmadi: {', '.join(pending)}", file=sys.stderr)
            print(f"Oxirgi xato: {last_error}", file=sys.stderr)
            return 1
        pending = [table for table in pending if table not in progressed]

    print("\nKo'chirildi:")
    problems = []
    for table in tables:
        connection = target_store._connect()
        try:
            after = connection.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
            after_count = int(dict(after)["n"])
        finally:
            connection.close()
        mark = "✓" if after_count == counts[table] else "✗"
        if after_count != counts[table]:
            problems.append(table)
        print(f"  {mark} {table:<32} {counts[table]:>7} → {after_count:>7}")

    if problems:
        print(f"\nQatorlar soni MOS KELMADI: {', '.join(problems)}", file=sys.stderr)
        print("`ENES_CONTROL_DATABASE_URL` ni QO'YMANG.", file=sys.stderr)
        return 1

    print(
        "\nHammasi mos.  Endi `ENES_CONTROL_DATABASE_URL` ni qo'yib cloud'ni "
        "qayta ishga tushiring.\nManba SQLite fayli tegilmadi — qaytish uchun "
        "o'zgaruvchini olib tashlang."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
