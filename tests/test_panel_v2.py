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

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "frontend" / "src"
SHELLS = ROOT / "frontend"
STATIC = ROOT / "cloud" / "static"
#: Chizish vositasi cloud'dan TASHQARIDA turadi: Windows paketi `cloud/` ni
#: ko'chirmaydi, ya'ni bundle qilingan nusxa qurilmadagi bilan ajralib ketardi.
ZONE_EDITOR = (
    Path(__file__).resolve().parents[1] / "enes" / "local" / "static" / "zone-editor.js"
)

#: Do'kon egasiga ko'rinadigan fayllar.  `admin.tsx` bu ro'yxatda YO'Q:
#: admin panelini faqat biz ochamiz va u yerda ichki atamalar bo'lishi
#: mumkin.
OWNER_FILES = (
    "owner.tsx", "OwnerHome.tsx", "components.tsx", "EventEvidence.tsx",
    "Numbers.tsx", "Demography.tsx", "Heatmap.tsx", "VisionAgent.tsx",
    "SetupCameras.tsx", "GeometryEditor.tsx", "Connect.tsx", "EventTimeline.tsx",
    "Analytics.tsx", "overview.tsx", "Cameras.tsx", "CameraDetail.tsx",
)
#: Admin paneli fayllari — ichki atamalar mumkin, eski brend esa yo'q.
ADMIN_FILES = ("admin.tsx", "AdminHome.tsx", "AdminCustomer.tsx", "AdminTeam.tsx", "AdminSettings.tsx")
#: O'rnatuvchi (usta) paneli.  2026-09-12 da `cloud/static/installer.html`
#: dan ko'chdi — u oxirgi eski statik panel edi va shu sababdan ikki UI
#: ishidan hech narsa olmagan: faqat o'zbekcha, telefon uchun QA
#: qilinmagan, xato holatlari yo'q.  Usta OBYEKTDA, telefonda ishlaydi,
#: ya'ni umumiy qulflar (brauzer oynasi, modul darajasidagi `t()`,
#: yuklash boilerplate'i) unga ham tegishli.
INSTALLER_FILES = ("installer.tsx", "InstallerJobs.tsx", "InstallerCamera.tsx")


def src(name: str) -> str:
    return (SRC / name).read_text(encoding="utf-8")


def all_src() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(SRC.glob("*.ts*")))


def owner_src() -> str:
    return "\n".join(src(name) for name in OWNER_FILES)


def installer_src() -> str:
    return "\n".join(src(name) for name in INSTALLER_FILES)


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


def test_page_actions_stay_usable_on_phones() -> None:
    """Sahifa tugmalari telefonda YASHIRILMASIN.

    2026-09-11 QA: `.page-actions { display: none; }` (≤480 px) kamera
    «Jonli/AI», dalillar «Rasm/Klip», «Xodim qo'shish» va hisobot yuklash
    tugmalarini telefonda butunlay olib tashlagan edi; `.btn span
    { display: none; }` (≤760 px) esa tugmani nomsiz ikonkaga aylantirardi.
    Tugma sarlavha ostiga tushadi, lekin turadi."""
    css = src("styles.css")
    assert ".page-actions { display: none; }" not in css
    assert ".page-actions .btn span { display: none; }" not in css
    assert ".page-header .page-actions { width: 100%; flex-wrap: wrap; }" in css
    assert ".event-row .event-name { flex: 1 1 100%; }" in css, "dalil qatorida nom to'liq qolsin"
    # Til/tema telefonda «Yana» menyusida — filial tanlagichga joy qolsin.
    assert ".topbar .lang-switch, .topbar .theme-toggle { display: none; }" in css
    assert "drawer-tools" in src("owner.tsx")
    # Tablar qatori aylanishini ko'rsatadi (so'nuvchi chet).
    assert "mask-image" in css[css.index(".tabs {"):]


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
    """Jonli kadr tayanch rasmni — ya'ni xarita fonini — almashtirmasin.
    (Kamera plitkalari 2026-09-11 da `Cameras.tsx` ga ko'chdi.)"""
    assert "/live-frame" in src("Cameras.tsx")


def test_home_shows_five_stat_cards() -> None:
    """Bosh sahifada DOIM beshta ko'rsatkich (dizayn-3): karta soni
    3–5 orasida o'zgarsa 5 ustunli to'r bittasini yolg'iz qoldirardi.
    Yo'q ko'rsatkich o'rnida o'rinbosar (navbat, gavjum soat), yolg'on
    nol emas — bo'lmasa «—» va izoh."""
    home = src("OwnerHome.tsx")
    assert 'className="metric-grid metric-grid-5"' in home
    assert "metric-grid-${cardCount}" not in home
    assert home.count("<StatCard") >= 7, "5 karta + o'rinbosarlar"
    assert "panel.home.stat.no_data_yet" in home


