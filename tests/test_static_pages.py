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
#:
#: Oxirgi to'rttasi 2026-08-25 auditidan keyin qo'shildi.  Edu sahifasi
#: yuz namunalari "O'zbekiston hududidagi infratuzilmada qoladi;
#: xorijdagi serverga yuborilmaydi" deb yozib turgan edi, holbuki
#: server Contabo/Fransiyada (`whois 169.58.198.111`).  Bu shunchaki
#: noaniq gap emas — bolalar biometrikasi haqidagi YOZMA va'da edi.
#: Hosting hududi o'zgarmagunicha bu jumla saytga qaytib kela olmaydi.
FORBIDDEN_CLAIMS = (
    "barcha ip kamera",
    "barcha standart ip kamera",
    "barcha kamera mos",
    "har qanday kamera",
    "100% aniqlik",
    "o'g'rini aniqlaydi",
    "o‘g‘rini aniqlaydi",
    "xorijdagi serverga yuborilmaydi",
    "hududidagi infratuzilmada qoladi",
    "o'zbekiston hududida saqlanadi",
    "o‘zbekiston hududida saqlanadi",
)


def test_public_pages_make_no_unproven_guarantees() -> None:
    for page in pages():
        if page.name == "installer.html":
            continue  # o'rnatuvchi paneli — mijozga sotuv va'dasi bermaydi
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
    """Fayl o'zgarsa token HAR sahifada o'zgarishi **shart**.

    Shu test tufayli uni unutib bo'lmaydi: mazmun o'zgargan zahoti
    test qulaydi va to'g'ri qiymatni aytadi.

    Ilgari bu test faqat `site.html` ni qaraardi va aynan shu sababdan
    qolgan 13 sahifada token OYLAB eskirib turgan edi (2026-09-06 da
    topildi: site.html'da `256719bdcf`, boshqalarda `d4e6045b1a`).
    Ya'ni sayt yangilangan, mijozning brauzeri esa eski uslubni
    keshdan olib turgan.  Endi ro'yxat sahifalar bo'ylab yuriladi.
    """
    expected = _content_token(asset)
    referring = [p for p in pages() if f"/assets/{asset}?v=" in p.read_text(encoding="utf-8")]
    assert referring, f"{asset} birorta sahifada ishlatilmayapti — test bekorga o'tayapti"

    stale = [
        p.name
        for p in referring
        if f"/assets/{asset}?v={expected}" not in p.read_text(encoding="utf-8")
    ]
    assert not stale, (
        f"{asset} o'zgargan — bu sahifalardagi `?v=` ni `{expected}` ga almashtiring: "
        + ", ".join(stale)
    )


def test_shared_tokens_are_imported_with_a_cache_token() -> None:
    """Rang tokenlari sayt va panel uchun YAGONA fayldan keladi.

    `tokens.css` o'zgarganda mijozning brauzeri eski palitrani keshdan
    olmasin: `site.css` uni `?v=` bilan chaqiradi va bu test o'sha
    tokenni fayl mazmuni bilan solishtiradi.
    """
    css = (STATIC / "site.css").read_text(encoding="utf-8")
    expected = _content_token("tokens.css")
    assert f'@import "tokens.css?v={expected}";' in css, (
        f"tokens.css o'zgargan — site.css dagi `@import` tokenini `{expected}` ga almashtiring"
    )


# ── Havoladan to'g'ridan-to'g'ri kirish ──────────────────────────────────
#
# Do'kon egasiga "Telegram ID ingizni kiriting, keyin kodni kutib
# turing" deyish — u qilmaydigan ish.  Havola bosilishi bilan panel
# ochilishi kerak.  Havoladagi qiymat — uzun tasodifiy token (`?key=`);
# Telegram ID emas, chunki ID sir emas.


# ── Yangi mijoz paneli qoidalari ─────────────────────────────────────────
#
# Qaror (2026-08-17): panel yorug' brend uslubida, telefonli mijoz uchun.
# Bu testlar eski holat qaytib kelmasligini qo'riqlaydi.


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
    for name in ("connect.html", "pay.html", "install.html", "site.html", "aloqa.html", "edu.html"):
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
    # Panellar `tests/test_panel_v2.py` da tekshiriladi (ular endi React).
    for name in ("pay.html", "site.html"):
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
    # Panel ichidagi aloqa — `tests/test_panel_v2.py` da (React sidebar).
    for name in ("aloqa.html", "pay.html", "site.html", "edu.html"):
        html = (STATIC / name).read_text(encoding="utf-8")
        assert PHONE_HREF in html, f"{name}: telefon havolasi yo'q"


