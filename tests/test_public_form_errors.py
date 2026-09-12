"""Saytdagi formada xato bo'lsa foydalanuvchi MATN o'qisin.

Nega bu test bor.  FastAPI validatsiya xatosida `detail` ni RO'YXAT
qilib qaytaradi (`[{"loc": …, "msg": …, "type": …}]`).  Sayt skripti
esa uni `new Error(body.detail)` ga uzatardi va JavaScript obyektni
satrga aylantirib **`[object Object]`** yozardi.

Triggeri oson edi: telefon maydonida `minlength` yo'q, server esa
`min_length=5` talab qiladi — ya'ni raqamni qisqa kiritgan har mijoz
tushunarsiz texnik matn ko'rardi va formani tashlab ketardi.  Bu sotuv
voronkasining eng tepasidagi forma.

Himoya ikki qatlamli va ikkalasi ham tekshiriladi: server matn
qaytaradi, klient esa satr bo'lmagan `detail` ni ko'rsatmaydi.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "cloud" / "static"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ENES_CLOUD_ADMIN_KEY", "test-admin")
    monkeypatch.setenv("ENES_OWNER_JWT_SECRET", "o" * 64)
    monkeypatch.setenv("ENES_PORTAL_JWT_SECRET", "p" * 64)
    monkeypatch.setattr("cloud.main.DB_PATH", tmp_path / "cloud.db")
    monkeypatch.setattr("cloud.main._store", None)
    monkeypatch.setattr("cloud.main._event_store", None)
    monkeypatch.setattr("cloud.main._event_store_key", None)
    from cloud.main import app

    return TestClient(app)


def _detail(payload: Dict[str, Any]) -> Any:
    return payload.get("detail")


# ── Server: ochiq API matn qaytaradi ───────────────────────────────────


def test_a_short_phone_gets_a_readable_answer(client: TestClient) -> None:
    """Aynan foydalanuvchi ko'rgan holat: bitta raqamli telefon."""
    response = client.post("/api/v1/public/leads", json={"phone": "1", "consent": True})

    assert response.status_code == 422
    detail = _detail(response.json())
    assert isinstance(detail, str), f"`detail` hamon ro'yxat: {detail!r}"
    assert "[object" not in detail
    assert len(detail) > 10, "matn bo'sh yoki juda qisqa"


def test_the_answer_follows_the_request_language(client: TestClient) -> None:
    """Ruscha sahifadagi forma ruscha xato ko'rsatsin."""
    answers = {}
    for lang in ("uz", "ru", "en"):
        response = client.post(
            "/api/v1/public/leads", json={"phone": "1"}, headers={"X-Lang": lang}
        )
        answers[lang] = _detail(response.json())

    assert all(isinstance(text, str) for text in answers.values())
    assert len({*answers.values()}) == 3, f"tillar bir xil matn berdi: {answers}"


def test_the_consent_and_phone_checks_are_translated(client: TestClient) -> None:
    """Qo'lda tekshirilgan shartlar ham katalogdan kelsin."""
    no_consent = client.post(
        "/api/v1/public/leads",
        json={"phone": "+998901234567", "consent": False},
        headers={"X-Lang": "ru"},
    )
    assert no_consent.status_code == 422
    assert "рози" not in _detail(no_consent.json()).lower(), "o'zbekcha matn qolgan"

    bad_phone = client.post(
        "/api/v1/public/leads",
        json={"phone": "+++++", "consent": True},
        headers={"X-Lang": "en"},
    )
    assert bad_phone.status_code == 422
    assert "phone" in _detail(bad_phone.json()).lower()


def test_the_device_and_panel_apis_keep_their_structured_detail(client: TestClient) -> None:
    """Faqat `/api/v1/public/*` matnga aylanadi.

    Panel `frontend/src/api.ts` da `detail` ni MAYDON bo'yicha o'qib
    qaysi maydon xato ekanini ko'rsatadi — uni satrga aylantirish
    tashxisni yo'qotardi.
    """
    response = client.post("/api/v1/devices/claim", json={})

    assert response.status_code == 422
    assert isinstance(_detail(response.json()), list), (
        "panel/qurilma API'si strukturali `detail` ni yo'qotdi"
    )


# ── Klient: ikkinchi qator himoya ──────────────────────────────────────