def test_event_rows_carry_thumbnails() -> None:
    """Hodisa ro'yxatida kadr rasmchasi — faqat rasmi BOR hodisada:
    har qatorga so'rov yuborilsa kirish-chiqishlar 404 bilan jurnalni
    to'ldiradi.  Do'kon nomi topbarda bitta chipda."""
    home = src("OwnerHome.tsx")
    assert "function EventThumb" in home and "/snapshot" in home
    assert "has_snapshot" in home
    assert "panel.home.recent.title" in home
    owner = src("owner.tsx")
    assert "topbar-user" in owner and "sidebar-user" not in owner


def test_camera_detail_is_deep_linkable() -> None:
    """Alohida kamera sahifasi manzildan ochilsin: `/owner/cameras/camera-01/alerts`.

    Ikkinchi segment tab nomi ham, kamera ID ham bo'lishi mumkin —
    naqsh server bilan bir xil; uchinchi segment kamera tabi.  Kamera
    tablari `TABS` ga QO'SHILMAYDI (u bo'lim tablari ro'yxati)."""
    router = src("router.ts")
    assert "sub" in router and "[active, navigate, param, sub]" in router
    owner = src("owner.tsx")
    assert "CAMERA_ID = /^camera-\\d{2}$/" in owner
    assert "<CameraDetail" in owner and "subRoute" in owner
    detail = src("CameraDetail.tsx")
    assert 'CAMERA_TABS = ["live", "analytics", "alerts"]' in detail
    assert "camera_id" in src("EventEvidence.tsx") and "camera_id" in src("EventTimeline.tsx")
    assert "CAMERA_TABS" not in owner[owner.index("const TABS"): owner.index("\n};", owner.index("const TABS"))]


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


def test_a_failed_request_never_leaves_a_skeleton() -> None:
    """Xato chizig'i bilan yonma-yon ABADIY skelet turmasin.

    2026-09-11 QA: Dalillar, AI yordamchi va Tarif sahifalarida API
    yiqilsa `catch` faqat xabarni yozar, ro'yxat esa `null` (= «hali
    yuklanmoqda») bo'lib qolar edi — ega xato matnini ham, «yuklanmoqda»
    skeletini ham birga ko'rardi.  Qoida: `catch` ro'yxatni BO'SH holatga
    o'tkazadi yoki alohida «yiqildi» bayrog'ini ko'taradi."""
    evidence = src("EventEvidence.tsx")
    catch_block = evidence[evidence.index(".catch(reason =>"): evidence.index(".catch(reason =>") + 220]
    assert "setEvents([])" in catch_block, "dalillar: xatoda ro'yxat bo'sh bo'lsin"
    billing = src("owner.tsx")
    load = billing[billing.index('api<Invoice[]>("/api/v1/owner/invoices"'):]
    assert "setInvoices([])" in load[: load.index("[siteId]")], "tarif: xatoda ro'yxat bo'sh bo'lsin"
    agent = src("VisionAgent.tsx")
    assert "setSettingsFailed(true)" in agent and "settingsFailed && settings === null" in agent
    # Xato — bitta komponent, qo'ng'iroqli «ma'lumot» chizig'i emas.
    # (`media-error` karta ICHIDAGI rasm xatosi uchun qoladi — u sahifa
    # xatosi emas, bitta kadrning izohi.)
    assert 'className="media-error"' not in src("Analytics.tsx"), "sahifa xatosi yalang'och qizil matn"
    for name in ("EventEvidence.tsx", "VisionAgent.tsx", "Analytics.tsx"):
        assert '"alert-strip alert-info"><Icon name="bell"/>' not in src(name), f"{name}: xato ma'lumot chizig'ida"
    assert "export function ErrorStrip" in src("components.tsx")


#: Admin sahifasi → o'sha sahifadagi yuklanish holati.  Har biri API
#: yiqilganda ro'yxatni BO'SH qilishi va `ErrorStrip onRetry` bilan
#: qayta urinish taklif qilishi shart.
ADMIN_LOADERS = {
    "admin.tsx": ("setItems([])", "setData({features:[]})", "setLeads([])"),
    "AdminSettings.tsx": ("setReadiness({ items: [] })",),
    "AdminTeam.tsx": ("setAccounts([])",),
    "AdminCustomer.tsx": ("setInfo({ releases: [] })",),
}


def test_the_admin_pages_also_recover_from_a_failed_request() -> None:
    """Ega panelida tuzatilgan naqsh adminga KO'CHMAGAN edi.

    2026-09-11 QA faqat ega panelini qamradi.  Adminda xuddi shu nuqson
    olti joyda turgan: `catch` xabarni yozardi, ro'yxat esa `null`
    («hali yuklanmoqda») bo'lib qolardi — xato chizig'i bilan yonma-yon
    abadiy skelet.  Admin ichki vosita, lekin obuna, to'lov va login
    aynan shu yerdan boshqariladi: «yuklanmoqda» da qotgan sahifa
    to'lovni qabul qilishga to'sqinlik qiladi.
    """
    for name, markers in ADMIN_LOADERS.items():
        code = src(name)
        for marker in markers:
            assert marker in code, f"{name}: xatoda ro'yxat bo'sh bo'lsin — `{marker}` yo'q"

    # Qayta urinish YUKLANISH xatosida bo'lsin va aynan o'sha
    # ro'yxatni `null` ga qaytarib qayta so'rasin.  (AMAL xatosi —
    # «Amal bajarilmadi» — boshqa narsa: u skelet qoldirmaydi va
    # `alert-strip` bo'lib qolaveradi.)
    retries = {
        "admin.tsx": ("setItems(null);void load()", "setData(null);void load()", "setLeads(null);void load()"),
        "AdminSettings.tsx": ("setReadiness(null); load()",),
        "AdminTeam.tsx": ("setAccounts(null); load()",),
    }
    for name, handlers in retries.items():
        code = src(name)
        for handler in handlers:
            assert handler in code, f"{name}: «Qayta urinish» yo'q yoki qayta so'ramaydi — `{handler}`"


