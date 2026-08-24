"""Panel sahifalaridagi JavaScript umuman ishga tushadimi.

Sabab haqiqiy xatodan: `owner.html` ichida `'So'rov bajarilmadi'` degan satr
bor edi — o'zbekcha apostrof JS satrini uzib qo'ygan.  Bitta sintaksis xatosi
esa **butun** `<script>` blokini o'ldiradi: kirish tugmasi ham, ma'lumot
yuklash ham ishlamaydi.  Sahifa esa chiroyli ochilaveradi, shuning uchun buni
faqat mijoz sezadi.

Tekshiruv `node --check` bilan bajariladi.  Node bo'lmasa test o'tkazib
yuboriladi — u yerda ham yolg'on "o'tdi" bo'lmasligi uchun sabab yoziladi.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import List

import pytest

STATIC = Path(__file__).resolve().parents[1] / "cloud" / "static"
SCRIPT = re.compile(r"<script>(.*?)</script>", re.S)


def pages() -> List[Path]:
    return sorted(path for path in STATIC.glob("*.html"))


@pytest.mark.parametrize("page", pages(), ids=lambda path: path.name)
def test_page_javascript_parses(page: Path, tmp_path: Path) -> None:
    if shutil.which("node") is None:
        pytest.skip("node topilmadi — JS sintaksisi tekshirilmadi")
    blocks = SCRIPT.findall(page.read_text(encoding="utf-8"))
    if not blocks:
        return

    bundle = tmp_path / f"{page.stem}.js"
    bundle.write_text("\n".join(blocks), encoding="utf-8")
    result = subprocess.run(
        ["node", "--check", str(bundle)], capture_output=True, text=True, timeout=30
    )

    assert result.returncode == 0, f"{page.name} JavaScript'ida sintaksis xatosi:\n{result.stderr}"


def test_every_page_has_a_language_and_charset() -> None:
    """Kirillcha/lotincha o'zbek matni charset'siz buziladi."""
    for page in pages():
        content = page.read_text(encoding="utf-8").lower()
        assert 'lang="uz"' in content or 'lang="en"' in content, page.name
        assert 'charset="utf-8"' in content, page.name


# ── Va'da qo'riqchisi ────────────────────────────────────────────────────
#
# Sayt matni bir necha marta koddan oldinga o'tib ketgan: "kameralarni 2
# daqiqada avtomatik topadi" deb yozilganda qidiruv funksiyasi umuman
# mavjud emas edi; "barcha IP kamera mos" degani esa loyihaning o'z hujjati
# (`docs/CROSS_PLATFORM_INSTALLER_PLAN.md`) aynan taqiqlagan gap edi.
#
# Bu tekshiruvlar sotuv matnini emas, **isbotlanmagan kafolatni** ushlaydi.

#: Sayt bermasligi kerak bo'lgan kafolatlar.
FORBIDDEN_CLAIMS = (
    "barcha ip kamera",
    "barcha standart ip kamera",
    "barcha kamera mos",
    "har qanday kamera",
    "100% aniqlik",
    "o'g'rini aniqlaydi",
    "o‘g‘rini aniqlaydi",
)


def test_public_pages_make_no_unproven_guarantees() -> None:
    for page in pages():
        if page.name in {"admin.html", "installer.html", "owner.html"}:
            continue  # ichki panellar, mijozga sotuv va'dasi bermaydi
        text = page.read_text(encoding="utf-8").lower()
        for claim in FORBIDDEN_CLAIMS:
            assert claim not in text, (
                f"{page.name}: isbotlanmagan kafolat — «{claim}». "
                "Qo'llab-quvvatlanadigan NVR ro'yxatini yozing."
            )


def test_attendance_is_marked_as_a_closed_pilot() -> None:
    """`docs/DOKON_MVP.md`: davomat Face ID — yozma rozilikli **bepul yopiq
    pilot**, production'da fail-closed.  Uni oddiy funksiya sifatida sotish
    huquqiy risk."""
    site = (STATIC / "site.html").read_text(encoding="utf-8").lower()
    if "face id" in site:
        assert "pilot" in site, "Face ID yopiq pilot ekani ko'rsatilmagan"


def test_download_section_does_not_hardcode_a_file_size() -> None:
    """Ilgari sahifada "115 MB bundle" deb turardi, fayl esa umuman mavjud
    emas edi va tugma 503 qaytarardi.  Hajm serverdan olinadi."""
    site = (STATIC / "site.html").read_text(encoding="utf-8")
    assert not re.search(r"\d{2,4}\s*MB", site), "hajm sahifaga qo'lda yozilmasin"
    assert "windows-release" in (STATIC / "site.js").read_text(encoding="utf-8"), (
        "yuklab olish holati serverdan so'ralishi kerak"
    )


def test_pages_do_not_reference_removed_scripts() -> None:
    """`run_windows.bat`, `install_windows.bat` va maket onboarding
    o'chirildi — ularga ishora qilgan yo'riqnoma mijozni yo'qolgan faylga
    yuborardi."""
    removed = (
        "run_windows.bat",
        "install_windows.bat",
        "local-onboarding",
        "chaqimchi_ai.pair_sotqin",
    )
    for page in pages():
        text = page.read_text(encoding="utf-8")
        for name in removed:
            assert name not in text, f"{page.name}: o'chirilgan faylga ishora — {name}"


# ── Ikonkalar, fokus va rasm hajmi ───────────────────────────────────────

ICONS = STATIC / "icons.svg"


#: Ichki panellar — admin, o'rnatuvchi va mijoz kabineti.  Ular sotuv
#: sahifasi emas va u yerda emoji ishlatilishi muammo emas: foydalanuvchisi
#: bizning xodim yoki tanish mijoz, brend ko'rinishi esa hal qiluvchi emas.
INTERNAL_PAGES = {"admin.html", "installer.html", "owner.html"}

#: Bular emoji emas, tipografik belgilar — hamma joyda bir xil chiziladi.
TYPOGRAPHIC = {"─", "✓", "○", "★", "☑", "→", "←", "·"}


def test_public_pages_use_the_icon_sprite_not_emoji() -> None:
    """Emoji har qurilmada boshqacha: 🪟 Windows'da rangsiz kvadrat,
    Android'da butunlay boshqa shakl.  Brend ranglarini ham bermaydi."""
    import unicodedata

    for page in pages():
        if page.name in INTERNAL_PAGES:
            continue
        text = page.read_text(encoding="utf-8")
        emoji = {
            char
            for char in text
            if ord(char) > 0x2100 and unicodedata.category(char) == "So" and char not in TYPOGRAPHIC
        }
        assert not emoji, f"{page.name}: emoji ikonka qolgan — {sorted(emoji)}"


def test_icon_sprite_is_valid_and_small() -> None:
    """Sprite bitta so'rov bilan keladi; katta bo'lsa afzalligi yo'qoladi."""
    import xml.etree.ElementTree as ElementTree

    tree = ElementTree.parse(ICONS)
    symbols = [node.get("id") for node in tree.iter("{http://www.w3.org/2000/svg}symbol")]
    assert len(symbols) >= 8, f"ikonkalar kam: {symbols}"
    assert len(set(symbols)) == len(symbols), "takrorlangan id"
    assert ICONS.stat().st_size < 30_000, "sprite juda katta"


