#!/usr/bin/env python3
"""Tashlangan hodisalarni ko'rish, faylga saqlash yoki navbatga qaytarish.

Navbat umidsiz hodisani `dead_letter` jadvaliga ko'chiradi va u yerda
uni **hech kim ko'rmaydi**: heartbeat faqat sonini aytadi
(`outbox_poisoned`), o'qiydigan yoki qaytaradigan vosita esa yo'q edi.
2026-08-30 da do'kon kompyuterida shu tarzda **2 738 ta** hodisa turgan
edi va ularning 602 tasi sababsiz — nima yo'qolgani endi bilinmaydi.

Standart rejim — **faqat ko'rsatish**.  Qaytarish ALOHIDA so'raladi,
chunki eski hodisani qaytarish mijozning Telegramiga bir haftalik
trevogani to'kadi.  Odatda to'g'ri yo'l: `--export` bilan faylga olib,
keyin `--forget` bilan tozalash.

    python scripts/dead_letters.py                      # ro'yxat
    python scripts/dead_letters.py --export dead.jsonl  # faylga
    python scripts/dead_letters.py --requeue --newer-than-hours 2
    python scripts/dead_letters.py --forget --older-than-days 3
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chaqimchi_ai.outbox import EventOutbox  # noqa: E402
from chaqimchi_ai.paths import data_dir  # noqa: E402


def _outbox_path() -> Path:
    override = os.environ.get("CHAQIMCHI_RETAIL_OUTBOX", "").strip()
    return Path(override) if override else data_dir() / "outbox.db"


def _parse(stamp: str) -> datetime:
    """ISO vaqtni o'qiydi; buzuq bo'lsa "juda eski" deb hisoblaydi.

    Buzuq sana sabab skript yiqilsa operator navbatni umuman ko'ra
    olmasdi — bu yozuvning o'zidan ko'ra yomonroq.
    """
    try:
        moment = datetime.fromisoformat(str(stamp))
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=timezone.utc)
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", default=None, help="outbox.db yo'li (standart: data papkasi)")
    parser.add_argument("--limit", type=int, default=10_000, help="ko'p bo'lsa nechtasini olish")
    parser.add_argument("--export", metavar="FAYL", help="JSONL faylga saqlash")
    parser.add_argument(
        "--requeue", action="store_true", help="navbatga QAYTARISH (mijozga xabar boradi)"
    )
    parser.add_argument("--forget", action="store_true", help="butunlay o'chirish")
    parser.add_argument(
        "--newer-than-hours", type=float, default=None, help="faqat shu soatdan yangilariga tegish"
    )
    parser.add_argument(
        "--older-than-days", type=float, default=None, help="faqat shu kundan eskilariga tegish"
    )
    args = parser.parse_args()

    if args.requeue and args.forget:
        parser.error("--requeue va --forget birga ishlatilmaydi")

    path = Path(args.db) if args.db else _outbox_path()
    if not path.is_file():
        print(f"Navbat fayli topilmadi: {path}", file=sys.stderr)
        return 1

    outbox = EventOutbox(path, max_bytes=0)
    rows = outbox.dead_letters(limit=args.limit)
    if not rows:
        print("Tashlangan hodisa yo'q.")
        return 0

    now = datetime.now(timezone.utc)
    chosen = rows
    if args.newer_than_hours is not None:
        edge = now - timedelta(hours=args.newer_than_hours)
        chosen = [row for row in chosen if _parse(row["failed_at"]) >= edge]
    if args.older_than_days is not None:
        edge = now - timedelta(days=args.older_than_days)
        chosen = [row for row in chosen if _parse(row["failed_at"]) < edge]

    reasons = Counter((row["last_error"] or "sabab yozilmagan")[:80] for row in rows)
    oldest = min(_parse(row["failed_at"]) for row in rows)
    newest = max(_parse(row["failed_at"]) for row in rows)
    print(f"Navbat: {path}")
    print(f"Tashlangan: {len(rows)} ta · {oldest:%Y-%m-%d %H:%M} — {newest:%Y-%m-%d %H:%M} (UTC)")
    print(f"Tanlandi:   {len(chosen)} ta")
    print("Sabablari:")
    for reason, count in reasons.most_common(10):
        print(f"  {count:6d}x  {reason}")

    if args.export:
        target = Path(args.export)
        with target.open("w", encoding="utf-8") as handle:
            for row in chosen:
                handle.write(json.dumps(dict(row), ensure_ascii=False) + "\n")
        print(f"Saqlandi: {target} ({len(chosen)} ta)")

    if args.requeue:
        restored = outbox.requeue_dead_letters([row["event_id"] for row in chosen])
        print(f"Navbatga qaytarildi: {restored} ta")
    elif args.forget:
        with outbox._connect() as conn:  # noqa: SLF001 — operator vositasi
            for row in chosen:
                conn.execute("DELETE FROM dead_letter WHERE event_id=?", (row["event_id"],))
        print(f"O'chirildi: {len(chosen)} ta")
    else:
        print("\n(Faqat ko'rsatildi.  Qaytarish uchun --requeue, o'chirish uchun --forget.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
