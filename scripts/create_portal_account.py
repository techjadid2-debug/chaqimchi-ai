#!/usr/bin/env python3
"""Cloud bazasida login/parolli admin/o'rnatuvchi/mijoz yaratish.

Parol terminal argumentida berilmaydi: shell history va process listga tushmasligi
uchun ``getpass`` orqali ikki marta so'raladi.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cloud.store import CloudStore


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Chaqimchi portal akkaunti yaratish")
    result.add_argument("--db", default=os.environ.get("CHAQIMCHI_CLOUD_DB", "data/cloud/cloud.db"))
    result.add_argument("--username", required=True)
    result.add_argument("--name", required=True)
    result.add_argument("--role", required=True, choices=("admin", "installer", "customer"))
    result.add_argument("--status", default="active", choices=("pending", "active", "disabled"))
    result.add_argument("--site-id")
    result.add_argument("--phone")
    result.add_argument("--company")
    return result


def main() -> None:
    args = parser().parse_args()
    password = getpass.getpass("Yangi parol: ")
    confirmation = getpass.getpass("Parolni qaytaring: ")
    if password != confirmation:
        raise SystemExit("Parollar mos emas")
    store = CloudStore(Path(args.db))
    account = store.create_account(
        username=args.username,
        password=password,
        role=args.role,
        status=args.status,
        full_name=args.name,
        phone=args.phone,
        company=args.company,
        site_id=args.site_id,
    )
    print(f"Yaratildi: {account['username']} ({account['role']}, {account['status']})")


if __name__ == "__main__":
    main()