def test_the_site_script_never_renders_a_raw_object() -> None:
    """Eski javob keshdan kelsa ham matn chiqsin."""
    for name in ("site.js", "edu.js"):
        code = (STATIC / name).read_text(encoding="utf-8")
        assert 'typeof' in code and 'detail === "string"' in code, (
            f"{name}: `detail` satr ekani tekshirilmaydi"
        )


def test_the_edu_form_shows_its_errors_in_red() -> None:
    """`err` sinfi `site.css` da YO'Q — xato matni kulrang chiqardi."""
    css = (STATIC / "site.css").read_text(encoding="utf-8")
    edu = (STATIC / "edu.js").read_text(encoding="utf-8")

    assert ".form-status.error" in css
    assert '"form-status err"' not in edu, "mavjud bo'lmagan sinf ishlatilyapti"
    assert '"form-status error"' in edu


def test_the_edu_form_validates_before_sending() -> None:
    """Forma `novalidate` — tekshiruv QO'LDA chaqirilishi shart."""
    edu_html = (STATIC / "edu.html").read_text(encoding="utf-8")
    edu_js = (STATIC / "edu.js").read_text(encoding="utf-8")

    assert "novalidate" in edu_html, "forma o'zgargan — testni ham yangilang"
    assert "reportValidity()" in edu_js, "bo'sh maydon bilan jo'natiladi"


def test_no_personal_telegram_handle_in_error_messages() -> None:
    """Xato matnidagi shaxsiy nom «bizga yozib qo'ying» degan
    noto'g'ri taassurot berardi — rasmiy kanal futerda va aloqa
    sahifasida bor."""
    edu = (STATIC / "edu.js").read_text(encoding="utf-8")
    assert "@fibotai" not in edu


# ── Forma maydonlari server qoidasi bilan bir xil ──────────────────────


def test_the_phone_fields_match_the_server_rule() -> None:
    """Brauzer tekshiruvi serverdan yumshoqroq bo'lsa forma jo'natiladi,
    server 422 beradi va mijoz sababini bilmaydi."""
    from cloud.main import PublicLeadBody

    field = PublicLeadBody.model_fields["phone"]
    minimum = next(item.min_length for item in field.metadata if hasattr(item, "min_length"))

    for name in ("site.html", "site.ru.html", "site.en.html", "edu.html"):
        html = (STATIC / name).read_text(encoding="utf-8")
        assert html.count('name="phone"') >= 1
        assert f'minlength="{minimum}"' in html, f"{name}: `minlength` yo'q yoki boshqa son"


# ── Yuklab olish qatori JS'siz ham gapirsin ────────────────────────────


def test_the_download_row_is_never_empty() -> None:
    """JS o'chiq yoki API javob bermasa hero'da BO'SH oq maydon qolardi.

    `#downloadReady` ham, forma ham `hidden` bilan boshlanardi va
    ikkinchisini faqat skript ko'rsatardi.  `install.html` da naqsh
    to'g'ri qilingan (`#guideDownloadPending` standart holda ko'rinadi) —
    bosh sahifa unutilgan edi.
    """
    for name in ("site.html", "site.ru.html", "site.en.html"):
        html = (STATIC / name).read_text(encoding="utf-8")
        form = html[html.index('id="notifyForm"'): html.index('id="notifyForm"') + 120]
        assert "hidden" not in form, f"{name}: forma standart holda yashirin"
        assert "<noscript>" in html, f"{name}: JS'siz holat uchun matn yo'q"


def test_the_install_page_does_not_pin_a_version() -> None:
    """Zaxira matnda `0.6.16` qotirilgan edi va o'n versiya orqada
    qolgan — mijoz uni «joriy» deb o'qirdi."""
    html = (STATIC / "install.html").read_text(encoding="utf-8")
    block = html[html.index('id="guideFileName"'): html.index('id="guideFileName"') + 90]

    assert "0.6." not in block, "zaxira matnda versiya raqami qolgan"
    assert "ENES_Setup" in block


# ── Futer tili ─────────────────────────────────────────────────────────


def test_the_home_page_footer_follows_the_page_language() -> None:
    """Bosh sahifa futeri partialdan NUSXA edi va havolalar qotirilgan:
    ruscha sahifada futer o'zbekcha sahifalarga olib borardi."""
    for lang, prefix in (("ru", "/ru"), ("en", "/en")):
        html = (STATIC / f"site.{lang}.html").read_text(encoding="utf-8")
        footer = html[html.rindex("<footer"):]

        for page in ("status", "hamkorlik", "aloqa"):
            assert f'href="{prefix}/{page}"' in footer, f"{lang}: /{page} tarjima qilinmagan"
            assert f'href="/{page}"' not in footer, f"{lang}: o'zbekcha /{page} qolgan"


