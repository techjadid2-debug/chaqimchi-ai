"""React panelining xulq qoidalari.

Bu fayl eski `cloud/static/owner.html` va `admin.html` uchun yozilgan
qulflarning DAVOMI.  Qoidalar o'sha-o'sha — ularning har biri jonli
do'konda yeyilgan xatodan o'rganilgan; faqat qaraladigan kod
o'zgardi: bir faylli HTML o'rniga `frontend/src/` dagi React manbasi.

Nega manba matni tekshiriladi, brauzer emas: panelda brauzer sinovi
yo'q va uni qo'shish alohida ish.  Matn tekshiruvi hammasini ushlay
olmaydi, lekin AYNAN QAYTIB KELADIGAN xatolarni ushlaydi — ular
odatda "bir joyda o'chirilgan, boshqa joyda qaytgan" ko'rinishida
bo'ladi.

Ko'chirilmagan qoidalar va sabablari — `docs/ISH_DAFTARI.md`
("Panel qoidalari" bo'limi).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from cloud.i18n import tg

SRC = Path(__file__).resolve().parents[1] / "frontend" / "src"
SHELLS = Path(__file__).resolve().parents[1] / "frontend"
STATIC = Path(__file__).resolve().parents[1] / "cloud" / "static"

#: Do'kon egasiga ko'rinadigan fayllar.  `admin.tsx` bu ro'yxatda YO'Q:
#: admin panelini faqat biz ochamiz va u yerda ichki atamalar bo'lishi
#: mumkin.
OWNER_FILES = (
    "owner.tsx", "OwnerHome.tsx", "components.tsx", "EventEvidence.tsx",
    "Numbers.tsx", "Demography.tsx", "Heatmap.tsx", "VisionAgent.tsx",
    "SetupCameras.tsx", "GeometryEditor.tsx", "Connect.tsx", "EventTimeline.tsx",
)
#: Admin paneli fayllari — ichki atamalar mumkin, eski brend esa yo'q.
ADMIN_FILES = ("admin.tsx", "AdminHome.tsx", "AdminCustomer.tsx", "AdminTeam.tsx", "AdminSettings.tsx")


def src(name: str) -> str:
    return (SRC / name).read_text(encoding="utf-8")


def all_src() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(SRC.glob("*.ts*")))


def owner_src() -> str:
    return "\n".join(src(name) for name in OWNER_FILES)


# ── Kirish ────────────────────────────────────────────────────────────────


def test_link_login_uses_the_token_endpoint() -> None:
    """Havola server tomonda tekshiriladi va Telegram ID ishlatilmaydi.

    `?tg=<id>` oqimi ataylab olib tashlangan: ID ochiq ma'lumot, u bilan
    kirish mumkin bo'lsa istalgan odam panelga kirardi.
    """
    api = src("api.ts")
    assert "/api/v1/owner/auth/link" in api, "token server tekshiruvidan o'tsin"
    assert "access_token" in api, "token faqat serverdan olinsin"
    assert 'params.get("tg")' not in all_src(), "Telegram ID bilan kirish qaytmasin"
    assert "params.get('tg')" not in all_src()


def test_link_token_is_scrubbed_from_the_address_bar() -> None:
    """Token — credential; kirilgach manzil qatorida qolmasin."""
    assert "history.replaceState" in src("api.ts")


def test_deep_link_survives_the_login_redirect() -> None:
    """`?key=` tozalanganda `location.hash` ham yo'qolardi — ya'ni
    Telegramdan kelgan bo'limga havola har doim Bosh sahifaga tushardi.

    Shuning uchun tozalash `pathname` va `hash` ni SAQLAB qoladi.
    """
    api = src("api.ts")
    scrub = api[api.index('params.delete("key")'):]
    scrub = scrub[: scrub.index("}\n")]
    assert "window.location.pathname" in scrub, "yo'l saqlansin"
    assert "window.location.hash" in scrub, "bo'limga havola saqlansin"


def test_panel_supports_authenticated_telegram_mini_app() -> None:
    """Panel bot ichida ochiladi: SDK yuklanmasa `initData` kelmaydi va
    parolsiz kirish jimgina parol so'rashga aylanardi."""
    assert "/api/v1/owner/auth/telegram-webapp" in src("api.ts")
    assert "initData" in src("api.ts")
    assert "telegram-web-app.js" in (SHELLS / "owner.html").read_text(encoding="utf-8")


