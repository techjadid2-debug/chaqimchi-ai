#!/usr/bin/env python3
"""Har faol sayt uchun edge config revisionini bir pog'ona ko'taradi.

Nima uchun kerak: qurilma konfigni KESHLAYDI va faqat revision
o'zgarganda qayta tortadi (`enes/local/cloud_config.py`).  Serverga
yangi bayroq qo'shilishi o'zi yetarli emas — dalada turgan dastur eski
keshdagi konfigda qolib ketadi va yangi funksiya jimgina o'chiq
turaveradi.  Bu tuzoq `docs/ISH_DAFTARI.md` da yozilgan.

Deploydan keyin **bir marta** yurgiziladi:

    docker compose exec cloud python scripts/bump_feature_revision.py

Hech narsa o'chirmaydi va sozlamaga tegmaydi: faqat `cloud_feature_revision`
sonini oshiradi (`cloud/main.py: bump_feature_revision`) — ya'ni
xavfsiz va bir necha marta yurgizilsa ham zarar yo'q.

`--dry-run` bilan nima o'zgarishini ko'rsatadi, lekin yozmaydi.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloud.main import bump_feature_revision, get_store  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="faqat ko'rsatadi, revisionni ko'tarmaydi"
    )
    parser.add_argument(
        "--site", default="", help="faqat shu sayt (bo'sh bo'lsa — hammasi)"
    )
    args = parser.parse_args()

    sites = get_store().list_sites()
    if args.site:
        sites = [item for item in sites if str(item.get("id")) == args.site]
        if not sites:
            print(f"Sayt topilmadi: {args.site}", file=sys.stderr)
            return 1

    # Obunasi tugagan saytga tegilmaydi: u baribir bo'sh funksiya
    # ro'yxati oladi va revision ko'tarish faqat bekorga konfig
    # yozuvini yaratardi.
    active = [
        item
        for item in sites
        if str(item.get("license_status") or "") not in {"expired", "suspended"}
    ]

    for site in active:
        site_id = str(site["id"])
        name = str(site.get("name") or site_id)
        if args.dry_run:
            print(f"[dry-run] {name} ({site_id})")
            continue
        saved = bump_feature_revision(site_id)
        print(f"{name} ({site_id}) → revision {saved['revision']}")

    skipped = len(sites) - len(active)
    print(f"\nJami: {len(active)} sayt" + (f", {skipped} tasi obunasiz — tegilmadi" if skipped else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
