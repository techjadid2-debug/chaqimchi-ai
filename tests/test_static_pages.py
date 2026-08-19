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
        assert not missing, f"{page.name}: spriteда yo'q ikonka — {sorted(missing)}"


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
    assert "if (token) { showApp(); } else { loginFromLink(); }" in html


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


def test_owner_attendance_card_stays_hidden_until_the_pilot_allows_it() -> None:
    """Davomat cloud-pilot sifatida qaytdi, lekin ESKI XATO qaytmasin.

    Ilgari davomat kartasi production'da har ochilishda 403 xato ko'rsatib
    turardi — mijozning birinchi taassuroti "buzuq narsa" edi.  Yangi
    qoida: karta standart holatda yashirin, faqat API ruxsat bersa
    ochiladi; 403 esa jim o'tkaziladi.
    """
    html = (STATIC / "owner.html").read_text(encoding="utf-8")
    assert 'class="card hidden" id="attendanceCard"' in html, "karta standart yashirin bo'lsin"
    assert "/api/v1/owner/faces" in html
    assert '$("attendanceCard").classList.add("hidden")' in html, "403 da karta jim yopilsin"


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


def test_old_admin_css_still_serves_the_installer_panel() -> None:
    """`admin.css` o'chirilmasin — unda hali bitta iste'molchi bor.

    Ilgari uni admin paneli, o'rnatuvchi paneli va to'lov sahifasi
    ishlatardi.  Admin panel yorug' brend uslubiga o'tdi, to'lov sahifasi
    ham (mijoz aynan pul to'lash paytida qorong'u ekranga tushmasligi
    kerak).  Qolgani — o'rnatuvchi paneli, u ichki vosita."""
    assert (STATIC / "admin.css").is_file()
    assert "admin.css" in (STATIC / "installer.html").read_text(encoding="utf-8"), (
        "o'rnatuvchi paneli uslubsiz qolib ketgan"
    )


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
