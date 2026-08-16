"""Saytdagi narx konfiguratori.

Nima uchun alohida test: narx bo'limi mijoz pul to'lash qaroriga keladigan
yagona joy, lekin uning mantig'i brauzerda (`site.js`) turadi va server
testlari uni umuman ko'rmaydi.

Eng xavfli xato — **jimgina noto'g'ri narx**: paketda kodi noto'g'ri yozilgan
funksiya `pricing.features` ichidan topilmaydi va narxga `0` bo'lib qo'shiladi.
Sahifa buzilmaydi, ogohlantirish chiqmaydi — mijoz shunchaki arzon narx
ko'radi va biz uni keyin ko'tarishga majbur bo'lamiz.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from cloud.store import DEFAULT_FEATURES

ROOT = Path(__file__).resolve().parents[1]
SITE_JS = ROOT / "cloud" / "static" / "site.js"
SITE_HTML = ROOT / "cloud" / "static" / "site.html"
SITE_CSS = ROOT / "cloud" / "static" / "site.css"


def _presets() -> list[dict]:
    """`site.js` dagi `PRESETS` massivini Node yordamida o'qiydi.

    Regexp bilan JSON qidirish o'rniga haqiqiy JS bajariladi — massiv
    formati o'zgarsa test yolg'on "o'tdi" bermaydi.
    """
    if shutil.which("node") is None:
        pytest.skip("node topilmadi — konfigurator mantig'i tekshirilmadi")
    source = SITE_JS.read_text(encoding="utf-8")
    match = re.search(r"const PRESETS = (\[.*?\n  \]);", source, re.S)
    assert match, "PRESETS massivi topilmadi — nomi o'zgargan bo'lishi mumkin"
    script = f"console.log(JSON.stringify({match.group(1)}))"
    result = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=30, check=True
    )
    return json.loads(result.stdout)


CATALOG_CODES = {code for code, *_rest in DEFAULT_FEATURES}
CATALOG_PRICES = {code: price for code, _n, _c, _q, price in DEFAULT_FEATURES}

#: `cloud/main.py` dagi `public_pricing` shu qiymatni beradi
#: (`GUARANTEED_CAMERAS`).  Paketlar undan oshib ketmasligi kerak.
MAX_CAMERAS = 4


def test_every_preset_feature_exists_in_the_catalog() -> None:
    """Noto'g'ri kod narxga 0 bo'lib qo'shiladi va hech qayerda ko'rinmaydi."""
    for preset in _presets():
        for item in preset["items"]:
            assert item["code"] in CATALOG_CODES, (
                f"«{preset['name']}» paketida katalogda yo'q kod: {item['code']}. "
                f"Mavjudlari: {sorted(CATALOG_CODES)}"
            )


def test_presets_stay_within_the_accepted_camera_profile() -> None:
    """4 kamera — o'lchangan sig'im (`docs/DOKON_MVP.md`).  Paket undan
    oshsa, sotib bo'lmaydigan narsani sotgan bo'lamiz."""
    for preset in _presets():
        for item in preset["items"]:
            assert 1 <= item["cameras"] <= MAX_CAMERAS, (
                f"«{preset['name']}»: {item['code']} uchun {item['cameras']} kamera"
            )


def test_presets_are_ordered_from_cheap_to_expensive() -> None:
    """Mijoz kartalarni chapdan o'ngga o'qiydi; narx sakrab tushsa
    taqqoslash buziladi."""
    base = 2_000  # LITE_MONTHLY_PRICE_USD_CENTS
    totals = [
        base + sum(CATALOG_PRICES[item["code"]] * item["cameras"] for item in preset["items"])
        for preset in _presets()
    ]
    assert totals == sorted(totals), f"paket narxlari o'sib bormaydi: {totals}"


def test_the_popular_preset_is_in_the_middle() -> None:
    """Uchtadan o'rtadagisi belgilanadi — chekkadagi "ommabop" karta
    yonidagilarni arzon yoki qimmat ko'rsatib qo'yadi."""
    presets = _presets()
    badged = [index for index, preset in enumerate(presets) if preset.get("badge")]
    assert badged == [1], f"«Ommabop» belgisi o'rtada bo'lishi kerak, hozir: {badged}"


# ── Stepper ──────────────────────────────────────────────────────────────


def test_camera_stepper_replaced_the_dropdown() -> None:
    """`<select>` `<label>` ichida edi: uni bosganda checkbox ham
    almashishi mumkin edi va o'chirilgan holatda ko'rinmasdi."""
    source = SITE_JS.read_text(encoding="utf-8")
    assert "feature-cameras" not in source, "eski `<select>` qoldig'i"
    assert "cameraOptions" not in source, "eski `<option>` generatori qoldig'i"
    assert 'data-step="-1"' in source and 'data-step="1"' in source


def test_stepper_is_clamped_to_the_catalog_limit() -> None:
    """Chegara qo'lda yozilmasin: `pricing.max_cameras` serverdan keladi."""
    source = SITE_JS.read_text(encoding="utf-8")
    clamp = re.search(r"function setCameras\(row, value\) \{(.*?)\n  \}", source, re.S)
    assert clamp, "setCameras topilmadi"
    body = clamp.group(1)
    assert "pricing.max_cameras" in body, "chegara serverdan olinmayapti"
    assert "Math.min" in body and "Math.max" in body, "qiymat cheklanmayapti"


def test_stepper_is_reachable_with_a_keyboard() -> None:
    source = SITE_JS.read_text(encoding="utf-8")
    assert "ArrowRight" in source and "ArrowLeft" in source, "o'q tugmalari ishlamaydi"


# ── Sahifa tuzilishi ─────────────────────────────────────────────────────


def test_pricing_section_has_a_noscript_fallback() -> None:
    """JS o'chsa narx bo'limi abadiy "Narxlar yuklanmoqda…" turardi."""
    html = SITE_HTML.read_text(encoding="utf-8")
    assert "<noscript>" in html
    assert "JavaScript" in html


def test_mobile_price_bar_and_telegram_button_do_not_overlap() -> None:
    """Ikkalasi ham ekran pastida `position: fixed` — biri ikkinchisini
    yopib qo'yardi."""
    css = SITE_CSS.read_text(encoding="utf-8")
    assert ".mobile-lead-cta.is-hidden" in css, "Telegram tugmasi yashirilmaydi"
    assert ".sticky-price" in css
    js = SITE_JS.read_text(encoding="utf-8")
    assert "is-hidden" in js, "JS panelni almashtirmaydi"


def test_switches_announce_their_state() -> None:
    """`role="group"` ekran o'quvchiga qaysi biri tanlanganini aytmaydi."""
    html = SITE_HTML.read_text(encoding="utf-8")
    assert 'role="radiogroup"' in html
    assert 'aria-checked' in html


def test_summary_is_a_real_list() -> None:
    """`\\n` bilan ajratilgan matn ekran o'quvchida bitta uzun satr bo'lardi."""
    html = SITE_HTML.read_text(encoding="utf-8")
    assert '<ul id="summaryFeatures"' in html
    assert "white-space" not in SITE_JS.read_text(encoding="utf-8")


def test_buy_button_does_not_promise_a_checkout() -> None:
    """Forma to'lov sahifasiga olib bormaydi — u ariza yuboradi."""
    source = SITE_JS.read_text(encoding="utf-8")
    assert "Sotib olishni boshlash" not in source, (
        "tugma to'lov sahifasini va'da qiladi, aslida ariza yuboriladi"
    )