def test_every_referenced_icon_exists_in_the_sprite() -> None:
    """Nomi noto'g'ri yozilgan `<use>` sahifada bo'sh joy qoldiradi va
    hech qanday xato bermaydi — buni faqat ko'z bilan sezish mumkin."""
    import xml.etree.ElementTree as ElementTree

    tree = ElementTree.parse(ICONS)
    available = {node.get("id") for node in tree.iter("{http://www.w3.org/2000/svg}symbol")}
    for page in pages():
        used = set(re.findall(r"icons\.svg#([\w\-]+)", page.read_text(encoding="utf-8")))
        missing = used - available
        assert not missing, f"{page.name}: sprite'da yo'q ikonka — {sorted(missing)}"


def test_keyboard_focus_is_visible_everywhere() -> None:
    """Bungacha fokus ramkasi faqat `.field input` da bor edi — klaviatura
    bilan yuruvchi foydalanuvchi qayerda turganini ko'rmasdi (WCAG 2.4.7)."""
    css = (STATIC / "site.css").read_text(encoding="utf-8")
    assert ":focus-visible" in css


def test_browser_facing_images_are_small() -> None:
    """Logotip 38 px joyda ko'rsatiladi, lekin 516 KB fayl yuklanardi;
    `og.png` esa 891 KB edi.  Mobil internetda bu sezilarli kechikish."""
    for page in pages():
        text = page.read_text(encoding="utf-8")
        for name in re.findall(r"/assets/([\w\-.]+\.(?:png|jpg|jpeg|webp))", text):
            asset = STATIC / name
            if not asset.is_file():
                continue
            size_kb = asset.stat().st_size / 1024
            assert size_kb < 200, f"{page.name} → {name}: {size_kb:.0f} KB, juda katta"


# ── Versiya sahifada ko'rinsin ───────────────────────────────────────────
#
# Haqiqiy muammo: yuklab olish tugmasi faqat hajmni ko'rsatardi (68 MB),
# u esa har relizda bir xil.  Natijada yangi versiya chiqqanini
# sahifadan bilib bo'lmasdi va eski fayl qayta yuklab olinardi —
# "yuklab olganim eski fayl bilan bir xil ekan".


def test_landing_page_shows_the_installer_version() -> None:
    html = (STATIC / "site.html").read_text(encoding="utf-8")
    js = (STATIC / "site.js").read_text(encoding="utf-8")
    assert 'id="downloadVersion"' in html, "versiya uchun joy yo'q"
    assert "release.version" in js, "versiya API javobidan olinmayapti"


def test_install_guide_shows_the_installer_version() -> None:
    html = (STATIC / "install.html").read_text(encoding="utf-8")
    assert 'id="guideDownloadVersion"' in html
    assert "release.version" in html


def test_version_is_hidden_until_it_is_known() -> None:
    """Bo'sh "Versiya" yozuvi mijozni chalg'itadi — nashr qilinmagan
    bo'lsa umuman ko'rinmasin."""
    for name, marker in (
        ("site.html", "downloadVersion"),
        ("install.html", "guideDownloadVersion"),
    ):
        html = (STATIC / name).read_text(encoding="utf-8")
        block = html[html.index(f'id="{marker}"') :]
        assert "hidden" in block[: block.index(">") + 1], f"{name}: boshida yashirin bo'lsin"


# ── Kesh tokeni mazmunga bog'liq bo'lsin ─────────────────────────────────
#
# Haqiqiy xato: `?v=` qo'lda qo'yiladigan sana edi (`v=20260816-v12`) va
# uni yangilash unutildi.  JS o'zgardi, token o'zgarmadi — saytga qaytgan
# mijoz brauzer keshidan **eski** faylni olardi va tuzatish unga yetib
# bormasdi.  Serverda hammasi to'g'ri turardi, ekranda esa eskisi.


def _content_token(name: str) -> str:
    import hashlib

    return hashlib.sha256((STATIC / name).read_bytes()).hexdigest()[:10]


@pytest.mark.parametrize("asset", ["site.js", "site.css"])
def test_cache_token_matches_the_file_contents(asset: str) -> None:
    """Fayl o'zgarsa token ham o'zgarishi **shart**.

    Shu test tufayli uni unutib bo'lmaydi: mazmun o'zgargan zahoti
    test qulaydi va to'g'ri qiymatni aytadi.
    """
    html = (STATIC / "site.html").read_text(encoding="utf-8")
    expected = _content_token(asset)
    assert f"/assets/{asset}?v={expected}" in html, (
        f"{asset} o'zgargan — site.html dagi `?v=` ni `{expected}` ga almashtiring"
    )


# ── Havoladan to'g'ridan-to'g'ri kirish ──────────────────────────────────
#
# Do'kon egasiga "Telegram ID ingizni kiriting, keyin kodni kutib
# turing" deyish — u qilmaydigan ish.  Havola bosilishi bilan panel
# ochilishi kerak.  Havoladagi qiymat — uzun tasodifiy token (`?key=`);
# Telegram ID emas, chunki ID sir emas.


def test_owner_panel_logs_in_from_the_link() -> None:
    html = (STATIC / "owner.html").read_text(encoding="utf-8")
    assert "loginFromLink" in html
    assert 'params.get("key")' in html, "havoladagi token o'qilmayapti"
    assert "loginFromLink()" in html, "sahifa ochilganda chaqirilmayapti"


def test_link_login_uses_the_token_endpoint() -> None:
    """Havola server tomonda tekshiriladi va Telegram ID ishlatilmaydi.

    `?tg=<id>` oqimi ataylab olib tashlangan: ID ochiq ma'lumot, u bilan
    kirish mumkin bo'lsa istalgan odam panelga kirardi.  Bu test o'sha
    oqim qaytib kelmasligini qo'riqlaydi.
    """
    html = (STATIC / "owner.html").read_text(encoding="utf-8")
    block = html[html.index("async function loginFromLink") :]
    block = block[: block.index("async function passwordLogin")]
    assert "/api/v1/owner/auth/link" in block, "token server tekshiruvidan o'tsin"
    assert "d.access_token" in block, "token faqat serverdan olinsin"
    assert 'params.get("tg")' not in html, "Telegram ID bilan kirish qaytmasin"
    assert "params.get('tg')" not in html


def test_link_token_is_scrubbed_from_the_address_bar() -> None:
    """Token — credential; kirilgach manzil qatorida qolmasin."""
    html = (STATIC / "owner.html").read_text(encoding="utf-8")
    assert "history.replaceState" in html


def test_stored_session_wins_over_the_link() -> None:
    """Kirgan odam har safar qayta kirmasin."""
    html = (STATIC / "owner.html").read_text(encoding="utf-8")
    assert "if (token)" in html and "showApp();" in html
    assert "loginFromTelegramWebApp" in html
    assert "if (!opened) loginFromLink();" in html


