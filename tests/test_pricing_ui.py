"""Saytdagi tarif bo'limi.

Qaror (2026-08-17): 3 ta paket o'rniga BITTA tarif — "Chaqimchi Lite",
$20/oy, hammasi ichida.  Narx sahifaga yozilmaydi: `/api/v1/public/pricing`
dan keladi (so'm kursi bilan), ya'ni narx o'zgarsa sayt o'zi yangilanadi.

Bu testlar eski holat (ko'p paket, qo'lda yozilgan narx, to'q nav tugma)
qaytib kelmasligini qo'riqlaydi.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE_JS = ROOT / "cloud" / "static" / "site.js"
SITE_HTML = ROOT / "cloud" / "static" / "site.html"
SITE_CSS = ROOT / "cloud" / "static" / "site.css"


def test_single_lite_tariff_card() -> None:
    html = SITE_HTML.read_text(encoding="utf-8")
    js = SITE_JS.read_text(encoding="utf-8")

    assert 'id="liteCard"' in html, "bitta tarif kartasi bo'lsin"
    assert "Chaqimchi Lite" in html
    # Eski ko'p-paket mashinasi qaytmasin.
    assert "presetGrid" not in html
    assert "const PRESETS" not in js
    assert "data-billing" not in html, "oylik/yillik almashtirgich olib tashlangan"
    assert "Yillik to‘lovda 2 oy bepul" in html, "yillik chegirma bitta satr bo'lib qoladi"


def test_price_is_not_hardcoded_in_the_card() -> None:
    """Narx API'dan keladi — sahifada faqat joy turadi.

    Qotirilgan narx bir marta katalogdan orqada qolib, mijoz eski narxni
    ko'rgan edi.  noscript'dagi $20 bundan mustasno (JS'siz fallback).
    """
    html = SITE_HTML.read_text(encoding="utf-8")
    js = SITE_JS.read_text(encoding="utf-8")
    assert '<b id="litePrice">…</b>' in html, "narx joyi bo'sh (…) turishi kerak"
    assert "monthly_usd_cents" in js, "narx pricing API'dan olinsin"
    assert "usd_rate_uzs" in js, "so'm kursi serverdan olinsin"


def test_lite_price_shows_both_currencies() -> None:
    """Qaror: so'm + dollar birga ("~260 000 so'm ($20)")."""
    js = SITE_JS.read_text(encoding="utf-8")
    assert "so‘m" in js
    assert 'id="litePriceUsd"' in SITE_HTML.read_text(encoding="utf-8")


def test_dark_nav_button_is_gone() -> None:
    """Foydalanuvchi feedbacki (2026-08-17): to'q tugma noqulay — olib
    tashlangan.  Telegram havolasi aloqa bo'limida qoladi."""
    html = SITE_HTML.read_text(encoding="utf-8")
    nav = html[html.index("<nav") : html.index("</nav>")]
    assert "button" not in nav, "nav'da tugma bo'lmasin — faqat havolalar"
    # Placeholder saqlanadi: server uni haqiqiy bot havolasiga almashtiradi.
    assert "__TELEGRAM_REGISTER_URL__" in html


def test_hidden_attribute_always_wins() -> None:
    """Haqiqiy bag: inline `display:grid` `hidden`ni yengib, telefon
    formasi reliz chiqqanda ham ko'rinib turardi (skrinshotda ushlangan)."""
    css = SITE_CSS.read_text(encoding="utf-8")
    html = SITE_HTML.read_text(encoding="utf-8")
    assert "[hidden] { display: none !important; }" in css
    # notifyForm'da endi inline display yo'q.
    form_tag = html[html.index('id="notifyForm"') - 60 : html.index('id="notifyForm"') + 120]
    assert "display" not in form_tag, "inline display hidden'ni yengmasin"


def test_the_page_has_exactly_one_lead_form_flow() -> None:
    """Bitta lead forma qoidasi saqlanadi (chuqur minimalizm)."""
    html = SITE_HTML.read_text(encoding="utf-8")
    assert 'id="leadForm"' in html
    assert 'id="purchaseForm"' not in html
    assert html.count("<form") == 2, "leadForm va notifyForm'dan boshqa forma bo'lmasin"


def test_cta_leads_to_the_single_form() -> None:
    js = SITE_JS.read_text(encoding="utf-8")
    assert 'getElementById("liteCta")' in js
    assert "goToForm" in js
    assert "Chaqimchi Lite" in js, "tanlov admin xabarida ko'rinsin"


def test_buy_button_does_not_promise_a_checkout() -> None:
    """Tugma to'lov sahifasini va'da qilmaydi — ariza yuboriladi."""
    source = SITE_JS.read_text(encoding="utf-8")
    assert "Sotib olishni boshlash" not in source


def test_pricing_section_has_a_noscript_fallback() -> None:
    html = SITE_HTML.read_text(encoding="utf-8")
    assert "<noscript>" in html
    assert "JavaScript" in html
    assert "Chaqimchi Lite" in html[html.index("<noscript>") : html.index("</noscript>")]


def test_attendance_is_not_advertised() -> None:
    """Davomat (Face ID) arxivlangan — sotuv sahifasi uni taklif qilmasin."""
    html = SITE_HTML.read_text(encoding="utf-8").lower()
    assert "davomat" not in html
    assert "face id" not in html
