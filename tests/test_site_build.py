"""Uch tilli sayt — qurilish va marshrut qulflari.

Sayt `cloud/site/index.html` shablonidan `scripts/build_site.py` bilan
uch tilda quriladi va natija repoga commit qilinadi (panel bundle'i
kabi).  Bu testlar uchta narsani qo'riqlaydi:

1. Qurilgan sahifalar shablon va katalogdan ORQADA QOLMASIN — aks
   holda matn katalogda tuzatilgan, saytda esa eskisi turardi.
2. Har til alohida manzil, canonical va `hreflang` bilan e'lon qilinsin —
   bitta canonical bo'lsa Google uch sahifadan bittasini indekslaydi.
3. Eski brend nomi yangi sahifalarga qaytib kelmasin.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "cloud" / "static"
LANDINGS = {"uz": "site.html", "ru": "site.ru.html", "en": "site.en.html"}
PATHS = {"uz": "/", "ru": "/ru/", "en": "/en/"}


def landing(lang: str) -> str:
    return (STATIC / LANDINGS[lang]).read_text(encoding="utf-8")


def visible(html: str) -> str:
    """HTML izohlarisiz matn — izohlar «nega yo'q» sababini yozadi."""
    return re.sub(r"<!--.*?-->", "", html, flags=re.S)


def test_generated_pages_are_up_to_date() -> None:
    """Shablon yoki katalog o'zgarsa `build_site.py` qayta yurgizilsin.

    Buyruq xatoda to'g'ri yo'lni ham aytadi.
    """
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_site.py"), "--check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout


@pytest.mark.parametrize("lang", list(LANDINGS))
def test_every_language_gets_its_own_landing(lang: str) -> None:
    html = landing(lang)
    assert f'<html lang="{lang}"' in html
    assert "{{" not in html, "o'rinbosar qurilishdan o'tib ketgan"
    # Canonical — o'z til prefiksi bilan.  Bitta qatorlik xato, butun
    # SEO'ni yo'qotadi: uchala til bitta manzilni e'lon qilardi.
    assert f'<link rel="canonical" href="__PUBLIC_ORIGIN__{PATHS[lang]}">' in html
    for code, path in PATHS.items():
        assert f'hreflang="{code}" href="__PUBLIC_ORIGIN__{path}"' in html, f"{lang}: {code} alternativi yo'q"
    assert 'hreflang="x-default" href="__PUBLIC_ORIGIN__/"' in html


@pytest.mark.parametrize("lang", list(LANDINGS))
def test_the_language_switch_marks_the_current_language(lang: str) -> None:
    html = landing(lang)
    assert '<details class="lang-menu">' in html
    assert f'hreflang="{lang}" lang="{lang}" aria-current="true"' in html
    # Nav'da tugma yo'q — tanlagich ham shu qoidaga bo'ysunadi.
    nav = html[html.index("<nav") : html.index("</nav>")]
    assert "button" not in nav


@pytest.mark.parametrize("lang", list(LANDINGS))
def test_structured_data_is_valid_in_every_language(lang: str) -> None:
    """JSON-LD sintaksis xatosi bilan jimgina e'tiborsiz qolinadi."""
    html = landing(lang)
    block = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    assert block, "JSON-LD bloki yo'q"
    data = json.loads(block.group(1).replace("__PUBLIC_ORIGIN__", "https://enes.uz"))
    org, app, faq = data["@graph"]
    assert org["name"] == "ENES Monitoring"
    assert app["inLanguage"] == lang
    assert app["url"] == f"https://enes.uz{PATHS[lang]}"
    for question in faq["mainEntity"]:
        needle = question["name"].split("?")[0][:24]
        assert needle in html, f"{lang}: razmetkadagi savol sahifada yo'q — {needle}"


@pytest.mark.parametrize("lang", list(LANDINGS))
def test_the_landing_carries_no_old_brand(lang: str) -> None:
    """Rebrend: mijoz ko'radigan bosh sahifada eski nom qolmasin."""
    text = visible(landing(lang)).lower()
    assert "chaqimchi" not in text, f"{lang}: eski brend nomi qolgan"
    assert "ENES" in landing(lang)


def test_site_script_takes_its_strings_from_the_catalogue() -> None:
    """`site.js` uchala tilda BITTA fayl; satrlar sahifadan keladi."""
    js = (STATIC / "site.js").read_text(encoding="utf-8")
    assert "window.__SITE__" in js
    assert "function T(key" in js
    # Eski qotirilgan o'zbekcha satrlar qaytmasin.
    for literal in ("So‘rov yuborilmoqda", "Narxni yuklab bo", "Tanlash"):
        assert f'"{literal}' not in js, f"qotirilgan satr: {literal}"
    for lang in LANDINGS:
        html = landing(lang)
        assert f'window.__SITE__ = {{"lang": "{lang}"' in html, f"{lang}: skript satrlari yo'q"


def test_cache_tokens_are_computed_not_typed() -> None:
    """Qurish skripti tokenni fayl mazmunidan hisoblaydi — endi uni
    unutib bo'lmaydi (2026-09-06 da 13 sahifada oylab eskirgan edi)."""
    import hashlib

    for asset in ("site.css", "site.js"):
        expected = hashlib.sha256((STATIC / asset).read_bytes()).hexdigest()[:10]
        for lang in LANDINGS:
            assert f"/assets/{asset}?v={expected}" in landing(lang), f"{lang}: {asset} tokeni eskirgan"


# ── Marshrutlar ─────────────────────────────────────────────────────────


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    import cloud.main as main

    monkeypatch.setenv("CHAQIMCHI_CLOUD_ADMIN_KEY", "test-admin")
    monkeypatch.setenv("CHAQIMCHI_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    for key in ("CHAQIMCHI_PUBLIC_URL", "CHAQIMCHI_APP_URL", "CHAQIMCHI_API_URL",
                "CHAQIMCHI_DL_URL", "CHAQIMCHI_PARTNER_URL", "CHAQIMCHI_ADMIN_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "cloud.db")
    monkeypatch.setattr(main, "_store", None)
    return TestClient(main.app)


@pytest.mark.parametrize("path,lang", [("/", "uz"), ("/ru/", "ru"), ("/ru", "ru"), ("/en/", "en"), ("/en", "en")])
def test_each_language_is_served_at_its_own_path(client: TestClient, path: str, lang: str) -> None:
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 200, f"{path}: {response.status_code} — yo'naltirish yo'q, to'g'ridan-to'g'ri"
    assert f'<html lang="{lang}"' in response.text
    # Runtime o'rinbosarlar qo'yilgan.
    assert "__PUBLIC_ORIGIN__" not in response.text


def test_the_localized_landing_is_not_served_on_subdomains(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("CHAQIMCHI_PUBLIC_URL", "https://enes.uz")
    monkeypatch.setenv("CHAQIMCHI_APP_URL", "https://app.enes.uz")
    assert client.get("/ru/", headers={"host": "app.enes.uz"}).status_code == 404


def test_the_sitemap_lists_every_language_with_alternates(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("CHAQIMCHI_PUBLIC_URL", "https://enes.uz")
    body = client.get("/sitemap.xml", headers={"host": "enes.uz"}).text
    for path in PATHS.values():
        assert f"<loc>https://enes.uz{path}</loc>" in body
    assert 'xmlns:xhtml="http://www.w3.org/1999/xhtml"' in body
    assert 'hreflang="x-default" href="https://enes.uz/"' in body
    # Har til yozuvida uchala alternativ bo'lsin.
    assert body.count('hreflang="ru"') == len(PATHS)