def test_report_buttons_do_not_promise_excel() -> None:
    """Tugma «Excel» desa-yu fayl CSV bo'lsa — yolg'on yorliq.

    2026-09-11 QA: «Kunlik hisobot (Excel)» va «Oylik (Excel)» tugmalari
    `report.csv` yuklardi; uchinchisi esa halol «14 kunlik CSV» edi."""
    for key in ("panel.download.daily_csv", "panel.download.period_csv", "panel.download.traffic_csv"):
        for lang in ("uz", "ru", "en"):
            text = tg(lang, key)
            assert text != key, f"{lang}: {key} katalogda yo'q"
            assert "excel" not in text.lower(), f"{lang}: {key} = {text!r}"
    assert "daily_excel" not in src("owner.tsx") and "monthly_excel" not in src("owner.tsx")


def test_raw_fastapi_detail_is_not_shown() -> None:
    """«Internal Server Error» va «Not Found» ega ekraniga chiqmasin.

    Bu FastAPI'ning o'z matni — tarjimasiz va ma'nosiz.  O'rniga umumiy
    matn + HTTP kodi (qo'llab-quvvatlashga aytish uchun).  Serverning O'Z
    xabari (`X-Lang` bilan tarjima qilingan `detail`) esa qoladi."""
    api = src("api.ts")
    assert "GENERIC_DETAILS" in api and '"Internal Server Error"' in api
    assert "status >= 500" in api
    media = api[api.index("export async function mediaObjectUrl"):]
    assert "body.detail ||" not in media, "media xatosi ham umumiy qoidadan o'tsin"
    assert "errorText(body, response.status)" in media


def test_report_downloads_report_their_failure() -> None:
    """Yuklash tugmasi jim qolmasin: rad etilgan va'da toast bo'lib chiqsin."""
    reports = src("owner.tsx")
    page = reports[reports.index("function ReportsPage("):]
    page = page[: page.index("\n}\n")]
    assert "useToast()" in page and "panel.download.failed" in page
    assert "void downloadDailyReportCsv(siteId)" not in page, "yuklash `void` bilan tashlab yuborilmasin"


# ── Matn sifati ───────────────────────────────────────────────────────────


def test_panel_has_no_inline_event_handlers() -> None:
    """`onclick="..."` bilan ID string ichiga qo'yilardi — qochirish
    unutilsa buziladi.  JSX'da hodisa ishlovchisi jingalak qavsda
    bo'ladi; qo'shtirnoqli variant xom HTML yozilganini bildiradi."""
    found = re.search(r'\son(click|change|input|submit)\s*=\s*"', all_src())
    assert found is None, f"inline hodisa ishlovchisi: {found.group(0) if found else ''}"


def test_the_old_brand_stays_off_the_panels() -> None:
    """Rebrend (2026-09-08): mijoz va admin ko'radigan matnda «ENES»
    qolmasin.  Brauzer kalitlari (`enes_owner_token`) va env
    nomlari (`ENES_*`) F6 da o'zgaradi — ular istisno."""
    for name in OWNER_FILES + ADMIN_FILES + INSTALLER_FILES + ("Connect.tsx",):
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


def test_no_panel_uses_native_dialogs() -> None:
    """`prompt()`/`confirm()` — eski admin qoidasi (2026-08-19).

    Brauzer oynasida "auto" yoki "naqd" deb YOZISH kerak edi — bitta harf
    xato, amal bajarilmasdi.  React adminda `window.confirm` 2026-09-07 da
    qaytib kelgan edi (`PaymentsPage`); endi tasdiqlash `ConfirmDialog`,
    tanlov modal ichida tugma bilan.

    Qamrov 2026-09-12 da EGA fayllariga ham kengaytirildi: test faqat
    adminni tekshirgani uchun `GeometryEditor.tsx` da `window.prompt`
    va `window.confirm` jimgina qaytib kelgan edi.  Bu eng yomon
    joyi — zona nomlash Telegram WebView'da umuman ishlamasligi mumkin
    va usta obyektda aynan telefondan chizadi.

    O'sha kuni USTA paneli ham ro'yxatga kirdi: eski
    `cloud/static/installer.js` butunlay `alert()` va `confirm()` ustiga
    qurilgan edi — kamera o'chirish, yangi pairing kodi va har xato
    xabari.
    """
    for name in ADMIN_FILES + OWNER_FILES + INSTALLER_FILES:
        found = re.search(r"window\.(prompt|confirm|alert)\s*\(", src(name))
        assert found is None, f"{name}: brauzer oynasi qaytib kelgan: {found.group(0) if found else ''}"
    assert "useConfirm(" in admin_src(), "tasdiqlash o'z oynasi bilan bo'lsin"
    assert "usePrompt(" in owner_src(), "chizma nomlash o'z oynasi bilan bo'lsin"
    assert "useConfirm(" in installer_src(), "usta paneli tasdiqni o'z oynasida so'rasin"