def test_owner_panel_supports_authenticated_telegram_mini_app() -> None:
    html = (STATIC / "owner.html").read_text(encoding="utf-8")
    assert "telegram-web-app.js" in html
    assert "/api/v1/owner/auth/telegram-webapp" in html
    assert "telegramWebApp?.initData" in html


# ── Yangi mijoz paneli qoidalari ─────────────────────────────────────────
#
# Qaror (2026-08-17): panel yorug' brend uslubida, telefonli mijoz uchun.
# Bu testlar eski holat qaytib kelmasligini qo'riqlaydi.


def test_owner_panel_is_light_branded_not_admin_dark() -> None:
    """Panel admin.css (qorong'u dasturchi uslubi) bilan kelmasin."""
    html = (STATIC / "owner.html").read_text(encoding="utf-8")
    assert "owner.css" in html
    assert "admin.css" not in html
    assert "chaqimchi-logo" in html, "brend logotipi ko'rinsin"


def test_owner_staff_tab_disappears_when_the_feature_is_off() -> None:
    """Davomat cloud-pilot sifatida qaytdi, lekin ESKI XATO qaytmasin.

    Ilgari davomat kartasi production'da har ochilishda 403 xato
    ko'rsatib turardi — mijozning birinchi taassuroti "buzuq narsa" edi.
    Endi xodimlar alohida bo'lim: funksiya yoqilmagan saytda **tugmaning
    o'zi chizilmaydi**, ya'ni mijoz bo'sh va tushunarsiz bo'limga umuman
    tusha olmaydi.
    """
    html = (STATIC / "owner.html").read_text(encoding="utf-8")
    assert "/api/v1/owner/faces" in html
    assert "staffEnabled = false" in html, "403 da bo'lim tugmasi olib tashlansin"
    assert "visibleTabs()" in html, "tabbar faqat ochiq bo'limlarni chizsin"


def test_owner_can_add_staff_and_photos_without_us() -> None:
    """Butun ma'no shu: mijoz operatorga murojaat qilmasin."""
    html = (STATIC / "owner.html").read_text(encoding="utf-8")
    assert '"/api/v1/owner/employees"' in html, "xodim qo'shish"
    assert "/photos" in html and 'method: "POST"' in html, "rasm yuklash"
    assert 'accept="image/*"' in html, "telefonda kamera/galereya ochilsin"
    assert "toJpeg" in html, (
        "iPhone HEIC beradi va server uni qabul qilmaydi — brauzerda JPEG ga aylantirilsin"
    )


def test_owner_panel_does_not_break_binary_uploads() -> None:
    """`api()` chaqiruvchi bergan Content-Type ni o'chirib yuborardi —
    rasm `application/json` bo'lib ketardi va server 415 qaytarardi."""
    html = (STATIC / "owner.html").read_text(encoding="utf-8")
    assert 'if (options.body && !headers["Content-Type"])' in html


def test_the_attendance_camera_can_be_chosen_in_the_panel() -> None:
    """Kamera tanlanmasa qurilma yuz kadri umuman yubormaydi — ya'ni
    butun funksiya jimgina ishlamaydi."""
    html = (STATIC / "owner.html").read_text(encoding="utf-8")
    assert "attendance_camera_ids" in html
    assert "attendance_camera_roles" in html
    assert '"/api/v1/owner/config"' in html, "mavjud sozlama endpointi ishlatilsin"


def test_owner_panel_has_no_raw_json_editors() -> None:
    """Lines/Zones JSON textarealar oddiy mijozni cho'chitadi — endi
    geometriya faqat o'rnatuvchi vositasida."""
    html = (STATIC / "owner.html").read_text(encoding="utf-8")
    assert "linesJson" not in html
    assert "zonesJson" not in html
    assert "<textarea" not in html


def test_owner_panel_shows_camera_previews_and_refreshes() -> None:
    html = (STATIC / "owner.html").read_text(encoding="utf-8")
    assert "/preview" in html, "kamera rasmi endpointi ishlatilsin"
    assert "setInterval(refresh" in html, "avto-yangilanish bo'lsin"


def test_owner_can_ask_for_a_fresh_camera_frame() -> None:
    """Rasm kelmagan bo'lsa mijozda tuzatish tugmasi bo'lsin.

    Bungacha panel faqat GET qilardi va "rasm hali kelmagan" yozuvi
    boshi berk ko'cha edi: ustasiz ochilgan do'konda kadrni so'raydigan
    hech kim yo'q edi.
    """
    html = (STATIC / "owner.html").read_text(encoding="utf-8")
    assert "data-shot-refresh" in html, "kartochkada yangilash tugmasi bo'lsin"
    assert "requestFrame" in html
    assert 'onclick=' not in html.split("data-shot-refresh")[1][:400], "inline onclick yo'q"


def test_owner_settings_explain_what_each_number_does() -> None:
    """Raqam so'ralsa, u nimaga ta'sir qilishi yozilgan bo'lsin.

    Navbat ham, kassa nazorati ham `zone.queue` siz UMUMAN ishlamaydi
    (`chaqimchi_ai/scene_analytics.py` — ikkalasi `if queue_zones:`
    ichida).  Mijoz raqam kiritib, natijasini behuda kutmasin.
    """
    html = (STATIC / "owner.html").read_text(encoding="utf-8")
    assert "navbat zonasi chizilgan" in html
    assert "navbat zonasisiz ishlamaydi" in html
    assert "butun kadr" in html, "uzoq turish zonaga bog'liq emasligi aytilsin"
    assert 'id="queueWarn"' in html, "zona chizilmagan bo'lsa ogohlantirish bo'lsin"


def test_owner_panel_hides_the_unobservable_occupancy_limit() -> None:
    """Ko'rinmaydigan sozlama panelda turmasin.

    `occupancy_exceeded` qurilmada chiqadi va bulutga yoziladi, lekin
    hisobotda yo'q, hodisa filtrida yo'q va botga bormaydi (`warning`,
    bot esa faqat `critical`).  Ya'ni raqamni o'zgartirgan mijoz hech
    narsa sezmasdi.  Qiymat configda qoladi.
    """
    html = (STATIC / "owner.html").read_text(encoding="utf-8")
    assert "Odam limiti" not in html
    assert 'id="occupancy"' not in html
    assert "...currentConfig" in html, "yashirin qiymat saqlashda yo'qolmasin"


def test_owner_panel_does_not_ask_for_a_camera_role() -> None:
    """Kamera roli hech kim o'qimaydigan maydon edi.

    Qurilma kirish kamerasini CHIZIQDAN biladi
    (`chaqimchi_ai/retail/service.py: entrance_cameras`), roldan emas.
    Ro'yxatda bo'sh variant ham yo'q edi — birinchi "Saqlash" bosilishi
    bilan hamma kamera jimgina "Kirish" bo'lib qolardi.
    """
    html = (STATIC / "owner.html").read_text(encoding="utf-8")
    assert "ROLE_OPTIONS" not in html
    assert "camera_roles" not in html.replace("attendance_camera_roles", "")
    assert "attendance_camera_roles" in html, "davomat roli BOSHQA narsa — qolsin"
    assert "cameraSetup" in html, "kamera holati chiziq/zonadan hisoblansin"