def test_login_submits_as_a_form() -> None:
    """Telefon klaviaturasidagi "Kirish" tugmasi ham ishlashi kerak —
    `click` tinglovchisi buni qo'llab-quvvatlamaydi."""
    components = src("components.tsx")
    login = components[components.index("export function LoginScreen"):]
    assert "<form onSubmit=" in login
    assert "event.preventDefault()" in login


def test_login_screen_has_no_one_time_code_leftovers() -> None:
    """Kirish ekranida UCHTA yo'l bor edi — Telegram tugmasi, login/parol
    va Telegram kod — mijoz esa qaysi biri o'ziniki ekanini bilmasdi.
    Endi bitta asosiy yo'l: login va parol."""
    text = all_src()
    for gone in ("otpRequestBtn", "otpVerifyBtn", "requestOtp", "verifyOtp",
                 "auth/request", "auth/verify"):
        assert gone not in text, f"eski kod bilan kirish qoldig'i: {gone}"


def test_the_shopkeeper_is_never_asked_for_a_telegram_id() -> None:
    """A'zo qo'shish uchun RAQAMLI Telegram ID so'ralardi.  Do'kon egasi
    na o'ziniki, na xodiminikini biladi — funksiya amalda ishlamasdi.
    Endi panel bir martalik havola beradi, bot o'zi qo'shadi."""
    owner = src("owner.tsx")
    assert "/api/v1/owner/telegram-invite" in owner
    assert "123456789" not in owner, "raqamli ID maydoni qaytmasin"


# ── Mobil va teginish ─────────────────────────────────────────────────────


def test_tap_targets_are_big_enough() -> None:
    """34px barmoq uchun kichik — 40px eng kichik ishonchli o'lcham."""
    css = src("styles.css")
    button = css[css.index(".btn {"): css.index("}", css.index(".btn {"))]
    assert "min-height: 44px" in button
    assert css.count("@media") >= 4, "telefon, planshet va kompyuter uchun qoidalar"


def test_canvas_accepts_touch() -> None:
    """`touch-action` bo'lmasa kanvasni sudrash o'rniga sahifa siljiydi —
    ya'ni pol burchaklarini telefondan to'g'irlab bo'lmaydi."""
    assert "touch-action" in src("styles.css")


def test_media_opens_inline_not_in_a_popup() -> None:
    """`window.open(blob)` popup-blockerda yutilardi va xato jim qolardi.
    Blob URL ham bo'shatilsin — aks holda xotira oqadi."""
    assert "window.open(" not in owner_src(), "popup qaytmasin"
    assert "revokeObjectURL" in src("EventEvidence.tsx")


# ── Funksiya darvozalari ──────────────────────────────────────────────────


def test_panel_has_no_raw_json_editors() -> None:
    """Lines/Zones JSON textarealar oddiy mijozni cho'chitadi — geometriya
    faqat chizish vositasida bo'lsin."""
    text = all_src()
    assert "linesJson" not in text
    assert "zonesJson" not in text
    # `<textarea>` faqat AI yordamchisining savol maydonida bo'lsin.
    for name in OWNER_FILES:
        if name == "VisionAgent.tsx":
            continue
        assert "<textarea" not in src(name), f"{name}: xom matn maydoni"


