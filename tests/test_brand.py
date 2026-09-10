"""Brend qo'riqchisi: eski nom kodga qaytib kelmasin, eski qurilma esa ishlayversin.

2026-09 rebrendi (Chaqimchi AI → ENES) 300 dan ortiq faylga tegdi.  Bu
test ikki narsani qulflaydi:

1. Yangi kodda eski nom faqat RUXSAT ETILGAN joylarda: ko'priklar
   (eski paket nomi, eski env prefiksi, eski reliz prefiksi, eski
   Windows vazifa/registr nomlari) — ularning har biri o'rnatilgan
   qurilma yoki jonli server uchun kerak va o'chirilishi alohida qaror.
2. Ko'priklarning o'zi ishlaydi: eski reliz nomi topiladi, eski
   ma'lumot papkasi ishlatiladi.  ⚠️ Ma'lumot papkasi ko'prigi IKKI
   modulda kerak — `enes/paths.py` (Box) va `enes/local/paths.py`
   (do'kon dasturi).  Bu yerdagi test uzoq vaqt faqat birinchisini
   tekshirdi va 2026-09-09 da pilot aynan ikkinchisi yo'qligidan
   to'xtadi; ikkinchisining qulfi `tests/test_local_paths.py` da.

F7 cutover (2026-09-11): bot nomi `@enes_monitoring_bot` — eski nom
taqiqda.  Domen `chaqimchi.uz` esa ATAYLAB ruxsatda qoladi: ikkala
domen parallel ishlaydi (Caddyfile ikki nomli bloklar, pilot qurilmasi
eski `api.` da), 301 bosqichida bu ruxsat olib tashlanadi.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: Eski nomni saqlashga HAQLI fayllar — har birining sababi yonida.
ALLOWED_FILES = {
    "chaqimchi_ai/__init__.py",        # eski paket nomi ko'priki (qurilma yangilanishi)
    "enes/envcompat.py",               # CHAQIMCHI_* → ENES_* ko'priki
    "enes/paths.py",                   # eski ma'lumot papkasi bor bo'lsa ishlatiladi (Box)
    "enes/local/paths.py",             # xuddi shu ko'prik — do'kon dasturi uchun
    "tests/test_local_paths.py",       # o'sha ko'prikning qulfi
    "enes/local/autostart.py",         # eski vazifa/Run kaliti o'chiriladi
    "enes/local/chain_processes.py",   # eski nomdagi zanjir ham o'ldiriladi
    "enes/signed_update.py",           # eski `product` nomi (o'tish relizi + orqaga qaytish)
    "scripts/publish_windows_release.sh",  # o'tish relizi eski nom bilan chiqadi
    "Makefile",                        # o'tish relizi bayrog'i (LEGACY_NAME)
    "docs/RELIZ_VA_OTA.md",            # o'tish relizi tartibi hujjatlangan
    "tests/test_rollout.py",           # o'tish relizi nomining qulfi
    "scripts/windows_installer.nsi",   # eski o'rnatishni topib olib tashlaydi
    "scripts/build_windows_payload.py",  # ko'prik papkasi payloadga kiradi
    "scripts/sign_release.py",         # eski arxivni qayta imzolash, eski kalit yo'li
    "scripts/generate_update_key.py",  # eski kalit yo'li
    "cloud/main.py",                   # eski reliz nomi va product_name
    "cloud/store.py",                  # bazadagi eski product_name qatorlari
    "tests/test_brand.py",
    "tests/test_envcompat.py",
    "tests/test_windows_installer.py",
    "tests/test_panel_v2.py",          # eski brend qo'riqchisi
    "tests/test_site_build.py",        # eski brend qo'riqchisi
    "tests/test_sign_release.py",      # repo papkasi nomi
    "cloud/static/v2/owner-sw.js",     # kesh nomi tarixi (izoh)
    "CLAUDE.md",                       # ko'priklar va eski kalit yo'li hujjatlangan
}

#: 301 bosqichigacha qoladigan belgilar: eski domen (parallel rejim),
#: repo manzili, eski env prefiksi (ko'prik).
ALLOWED_TOKENS = re.compile(r"chaqimchi\.uz|chaqimchi-ai\.git|CHAQIMCHI_")

#: Butunlay tekshirilmaydigan yo'llar.
#: Tarix hujjatlari — ular o'sha paytdagi nomni saqlaydi.
SKIPPED_PREFIXES = ("releases/", "docs/archive/", "cloud/static/v2/assets/", "chaqimchi_ai/")
SKIPPED_FILES = {"STRATEGIK_AUDIT_VA_REJA.md", "ISH_DAFTARI.md", "AUDIT_TAHLIL.md"}
TEXT_SUFFIXES = {
    ".py", ".ts", ".tsx", ".html", ".css", ".js", ".json", ".yml", ".yaml", ".toml",
    ".sh", ".nsi", ".service", ".timer", ".example", ".txt", ".cfg", ".ini", ".svg", ".md",
}


def _tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split("\n")
    return [Path(line) for line in out if line]


def test_the_old_brand_survives_only_in_the_bridges() -> None:
    offenders: list[str] = []
    for rel in _tracked_files():
        text_path = str(rel)
        if text_path.startswith(SKIPPED_PREFIXES) or rel.name in SKIPPED_FILES:
            continue
        if rel.suffix not in TEXT_SUFFIXES and rel.name not in ("Makefile", "Dockerfile.cloud", ".gitignore"):
            continue
        if text_path in ALLOWED_FILES:
            continue
        try:
            text = (ROOT / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        cleaned = ALLOWED_TOKENS.sub("", text)
        for number, line in enumerate(cleaned.splitlines(), 1):
            if "chaqimchi" in line.lower():
                offenders.append(f"{text_path}:{number}: {line.strip()[:90]}")
    assert not offenders, "eski brend qaytib keldi:\n" + "\n".join(offenders[:40])


def test_legacy_release_names_are_still_served() -> None:
    """Serverdagi `chaqimchi-windows-0.6.29.exe` yangi kodda ham topilsin —
    aks holda birinchi `enes-windows` relizigacha qurilmalar yangilanmasdi."""
    from cloud.main import RELEASE_FILE_PATTERN, WINDOWS_RELEASE_PATTERN

    for name in ("enes-windows-0.7.0.exe", "chaqimchi-windows-0.6.29.exe"):
        assert WINDOWS_RELEASE_PATTERN.match(name), name
        assert RELEASE_FILE_PATTERN.match(name), name
    assert RELEASE_FILE_PATTERN.match("chaqimchi-sotqin-0.6.0.tar.gz")
    assert not WINDOWS_RELEASE_PATTERN.match("other-windows-1.0.exe")


def test_a_versioned_legacy_release_is_found(tmp_path: Path, monkeypatch) -> None:
    from cloud import main

    (tmp_path / "chaqimchi-windows-0.6.29.exe").write_bytes(b"MZ")
    (tmp_path / "chaqimchi-windows-0.6.29.json").write_text("{}")
    monkeypatch.setattr(main, "_release_dirs", lambda: [tmp_path])

    found = main._windows_release_by_version("0.6.29")

    assert found is not None and found["exe"].name == "chaqimchi-windows-0.6.29.exe"
    assert main.latest_windows_release()["version"] == "0.6.29"


def test_the_old_data_folder_is_used_when_the_new_one_does_not_exist(
    tmp_path: Path, monkeypatch
) -> None:
    """Yangilangan kompyuterda sozlama, token va bufer eski papkada —
    yangi nom bilan bo'sh papkaga o'tib ketsa qurilma «juftlanmagan»
    bo'lib qolardi."""
    from enes import paths

    monkeypatch.setattr(paths, "_LINUX_LEGACY", {str(tmp_path / "opt/enes"): str(tmp_path / "opt/chaqimchi")})
    legacy = tmp_path / "opt/chaqimchi"
    legacy.mkdir(parents=True)

    assert paths._linux_dir(str(tmp_path / "opt/enes")) == legacy

    (tmp_path / "opt/enes").mkdir()
    assert paths._linux_dir(str(tmp_path / "opt/enes")) == tmp_path / "opt/enes"


@pytest.mark.parametrize("name", ["Chaqimchi AI", "Chaqimchi AI Update"])
def test_the_installer_removes_the_old_named_tasks(name: str) -> None:
    """Eski vazifa qolsa dastur ikki nusxada ochiladi."""
    nsi = (ROOT / "scripts" / "windows_installer.nsi").read_text(encoding="utf-8")
    assert f'schtasks /Delete /F /TN "{name}"' in nsi
    assert 'Uninstall\\ChaqimchiAI" "UninstallString"' in nsi, "eski o'rnatish topilmaydi"