def test_owner_live_view_uses_its_own_endpoint() -> None:
    """Jonli kadr tayanch rasmni — ya'ni xarita fonini — almashtirmasin."""
    html = (STATIC / "owner.html").read_text(encoding="utf-8")
    assert "/live-frame" in html, "jonli oqim o'z endpointidan o'qilsin"


def test_owner_media_opens_in_a_modal_with_errors_shown() -> None:
    """`window.open(blob)` popup-blockerda yutilardi va xato jim qolardi."""
    html = (STATIC / "owner.html").read_text(encoding="utf-8")
    assert "window.open(" not in html
    assert "renderMediaInModal" in html
    assert "URL.revokeObjectURL" in html, "blob URL oqib ketmasin"


def test_owner_panel_does_not_say_sotqin() -> None:
    """Ichki kod nomi mijozga ko'rinmasin."""
    html = (STATIC / "owner.html").read_text(encoding="utf-8")
    assert "Sotqin" not in html


# ── Admin panel qoidalari ────────────────────────────────────────────────
#
# Qaror (2026-08-19): panel chap yon menyuli, olti bo'limli va yorug'
# brend uslubida.  Sabab foydalanuvchining o'z so'zi bilan: sakkizta karta
# bitta uzun ustunda turardi, navigatsiya yo'q edi, muhim amallar esa
# brauzerning oddiy `prompt` oynasida "auto" yoki "naqd" deb **yozishni**
# talab qilardi.  Quyidagi testlar eski holat qaytib kelmasligini
# qo'riqlaydi.

#: Menyudagi bo'limlar — manzil ham shular ustiga qurilgan (`#/mijozlar`).
ADMIN_SECTIONS = ("boshqaruv", "mijozlar", "tolovlar", "arizalar", "jamoa", "sozlamalar")


def test_admin_panel_has_a_left_sidebar_with_six_sections() -> None:
    html = (STATIC / "admin.html").read_text(encoding="utf-8")
    assert 'class="sidenav"' in html, "chap yon menyu bo'lsin"
    assert 'id="navList"' in html, "menyu ro'yxati bo'lsin"
    for section in ADMIN_SECTIONS:
        assert f'id: "{section}"' in html, f"«{section}» bo'limi yo'qolgan"


def test_admin_panel_has_no_native_dialogs() -> None:
    """`prompt()`/`confirm()` — bu yerda chalkashlikning asosiy sababi edi:
    yangilanish siyosati uchun `auto` yoki `0.6.0` deb yozish, to'lov uchun
    aynan `naqd` deb yozish kerak bo'lardi.  Bitta harf xato — amal
    bajarilmasdi.  (`confirmDialog(` bu qoidaga tushmaydi.)"""
    html = (STATIC / "admin.html").read_text(encoding="utf-8")
    found = re.search(r"(?<![\w.])(prompt|confirm)\s*\(", html)
    assert found is None, f"brauzer oynasi qaytib kelgan: {found.group(0) if found else ''}"


def test_admin_panel_has_no_inline_event_handlers() -> None:
    """`onclick="..."` bilan ID string ichiga qo'yilardi — qochirish
    unutilsa buziladi.  Endi hamma narsa `data-act` jadvali orqali."""
    html = (STATIC / "admin.html").read_text(encoding="utf-8")
    assert re.search(r'\son\w+\s*=\s*"', html) is None, "inline hodisa ishlovchisi qolmasin"


def test_admin_panel_is_light_and_reuses_the_customer_design_system() -> None:
    """Panel mijoz paneli bilan bitta dizayn tilida bo'lsin."""
    html = (STATIC / "admin.html").read_text(encoding="utf-8")
    assert "owner.css" in html, "umumiy dizayn tizimi ulansin"
    assert "panel.css" in html, "admin qismlari alohida faylda"
    assert "admin.css" not in html, "eski qorong'u uslub qaytib kelmasin"
    css = (STATIC / "panel.css").read_text(encoding="utf-8")
    assert "#0a0c10" not in css, "qorong'u fon qaytib kelmasin"


def test_the_dark_admin_css_is_gone_for_good() -> None:
    """`admin.css` o'chirilgan va hech bir sahifa uni chaqirmaydi.

    U qorong'u "dasturchi terminali" uslubi edi: admin paneli, to'lov
    sahifasi va o'rnatuvchi paneli navbat bilan undan yorug' brend
    uslubiga o'tdi.  2026-08-24 da oxirgi iste'molchi (o'rnatuvchi
    paneli) ham ko'chdi — fayl o'chirildi.

    Test qoladi: qorong'u uslub biror sahifaga qaytib kelsa, usta yoki
    mijoz saytdan panelga o'tganda butunlay boshqa mahsulotga
    tushgandek bo'ladi."""
    assert not (STATIC / "admin.css").exists(), "qorong'u uslub qaytib kelmasin"
    # Faqat HAQIQIY ulanish tekshiriladi, matnda eslatilishi emas:
    # sahifalardagi izohlar o'tmishni tushuntirib turishi foydali.
    for page in pages():
        links = re.findall(r'<link[^>]+href="([^"]+)"', page.read_text(encoding="utf-8"))
        assert not any("admin.css" in href for href in links), page.name


def test_admin_panel_is_responsive() -> None:
    """Ilgari `admin.css` da bitta ham `@media` yo'q edi va 10 ustunli
    jadval telefonda yon tomonga cheksiz siljirdi."""
    css = (STATIC / "panel.css").read_text(encoding="utf-8")
    assert css.count("@media") >= 2, "telefon va planshet uchun qoidalar bo'lsin"
    assert ".sidenav.open" in css, "telefonda menyu chiqib chiquvchi bo'lsin"


def test_admin_toast_floats_above_the_page() -> None:
    """Xabarnoma sahifa tepasida turardi: pastdagi tugmani bosgan
    foydalanuvchi javobni umuman ko'rmasdi."""
    css = (STATIC / "panel.css").read_text(encoding="utf-8")
    toast = css[css.index("#toast {") : css.index("}", css.index("#toast {"))]
    assert "position: fixed" in toast


def test_admin_customer_page_is_deep_linkable() -> None:
    """Boshqaruvdagi «diqqat talab qiladi» ro'yxati to'g'ridan-to'g'ri
    mijozga olib borishi va brauzerning Orqasi ishlashi kerak."""
    html = (STATIC / "admin.html").read_text(encoding="utf-8")
    assert "hashchange" in html
    assert "#/mijozlar/" in html


def test_admin_panel_speaks_plain_uzbek() -> None:
    """Ichki jargon ekranga chiqmasin."""
    html = (STATIC / "admin.html").read_text(encoding="utf-8")
    for word in (
        "Production tayyorligi",
        "Tannarx",
        "Draftni",
        "Biznes preset",
        "Onboarding",
        "Legacy",
        "CHAQIMCHI_PUBLIC_URL",
        "poll'da",
    ):
        assert word not in html, f"jargon qaytib kelgan: «{word}»"


