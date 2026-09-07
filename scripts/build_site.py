#!/usr/bin/env python3
"""Ommaviy saytni uch tilda quradi: shablon + katalog → statik HTML.

Nega statik, so'rov paytida emas.  Qidiruv tizimiga har til uchun
ALOHIDA manzil kerak (`/`, `/ru/`, `/en/`) va sahifa mazmuni doimiy
bo'lishi kerak.  Server so'rov paytida render qilsa yangi bog'liqlik
(shablon dvigateli) kerak bo'lardi va har so'rovda ish qilinardi;
statik fayl esa oddiy `FileResponse`.  Natija repoga commit qilinadi —
xuddi panel bundle'i kabi — va `--check` u eskirmaganini `make test`
ichida tekshiradi.

Nega `{{kalit}}` — o'z formatimiz.  Jinja kabi kutubxona faqat shu
uchun qo'shilmaydi: kerak bo'lgani almashtirish, shart va sikl emas.
Matn `i18n/{uz,ru,en}.json` dagi `site.*` kalitlaridan keladi — panel
va Telegram bilan bitta katalog, ya'ni "O‘zbekcha" so'zi bir joyda.

Maxsus o'rinbosarlar:
    {{lang}}              — `uz` / `ru` / `en`
    {{path}}              — `/` / `/ru/` / `/en/` (canonical va havolalar)
    {{hreflang}}          — uchala til + `x-default` uchun `<link rel=alternate>`
    {{lang_switch}}       — til tanlagich (`<details>`, tugmasiz)
    {{site_json}}         — `site.js.*` kalitlari — `window.__SITE__`
    {{asset:site.css}}    — `/assets/site.css?v=<sha256 boshi>` (kesh tokeni
                            mazmundan hisoblanadi, qo'lda yangilanmaydi)
    {{json:kalit}}        — JSON satr literali (JSON-LD uchun)
    {{inline:fayl.svg}}   — `cloud/static/` dagi faylni joyiga qo'yadi
                            (brend belgisi `currentColor` bilan ishlasin)

Yetishmagan kalit — XATO, jimgina o'zbekchaga tushish emas: sayt oflayn
quriladi va xato shu yerda ko'rinishi kerak, mijoz ekranida emas.

Ishlatish:
    python scripts/build_site.py            # yozadi
    python scripts/build_site.py --check    # eskirganini tekshiradi
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "cloud" / "site"
STATIC = ROOT / "cloud" / "static"
CATALOGUE_DIR = ROOT / "i18n"

LANGS = ("uz", "ru", "en")
DEFAULT_LANG = "uz"

#: Tilning manzil prefiksi.  O'zbekcha — ildizda: u standart va eski
#: havolalar (`/#aloqa`) o'zgarmasdan ishlayveradi.
LANG_PATHS = {"uz": "/", "ru": "/ru/", "en": "/en/"}

#: Qisqa belgi til tanlagichda.
LANG_SHORT = {"uz": "UZ", "ru": "RU", "en": "EN"}

#: Shablon → har til uchun chiqish fayli.  Fayllar `cloud/static/`
#: ildizida, tekis nomda: `tests/test_static_pages.py` dagi `pages()`
#: ularni o'zi topadi va sayt qoidalari uchala tilga ham tekshiriladi.
PAGES = {
    "index.html": {"uz": "site.html", "ru": "site.ru.html", "en": "site.en.html"},
}

JS_PREFIX = "site.js."

PLACEHOLDER = re.compile(r"\{\{(?:(asset|json|inline):)?([\w.\-]+)\}\}")

BANNER = (
    "<!-- AVTOMATIK YASALGAN — QO'LDA TAHRIRLAMANG.\n"
    "     Manba: cloud/site/{template} + i18n/{lang}.json\n"
    "     Yangilash: python scripts/build_site.py -->\n"
)


def load_catalogue() -> dict[str, dict]:
    return {
        lang: json.loads((CATALOGUE_DIR / f"{lang}.json").read_text(encoding="utf-8"))
        for lang in LANGS
    }


def asset_token(name: str) -> str:
    """`tests/test_static_pages.py::_content_token` bilan AYNAN bir xil."""
    return hashlib.sha256((STATIC / name).read_bytes()).hexdigest()[:10]


def hreflang_links() -> str:
    lines = [
        f'<link rel="alternate" hreflang="{lang}" href="__PUBLIC_ORIGIN__{path}">'
        for lang, path in LANG_PATHS.items()
    ]
    # `x-default` — til aniqlanmaganda qidiruv tizimi qaysi sahifani
    # ko'rsatsin: o'zbekcha, chunki mijozlarning ko'pi shu yerda.
    lines.append(f'<link rel="alternate" hreflang="x-default" href="__PUBLIC_ORIGIN__{LANG_PATHS[DEFAULT_LANG]}">')
    return "\n  ".join(lines)


def lang_switch(lang: str, texts: dict) -> str:
    """Til tanlagich — `<details>`, JS'siz va TUGMASIZ.

    `<nav>` ichida `<button>` bo'lmasligi kerak (`test_dark_nav_button_is_gone`);
    `<details>` klaviatura va ekran o'quvchisi uchun tekin ishlaydi.
    """
    items = []
    for code, path in LANG_PATHS.items():
        current = ' aria-current="true"' if code == lang else ""
        items.append(
            f'<a href="{path}" hreflang="{code}" lang="{code}"{current}>{texts[f"site.lang.{code}"]}</a>'
        )
    return (
        '<details class="lang-menu">'
        f'<summary aria-label="{texts["site.nav.lang"]}"><span>{LANG_SHORT[lang]}</span></summary>'
        '<div class="lang-menu-list">' + "".join(items) + "</div>"
        "</details>"
    )


def site_json(lang: str, texts: dict) -> str:
    strings = {key[len(JS_PREFIX):]: value for key, value in texts.items() if key.startswith(JS_PREFIX)}
    return json.dumps({"lang": lang, "t": strings}, ensure_ascii=False, sort_keys=True)


def render(template_name: str, lang: str, texts: dict) -> str:
    source = (TEMPLATES / template_name).read_text(encoding="utf-8")
    missing: list[str] = []

    def replace(match: re.Match) -> str:
        kind, key = match.group(1), match.group(2)
        if kind == "asset":
            return f"/assets/{key}?v={asset_token(key)}"
        if kind == "inline":
            return (STATIC / key).read_text(encoding="utf-8").strip()
        if kind == "json":
            value = texts.get(key)
            if value is None:
                missing.append(key)
                return match.group(0)
            return json.dumps(value, ensure_ascii=False)
        if key == "lang":
            return lang
        if key == "path":
            return LANG_PATHS[lang]
        if key == "hreflang":
            return hreflang_links()
        if key == "lang_switch":
            return lang_switch(lang, texts)
        if key == "site_json":
            return site_json(lang, texts)
        value = texts.get(key)
        if not isinstance(value, str):
            missing.append(key)
            return match.group(0)
        return value

    body = PLACEHOLDER.sub(replace, source)
    if missing:
        raise SystemExit(f"build_site: {lang}/{template_name} — kalit yo'q: {sorted(set(missing))}")
    leftover = re.findall(r"\{\{[^}]*\}\}", body)
    if leftover:
        raise SystemExit(f"build_site: {lang}/{template_name} — noma'lum o'rinbosar: {leftover[:5]}")
    banner = BANNER.format(template=template_name, lang=lang)
    return body.replace("<!doctype html>\n", "<!doctype html>\n" + banner, 1)


def expected_outputs() -> dict[Path, str]:
    catalogue = load_catalogue()
    outputs: dict[Path, str] = {}
    for template_name, targets in PAGES.items():
        for lang, filename in targets.items():
            outputs[STATIC / filename] = render(template_name, lang, catalogue[lang])
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description="Ommaviy saytni uch tilda quradi.")
    parser.add_argument("--check", action="store_true", help="faqat tekshirish, yozmaslik")
    args = parser.parse_args()

    outputs = expected_outputs()
    if args.check:
        stale = [
            path.name
            for path, text in outputs.items()
            if not path.exists() or path.read_text(encoding="utf-8") != text
        ]
        if stale:
            print(
                "sayt: shablon yoki katalog o'zgargan, qurilgan sahifalar eskirgan: "
                + ", ".join(stale)
                + "\nTuzatish: python scripts/build_site.py",
                file=sys.stderr,
            )
            return 1
        print("sayt: qurilgan sahifalar yangi")
        return 0

    for path, text in outputs.items():
        path.write_text(text, encoding="utf-8")
        print(f"{path.relative_to(ROOT)}: yozildi")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