def test_the_shape_editor_can_be_named_without_a_browser_dialog() -> None:
    """Muharrir callbacki PROMISE ham qabul qilsin.

    `zone-editor.js` uchta joyda ishlatiladi: lokal sehrgar (do'kon
    kompyuterining brauzeri — u yerda `prompt()` normal), eski
    o'rnatuvchi paneli va React paneli.  React'da modal oyna asinxron,
    ya'ni sinxron `askName` kontrakti bilan uni ulash IMKONSIZ edi.
    Kontrakt `Promise.resolve()` orqasiga olindi — satr qaytargan eski
    chaqiruvchilar o'zgarmadi.
    """
    editor = ZONE_EDITOR.read_text(encoding="utf-8")

    assert "Promise.resolve(" in editor, "callback promise qabul qilmaydi"
    assert "function _ask(" in editor, "nom so'rash bitta joyda bo'lsin"
    # Tasdiq oynasi ochiq turganda ro'yxat o'zgarishi mumkin — indeks
    # bo'yicha o'chirish butunlay boshqa shaklga tegib ketardi.
    assert "list.indexOf(target)" in editor, "o'chirish indeks bo'yicha qolgan"


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
    """Uchala panel bitta uslub faylidan kelsin — aks holda ular
    asta-sekin ajralib ketadi.

    Usta paneli buning jonli isboti: u 2026-08-24 dan o'z CSS'i bilan
    yashadi va shu sababdan ikki dizayn ishidan ham chetda qoldi."""
    for entry in ("owner.tsx", "admin.tsx", "installer.tsx"):
        assert 'import "./styles.css"' in src(entry), f"{entry}: umumiy uslub yo'q"


def test_the_stylesheet_has_no_unterminated_comment() -> None:
    """Yopilmagan `/*` o'zidan keyingi HAMMA qoidani yeb qo'yadi va
    sahifa uslubsiz ochiladi."""
    for path in (SRC / "styles.css", STATIC / "site.css", STATIC / "tokens.css"):
        text = path.read_text(encoding="utf-8")
        assert text.count("/*") == text.count("*/"), f"{path.name}: izoh yopilmagan"


@pytest.mark.parametrize("shell", ["owner.html", "admin.html", "installer.html"])
def test_shells_carry_the_new_brand(shell: str) -> None:
    """Qobiqda eski brend qoldig'i bo'lmasin."""
    text = (SHELLS / shell).read_text(encoding="utf-8")
    assert "chaqimchi-logo" not in text, "eski logotip havolasi qoldi"
    assert 'content="#4285f4"' not in text, "eski brend ko'ki qoldi"


def test_logging_out_asks_the_server_too() -> None:
    """«Chiqish» faqat brauzerdagi kalitni o'chirmasin.

    Ilgari ikkala panelda ham tugma `clearToken` dan iborat edi:
    tokenni nusxa olgan odam uchun hech narsa o'zgarmasdi, u 12 soat
    davomida ishlayverardi.  Endi `api.ts: logout()` avval serverga
    boradi (`auth_version` oshadi), keyin kalitni o'chiradi.
    """
    helper = src("api.ts")
    assert "/api/v1/owner/auth/logout" in helper
    assert "/api/v1/auth/logout" in helper

    for name in ("owner.tsx", "admin.tsx"):
        text = src(name)
        assert "serverLogout" in text, f"{name}: chiqish serverga bormayapti"
        # Faqat `clearToken` bilan tugaydigan chiqish qaytib kelmasin.
        assert 'clearToken("owner");setAuthenticated' not in text
        assert 'clearToken("admin");setAuthenticated' not in text


# ── Menyu: 8 bo'lim va eski manzillar ─────────────────────────────────────