# ── Mijoz paneli: bitta operativ ekran ───────────────────────────────────
#
# Panel bitta uzun ustun edi: telefonda 13 400px — o'n olti ekran, va
# uning taxminan 60% i 101 qatorli xom hodisa jadvali edi.  Do'kon egasi
# uni telefondan ochadi.
#
# Bo'limlar STATIK markup: JS satrlaridan yasalsa quyidagi va yuqoridagi
# matn-tekshiruvlar (masalan `class="card hidden" id="attendanceCard"`)
# ishlamay qolardi.

def test_owner_canvas_accepts_touch() -> None:
    """`touch-action` bo'lmasa kanvasni sudrash o'rniga sahifa siljiydi —
    ya'ni pol burchaklarini telefondan to'g'irlab bo'lmaydi.  Lokal
    panelda bu allaqachon to'g'ri qilingan."""
    css = (STATIC / "owner.css").read_text(encoding="utf-8")
    assert "touch-action" in css


def test_owner_tap_targets_are_big_enough() -> None:
    """34px barmoq uchun kichik — 40px eng kichik ishonchli o'lcham."""
    css = (STATIC / "owner.css").read_text(encoding="utf-8")
    small = css[css.index(".button.small {") : css.index("}", css.index(".button.small {"))]
    assert "min-height: 40px" in small
    assert css.count("@media") >= 4, "telefon, planshet va kompyuter uchun qoidalar"


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


# ── Mijoz demografiyasi haqidagi va'da ──────────────────────────────────


def test_a_the_privacy_page_covers_customer_demographics() -> None:
    """Jins/yosh statistikasi ishlab turibdi, maxfiylik sahifasi esa
    faqat XODIM biometrikasi haqida gapirardi.

    Ya'ni mijoz o'zi haqida yig'ilayotgan yagona ma'lumotni rasmiy
    sahifadan topa olmasdi.
    """
    html = (STATIC / "privacy.html").read_text(encoding="utf-8")

    assert "demografiya" in html.lower()
    assert "embedding" in html.lower(), "yuz namunasi OLINMASLIGI aytilsin"


def test_a_the_youngest_age_band_is_not_swallowed_as_a_tag() -> None:
    """`<18` deb yozilsa brauzer uni teg deb biladi va undan keyingi
    matnni yutib yuboradi.  Bu shu bo'limdagi eng ehtimolli jimgina
    xato."""
    html = (STATIC / "privacy.html").read_text(encoding="utf-8")

    assert "&lt;18" in html
    assert "(<18" not in html


def test_a_the_anonymity_promise_is_the_same_on_every_page() -> None:
    """Uch sahifa bitta va'dani beradi.  Biri o'zgarsa boshqalari
    jimgina yolg'onga aylanardi."""
    for name in ("privacy.html", "docs/xavfsizlik.html", "kuzatuv-eslatmasi.html"):
        text = (STATIC / name).read_text(encoding="utf-8").lower()

        assert "tanilmaydi" in text or "tanimaydi" in text, name
        assert "saqlanmaydi" in text, name


def test_a_the_shop_gets_a_printable_notice_for_its_door() -> None:
    """Do'kon egasi mijozga tushuntira olishi kerak, biz esa unga
    tayyor matn beramiz — aks holda u o'zi yozadi yoki umuman
    osmaydi."""
    html = (STATIC / "kuzatuv-eslatmasi.html").read_text(encoding="utf-8")

    assert "window.print()" in html
    assert "@media print" in html
    assert "class=\"blank\"" in html, "do'kon o'z nomini to'ldirsin"
    # Maxfiylik sahifasidan unga yo'l bo'lsin.
    assert "/kuzatuv-eslatmasi" in (STATIC / "privacy.html").read_text(encoding="utf-8")


def test_the_public_offer_exists_and_is_reachable_from_the_footer() -> None:
    """To'lov qabul qilinadigan saytda oferta bo'lishi SHART.

    2026-08-25 auditi (KRITIK-3): sayt hisob-faktura beryapti, oferta
    esa umuman yo'q edi.  Bahsli holatda xizmat doirasi, javobgarlik
    chegarasi va pul qaytarish tartibini ko'rsatadigan hujjat
    bo'lmasdi.
    """
    offer = (STATIC / "oferta.html").read_text(encoding="utf-8")

    for band in (
        "Javobgarlik chegarasi",
        "Pul qaytarish",
        "Bepul sinov",
        "Nizolar",
    ):
        assert band.lower() in offer.lower(), band

    # Footer'dan yo'l bo'lmasa, hujjat bor-u mijoz uni topolmaydi.
    assert '"/oferta"' in (STATIC / "site.html").read_text(encoding="utf-8")


