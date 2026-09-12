#!/usr/bin/env python3
"""`releases/` papkasidagi eski Windows relizlarini tozalash.

Papka hech qachon tozalanmasdi: har nashr qilingan `.exe` (~100 MB)
abadiy qolar edi va serverda 1,9 GB ga o'sdi.  Mantiq bitta joyda —
`cloud/main.py: prune_windows_releases()`; bu skript uni qo'ldan va
nashr skriptidan chaqirish uchun.

Ishlatish (server, konteyner ichida):

    # 1) nima o'chishini KO'RSATADI, o'chirmaydi:
    docker compose exec -T cloud python scripts/prune_releases.py --reja

    # 2) o'chirish HOST tomonda bajariladi — konteynerda `releases/`
    #    `:ro` bilan ulangan (`docker-compose.enes.yml`):
    cd /home/deploy/enes/releases && rm -f <ro'yxatdagi fayllar>

Lokal (noutbukda papka yozuvga ochiq, ya'ni bir qadamda):

    python3 scripts/prune_releases.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

# Skript sifatida ishga tushirilganda repo ildizi `sys.path` da bo'lmaydi
# va `import cloud` yiqiladi (`scripts/create_portal_account.py` naqshi).
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--reja",
        action="store_true",
        help="faqat o'chiriladigan fayllar ro'yxati (har qatorda bitta nom)",
    )
    parser.add_argument(
        "--saqla",
        type=int,
        default=None,
        metavar="N",
        help="har prefiks bo'yicha shuncha juftlik qoladi (standart 3)",
    )
    args = parser.parse_args(argv)

    # Import shu yerda: `--help` uchun butun cloud ilovasini ko'tarish
    # kerak emas va importning o'zi env talab qiladi.
    from cloud.main import WINDOWS_RELEASE_KEEP, prune_windows_releases

    keep = WINDOWS_RELEASE_KEEP if args.saqla is None else args.saqla
    report = prune_windows_releases(keep, dry_run=args.reja)

    if report["skipped"]:
        print(
            "Tozalash bajarilmadi: qurilma versiyalarini o'qib bo'lmadi "
            "(sabab jurnalda).  Hech narsa o'chirilmadi.",
            file=sys.stderr,
        )
        return 1

    if args.reja:
        # Faqat nomlar: chiqish nashr skriptida `rm` ga uzatiladi, ya'ni
        # begona qator bo'lmasligi kerak.
        for name in report["planned"]:
            print(name)
        return 0

    for name in report["deleted"]:
        print(f"o'chirildi: {name}")
    print(f"Bo'shadi: {report['freed_bytes'] // (1024 * 1024)} MB")
    if report["failed"]:
        print(
            f"O'chmagan fayl: {len(report['failed'])} ta — konteynerda papka "
            "faqat o'qish uchun ulangan bo'lsa, `--reja` bilan ro'yxat oling "
            "va host tomonda o'chiring.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