def test_every_old_section_still_opens_from_its_old_link() -> None:
    """Menyu 14 bo'limdan 8 taga qisqardi (2026-09-10, dizayn-3).

    Eski bo'lim nomlari Telegram xabarlaridagi havolalarda, xatcho'plarda
    va koddagi `onNavigate("billing")` chaqiruvlarida qolgan.  Har biri
    yangi bo'lim ichidagi tabga XARITADA bo'lishi shart — bo'lmasa havola
    jimgina bosh sahifaga tushadi va ega «tugma ishlamayapti» deydi.
    """
    text = src("owner.tsx")
    legacy = re.search(r"const LEGACY_ROUTES = \{(.*?)\} as const;", text, re.S)
    assert legacy, "LEGACY_ROUTES xaritasi yo'q"
    mapped = set(re.findall(r"^\s*(\w+): \[", legacy.group(1), re.M))
    old_sections = {"setup", "zones", "agent", "traffic", "heatmap", "telegram", "billing", "branches"}
    assert old_sections <= mapped, f"xaritada yo'q: {sorted(old_sections - mapped)}"

    nav_ids = set(re.findall(r'\{ id: "(\w+)", key: "panel\.nav\.', text))
    tabs = dict(re.findall(r'^\s*(\w+): \[([^\]]*)\]', re.search(r"const TABS[^{]*\{(.*?)\n\};", text, re.S).group(1), re.M))
    for old, section, tab in re.findall(r'^\s*(\w+): \["(\w+)", "(\w+)"\]', legacy.group(1), re.M):
        assert section in nav_ids, f"{old} → {section}: bunday bo'lim menyuda yo'q"
        assert f'"{tab}"' in tabs.get(section, ""), f"{old} → {section}/{tab}: bunday tab yo'q"
    # Xarita `usePanelRoute` ga uzatilgan — aks holda u shunchaki bezak.
    assert 'usePanelRoute("/owner", ROUTE_IDS, "home", LEGACY_ROUTES)' in text


def test_the_owner_menu_is_short_enough_for_a_phone() -> None:
    """Sakkiztadan ko'p bo'lim — telefonda «Yana» ichida yo'qoladi."""
    text = src("owner.tsx")
    nav = re.search(r"const NAV_ITEMS[^\[]*\[(.*?)\n\];", text, re.S).group(1)
    assert len(re.findall(r'\{ id: "', nav)) <= 8
    for tab_id in re.findall(r'"(\w+)"', re.search(r"const TABS[^{]*\{(.*?)\n\};", text, re.S).group(1)):
        assert f'"panel.tabs.{tab_id}"' in src("i18n/catalogue.generated.ts"), f"panel.tabs.{tab_id} katalogda yo'q"


def test_no_panel_resolves_a_label_at_import_time() -> None:
    """`t()` MODUL DARAJASIDA chaqirilmasin.

    Modul yuklanganda til hali tanlanmagan (`initLang()` qobiq faylining
    oxirida chaqiriladi), ya'ni import paytida ochilgan yorliq DOIM
    o'zbekcha qoladi.  Ega panelida bu 2026-09-08 da tuzatilgan
    (`NAV_ITEMS` kalit saqlaydi), adminda esa bitta yorliq
    (`panel.nav.leads`) jimgina qotib qolgan edi.

    Tekshiruv: modul darajasidagi `const` e'lonlari ichida `t(` bo'lmasin.
    """
    for name in OWNER_FILES + ADMIN_FILES + INSTALLER_FILES:
        code = src(name)
        for index, line in enumerate(code.splitlines(), start=1):
            if not line.startswith("const ") and not line.startswith("  {id:"):
                continue
            assert "t(\"" not in line and "t(`" not in line, (
                f"{name}:{index} — yorliq import paytida ochilyapti: {line.strip()[:80]}"
            )


def test_the_csv_download_works_in_safari_too() -> None:
    """`<a>` DOMga qo'shilsin va manzil darhol bekor qilinmasin.

    To'rtta yuklash joyi bir xil boilerplate'ni alohida yozgan edi va
    uchtasida ham ikkita xato bor: element hujjatga qo'shilmasdi
    (Safari va ba'zi WebView'lar bunday `click()` ni jimgina tashlab
    yuboradi — tugma bosiladi, hech narsa yuklanmaydi, xato ham
    chiqmaydi) va `revokeObjectURL` sinxron chaqirilardi (brauzer
    yuklashni boshlashga ulgurmasdan manzil o'chardi).
    """
    api_src = src("api.ts")
    assert "export function downloadBlobUrl" in api_src, "umumiy yordamchi yo'q"
    assert "document.body.appendChild(link)" in api_src, "`<a>` DOMga qo'shilmaydi"
    assert "window.setTimeout(" in api_src, "`revokeObjectURL` darhol chaqirilyapti"

    # Chaqiruv joylarida boilerplate QAYTA paydo bo'lmasin.
    for name in ("owner.tsx", "admin.tsx") + INSTALLER_FILES:
        code = src(name)
        assert "document.createElement(\"a\")" not in code, (
            f"{name}: yuklash boilerplate'i qaytib kelgan — `downloadBlobUrl()` ishlatilsin"
        )


