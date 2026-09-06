#!/usr/bin/env python3
"""Katalogdan panel uchun TypeScript moduli yasaydi.

## Nega kodgeneratsiya

Katalog bitta bo'lishi kerak (`i18n/{uz,ru,en}.json`), aks holda
serverdagi va paneldagi matn ajralib ketadi.  Lekin brauzerga BUTUN
katalogni yuborish ham noto'g'ri: Telegram xabarlari, CSV sarlavhalari
va sayt matnlari panelga umuman kerak emas — ular bekorga trafik va
bekorga xotira.

Shuning uchun bu skript panelga tegishli bo'limlarnigina ajratib,
`frontend/src/i18n/catalogue.generated.ts` ga yozadi.

Natija **commit qilinadi**: `npm run build` Pythonsiz ham ishlashi
kerak (Docker'ning birinchi bosqichi — toza `node:22-alpine`).

`--check` rejimi `make test` da chaqiriladi: katalog o'zgarib,
generatsiya unutilgan bo'lsa test qulaydi.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOGUE_DIR = ROOT / "i18n"
OUTPUT = ROOT / "frontend" / "src" / "i18n" / "catalogue.generated.ts"

LANGS = ("uz", "ru", "en")

#: Panelga YUBORILADIGAN bo'limlar.
#:
#: Yangi bo'lim qo'shishdan oldin so'rang: "buni panel chizadimi?"
#: Telegram va CSV matnini server chizadi — ular bu yerda emas.
PANEL_PREFIXES = (
    "event.",       # hodisa nomlari — panel `event_type` dan chizadi
    "format.",      # sana, son (server bilan bir xil bo'lishi shart)
    "money.",       # pul — panel ham, digest ham bir xil ko'rsatsin
    "panel.",       # panelning o'z matni
    "trust.",       # ishonch balli qismlari
    "capability.",  # "nega ishlamayapti" izohlari
    "checklist.",   # tayyorlik ro'yxati
)

HEADER = """/* AVTOMATIK YASALGAN — QO'LDA TAHRIRLAMANG.
 *
 * Manba: `i18n/{uz,ru,en}.json`
 * Yangilash: `python scripts/build_i18n.py`
 * Tekshirish: `python scripts/build_i18n.py --check` (`make test` ichida)
 *
 * Bu yerda katalogning FAQAT panelga tegishli qismi bor: Telegram,
 * CSV va sayt matnlari serverda chiziladi va brauzerga yuborilmaydi.
 */
"""


def panel_subset(data: dict) -> dict:
    return {k: v for k, v in data.items() if k.startswith(PANEL_PREFIXES)}


def render() -> str:
    blocks = []
    for lang in LANGS:
        raw = json.loads((CATALOGUE_DIR / f"{lang}.json").read_text(encoding="utf-8"))
        subset = panel_subset(raw)
        body = json.dumps(subset, ensure_ascii=False, indent=2, sort_keys=True)
        blocks.append(f"  {lang}: {body},")
    joined = "\n".join(blocks)
    # `as const` bermaymiz: kalitlar soni yuzlab bo'lganda `tsc` uchun
    # ulkan literal tip hosil bo'lardi va typecheck sezilarli sekinlashardi.
    return (
        HEADER
        + "\nexport type CatalogueEntry = string | string[];\n"
        + "\nexport const CATALOGUE: Record<string, Record<string, CatalogueEntry>> = {\n"
        + joined
        + "\n};\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="faqat tekshirish, yozmaslik")
    args = parser.parse_args()

    expected = render()
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != expected:
            print(
                "i18n: katalog o'zgargan, lekin TypeScript nusxasi eskirgan.\n"
                "Tuzatish: python scripts/build_i18n.py",
                file=sys.stderr,
            )
            return 1
        print("i18n: TypeScript nusxasi yangi")
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(expected, encoding="utf-8")
    print(f"{OUTPUT.relative_to(ROOT)}: yozildi")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
