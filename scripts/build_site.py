#!/usr/bin/env python3
"""Ommaviy saytni quradi: shablon + katalog → statik HTML, uch tilda.

Nega statik, so'rov paytida emas.  Qidiruv tizimiga har til uchun
ALOHIDA manzil kerak (`/`, `/ru/`, `/en/`) va sahifa mazmuni doimiy
bo'lishi kerak.  Server so'rov paytida render qilsa yangi bog'liqlik
(shablon dvigateli) kerak bo'lardi va har so'rovda ish qilinardi;
statik fayl esa oddiy `FileResponse` (+ runtime o'rinbosarlar:
`__PUBLIC_ORIGIN__`, `__APP_URL__` — ularni server qo'yadi).  Natija
repoga commit qilinadi — xuddi panel bundle'i kabi — va `--check` u
eskirmaganini `make test` ichida tekshiradi.

Nega `{{kalit}}` — o'z formatimiz.  Jinja kabi kutubxona faqat shu
uchun qo'shilmaydi: kerak bo'lgani almashtirish va `include`, shart va
sikl emas.  Matn `i18n/{uz,ru,en}.json` dagi `site.*` kalitlaridan
keladi — panel va Telegram bilan bitta katalog.

Sahifalar ikki xil:
  - uch tilli (bosh sahifa, aloqa, hamkorlik, holat, yuklab olish,
    ulash) — matn katalogda, har til alohida fayl;
  - faqat o'zbekcha (yuridik hujjatlar, o'rnatish yo'riqnomasi, edu,
    to'lov) — matn shablonning o'zida, umumiy nav/footer va brend
    katalogdan.  Yuridik matn tarjima qilinmaydi: noto'g'ri tarjima
    qilingan oferta huquqiy javobgarlik.

O'rinbosarlar:
    {{lang}}                 — `uz` / `ru` / `en`
    {{path}}                 — shu sahifaning shu tildagi manzili
    {{home}}                 — bosh sahifa: `/`, `/ru/`, `/en/`
    {{page:aloqa}}           — boshqa sahifaning shu tildagi manzili
                               (tilda yo'q bo'lsa — o'zbekchasi)
    {{hreflang}}             — `<link rel=alternate>` (uch tilli va
                               indekslanadigan sahifalarda; boshqasida bo'sh)
    {{lang_switch}}          — til tanlagich (`<details>`, tugmasiz)
    {{site_json}}            — `site.js.*` kalitlari — `window.__SITE__`
    {{asset:site.css}}       — `/assets/site.css?v=<sha256 boshi>`
    {{json:kalit}}           — JSON satr literali (JSON-LD, inline JS)
    {{inline:fayl.svg}}      — `cloud/static/` dagi faylning o'zi
    {{include:partials/x}}   — `cloud/site/` dagi umumiy qism (rekursiv)

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
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "cloud" / "site"
STATIC = ROOT / "cloud" / "static"
CATALOGUE_DIR = ROOT / "i18n"

LANGS = ("uz", "ru", "en")
DEFAULT_LANG = "uz"

#: Bosh sahifa prefiksi.  O'zbekcha — ildizda: u standart va eski
#: havolalar (`/#aloqa`) o'zgarmasdan ishlayveradi.
LANG_PATHS = {"uz": "/", "ru": "/ru/", "en": "/en/"}
LANG_SHORT = {"uz": "UZ", "ru": "RU", "en": "EN"}

JS_PREFIX = "site.js."
PLACEHOLDER = re.compile(r"\{\{(?:(asset|json|inline|include|page):)?([\w./\-]+)\}\}")
BANNER = (
    "<!-- AVTOMATIK YASALGAN — QO'LDA TAHRIRLAMANG.\n"
    "     Manba: cloud/site/{template} + i18n/{lang}.json\n"
    "     Yangilash: python scripts/build_site.py -->\n"
)


@dataclass(frozen=True)
class Page:
    template: str
    #: til → manzil.  Faqat `uz` bo'lsa sahifa o'zbekcha.
    paths: dict[str, str]
    #: til → `cloud/static/` dagi fayl.
    outputs: dict[str, str]
    #: `hreflang` va sitemap uchun.  `noindex` sahifalarda `False`.
    indexable: bool = True

    @property
    def slug(self) -> str:
        return self.template.removesuffix(".html")


def _three(slug: str, index: bool = True) -> Page:
    """Uch tilli oddiy sahifa: `/x`, `/ru/x`, `/en/x` → `x.html`, `x.ru.html`, `x.en.html`."""
    return Page(
        f"{slug}.html",
        {"uz": f"/{slug}", "ru": f"/ru/{slug}", "en": f"/en/{slug}"},
        {"uz": f"{slug}.html", "ru": f"{slug}.ru.html", "en": f"{slug}.en.html"},
        indexable=index,
    )


def _uz(slug: str, path: str | None = None, index: bool = True) -> Page:
    return Page(f"{slug}.html", {"uz": path or f"/{slug}"}, {"uz": f"{slug}.html"}, indexable=index)


PAGES: tuple[Page, ...] = (
    Page("index.html", dict(LANG_PATHS), {"uz": "site.html", "ru": "site.ru.html", "en": "site.en.html"}),
    _three("aloqa"),
    _three("hamkorlik"),
    _three("status", index=False),
    _three("connect", index=False),
    # `dl.` subdomenida turadi: manzillar o'sha host ildiziga nisbatan.
    Page("dl.html", dict(LANG_PATHS), {"uz": "dl.html", "ru": "dl.ru.html", "en": "dl.en.html"}, indexable=False),
    _uz("install"),
    _uz("privacy", "/maxfiylik"),
    _uz("oferta"),
    _uz("rozilik-shabloni"),
    _uz("kuzatuv-eslatmasi"),
    _uz("edu"),
    _uz("installer-guide", index=False),
    _uz("pay", index=False),
    # Brendli 404 — server noma'lum apex manzil uchun beradi (`cloud/main.py`).
    _uz("404", index=False),
)
PAGE_BY_SLUG = {page.slug: page for page in PAGES}


def load_catalogue() -> dict[str, dict]:
    return {
        lang: json.loads((CATALOGUE_DIR / f"{lang}.json").read_text(encoding="utf-8"))
        for lang in LANGS
    }


def asset_token(name: str) -> str:
    """`tests/test_static_pages.py::_content_token` bilan AYNAN bir xil."""
    return hashlib.sha256((STATIC / name).read_bytes()).hexdigest()[:10]


def hreflang_links(page: Page) -> str:
    if not page.indexable or len(page.paths) < 2:
        return ""
    lines = [
        f'<link rel="alternate" hreflang="{lang}" href="__PUBLIC_ORIGIN__{path}">'
        for lang, path in page.paths.items()
    ]
    # `x-default` — til aniqlanmaganda qidiruv tizimi qaysi sahifani
    # ko'rsatsin: o'zbekcha, chunki mijozlarning ko'pi shu yerda.
    lines.append(
        f'<link rel="alternate" hreflang="x-default" href="__PUBLIC_ORIGIN__{page.paths[DEFAULT_LANG]}">'
    )
    return "\n  ".join(lines)


def lang_switch(page: Page, lang: str, texts: dict) -> str:
    """Til tanlagich — `<details>`, JS'siz va TUGMASIZ.

    `<nav>` ichida `<button>` bo'lmasligi kerak (`test_dark_nav_button_is_gone`);
    `<details>` klaviatura va ekran o'quvchisi uchun tekin ishlaydi.
    Sahifa boshqa tilda yo'q bo'lsa (yuridik hujjat) — o'sha tildagi
    bosh sahifaga olib boradi.
    """
    items = []
    for code in LANGS:
        target = page.paths.get(code)
        current = ' aria-current="true"' if code == lang else ""
        if target is None:
            # Sahifa BU TILDA yo'q (yuridik hujjat faqat o'zbekcha).
            # Ilgari havola o'sha tildagi BOSH sahifaga olib borardi:
            # odam ofertani ruscha o'qimoqchi bo'lib bosadi va butunlay
            # boshqa sahifaga tushadi — bu buzilgan havola bilan bir xil
            # taassurot.  Endi band tanlanmaydi va SABABI aytiladi.
            label = texts[f"site.lang.{code}"]
            items.append(
                f'<span lang="{code}" aria-disabled="true"'
                f' title="{texts["site.lang.only_uz"]}">{label}</span>'
            )
            continue
        items.append(
            f'<a href="{target}" hreflang="{code}" lang="{code}"{current}>{texts[f"site.lang.{code}"]}</a>'
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


def render_text(source: str, page: Page, lang: str, texts: dict, *, where: str) -> str:
    missing: list[str] = []

    def replace(match: re.Match) -> str:
        kind, key = match.group(1), match.group(2)
        if kind == "asset":
            return f"/assets/{key}?v={asset_token(key)}"
        if kind == "inline":
            return (STATIC / key).read_text(encoding="utf-8").strip()
        if kind == "include":
            partial = (TEMPLATES / key).read_text(encoding="utf-8")
            return render_text(partial, page, lang, texts, where=key).strip()
        if kind == "page":
            other = PAGE_BY_SLUG.get(key)
            if other is None:
                missing.append(f"page:{key}")
                return match.group(0)
            return other.paths.get(lang, other.paths[DEFAULT_LANG])
        if kind == "json":
            value = texts.get(key)
            if value is None:
                missing.append(key)
                return match.group(0)
            return json.dumps(value, ensure_ascii=False)
        if key == "lang":
            return lang
        if key == "path":
            return page.paths.get(lang, page.paths[DEFAULT_LANG])
        if key == "home":
            return LANG_PATHS[lang]
        if key == "hreflang":
            return hreflang_links(page)
        if key == "lang_switch":
            return lang_switch(page, lang, texts)
        if key == "site_json":
            return site_json(lang, texts)
        value = texts.get(key)
        if not isinstance(value, str):
            missing.append(key)
            return match.group(0)
        return value

    body = PLACEHOLDER.sub(replace, source)
    if missing:
        raise SystemExit(f"build_site: {lang}/{where} — kalit yo'q: {sorted(set(missing))}")
    return body


def render(page: Page, lang: str, texts: dict) -> str:
    source = (TEMPLATES / page.template).read_text(encoding="utf-8")
    body = render_text(source, page, lang, texts, where=page.template)
    leftover = re.findall(r"\{\{[^}]*\}\}", body)
    if leftover:
        raise SystemExit(f"build_site: {lang}/{page.template} — noma'lum o'rinbosar: {leftover[:5]}")
    banner = BANNER.format(template=page.template, lang=lang)
    # `<!doctype html>` katta-kichik harfda farq qilishi mumkin (eski
    # sahifalar `<!DOCTYPE html>` bilan) — ikkalasi ham qabul qilinadi.
    return re.sub(r"^(<!doctype html>\n)", lambda m: m.group(1) + banner, body, count=1, flags=re.I)


def expected_outputs() -> dict[Path, str]:
    catalogue = load_catalogue()
    outputs: dict[Path, str] = {}
    for page in PAGES:
        for lang, filename in page.outputs.items():
            outputs[STATIC / filename] = render(page, lang, catalogue[lang])
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