def test_modal_windows_really_trap_the_focus() -> None:
    """Izoh «fokus oyna ichida» deb YOZILGAN, kod esa qilmasdi.

    `aria-modal="true"` faqat skrinriderga aytadi, klaviaturani
    to'smaydi — Tab bosgan odam oyna ortidagi sahifaga chiqib ketardi
    va u yerda ko'rinmas tugmalarni bosardi.  Yopilganda fokus hech
    qayerga qaytmasdi.  Telegram WebView'da bu ayniqsa muhim: u yerda
    brauzer oynalari yo'q va butun panel modal oynalarga tayanadi.
    """
    code = src("components.tsx")

    assert "export function useFocusTrap" in code, "fokus tuzog'i yo'q"
    assert 'event.key !== "Tab"' in code, "Tab halqasi yo'q"
    assert "previous.focus()" in code, "yopilganda fokus qaytmaydi"
    # `Modal` ham, buyruq palitrasi ham shu bitta hook'ni ishlatsin.
    assert code.count("useFocusTrap(onClose)") >= 2, (
        "oynalardan biri hamon tuzoqsiz — `Modal` va palitra ikkalasi ham"
    )


def test_the_tabs_say_which_panel_they_open() -> None:
    """`role="tab"` yetarli emas: tugma qayerga olib borishini ham aytsin."""
    components = src("components.tsx")
    assert "aria-controls={panelId}" in components
    assert 'role="tabpanel"' in components and "aria-labelledby" in components

    for name in ("owner.tsx", "CameraDetail.tsx", "InstallerJobs.tsx"):
        assert "panelId=" in src(name), f"{name}: tab qatori panelga bog'lanmagan"
        assert "<TabPanel" in src(name), f"{name}: tab tarkibi `tabpanel` emas"


def test_search_stays_reachable_on_a_phone() -> None:
    """Telefonda `⌘K` yo'q — tugma yashirilsa qidiruv umuman yo'qoladi.

    Admin 60+ mijozni faqat aylantirib topardi.
    """
    css = (SRC / "styles.css").read_text(encoding="utf-8")
    phone = css[css.index("@media (max-width: 760px)"):]

    assert ".search-trigger, .topbar-date, .status-chip { display: none; }" not in phone, (
        "qidiruv tugmasi telefonda yashirilgan"
    )
    assert ".search-trigger span, .search-trigger kbd { display: none; }" in phone, (
        "tugma ixchamlashmagan — tor topbarda joy yetmaydi"
    )


def test_focus_is_visible_in_the_search_boxes() -> None:
    """`outline: none` o'ram halqasi bilan QOPLANSIN.

    Global `:focus-visible` bu maydonlarga tegmaydi: ko'rinadigan
    chegara maydonda emas, o'ramda (`.palette-input`, `.table-search`).
    """
    css = (SRC / "styles.css").read_text(encoding="utf-8")

    for wrapper in (".palette-input", ".table-search"):
        assert f"{wrapper}:focus-within {{ outline:" in css, f"{wrapper}: fokus ko'rinmaydi"


def test_the_severity_dot_does_not_speak_only_in_colour() -> None:
    """Rang ko'rmaydigan odam uchun muhim va oddiy xabar bir xil edi."""
    owner = src("owner.tsx")
    dot = owner[owner.index("notif-dot sev-") - 60: owner.index("notif-dot sev-") + 260]

    assert "aria-label" in dot, "muhimlik faqat rang bilan aytilyapti"


def test_the_ai_assistant_hides_when_it_is_not_connected() -> None:
    """Gemini kaliti yo'q do'konda tab ochilar, har savol xato berardi.

    Jonli bazada `vision_observations` = 0 — ya'ni funksiya amalda
    o'lik, lekin panel uni sotilgan bo'lim sifatida ko'rsatardi.
    Qaror SERVERDA: `capabilities.agent` `vision_agent.configured()`
    dan keladi va panelda ikkinchi shart yozilmaydi.
    """
    owner = src("owner.tsx")
    assert "capabilities?.agent?.ready" in owner, "darvoza panelda o'qilmaydi"
    assert 'hidden={agentReady ? [] : ["agent"]}' in owner, "tab yashirilmaydi"
    # `TABS` ro'yxatining O'ZI o'zgarmasin: manzil xaritasi unga bog'langan.
    assert 'alerts: ["evidence", "agent"]' in owner, "`TABS` literali o'zgargan"
    # To'g'ridan-to'g'ri kirilsa sabab aytilsin, oq sahifa emas.
    assert "panel.agent.off_title" in owner


def test_the_employees_section_hides_when_attendance_is_closed() -> None:
    """Davomat yopiq pilot: yoqilmagan serverda har so'rov 403 berardi."""
    owner = src("owner.tsx")
    assert "capabilities?.attendance?.ready" in owner
    assert "attendanceReady" in owner


def test_the_camera_page_has_only_one_heading() -> None:
    """`EventEvidence` o'z `PageHeader`ini chizib, ikki sahifa ustma-ust
    bo'lib ko'rinardi (2026-09-11 QA).  Kun tanlagich esa QOLADI —
    funksiya yo'qolishi sarlavha takrorlanishidan yomonroq."""
    evidence = src("EventEvidence.tsx")
    assert "embedded = false" in evidence, "`embedded` propi yo'q"
    assert "{embedded ? null : <PageHeader" in evidence, "ichma-ich sarlavha chizilyapti"
    assert "embedded && dayPicker" in evidence, "kun tanlagich yo'qolgan"
    assert "embedded/>" in src("CameraDetail.tsx"), "kamera sahifasi propni bermaydi"


