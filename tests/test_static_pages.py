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
    removed = ("run_windows.bat", "install_windows.bat", "local-onboarding", "chaqimchi_ai.pair_sotqin")
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
            if ord(char) > 0x2100
            and unicodedata.category(char) == "So"
            and char not in TYPOGRAPHIC
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
        for name in re.findall(r'/assets/([\w\-.]+\.(?:png|jpg|jpeg|webp))', text):
            asset = STATIC / name
            if not asset.is_file():
                continue
            size_kb = asset.stat().st_size / 1024
            assert size_kb < 200, f"{page.name} → {name}: {size_kb:.0f} KB, juda katta"