def test_admin_panel_translates_raw_api_codes() -> None:
    """API xom kod qaytaradi (`probe_status: "online"`, `status:
    "assigned"`).  Ular to'g'ridan-to'g'ri chizilsa foydalanuvchi
    inglizcha holat nomlarini ko'radi — har biri lug'atdan o'tsin."""
    html = (STATIC / "admin.html").read_text(encoding="utf-8")
    for table in ("PROBE_LABEL", "ASSIGN_LABEL", "CONFIG_LABEL", "CONN_LABEL", "STATUS_LABEL"):
        assert f"const {table} = {{" in html, f"{table} lug'ati yo'q"
    # Xom qiymat lug'atdan o'tmasdan chizilmasin.
    assert "esc(c.probe_status)" not in html
    assert "esc(a.status)}</span>" not in html


def test_admin_lists_all_have_empty_states() -> None:
    """Yangi bazada bo'limlar bo'm-bo'sh emas, nima qilish kerakligini
    aytadigan matn bilan ochilsin."""
    html = (STATIC / "admin.html").read_text(encoding="utf-8")
    assert html.count("emptyState(") >= 7


# ── Mijoz yo'li: sotuvni yo'qotadigan joylar ─────────────────────────────
#
# Bularning har biri mijozni to'xtatib qo'yadigan turdan: dastur to'g'ri
# yuklab olinadi-yu, yo'riqnoma uni "noto'g'ri" deb ataydi; to'lov
# sahifasida muammo chiqsa "menejerga murojaat qiling" deyiladi, lekin
# menejerning hech qanday manzili yo'q.


def test_the_install_guide_describes_the_real_file_name() -> None:
    """Server fayl nomiga versiyani qo'shadi (`Chaqimchi_AI_Setup-0.6.2.exe`)
    — mijoz yangi versiyani olganini shundan ko'radi.  Yo'riqnoma esa
    aynan `Chaqimchi_AI_Setup.exe` bo'lishini talab qilardi va boshqasini
    "manba kodi, o'rnatilmaydi" deb atardi.  Mijoz TO'G'RI faylni yuklab
    olib, uni tashlab yuborardi — kritik yo'ldagi o'zi yaratgan xavotir.
    """
    guide = (STATIC / "install.html").read_text(encoding="utf-8")
    assert "Fayl nomi: <code>Chaqimchi_AI_Setup.exe</code>" not in guide
    assert "manba kodini yuklab olgansiz" not in guide


def test_no_page_links_to_an_anchor_that_does_not_exist() -> None:
    """Beshta tugma mavjud bo'lmagan langarga ketardi — shulardan biri
    "o'zim uddalay olmadim, usta chaqiring" degan zaxira yo'l edi."""
    site = (STATIC / "site.html").read_text(encoding="utf-8")
    available = set(re.findall(r'id="([a-zA-Z][\w-]*)"', site))
    for page in pages():
        html = page.read_text(encoding="utf-8")
        for anchor in set(re.findall(r'href="/#([\w-]+)"', html)):
            assert anchor in available, f"{page.name}: `/#{anchor}` — bunday langar yo'q"


def test_the_internal_codename_stays_off_customer_pages() -> None:
    """«Sotqin» o'zbekchada *xoin* degani.  U ichki kod nomi va mijoz
    ko'radigan sahifada turmasligi kerak."""
    for name in ("connect.html", "pay.html", "install.html", "site.html", "aloqa.html"):
        html = (STATIC / name).read_text(encoding="utf-8")
        assert "Sotqin" not in html, f"{name}: ichki nom mijozga ko'rinyapti"


def test_the_installer_guide_is_not_offered_to_search_engines() -> None:
    """U ichki hujjat: mahsulotni 16 marta «Sotqin» deb ataydi va
    `systemctl` buyruqlarini ko'rsatadi.  Brend nomini qidirgan mijoz
    unga tushib qolmasin."""
    html = (STATIC / "installer-guide.html").read_text(encoding="utf-8")
    assert "index,follow" not in html
    assert "noindex" in html


def test_one_sku_has_one_name() -> None:
    """Mijozga «Chaqimchi Lite» sotiladi, to'lov sahifasida esa
    «Sotqin R1» yozilardi — bitta mahsulot, uch xil nom."""
    for name in ("pay.html", "site.html", "owner.html", "admin.html"):
        html = (STATIC / name).read_text(encoding="utf-8")
        assert "Sotqin R1" not in html and "Sotqin Base" not in html


def test_every_payment_dead_end_offers_a_way_out() -> None:
    """To'lov sahifasi — pul oladigan yagona joy.  Onlayn to'lov
    ulanmagan bo'lsa yoki hisob bekor qilingan bo'lsa mijoz shu yerda
    qolib ketardi: na telefon, na Telegram, na orqaga qaytish."""
    html = (STATIC / "pay.html").read_text(encoding="utf-8")
    assert "menejer bilan bog'laning" not in html
    assert "menejerga murojaat qiling" not in html
    assert "__TELEGRAM_REGISTER_URL__" in html, "aloqa havolasi bo'lsin"
    assert "__APP_URL__" in html, "panelga qaytish yo'li bo'lsin"


def test_the_payment_page_is_not_a_dark_developer_screen() -> None:
    """Mijoz yorug' paneldan bosadi va qorong'u sahifaga tushardi —
    aynan pul to'lash paytida."""
    html = (STATIC / "pay.html").read_text(encoding="utf-8")
    assert "admin.css" not in html
    assert "owner.css" in html


def test_the_contact_page_has_a_working_channel_not_a_placeholder() -> None:
    """Sahifada `+998 __ ___ __ __` turardi — pul to'lamoqchi bo'lgan
    do'kon egasi telefon o'rnida chiziqchalarni ko'rardi."""
    html = (STATIC / "aloqa.html").read_text(encoding="utf-8")
    assert "__ ___ __ __" not in html, "soxta raqam o'rniga ishlaydigan kanal ko'rsatilsin"
    assert "__TELEGRAM_REGISTER_URL__" in html


def test_the_privacy_page_does_not_call_itself_unfinished() -> None:
    """Sahifa o'z ichida «production'dan oldin qo'shilishi shart» deb
    turardi — u esa ikkita rozilik belgisidan havola qilinadi va
    production allaqachon ishlayapti."""
    html = (STATIC / "privacy.html").read_text(encoding="utf-8")
    assert "production domen ishga tushishidan oldin" not in html
    assert "ishlab chiqarishdan oldin" not in html


def test_every_page_has_a_favicon() -> None:
    """Brauzer yorlig'ida bo'sh belgi turardi va har ochilishda 404
    ketardi (olti soatda 44 marta)."""
    assert (STATIC / "favicon.svg").is_file()
    for page in pages():
        html = (STATIC / page.name).read_text(encoding="utf-8")
        assert 'rel="icon"' in html, f"{page.name}: favicon havolasi yo'q"


#: Rasmiy telefon.  Bitta joyda yozilsin — o'zgarganda hammasi bir vaqtda
#: yangilanishi kerak, aks holda sahifalar bir-biriga zid raqam ko'rsatadi.
PHONE_HREF = "tel:+998932225070"