def test_there_is_only_one_metric_card_component() -> None:
    """Ikkita ko'rsatkich kartasi ikki panelda boshqacha ko'rinardi.

    Ega paneli `StatCard` ga o'tgach admin eskisida (`MetricCard`)
    qolib ketdi — aynan bitta karta, faqat o'zgarish va sparkline'siz.
    `StatCard` ning o'sha proplari IXTIYORIY, ya'ni ikkinchi komponent
    umuman kerak emas edi.
    """
    assert "export function MetricCard" not in src("components.tsx")
    # Izohda nom sifatida uchraydi (nega o'chirilgani yozilgan), shuning
    # uchun ISHLATILISHI qidiriladi: `<MetricCard`.
    for name in ADMIN_FILES + OWNER_FILES + INSTALLER_FILES:
        assert "<MetricCard" not in src(name), f"{name}: eski karta qaytib kelgan"


def test_the_dead_css_is_gone() -> None:
    """Ishlatilmaydigan qoida keyingi odamni «bu qayerda chiziladi?»
    degan qidiruvga yuboradi."""
    css = (SRC / "styles.css").read_text(encoding="utf-8")
    for rule in (".metric-grid-4", ".traffic-card", ".plan-heatmap"):
        assert rule not in css, f"{rule}: o'lik qoida qaytib kelgan"


def test_the_colours_come_from_the_tokens() -> None:
    """Rang ikki joyda yozilsa palitra o'zgarganda biri eskirib qoladi.

    `--heat-scale` xom RGB uchligi saqlaydi: kanvas `rgb()` satrini
    emas, SON talab qiladi.
    """
    tokens = (Path(__file__).resolve().parents[1] / "cloud" / "static" / "tokens.css").read_text(
        encoding="utf-8"
    )
    assert "--heat-scale:" in tokens, "issiqlik shkalasi tokenlarda yo'q"


# ── O'rnatuvchi (usta) paneli ────────────────────────────────────────────
#
# 2026-09-12: `cloud/static/installer.html` — oxirgi eski statik panel —
# React'ga ko'chdi.  Quyidagi qulflar aynan shu ko'chishda yo'qolishi
# oson bo'lgan narsalarni ushlab turadi.


def test_the_installer_panel_is_react_now() -> None:
    """Marshrut React qobig'iga tushsin va eski fayllar qaytmasin.

    Eski panel mustaqil yashagani uchun ikki UI ishidan ham chetda
    qoldi.  Uchta fayl o'chdi: `installer.html` (qo'lda yozilgan qobiq),
    `installer.js` (sahifa mantig'i) va `geometry-panel.js` (chizish
    panelining IKKINCHI nusxasi — «javon» belgisi aynan shu yerda
    tushib qolgan edi).
    """
    main = (ROOT / "cloud" / "main.py").read_text(encoding="utf-8")
    assert '"v2/installer.html"' in main, "marshrut React qobig'iga bormaydi"
    assert '_static_page("installer.html")' not in main, "eski qobiq qaytib kelgan"
    # SPA ning ichki yo'llari ham qobiqqa tushsin: usta sahifani
    # yangilaganda yoki havolani ulashganda 404 chiqmasin.
    assert '@app.get("/installer/{panel_path:path}"' in main, "SPA yo'llari yo'q"

    for gone in ("installer.html", "installer.js", "geometry-panel.js"):
        assert not (STATIC / gone).is_file(), f"eski fayl qaytib kelgan: {gone}"

    vite = (SHELLS / "vite.config.ts").read_text(encoding="utf-8")
    assert "installer.html" in vite, "qobiq Vite kirish nuqtalarida yo'q"


def test_every_shell_carries_the_same_theme_script() -> None:
    """Tema bootstrap'i uchala qobiqda AYNAN bir xil bo'lsin.

    CSP'da bitta hash bor (`deploy/Caddyfile*`) va u shu skriptdan
    hisoblangan.  Bir belgi farq qilsa yangi qobiq CSP ostida
    TEMASIZ ochiladi — kechasi telefonda ko'zni qamashtiradigan oq
    ekran, va brauzer buni hech qayerda aytmaydi.
    """
    blocks = re.compile(r"<script(?![^>]*\bsrc=)([^>]*)>(.*?)</script>", re.S)
    bodies = set()
    for shell in ("owner.html", "admin.html", "installer.html"):
        text = (SHELLS / shell).read_text(encoding="utf-8")
        bodies |= {body for attrs, body in blocks.findall(text) if "json" not in attrs}
    assert len(bodies) == 1, "qobiqlardagi inline skript ajralib ketdi — hash buziladi"
    assert "localStorage.getItem" in next(iter(bodies))