def test_the_home_page_uses_the_shared_footer() -> None:
    """Nusxa qaytib kelmasin — u aynan shu xatoni qayta keltiradi."""
    source = (ROOT / "cloud" / "site" / "index.html").read_text(encoding="utf-8")
    assert "{{include:partials/footer.html}}" in source
    assert '<footer class="band-dark">' not in source, "futer yana nusxa qilingan"


# ── O'lik langar ───────────────────────────────────────────────────────


def test_no_page_links_to_a_missing_anchor() -> None:
    """`__TELEGRAM_REGISTER_URL__` zaxirasi `/#pilot` edi — saytda
    bunday `id` umuman yo'q (bo'lim `#aloqa`)."""
    main = (ROOT / "cloud" / "main.py").read_text(encoding="utf-8")
    assert "/#pilot" not in main, "o'lik langar qaytib kelgan"

    home = (STATIC / "site.html").read_text(encoding="utf-8")
    assert 'id="aloqa"' in home, "`#aloqa` bo'limi yo'qolgan — zaxira langar sinadi"


def test_the_bot_name_comes_from_the_server(client: TestClient) -> None:
    """Nom sahifada qotirilgan edi: bot almashganda havola yangi botga,
    matn esa eskisiga ishora qilardi."""
    source = (ROOT / "cloud" / "site" / "aloqa.html").read_text(encoding="utf-8")
    assert "__TELEGRAM_BOT_NAME__" in source
    assert "@enes_monitoring_bot" not in source, "nom hamon qotirilgan"

    rendered = client.get("/aloqa").text
    assert "__TELEGRAM_BOT_NAME__" not in rendered, "o'rinbosar almashtirilmagan"


# ── Holat sahifasi: nosozlikda QAYSI qism yiqilganini aytadi ───────────


def test_the_status_page_lists_the_checks() -> None:
    """Server `checks[]` ni allaqachon qaytarardi, sahifa esa javobni
    TASHLAB yuborib faqat «ishlayapti / aloqa yo'q» derdi — nosozlikda
    mijoz ham, biz ham qaysi qism yiqilganini bu sahifadan bilib
    olmasdik."""
    js = (STATIC / "status.js").read_text(encoding="utf-8")
    html = (STATIC / "status.html").read_text(encoding="utf-8")

    assert 'id="checksList"' in html, "ro'yxat uchun joy yo'q"
    assert "payload.checks" in js, "javobdagi tekshiruvlar o'qilmaydi"
    # Ichki nom tarjimasi bo'lmasa o'sha nom chiqsin: yangi tekshiruv
    # qo'shilganda sahifa uni JIM tashlab yuborishi eng yomon natija.
    assert "|| name" in js


def test_the_status_page_turns_red(tmp_path: Path) -> None:
    """Ilgari faqat `online` sinfi bor edi va nosozlikda chiroq KULRANG
    qolardi — aynan «hali tekshirilmoqda» bilan bir xil ko'rinish."""
    css = (STATIC / "site.css").read_text(encoding="utf-8")
    js = (STATIC / "status.js").read_text(encoding="utf-8")

    assert ".status-light.down" in css
    assert 'classList.add("down")' in js


def test_the_status_page_gives_up_after_a_timeout() -> None:
    """Timeoutsiz sahifa «Tekshirilmoqda…» da ABADIY qotib qolardi —
    brauzer so'rovni o'zi uzmaydi."""
    js = (STATIC / "status.js").read_text(encoding="utf-8")

    assert "AbortController" in js
    assert "8000" in js, "kutish muddati yo'q"
    assert "AbortError" in js, "timeout xatosi oddiy uzilishdan ajratilmagan"


def test_the_status_page_distinguishes_partial_failure() -> None:
    """«Aloqa yo'q» va «bir qismi ishlamayapti» — boshqa-boshqa holat
    va mijoz uchun farqi bor."""
    js = (STATIC / "status.js").read_text(encoding="utf-8")
    assert "partialTitle" in js


# ── Telefon menyusi ────────────────────────────────────────────────────


