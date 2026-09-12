#!/usr/bin/env python3
"""`site.css` / `docs.css` kesh tokenini HAMMA sahifada yangilaydi.

Nega kerak: `scripts/build_site.py` `?v=` ni faqat shablondan qurilgan
sahifalarda hisoblaydi; qo'lda yozilgan `docs/*.html` eski token bilan
qolib, brauzer eski uslubni keshdan olardi (13 sahifa oylab eskirgan —
docs/ISH_DAFTARI.md tuzoqlari).  `tokens.css`
o'zgarganda esa zanjir uzunroq: avval `site.css`/`docs.css` ichidagi
`@import "tokens.css?v=…"` yangilanadi, keyin ularning o'z tokeni.

Tartib:  tokens/site/docs.css ni tahrirlang → shu skript → `build_site.py`
(shablonli sahifalar qayta quriladi, token bir xil chiqadi) → testlar.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "cloud" / "static"


def token(path: Path) -> str:
    # `tests/test_static_pages.py::_content_token` bilan bir xil formula.
    return hashlib.sha256(path.read_bytes()).hexdigest()[:10]


def main() -> int:
    tokens_tok = token(STATIC / "tokens.css")
    changed = 0
    for css in (STATIC / "site.css", STATIC / "docs" / "docs.css"):
        text = css.read_text(encoding="utf-8")
        fresh = re.sub(r"tokens\.css\?v=[0-9a-f]{10}", f"tokens.css?v={tokens_tok}", text)
        if fresh != text:
            css.write_text(fresh, encoding="utf-8")
            changed += 1
    site_tok = token(STATIC / "site.css")
    docs_tok = token(STATIC / "docs" / "docs.css")
    for page in [*STATIC.glob("*.html"), *(STATIC / "docs").glob("*.html")]:
        text = page.read_text(encoding="utf-8")
        fresh = re.sub(r"site\.css\?v=[0-9a-f]{10}", f"site.css?v={site_tok}", text)
        fresh = re.sub(r"docs\.css\?v=[0-9a-f]{10}", f"docs.css?v={docs_tok}", fresh)
        if fresh != text:
            page.write_text(fresh, encoding="utf-8")
            changed += 1
    print(f"tokens.css={tokens_tok} site.css={site_tok} docs.css={docs_tok} — {changed} fayl yangilandi")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