def test_the_camera_role_is_offered_but_never_forced() -> None:
    """Rol MAJBURIY bo'lmasin.

    Tarix ikki bosqichli va ikkalasi ham qulflanishi kerak:
    1. Ilgari ro'yxatda bo'sh variant yo'q edi va birinchi "Saqlash"
       bosilishi bilan hamma kamera jimgina "Kirish" bo'lib qolardi —
       shu sababdan rol maydoni butunlay olib tashlangan edi.
    2. 2026-08-22 da rol qaytarildi, lekin boshqa shartda: tizim
       taklif qiladi, odam tasdiqlaydi (`af08057`).  Ya'ni "Rol
       tanlanmagan" varianti bo'lishi va standart qiymat BO'SH
       bo'lishi shart.

    Shu test birinchi xatoning qaytishini to'sadi.
    """
    setup = src("SetupCameras.tsx")
    assert 'name="role"' in setup, "rol maydoni bor"
    assert 'defaultValue=""' in setup, "standart qiymat bo'sh bo'lsin"
    assert '<option value="">' in setup, "«Rol tanlanmagan» varianti bo'lsin"
    # Nom maydoni ham bo'sh boshlansin: "Kirish eshigi" jim standarti
    # hamma kamerani kirish qilib ko'rsatib qo'yardi.
    assert 'placeholder={t("panel.setup.name_placeholder")}' in setup
    assert "Masalan: Kassa" in tg("uz", "panel.setup.name_placeholder")


def test_panel_hides_the_unobservable_occupancy_limit() -> None:
    """Ko'rinmaydigan sozlama panelda turmasin: `occupancy_exceeded`
    hisobotda ham, hodisa filtrida ham yo'q va botga bormaydi — raqamni
    o'zgartirgan mijoz hech narsa sezmasdi."""
    assert "Odam limiti" not in owner_src()


def test_live_view_uses_its_own_endpoint() -> None:
    """Jonli kadr tayanch rasmni — ya'ni xarita fonini — almashtirmasin."""
    assert "/live-frame" in src("owner.tsx")


def test_plan_locked_sections_show_a_lock_not_an_error() -> None:
    """Tarifda yo'q bo'lim YO'QOLMASIN, qulflangan holda ko'rinsin.

    Yo'qolgan bo'lim mijozga "buzilibdi" degan taassurot beradi, qulf
    esa "ko'tarish mumkin" deydi (`enes/licensing/plans.py`
    dagi izohga qarang).
    """
    assert "PlanLock" in src("components.tsx")
    for name in ("Demography.tsx", "Heatmap.tsx", "EventEvidence.tsx"):
        assert "hasFeature" in src(name), f"{name}: tarif darvozasi yo'q"


def test_employee_photos_survive_an_iphone() -> None:
    """iPhone galereyadan HEIC beradi, server esa faqat JPEG/PNG qabul
    qiladi (415).  Konvertatsiyasiz do'kon egasi xodim rasmini
    telefonidan umuman yuklay olmasdi."""
    assert "toJpeg" in src("api.ts"), "brauzerda JPEG ga aylantirish bo'lsin"
    owner = src("owner.tsx")
    assert "toJpeg(" in owner, "yuklashdan oldin aylantirilsin"
    assert 'accept="image/*"' in owner, "telefonda kamera/galereya ochilsin"
    # `api()` chaqiruvchi bergan Content-Type ni o'chirib yubormasin —
    # aks holda rasm `application/json` bo'lib ketadi va server 415 beradi
    # (eski panelda aynan shu xato bo'lgan).
    assert '!headers.has("Content-Type")' in src("api.ts")


# ── Ma'lumot ko'rsatish ───────────────────────────────────────────────────


def test_event_list_is_not_a_hundred_rows() -> None:
    """101 qator sahifaning 60% ini egallardi."""
    owner = src("owner.tsx")
    assert "limit=100" not in owner
    assert re.search(r"limit=\d{1,2}\b", owner), "hodisa ro'yxati cheklansin"


def test_the_heatmap_explains_its_colours() -> None:
    """Xarita rangi qat'iy qizil emas, ko'kdan qizilgacha — va izohli.

    Ilgari bitta qizil rangning faqat shaffofligi o'zgarardi: 0.25 va
    0.45 shaffoflik ko'zga deyarli bir xil ko'rinadi.  Rang shkalasi
    (legenda) esa umuman yo'q edi — mijoz rangni raqamga bog'lay
    olmasdi.
    """
    heatmap = src("Heatmap.tsx")
    assert "heat-legend" in heatmap, "rang shkalasi ko'rsatilsin"
    assert ".heat-legend" in src("styles.css")
    assert "rgba(220, 38, 38" not in heatmap, "eski qotirilgan qizil qaytmasin"