def test_the_customer_can_reach_a_human_from_every_dead_end() -> None:
    """Mijozga "bizga yozing" deyiladigan har joyda aloqa yo'li bo'lsin.

    Mijoz panelida bu gap to'rt marta uchraydi, aloqa havolasi esa faqat
    KIRISH ekranida edi — u kirgandan keyin butunlay yashiriladi.  Ya'ni
    "yozing" deb aytilardi-yu, qayerga yozishni ko'rsatilmasdi.
    """
    for name in ("aloqa.html", "pay.html", "site.html", "owner.html"):
        html = (STATIC / name).read_text(encoding="utf-8")
        assert PHONE_HREF in html, f"{name}: telefon havolasi yo'q"


def test_the_owner_panel_shows_help_after_login_not_only_before() -> None:
    """Yordam bloki `#app` ichida bo'lsin: kirish ekranidagi havola
    kirgandan keyin `display:none` bo'lib qoladi."""
    html = (STATIC / "owner.html").read_text(encoding="utf-8")
    body = html[html.index("<main") : html.index("</main>")]
    assert PHONE_HREF in body, "yordam bloki panel ichida bo'lsin"


# ── Mijoz paneli: bitta operativ ekran ───────────────────────────────────
#
# Panel bitta uzun ustun edi: telefonda 13 400px — o'n olti ekran, va
# uning taxminan 60% i 101 qatorli xom hodisa jadvali edi.  Do'kon egasi
# uni telefondan ochadi.
#
# Bo'limlar STATIK markup: JS satrlaridan yasalsa quyidagi va yuqoridagi
# matn-tekshiruvlar (masalan `class="card hidden" id="attendanceCard"`)
# ishlamay qolardi.

def test_owner_panel_has_one_operational_screen_without_tabs() -> None:
    html = (STATIC / "owner.html").read_text(encoding="utf-8")
    assert 'id="operationalDashboard"' in html
    assert 'id="cameraOverview"' in html
    assert 'id="operationalHeatCanvas"' in html
    assert 'id="operationalSecurity"' in html
    assert 'class="tabbar"' not in html
    assert "renderOperational" in html
    assert 'data-heatmode="plan"' not in html


def test_owner_tabs_fail_independently() -> None:
    """Bitta so'rov yiqilsa butun panel bo'shab qolmasin.

    Ilgari `refresh()` hamma so'rovni bitta `try` ichida bajarardi:
    `/report` yiqilsa Hodisalar, Xavfsizlik, Kunlar va Davomat kartalari
    ham bo'sh qolardi — uzilish "bugun mijoz yo'q" bilan bir xil
    ko'rinardi.  Bu mahsulot uchun eng yomon aralashtirish.
    """
    html = (STATIC / "owner.html").read_text(encoding="utf-8")
    assert "needSettled" in html
    assert "allSettled" in html, "so'rovlar bir-birini yiqitmasin"
    assert html.count("cardError(") >= 4, "har karta o'z xatosini ko'rsatsin"
    assert "data-retry" in html, "qayta urinish tugmasi bo'lsin"


def test_owner_event_list_is_not_a_hundred_rows() -> None:
    """101 qator sahifaning 60% ini egallardi."""
    html = (STATIC / "owner.html").read_text(encoding="utf-8")
    assert 'limit: "100"' not in html
    assert "eventLimit = 25" in html
    assert "event-card" in html, "telefonda jadval emas, kartochka"


def test_owner_canvas_accepts_touch() -> None:
    """`touch-action` bo'lmasa kanvasni sudrash o'rniga sahifa siljiydi —
    ya'ni pol burchaklarini telefondan to'g'irlab bo'lmaydi.  Lokal
    panelda bu allaqachon to'g'ri qilingan."""
    css = (STATIC / "owner.css").read_text(encoding="utf-8")
    assert "touch-action" in css


def test_owner_drag_does_not_storm_the_server() -> None:
    """Har `pointermove` da issiqlik xaritasi ham, kamera rasmi ham qayta
    so'ralardi — bir soniyalik sudrash o'nlab so'rov tug'dirardi."""
    html = (STATIC / "owner.html").read_text(encoding="utf-8")
    move = html[html.index('addEventListener("pointermove"') : html.index('addEventListener("pointerup"')]
    assert "loadHeatmap()" not in move, "so'rov sudrash paytida emas, oxirida"
    assert "requestAnimationFrame" in move


def test_owner_tap_targets_are_big_enough() -> None:
    """34px barmoq uchun kichik — 40px eng kichik ishonchli o'lcham."""
    css = (STATIC / "owner.css").read_text(encoding="utf-8")
    small = css[css.index(".button.small {") : css.index("}", css.index(".button.small {"))]
    assert "min-height: 40px" in small
    assert css.count("@media") >= 4, "telefon, planshet va kompyuter uchun qoidalar"


def test_owner_deep_link_survives_the_login_redirect() -> None:
    """`?key=` tozalanganda `location.hash` ham yo'qolardi — ya'ni
    Telegramdan kelgan bo'limga havola har doim Bugun'ga tushardi."""
    html = (STATIC / "owner.html").read_text(encoding="utf-8")
    scrub = html[html.index("params.delete(\"key\")") : html.index("showApp();", html.index("params.delete(\"key\")"))]
    assert "location.hash" in scrub


def test_owner_login_screen_offers_exactly_one_way_in() -> None:
    """Kirish ekranida UCHTA yo'l bor edi — Telegram tugmasi, login/parol
    va Telegram kod — mijoz esa qaysi biri o'ziniki ekanini bilmasdi.

    Endi bitta asosiy yo'l: login va parol.  Telegram kodi butunlay
    olib tashlandi (bu yerda emas, kirgandan keyin ulanadi)."""
    html = (STATIC / "owner.html").read_text(encoding="utf-8")
    login = html[html.index('<section id="login"') : html.index("</section>")]
    assert login.count("<button") == 1, "kirish ekranida bitta asosiy tugma qolsin"
    for gone in ("otpRequestBtn", "otpVerifyBtn", "requestOtp", "verifyOtp", "auth/request", "auth/verify"):
        assert gone not in html, f"eski kod bilan kirish qoldiqlari: {gone}"


def test_owner_login_submits_as_a_form() -> None:
    """Telefon klaviaturasidagi "Kirish" tugmasi ham ishlashi kerak —
    `click` tinglovchisi buni qo'llab-quvvatlamaydi."""
    html = (STATIC / "owner.html").read_text(encoding="utf-8")
    assert '<form id="loginForm"' in html
    assert '$("loginForm").addEventListener("submit"' in html
    assert "event.preventDefault()" in html


def test_owner_never_asks_the_shopkeeper_for_a_telegram_id() -> None:
    """A'zo qo'shish uchun RAQAMLI Telegram ID so'ralardi.  Do'kon egasi
    na o'ziniki, na xodiminikini biladi — ya'ni funksiya amalda ishlamasdi.
    Endi panel bir martalik havola beradi, bot o'zi qo'shadi."""
    html = (STATIC / "owner.html").read_text(encoding="utf-8")
    assert "newMemberId" not in html
    assert 'inputmode="numeric" placeholder="Masalan: 123456789"' not in html
    assert "/api/v1/owner/telegram-invite" in html
    # Yangi oyna ochilmaydi: telefonda u bo'sh varaq bo'lib qolardi.
    connect = html[html.index("async function connectMyTelegram") : html.index("async function toggleDigest")]
    assert "location.href = data.url" in connect