def test_the_installer_never_leaves_a_skeleton() -> None:
    """API yiqilsa xato KO'RINSIN, skelet esa yo'qolsin.

    Eski panelda kamera ro'yxati xatosi `cameraList.textContent` ga
    yozilardi, obyekt ro'yxatiniki esa umuman yo'q edi: so'rov
    yiqilsa usta bo'sh ekranga qarab qolardi.  Qoida (2026-09-11 QA):
    `catch` ro'yxatni BO'SH holatga o'tkazadi — `null` «hali
    yuklanmoqda» degani.
    """
    for name in ("installer.tsx", "InstallerCamera.tsx", "InstallerJobs.tsx"):
        code = src(name)
        for index, line in enumerate(code.splitlines(), start=1):
            if "catch (reason)" not in line:
                continue
            block = "\n".join(code.splitlines()[index - 1 : index + 8])
            if "setJobs(" in block or "setCameras(" in block:
                assert "([])" in block, f"{name}:{index} — xatoda ro'yxat bo'shatilmagan"
    assert "<ErrorStrip" in installer_src(), "xato chizig'i yo'q"
    assert "onRetry=" in installer_src(), "qayta urinish tugmasi yo'q"


def test_the_installer_speaks_three_languages() -> None:
    """Har ko'rinadigan matn katalogdan kelsin — uchala tilda ham.

    Eski panel FAQAT o'zbekcha edi: matn HTML ichida yozilgan va uni
    tarjima qilishning yo'li yo'q edi.
    """
    used = set(re.findall(r't\("(panel\.[a-z0-9_.]+)"', installer_src()))
    assert len(used) > 60, "matn hamon kodda qotib turibdi"
    for key in sorted(used):
        for lang in ("uz", "ru", "en"):
            assert tg(lang, key) != key, f"{lang}: {key} katalogda yo'q"


def test_the_installer_reads_the_face_id_verdict_from_the_server() -> None:
    """Chegara panelda QAYTA HISOBLANMAYDI.

    Qaror bitta joyda chiqadi (`enes/camera_roles.py: face_id_state`) va
    panel faqat matn tanlaydi.  Ikkinchi manba yasalsa ular bir-biridan
    ajralib ketardi — `FACE_MIN_BBOX_RATIO` bilan bir marta shunday
    bo'lgan.
    """
    camera = src("InstallerCamera.tsx")
    assert "face_id_state" in camera, "server qarori o'qilmayapti"
    # Panelda piksel chegarasi bo'lmasin: `720`, `480` kabi sonlar
    # ikkinchi manbaning birinchi belgisi.
    assert not re.search(r"\b(720|480|288)\b", camera), "chegara panelda qayta hisoblanyapti"


def test_a_zone_can_be_finished_with_a_finger() -> None:
    """Zonani yakunlash faqat `dblclick` da qolmasin.

    Muharrirda zonani yopish ikki marta bosishga, qoralamani tashlash
    esa sichqonchaning O'NG tugmasiga bog'langan — telefonda ikkalasi
    ham yo'q.  Ya'ni usta obyektda nuqtalarni qo'yib, zonani UMUMAN
    yopa olmasdi.  Metodlar muharrirda bor edi, faqat hech kim
    chaqirmagan.
    """
    editor = src("GeometryEditor.tsx")
    assert "finishDraft()" in editor, "«Zonani yakunlash» tugmasi yo'q"
    assert "cancelDraft()" in editor, "«Bekor qilish» tugmasi yo'q"
    assert "removeShape(" in editor, "shaklni o'chirish faqat o'ng tugmada qolgan"
    types = (SRC / "zone-editor.d.ts").read_text(encoding="utf-8")
    assert "finishDraft(): boolean" in types and "cancelDraft(): void" in types

    heat = src("Heatmap.tsx")
    assert '--heat-scale' in heat, "xarita shkalani tokendan o'qimaydi"
    assert "HEAT_FALLBACK" in heat, "stil yuklanmagan holat uchun zaxira yo'q"

    theme = src("theme.ts")
    assert '"--surface"' in theme, "manzil qatori rangi tokendan o'qilmaydi"
    assert "META_FALLBACK" in theme, "bootstrap uchun zaxira yo'q"


def test_the_route_hook_watches_its_legacy_map() -> None:
    """`legacy` deps'da yo'q edi — `popstate` eski xaritani ushlab turardi.

    Standart qiymat modul darajasida bo'lishi SHART: `= {}` har
    chizishda yangi obyekt yasaydi va effekt har renderda qayta ishga
    tushardi (aynan shu sababdan dep tushirib qoldirilgan edi).
    """
    router = src("router.ts")
    assert "const NO_LEGACY" in router, "barqaror standart qiymat yo'q"
    assert "[base, ids, fallback, legacy]" in router, "`legacy` deps'da yo'q"
    assert "legacy: LegacyRoutes = {}" not in router, (
        "parametr standarti hamon har chizishda yangi obyekt yasaydi"
    )


def test_the_admin_has_one_telemetry_section() -> None:
    """«Qurilmalar» va «Monitoring» AYNAN bir sahifani chizardi."""
    admin = src("admin.tsx")
    assert '{id:"devices"' not in admin, "menyuda ikkinchi qator qolgan"
    # Eski xatcho'p ishlashi kerak — yo'naltirish orqali.
    assert 'devices: ["monitoring"' in admin, "eski manzil yo'naltirilmaydi"