def test_lists_have_empty_states() -> None:
    """Yangi bazada bo'limlar bo'm-bo'sh emas, nima qilish kerakligini
    aytadigan matn bilan ochilsin."""
    assert all_src().count("<EmptyState") >= 10


# ── Matn sifati ───────────────────────────────────────────────────────────


def test_panel_has_no_inline_event_handlers() -> None:
    """`onclick="..."` bilan ID string ichiga qo'yilardi — qochirish
    unutilsa buziladi.  JSX'da hodisa ishlovchisi jingalak qavsda
    bo'ladi; qo'shtirnoqli variant xom HTML yozilganini bildiradi."""
    found = re.search(r'\son(click|change|input|submit)\s*=\s*"', all_src())
    assert found is None, f"inline hodisa ishlovchisi: {found.group(0) if found else ''}"


def test_the_old_brand_stays_off_the_panels() -> None:
    """Rebrend (2026-09-08): mijoz va admin ko'radigan matnda «Chaqimchi»
    qolmasin.  Brauzer kalitlari (`chaqimchi_owner_token_v2`) va env
    nomlari (`ENES_*`) F6 da o'zgaradi — ular istisno."""
    for name in OWNER_FILES + ADMIN_FILES + ("Connect.tsx",):
        found = re.search(r"Chaqimchi(?![_A-Z])", src(name))
        assert found is None, f"{name}: eski brend matni — {found.group(0) if found else ''}"


def test_the_internal_codename_stays_off_the_owner_panel() -> None:
    """Ichki kod nomi mijozga ko'rinmasin."""
    assert "Sotqin" not in owner_src()


def test_one_sku_has_one_name() -> None:
    """Mijozga «Lite» sotiladi, to'lov sahifasida esa «Sotqin R1»
    yozilardi — bitta mahsulot, uch xil nom."""
    text = all_src()
    assert "Sotqin R1" not in text and "Sotqin Base" not in text


def test_panel_speaks_plain_uzbek() -> None:
    """Ichki jargon ekranga chiqmasin."""
    text = owner_src()
    for word in ("Production tayyorligi", "Draftni", "Biznes preset",
                 "Onboarding", "Legacy", "ENES_PUBLIC_URL", "poll'da"):
        assert word not in text, f"jargon qaytib kelgan: «{word}»"


def test_the_customer_can_reach_a_human_from_every_dead_end() -> None:
    """Panel to'rt joyda "bizga yozing" deydi — qayerga yozishni ham
    ko'rsatsin.  Ilgari aloqa havolasi faqat KIRISH ekranida edi va u
    kirgandan keyin butunlay yashirinardi.

    Raqam sayt bilan bir xil bo'lishi shart: ikki xil raqam eng
    bilinmaydigan xatolardan biri.
    """
    components = src("components.tsx")
    assert 'SUPPORT_PHONE = "+998932225070"' in components
    assert "tel:${SUPPORT_PHONE}" in components
    site = (STATIC / "site.html").read_text(encoding="utf-8")
    assert "tel:+998932225070" in site, "saytdagi raqam bilan bir xil bo'lsin"


# ── Admin support vositalari (eski `admin.html` dan ko'chirilgan) ─────────
#
# 2026-09-08 (F4a): eski adminning 15+ vositasi `AdminCustomer.tsx`,
# `AdminTeam.tsx` va `AdminSettings.tsx` ga ko'chdi.  Quyidagi qulflar
# ular qaytib yo'qolib qolmasligini qo'riqlaydi.

def admin_src() -> str:
    return "\n".join(src(name) for name in ADMIN_FILES)