def test_owner_uses_the_shop_day_not_utc() -> None:
    """«Kecha» tugmasi `Date.now() - 86400000` ni UTC sanaga aylantirardi.

    Toshkent UTC+5: yarim tundan 05:00 gacha bu IKKI kun oldingi
    hisobotni so'rardi va panel bo'sh ko'rinardi.  Server esa kunni
    `Asia/Tashkent` bo'yicha ajratadi — ikkalasi bitta kunni tushunishi
    shart.  Brauzerda o'lchandi: `?date=2026-08-18` o'rniga `2026-08-19`.
    """
    html = (STATIC / "owner.html").read_text(encoding="utf-8")
    assert 'timeZone: "Asia/Tashkent"' in html
    assert "toISOString().slice(0, 10)" not in html, "UTC sanasi qaytib kelmasin"


def test_owner_shows_the_data_it_already_fetches() -> None:
    """Server bu maydonlarni qaytarardi, panel esa tashlab yuborardi."""
    html = (STATIC / "owner.html").read_text(encoding="utf-8")
    for field in ("xodim_chiqarilgan", "queue.average", "quietest_day", "previous_total"):
        assert field in html, f"`{field}` hali ko'rsatilmayapti"
    assert "drawDwell" in html, "«qayerda uzoq turishadi» ro'yxati"


def test_owner_hourly_chart_can_show_occupancy() -> None:
    """`hourly[].exited` olinardi va ishlatilmasdi.  Kirganlar minus
    chiqqanlar — «soat 15:00 da do'konda nechta odam bor edi» degan
    savolning javobi."""
    html = (STATIC / "owner.html").read_text(encoding="utf-8")
    assert 'data-hourmode="inside"' in html
    assert "h.exited" in html


def test_the_hero_shows_the_product_frame_as_live_markup() -> None:
    """Hero'dagi panel ramkasi HTML bo'lsin, skrinshot emas.

    2026-08-24 da eski izometrik sahna o'chirildi: u chizilgan
    illyustratsiya edi va mahsulotni ko'rsatmasdi.  O'rniga panel
    ramkasi — jonli kadr ustida ikkita karta.

    Ramka rasmga aylantirilmasin: matn har ekranda o'qiladigan bo'lib
    qolishi, kichik ekranda esa kartalar CSS bilan yashirinishi kerak.
    Skrinshotda ikkalasi ham imkonsiz.
    """
    site = (STATIC / "site.html").read_text(encoding="utf-8")
    css = (STATIC / "site.css").read_text(encoding="utf-8")

    assert 'class="panel-chrome"' in site, "panel ramkasi sahifa ichida bo'lsin"
    assert "Bugungi mijozlar" in site, "ko'rsatkich kartasi matni sahifada bo'lsin"
    assert ".panel-card" in css, "kartalar ko'rinishi uslub faylidan boshqarilsin"
    # Haqiqiy 3D ataylab yo'q: yopishqoq sarlavhadagi `backdrop-filter`
    # bilan yonma-yon turganda u arzon telefonlarda sahifani silkitadi.
    assert "rotateX" not in css
    assert "perspective" not in css


def test_reduced_motion_stops_animations_not_just_transitions() -> None:
    """Ilgari faqat `transition` to'xtardi — `animation` davom etardi."""
    css = (STATIC / "site.css").read_text(encoding="utf-8")
    block = css[css.index("@media (prefers-reduced-motion: reduce)") :]
    block = block[: block.index("\n}") + 2]
    assert "animation: none" in block


def test_the_landing_shows_the_real_panel_not_a_drawing() -> None:
    """Bosh sahifada mahsulotning O'ZI ko'rinsin.

    Rasmlar `scripts/make_panel_screenshots.py` bilan olinadi: interfeys
    haqiqiy, raqamlar namunaviy.  Hajm chegarasi yuqoridagi umumiy
    test bilan tekshiriladi.
    """
    site = (STATIC / "site.html").read_text(encoding="utf-8")
    # Versiya raqami fayl nomida: rasm qayta olinganda nom ham
    # o'zgarishi SHART, aks holda qaytgan mijoz brauzer keshidan eski
    # panel suratini oladi va sayt endi mavjud bo'lmagan interfeysni
    # reklama qiladi.  v3/v4 — 2026-08-24, yangi dizayndagi panel.
    for image in ("panel-bugun-v3.webp", "panel-xarita-v4.webp"):
        assert image in site, image
        assert (STATIC / image).is_file(), image
    # Ekrandan pastda — birinchi ochilishni sekinlashtirmasin.
    proof = site[site.index('id="imkoniyat"') : site.index('id="narx"')]
    assert proof.count('loading="lazy"') == 2


def live_css(css: str) -> str:
    """Brauzer HAQIQATAN ko'radigan CSS: izohlar olib tashlangan.

    Oddiy regex yetmaydi va buning aniq sababi bor.  2026-08-21 da
    `site.css` da yopilmagan izoh paydo bo'ldi (o'lik qoidalarni
    tozalaydigan skript izohlarni bilmasdi va ular ichidagi `{ }` ni
    qoida deb o'yladi).  Natijada ro'yxatdan o'tish formasining butun
    uslubi izoh ichida qolib ketdi — jonli saytda forma tarqalib, spam
    tuzog'i (`.honey`) esa mijozga KO'RINIB turdi.

    Yopilmagan izoh o'zidan keyingi hamma narsani yutadi, shuning uchun
    bu yerda u ataylab "shu joydan keyin hech narsa yo'q" deb
    hisoblanadi — brauzer aynan shunday qiladi.
    """
    out, index = [], 0
    while True:
        start = css.find("/*", index)
        if start == -1:
            out.append(css[index:])
            return "".join(out)
        out.append(css[index:start])
        end = css.find("*/", start + 2)
        if end == -1:
            return "".join(out)  # yopilmagan — qolgani o'lik
        index = end + 2


def test_the_stylesheet_has_no_unterminated_comment() -> None:
    """Bitta yopilmagan `/*` butun fayl oxirini o'ldiradi.

    Buni bitta qator bilan ushlash mumkin edi va ushlanmadi: jonli
    saytda forma bir necha soat buzuq turdi.
    """
    for name in ("site.css", "owner.css", "admin.css", "docs/docs.css"):
        path = STATIC / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        assert text.count("/*") == text.count("*/"), f"{name}: izoh yopilmagan"