def test_the_phone_menu_closes_on_an_outside_tap() -> None:
    """Menyuni ochib sahifaning boshqa joyiga bosgan odam uni ochiq
    qoldirib ketardi va u telefonda kontentning yarmini to'sardi."""
    js = (STATIC / "site.js").read_text(encoding="utf-8")

    assert "pointerdown" in js, "tashqariga bosish yopmaydi"
    assert "summary.focus()" in js, "Escape'dan keyin fokus qaytmaydi"


# ── Jadval, tegish maydoni, tanlagich ──────────────────────────────────


def test_the_legal_tables_are_styled_and_scrollable() -> None:
    """`site.css` da `table` uchun BITTA ham qoida yo'q edi: yuridik
    hujjatdagi jadvallar telefonda ekrandan chiqib ketardi."""
    css = (STATIC / "site.css").read_text(encoding="utf-8")

    assert "\ntable {" in css, "umumiy jadval qoidasi yo'q"
    assert "border-collapse" in css
    assert "overflow-x: auto" in css, "telefonda jadval aylanmaydi"


def test_the_footer_links_are_big_enough_to_tap() -> None:
    """Futer havolalari ~20 px edi — telefonda barmoq bilan bosishga
    juda kichik."""
    css = (STATIC / "site.css").read_text(encoding="utf-8")
    rule = css[css.index("footer > div a {"):]
    rule = rule[: rule.index("}")]

    assert "min-height: 40px" in rule, f"tegish maydoni kichik: {rule}"


def test_the_calculator_select_has_a_name_and_a_tap_target() -> None:
    """`<label>` ichida ikkita boshqaruv bor edi: brauzer yorliqni faqat
    birinchisiga bog'laydi va skrinrider tanlagichni «nomsiz» deb
    o'qirdi."""
    js = (STATIC / "site.js").read_text(encoding="utf-8")
    css = (STATIC / "site.css").read_text(encoding="utf-8")

    assert 'aria-label="${label}"' in js
    rule = css[css.index(".calc-feature select {"):]
    assert "min-height: 40px" in rule[: rule.index("}")]


# ── Til tanlagich va yetib boradigan sahifalar ─────────────────────────


def test_a_uz_only_page_does_not_pretend_to_have_translations() -> None:
    """Band bosilganda odam o'sha tildagi BOSH sahifaga tushardi —
    buzilgan havola bilan bir xil taassurot."""
    offer = (STATIC / "oferta.html").read_text(encoding="utf-8")
    switch = offer[offer.index('class="lang-menu"'):]
    switch = switch[: switch.index("</details>")]

    assert 'aria-disabled="true"' in switch, "tarjimasiz band havola bo'lib qolgan"
    assert 'href="/ru/"' not in switch, "ruscha band bosh sahifaga olib boradi"


def test_every_page_can_reach_the_education_page() -> None:
    """`/edu` ga havola FAQAT bosh sahifada edi — ichki sahifadan unga
    yetib bo'lmasdi."""
    for name in ("oferta.html", "status.html", "install.html", "site.ru.html"):
        html = (STATIC / name).read_text(encoding="utf-8")
        assert 'href="/edu"' in html, f"{name}: `/edu` ga havola yo'q"


def test_every_indexable_page_has_a_social_card() -> None:
    """Mijoz Telegramda `/oferta` yoki `/install` havolasini ulashsa
    karta nomsiz va rasmsiz chiqardi — «ishonchsiz havola» taassuroti,
    va aynan shu sahifalar sotuv jarayonida ulashiladi."""
    for name in ("oferta.html", "privacy.html", "install.html", "edu.html", "site.html"):
        html = (STATIC / name).read_text(encoding="utf-8")
        assert 'property="og:title"' in html, f"{name}: OG kartasi yo'q"
        assert 'rel="canonical"' in html, f"{name}: canonical yo'q"
        # `og:url` va `canonical` bitta manzildan bo'lsin.
        canonical = html[html.index('rel="canonical" href="') + 22:]
        canonical = canonical[: canonical.index('"')]
        assert f'property="og:url" content="{canonical}"' in html, f"{name}: manzillar ajralgan"


def test_internal_links_use_the_canonical_privacy_url() -> None:
    """`/privacy` va `/maxfiylik` bitta sahifa; canonical `/maxfiylik`.
    Ichki havola non-canonical manzilga ishora qilmasin."""
    for path in sorted((ROOT / "cloud" / "site").glob("*.html")):
        assert 'href="/privacy"' not in path.read_text(encoding="utf-8"), path.name