def test_the_offer_promises_no_more_than_the_code_delivers() -> None:
    """Ofertadagi raqamlar KODDAN kelishi kerak.

    Hujjat bir marta yozilib qolib ketadi, kod esa o'zgaradi — shu
    payt oferta jimgina yolg'onga aylanadi va aynan u sud uchun dalil
    bo'ladi.  Shuning uchun bog'liqlik test bilan ushlab turiladi.
    """
    from chaqimchi_ai.licensing.plans import PLANS
    from cloud.main import MEDIA_RETENTION_HOURS_DEFAULT
    from cloud.store import GRACE_DAYS

    offer = (STATIC / "oferta.html").read_text(encoding="utf-8")

    for plan_key in ("boshlangich", "biznes"):
        plan = PLANS[plan_key]
        price = f"{plan.monthly_price():,}".replace(",", " ")
        assert price in offer, f"{plan_key} narxi ofertada boshqacha: {price}"
        assert f"{plan.max_cameras} tagacha" in offer, plan_key

    assert f"<td>{MEDIA_RETENTION_HOURS_DEFAULT} soat</td>" in offer, "media muddati"
    assert f"<b>{GRACE_DAYS} kun</b>" in offer, "qo'shimcha muddat"


def test_the_offer_repeats_the_limits_the_site_promises() -> None:
    """«Nima qilmaydi» bo'limi sotuv matnining teskarisi emas,
    davomi bo'lsin: saytda taqiqlangan va'dalar bu yerda ATAYLAB
    inkor qilinadi."""
    offer = (STATIC / "oferta.html").read_text(encoding="utf-8").lower()

    for denial in ("o‘g‘rilikni", "yong‘in", "xaridorni", "kafolatlamaydi"):
        assert denial in offer, denial


# ── Sotuv sahifasi: faqat ISHLAYDIGAN narsa va'da qilinadi ──────────────
#
# 2026-08-26 o'lchovi: jonli do'kondan 4 606 ta yuz kadri keldi va cloud
# ularning BIRORTASINI ham tanimadi; `demography_daily` butunlay nol edi.
# Sayt esa ikkalasini ham "olasiz" deb sotardi.  Bu FORBIDDEN_CLAIMS ga
# qo'shilmaydi (ibora emas, FUNKSIYA), shuning uchun alohida test.


def _landing_text() -> str:
    """Bosh sahifaning ko'rinadigan matni — HTML izohlarisiz.

    Izohlar chiqarib tashlanadi: ular aynan "nega bu yerda yo'q" degan
    sababni yozadi va tekshiruvni yolg'on yiqitardi.
    """
    import re

    html = (STATIC / "site.html").read_text(encoding="utf-8")
    return re.sub(r"<!--.*?-->", "", html, flags=re.S).lower()


def test_landing_does_not_sell_attendance_or_demography() -> None:
    """Yopiq pilot sotuv sahifasida sotilmaydi.

    Ishlayotgani O'LCHANGACH qaytariladi — o'shanda bu testni ham
    yangilash kerak bo'ladi va aynan shu narsa esdan chiqmasligini
    ta'minlaydi.
    """
    text = _landing_text()
    for claim in ("xodim davomati", "xodimlar davomati", "face id", "mijoz portreti"):
        assert claim not in text, (
            f"bosh sahifada «{claim}» sotilyapti — u hozir yopiq pilot va "
            "jonli o'lchovda ishlamayapti"
        )


def test_landing_promises_only_measured_features() -> None:
    """Va'da qilinayotgan to'rttasi jonli bazada tasdiqlangan."""
    text = _landing_text()
    # Sanash, xarita, tungi nazorat va navbat — 2026-08-26 da o'lchandi.
    assert "kirdi" in text
    assert "javon oldida" in text or "xarita" in text
    assert "yopiq payt" in text
    assert "navbat" in text


def test_footer_credits_the_hardware_partner() -> None:
    html = (STATIC / "site.html").read_text(encoding="utf-8")
    assert "Powered by NS camera" in html


def test_landing_has_canonical_and_valid_structured_data() -> None:
    """Google uchun mashina o'qiydigan ma'lumot — va u BUZUQ bo'lmasin.

    JSON-LD sintaksis xatosi bilan jimgina e'tiborsiz qolinadi: sahifa
    ochiladi, hech qanday xato ko'rinmaydi, foyda esa nol.
    """
    import json
    import re

    html = (STATIC / "site.html").read_text(encoding="utf-8")
    assert 'rel="canonical"' in html

    block = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    assert block, "JSON-LD bloki yo'q"
    data = json.loads(block.group(1).replace("__PUBLIC_ORIGIN__", "https://chaqimchi.uz"))
    types = [item["@type"] for item in data["@graph"]]
    assert types == ["Organization", "SoftwareApplication", "FAQPage"]
    # Razmetkadagi savol sahifada ham bo'lishi kerak — Google mos
    # kelmagan FAQ razmetkasini jazolaydi.
    for question in data["@graph"][2]["mainEntity"]:
        needle = question["name"].split("?")[0][:24]
        assert needle in html, f"razmetkadagi savol sahifada yo'q: {needle}"