def test_shared_pages_keep_the_styles_they_use() -> None:
    """`site.css` ni TO'QQIZTA sahifa bo'lishadi.

    Bosh sahifa qayta qurilganda o'lik qoidalar tozalandi.  Xavf aniq
    edi: `install.html` yoki `installer-guide.html` ishlatadigan sinf ham
    "landingda ishlatilmayapti" degan sabab bilan o'chib ketishi mumkin —
    va sahifa shunchaki uslubsiz ochilardi.

    Tekshiruv ro'yxatga emas, HAQIQATGA tayanadi: har sahifada uchraydigan
    har bir sinf uchun `site.css` da **tirik** qoida bo'lishi shart.

    "Tirik" so'zi bu yerda asosiy: ilgari sinf nomi izoh ICHIDA
    turgani ham "qoida bor" deb hisoblanardi va shu sabab test buzilgan
    faylni yashil deb o'tkazib yubordi.
    """
    css = live_css((STATIC / "site.css").read_text(encoding="utf-8"))
    pages = [
        page
        for page in STATIC.glob("*.html")
        if "site.css" in page.read_text(encoding="utf-8")
    ]
    assert len(pages) >= 8, "site.css ni ko'p sahifa bo'lishadi"

    #: Qoidasiz ishlatiladigan sinflar: `icon` — sprayt uchun belgi,
    #: `hidden` — atribut, `hero-copy`/`proof` esa grid bolasi va
    #: ularning ko'rinishi ota-elementdan keladi.
    exempt = {"icon", "hidden", "hero-copy", "proof"}

    shared = set(re.findall(r"\.([a-zA-Z][\w-]*)", css))
    missing: dict[str, set[str]] = {}
    for page in pages:
        markup = page.read_text(encoding="utf-8")
        # Sahifaning O'Z `<style>` bloki ham hisobga olinadi: ba'zi
        # sahifalar (yo'riqnoma, rozilik shabloni) uslubini o'zida
        # olib yuradi.
        inline = live_css(
            "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", markup, re.S))
        )
        known = shared | set(re.findall(r"\.([a-zA-Z][\w-]*)", inline))
        for attr in re.findall(r'class="([^"]+)"', markup):
            for name in attr.split():
                if name in exempt or name in known:
                    continue
                missing.setdefault(page.name, set()).add(name)
    assert not missing, f"uslubi yo'q sinflar: {missing}"


def test_the_cloud_image_carries_the_model_manifests() -> None:
    """Manifestsiz `fetch_face_models.py` konteynerda ishlamaydi.

    Bu aynan jonli deployda ushlangan: skript manifestni repodan
    o'qiydi, Dockerfile esa `models/` ni ko'chirmasdi — natijada
    modelni o'rnatib bo'lmasdi va davomat jimgina ishlamay qolardi.
    Eski skript checksumlarni o'z ichida saqlagani ham shu sababdan
    edi.
    """
    root = STATIC.parents[1]
    dockerfile = (root / "Dockerfile.cloud").read_text(encoding="utf-8")
    assert "COPY models ./models" in dockerfile

    ignored = (root / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert "models/" not in [line.strip() for line in ignored]

    manifest = json.loads((root / "models" / "faces_manifest.json").read_text(encoding="utf-8"))
    assert manifest["license"] == "Apache-2.0"
    assert len(manifest["files"]) == 6, "har model uchun .xml va .bin"


def test_the_heatmap_explains_its_colours() -> None:
    """Xarita rangi qat'iy qizil emas, ko'kdan qizilgacha — va izohli.

    Ilgari bitta qizil rangning faqat shaffofligi o'zgarardi: 0.25 va
    0.45 shaffoflik ko'zga deyarli bir xil ko'rinadi, ayniqsa rangli
    kamera kadri ustida.  Rang shkalasi (legenda) esa umuman yo'q edi —
    mijoz rangni raqamga bog'lay olmasdi.
    """
    owner = (STATIC / "owner.html").read_text(encoding="utf-8")
    css = (STATIC / "owner.css").read_text(encoding="utf-8")

    assert "HEAT_STOPS" in owner
    assert "heatColor(" in owner
    assert "heatLegendGradient(" in owner
    assert 'id="heatLegend"' in owner
    assert ".heat-legend" in css

    # Eski qotirilgan qizil ikkala chizish joyidan ham ketgan bo'lsin —
    # bittasi qolib ketsa xarita ikki xil ko'rinardi.
    assert "rgba(220, 38, 38" not in owner

    # Legenda qulflash ro'yxatida: Boshlang'ich tarifida yolg'iz
    # osilib qolmasin.
    locks = owner[owner.index("function applyPlanLocks") :]
    locks = locks[: locks.index("\n  }")]
    assert "heatLegend" in locks


# ── Ikonka sprayti ──────────────────────────────────────────────────────


def test_the_icon_sprite_parses_as_xml() -> None:
    """SVG XML sifatida o'qiladi — bitta xato butun sprayti o'ldiradi.

    2026-08-24 da izoh ichiga CSS o'zgaruvchisi nomi yozilgan edi
    (ketma-ket ikkita tire).  XML uni izohning tugashi deb bildi, fayl
    yaroqsiz bo'ldi va SAYTDAGI HAMMA IKONKA g'oyib bo'ldi.  Brauzer
    konsolda hech narsa demaydi — xato faqat ko'z bilan ko'rinadi.
    """
    import xml.etree.ElementTree as ET

    ET.parse(STATIC / "icons.svg")


def test_every_icon_the_pages_ask_for_actually_exists() -> None:
    """Yo'q `id` ga murojaat jimgina bo'sh joy qoldiradi.

    Sprayt va uni ishlatuvchilar boshqa-boshqa fayllarda: ikonkani
    qayta nomlash oson, hamma murojaatni yangilashni unutish ham.
    """
    import re
    import xml.etree.ElementTree as ET

    tree = ET.parse(STATIC / "icons.svg")
    have = {
        symbol.get("id")
        for symbol in tree.getroot().iter("{http://www.w3.org/2000/svg}symbol")
    }
    assert have, "sprayt bo'sh"

    wanted: set = set()
    for path in list(STATIC.rglob("*.html")) + list(STATIC.rglob("*.js")):
        wanted |= set(re.findall(r"icons\.svg#([a-z-]+)", path.read_text(encoding="utf-8")))
    # Tarif punktlari ikonka nomini serverdan oladi.
    plans = STATIC.parents[1] / "chaqimchi_ai" / "licensing" / "plans.py"
    wanted |= set(re.findall(r'icon="([a-z-]+)"', plans.read_text(encoding="utf-8")))

    missing = sorted(wanted - have)
    assert not missing, f"sprayda yo'q ikonkalar: {missing}"


def test_the_icons_take_their_colour_from_the_page() -> None:
    """Yassi dizayn: rang CSS dan keladi, sprayda qattiq rang yo'q.

    Eski "3D" ikonkalarda gradient va soya qotirilgan edi — ular ko'k
    dizaynga o'tgandan keyin ham eski ko'rinishda qolib ketgandi.
    """
    text = (STATIC / "icons.svg").read_text(encoding="utf-8")

    assert "currentColor" in text
    assert "linearGradient" not in text, "gradient — eski 3D uslub qoldig'i"
    # Izohdagi misollar hisobga olinmasin: faqat haqiqiy atributlar.
    import re

    for attr in re.findall(r'(?:fill|stroke)="([^"]+)"', text):
        assert attr in {"none", "currentColor"}, f"qattiq rang: {attr}"
