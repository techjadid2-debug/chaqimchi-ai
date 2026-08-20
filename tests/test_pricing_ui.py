"""Saytdagi tarif bo'limi.

Qaror (2026-08-21): bitta tarif o'rniga UCHTA — Boshlang'ich, Biznes,
Tarmoq.  Bitta tarif ($20, hammasi ichida) 2026-08-17 da joriy qilingan
edi va u ikki tomondan zarar keltirardi: kichik do'kon uchun arzon kirish
nuqtasi yo'q edi, katta mijozdan ko'proq pul olishning yo'li ham yo'q edi.

Uchta TENG ustun qarorni qiyinlashtiradi — shuning uchun o'rtadagisi
ajratilgan va ko'z birinchi o'shanga tushadi.

Narx sahifaga YOZILMAYDI: `/api/v1/public/pricing` dan tayyor so'mda
keladi.  Ilgari so'mga o'girish formulasi `site.js` da qaytadan yozilgan
edi — ikki joydagi formula bir-biridan uzoqlashib, sayt bir narxni,
hisob-faktura boshqasini ko'rsatishi mumkin edi.

Bu testlar eski holat (qo'lda yozilgan narx, to'q nav tugma, ko'p forma)
qaytib kelmasligini qo'riqlaydi.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE_JS = ROOT / "cloud" / "static" / "site.js"
SITE_HTML = ROOT / "cloud" / "static" / "site.html"
SITE_CSS = ROOT / "cloud" / "static" / "site.css"


def test_three_tariff_cards_come_from_the_api() -> None:
    html = SITE_HTML.read_text(encoding="utf-8")
    js = SITE_JS.read_text(encoding="utf-8")

    assert 'id="planGrid"' in html, "kartalar uchun joy bo'lsin"
    assert "renderPlans" in js
    # Eski bitta-karta mashinasi qaytmasin.
    assert 'id="liteCard"' not in html
    assert "renderLite" not in js
    assert "data-billing" not in html, "oylik/yillik almashtirgich yo'q"
    assert "Yillik to‘lovda 2 oy bepul" in html, "yillik chegirma bitta satr bo'lib qoladi"


def test_the_middle_plan_is_the_highlighted_one() -> None:
    """Ajratish serverdan keladi, sahifaga yozilmaydi.

    Aks holda tariflar tartibi o'zgarganda "Eng ommabop" yorlig'i
    noto'g'ri kartada qolib ketardi.
    """
    js = SITE_JS.read_text(encoding="utf-8")
    html = SITE_HTML.read_text(encoding="utf-8")
    assert "plan.highlight" in js
    assert "plan.badge" in js
    assert "Eng ommabop" not in html, "yorliq HTMLga qotirilmasin"


def test_the_site_does_not_recompute_the_price_itself() -> None:
    """Sayt va hisob-faktura bitta so'mni ham farq qilmasligi kerak.

    Bungacha `site.js` `(cents * rate + 99) / 100` formulasini QAYTADAN
    yozgan edi.  Serverda yaxlitlash qadami qo'shilganda ikkalasi
    darrov uzoqlashib ketardi.
    """
    js = SITE_JS.read_text(encoding="utf-8")
    assert "monthly_uzs" in js, "so'm summasi serverdan olinsin"
    assert "usd_rate_uzs" not in js, "so'mga o'girish saytda takrorlanmasin"


def test_the_network_plan_shows_no_number_and_no_false_promise() -> None:
    """Tarmoqda narx yo'q va bitta login VA'DA QILINMAYDI.

    Ko'p do'konni bitta logindan ko'rish kodi hali yo'q
    (`portal_accounts.site_id` bitta) — sayt uni sotmasin.
    """
    js = SITE_JS.read_text(encoding="utf-8")
    assert 'price_kind === "on_request"' in js, "narxsiz tarif alohida yo'l bilan chizilsin"
    assert "plan.note" in js, "halollik izohi kartada chiqsin"


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


def test_every_plan_cta_leads_to_the_same_form() -> None:
    """Uchala tugma ham bitta formaga olib boradi.

    Sahifada bir nechta raqobatlashuvchi harakat bo'lmasin — bu 2026-08-17
    da hal qilingan muammo edi va uch karta bilan qaytishi oson.
    """
    js = SITE_JS.read_text(encoding="utf-8")
    html = SITE_HTML.read_text(encoding="utf-8")
    assert "data-plan-cta" in js
    assert js.count("goToForm(") >= 2
    # Tanlangan tarif yashirin maydonga yoziladi — Boshlang'ichni bosgan
    # mijoz Biznes obyektini olib qolmasin.
    assert 'id="plan"' in html
    assert 'getElementById("plan")' in js


def test_buy_button_does_not_promise_a_checkout() -> None:
    """Tugma to'lov sahifasini va'da qilmaydi — ariza yuboriladi."""
    source = SITE_JS.read_text(encoding="utf-8")
    assert "Sotib olishni boshlash" not in source


def test_pricing_section_has_a_noscript_fallback() -> None:
    html = SITE_HTML.read_text(encoding="utf-8")
    assert "<noscript>" in html
    assert "JavaScript" in html
    fallback = html[html.index("<noscript>") : html.index("</noscript>")]
    for plan in ("Boshlang‘ich", "Biznes", "Tarmoq"):
        assert plan in fallback, plan


def test_attendance_is_only_advertised_with_licensed_models() -> None:
    """Davomatni sotish faqat tijoratga ochiq model bilan.

    Bu tekshiruv `buffalo_l` (tadqiqot litsenziyasi) sababli qurilgan
    edi va "hech qachon eslatilmasin" degan ma'noda edi.  Modellar
    Apache-2.0 ga o'tkazilgach taqiq o'rinsiz — lekin BOG'LIQLIK
    qolishi kerak: litsenziya orqaga qaytsa, sotuv matni ham qaytsin.
    """
    from chaqimchi_ai.licensing.plans import PLANS
    from cloud import faces

    mentions = any("davomat" in item.lower() for item in PLANS["biznes"].includes)
    assert mentions is faces.MODELS_LICENSED_FOR_COMMERCIAL_USE, (
        "Tarif kartasidagi davomat va model litsenziyasi bir-biriga bog'liq bo'lishi kerak"
    )


def test_the_plan_cards_hardcode_no_feature_list() -> None:
    """Tarif kartalari serverdan keladi, HTMLda yozilmaydi.

    FAQ va noscript bundan mustasno: ular JS ishlamaganda ham
    o'qilishi kerak bo'lgan matn.
    """
    html = SITE_HTML.read_text(encoding="utf-8")
    grid = html[html.index('id="planGrid"') : html.index("<noscript>")]
    assert "<li>" not in grid, "punktlar API'dan chizilsin"
    assert "so‘m" not in grid, "narx HTMLga yozilmasin"