def test_the_admin_can_fix_a_shop_remotely() -> None:
    """Admin do'konni masofadan tuzata olsin (2026-08-21 qarori).

    Bungacha do'kon sozlanmagan bo'lsa uni masofadan tuzatishning yo'li
    yo'q edi — jonli do'konda `lines: []` bo'lib qolgan va kirish soni
    kuniga 5 ta ko'rsatilgan.  `clean_chains` esa yetim zanjirlar va
    vaqt mintaqasi tuzatilgandan keyingi yagona masofaviy qayta ishga
    tushirish yo'li; `features/approve` — sotuv darvozasi.
    """
    admin = admin_src()
    for endpoint in ("/camera-inventory", "/jobs/clean-chains", "/jobs/benchmark",
                     "/diagnostics", "/features/approve", "/features/quote", "/onboarding",
                     "/pairing", "/update-policy", "/windows-releases", "/login-link",
                     "/installer-assignments", "/alerts/test", "/updates-paused",
                     "/payments/providers", "/faces", "/extend", "/plan"):
        assert endpoint in admin, f"React adminda yo'q: {endpoint}"


def test_the_admin_uses_no_native_dialogs() -> None:
    """`prompt()`/`confirm()` — eski admin qoidasi (2026-08-19).

    Brauzer oynasida "auto" yoki "naqd" deb YOZISH kerak edi — bitta harf
    xato, amal bajarilmasdi.  React adminda `window.confirm` 2026-09-07 da
    qaytib kelgan edi (`PaymentsPage`); endi tasdiqlash `ConfirmDialog`,
    tanlov modal ichida tugma bilan.
    """
    admin = admin_src()
    found = re.search(r"window\.(prompt|confirm|alert)\s*\(", admin)
    assert found is None, f"brauzer oynasi qaytib kelgan: {found.group(0) if found else ''}"
    assert "useConfirm(" in admin, "tasdiqlash o'z oynasi bilan bo'lsin"


def test_the_customer_page_is_deep_linkable() -> None:
    """«Diqqat talab qiladi» ro'yxatidan mijozga TO'G'RIDAN-TO'G'RI o'tilsin
    va brauzerning Orqasi ishlasin — `/admin/customers/<id>`."""
    router = src("router.ts")
    assert "param" in router, "ikkinchi segment o'qilmaydi"
    admin = src("admin.tsx")
    assert 'navigate("customers", site.id)' in admin, "qidiruvdan mijozga chuqur havola yo'q"
    assert "<AdminCustomer" in admin


def test_the_geometry_editor_serves_both_panels() -> None:
    """Chizish mantiqi bitta: ega o'zinikini, admin masofadan.  Ikki nusxa
    bo'lsa ular albatta ajralib ketardi."""
    editor = src("GeometryEditor.tsx")
    assert 'kind === "admin"' in editor
    assert "/api/v1/admin/sites/" in editor and "/api/v1/owner/config" in editor
    assert 'kind="admin"' in src("AdminCustomer.tsx")


# ── Dizayn tizimi ─────────────────────────────────────────────────────────


def test_both_panels_share_one_design_system() -> None:
    """Mijoz paneli va admin bitta uslub faylidan kelsin — aks holda
    ikkisi asta-sekin ajralib ketadi."""
    for entry in ("owner.tsx", "admin.tsx"):
        assert 'import "./styles.css"' in src(entry), f"{entry}: umumiy uslub yo'q"


def test_the_stylesheet_has_no_unterminated_comment() -> None:
    """Yopilmagan `/*` o'zidan keyingi HAMMA qoidani yeb qo'yadi va
    sahifa uslubsiz ochiladi."""
    for path in (SRC / "styles.css", STATIC / "site.css", STATIC / "tokens.css"):
        text = path.read_text(encoding="utf-8")
        assert text.count("/*") == text.count("*/"), f"{path.name}: izoh yopilmagan"


@pytest.mark.parametrize("shell", ["owner.html", "admin.html"])
def test_shells_carry_the_new_brand(shell: str) -> None:
    """Qobiqda eski brend qoldig'i bo'lmasin."""
    text = (SHELLS / shell).read_text(encoding="utf-8")
    assert "chaqimchi-logo" not in text, "eski logotip havolasi qoldi"
    assert 'content="#4285f4"' not in text, "eski brend ko'ki qoldi"
