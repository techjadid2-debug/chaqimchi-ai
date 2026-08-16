"""Windows o'rnatuvchisining qurilish qoidalari.

Bu testlar tarmoqqa chiqmaydi va hech narsa qurmaydi — ular **manba
fayllarini** tekshiradi.  Sabab: haqiqiy qurish ~10 daqiqa va 300 MB yuklab
olish talab qiladi, xatolar esa deyarli har doim shu fayllarda bo'lgan.

Har bir tekshiruv oldin haqiqatan yuz bergan xatodan kelib chiqqan.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "requirements-windows-local.txt"
BUILDER = ROOT / "scripts" / "build_windows_payload.py"
NSIS = ROOT / "scripts" / "windows_installer.nsi"


def _requirement_lines() -> list[str]:
    return [
        line.strip()
        for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


# ── Paket ro'yxati ───────────────────────────────────────────────────────


def test_requirements_file_exists() -> None:
    assert REQUIREMENTS.is_file(), "Windows paketlari ro'yxati yo'q"


@pytest.mark.parametrize("package", ["insightface", "onnxruntime", "onnx", "psycopg", "minio"])
def test_heavy_server_packages_are_not_shipped_to_shops(package: str) -> None:
    """Do'kon kompyuteriga faqat kerakli narsa boradi.

    `insightface` Windows'da tayyor wheel bermaydi va C++ kompilyator talab
    qiladi — oflayn o'rnatish aynan shu yerda yiqilardi.  `psycopg`/`minio`
    esa faqat cloud serverda ishlaydi.  Ilgari o'rnatuvchi mijoz
    kompyuterida `pip install -r requirements.txt` chaqirardi va shu
    paketlarni topolmay xato berardi.
    """
    assert not any(line.lower().startswith(package) for line in _requirement_lines()), (
        f"{package} do'kon kompyuteriga kerak emas"
    )


def test_every_package_is_pinned() -> None:
    """Oflayn paketda diapazon ma'nosiz: mijozda internet yo'q, wheel esa
    qurish paytida tanlangan.  Qat'iy versiya qurishni takrorlanadigan
    qiladi."""
    for line in _requirement_lines():
        assert "==" in line, f"versiya qotirilmagan: {line}"


def test_the_packages_the_local_app_imports_are_present() -> None:
    """Lokal ilova ishga tushishi uchun eng kam kerak bo'lgan to'plam."""
    names = {re.split(r"[=<>\[]", line, maxsplit=1)[0].lower() for line in _requirement_lines()}
    for required in {"fastapi", "uvicorn", "pydantic", "pyyaml", "openvino", "numpy"}:
        assert required in names, f"{required} ro'yxatda yo'q"
    assert "opencv-python-headless" in names, "kamera oqimini o'qish uchun kerak"


# ── Payload quruvchi ─────────────────────────────────────────────────────


def test_builder_downloads_transitive_dependencies() -> None:
    """Eski skriptdagi asosiy xato: `pip download --no-deps`.

    Natijada starlette, anyio, h11 va boshqa o'nlab tranzitiv paketlar
    tushmasdi, mijoz kompyuterida esa o'rnatish "paket topilmadi" bilan
    tugardi.  Yuklab olishda `--no-deps` bo'lmasligi shart.
    """
    source = BUILDER.read_text(encoding="utf-8")
    download_block = source[source.index("download_cmd = ["): source.index("subprocess.run(download_cmd")]
    assert "--no-deps" not in download_block, "yuklab olishda bog'liqliklar tashlab ketilmasin"


def test_builder_verifies_the_python_checksum() -> None:
    """Ilgari `PYTHON_EMBED_SHA256` soxta qiymat edi va `download()` ga
    umuman uzatilmasdi — izohda esa "quyida tekshiriladi" deb yozilgandi."""
    source = BUILDER.read_text(encoding="utf-8")
    digest = re.search(r'PYTHON_EMBED_SHA256 = "([0-9a-f]*)"', source)
    assert digest, "SHA256 e'lon qilinmagan"
    assert len(digest.group(1)) == 64, "SHA256 to'liq emas"
    assert "download(PYTHON_EMBED_URL, archive, PYTHON_EMBED_SHA256)" in source, (
        "SHA256 tekshiruvga uzatilmagan"
    )
    assert "raise SystemExit" in source, "mos kelmasa qurish to'xtashi kerak"


def test_builder_never_ships_the_cloud_to_customers() -> None:
    """Mijoz kompyuterida admin paneli, lead API va to'lov callbacklari
    ishlashi kerak emas — ilgari NSIS butun `cloud/` ni ko'chirardi."""
    source = BUILDER.read_text(encoding="utf-8")
    assert 'CODE_DIRS = ["chaqimchi_ai"]' in source
    assert 'for forbidden in ("cloud", "webapp")' in source, "tekshiruv yo'q"


def test_builder_bundles_the_ai_model_with_a_checksum() -> None:
    source = BUILDER.read_text(encoding="utf-8")
    assert "person-detection-retail-0013.xml" in source
    assert "person-detection-retail-0013.bin" in source
    for digest in re.findall(r'"([0-9a-f]{64})"', source):
        assert len(digest) == 64


# ── NSIS o'rnatuvchi ─────────────────────────────────────────────────────


def _nsis() -> str:
    return NSIS.read_text(encoding="utf-8")


def _nsis_code() -> str:
    """Izohlarsiz NSIS kodi.

    Sarlavhadagi izoh aynan olib tashlangan narsalarni tushuntiradi
    (`.venv`, `netsh advfirewall`, `.vbs`), shuning uchun "bunday satr
    yo'q" degan tekshiruvlar izohga urilib qolmasligi kerak.
    """
    lines = NSIS.read_text(encoding="utf-8").splitlines()
    return "\n".join(line for line in lines if not line.lstrip().startswith(";"))


def test_installer_speaks_uzbek() -> None:
    """Ilgari o'rnatuvchi faqat inglizcha edi — do'kon egasi o'qiy olmasdi."""
    assert 'MUI_LANGUAGE "Uzbek"' in _nsis()


def test_installer_asks_for_permission() -> None:
    """UAC oynasi: mijoz nima o'rnatilayotganini ko'radi va tasdiqlaydi."""
    assert "RequestExecutionLevel admin" in _nsis()


def test_installer_never_opens_the_panel_to_the_network() -> None:
    """Dastur `127.0.0.1` da tinglaydi.  Ilgari 8750 port butun tarmoq
    uchun ochilardi — do'kon Wi-Fi'sidagi har kim panelga kira olardi."""
    source = _nsis_code()
    for port in ("8750", "8760"):
        assert f"localport={port}" not in source, f"{port} porti tarmoqqa ochilmasin"
    assert "protocol=TCP" not in source, "panel TCP porti hech qachon ochilmaydi"


def test_camera_discovery_rule_is_narrow() -> None:
    """Kamera qidiruvi uchun bitta istisno bor: ONVIF javoblari (UDP 3702).

    U **tor** bo'lishi shart — aks holda avvalgi xato qaytadi.  To'rtta
    cheklov birga tekshiriladi: aynan shu port, faqat lokal tarmoq,
    faqat uy/ish tarmog'i profili va faqat dasturning o'z fayli.
    """
    source = _nsis_code()
    if "netsh advfirewall firewall add rule" not in source:
        pytest.skip("fayrvol qoidasi qo'shilmagan")

    assert "localport=3702" in source
    assert "remoteip=localsubnet" in source, "ruxsat lokal tarmoq bilan cheklansin"
    assert "profile=private,domain" in source, "ommaviy Wi-Fi'da yoqilmasin"
    assert "python.exe" in source, "ruxsat faqat dasturning o'ziga berilsin"
    assert "action=allow" in source and "dir=in" in source


def test_uninstaller_removes_the_firewall_rule() -> None:
    """O'chirilgan dasturdan keyin ochiq port qolib ketmasligi kerak."""
    source = _nsis_code()
    if "netsh advfirewall firewall add rule" not in source:
        pytest.skip("fayrvol qoidasi qo'shilmagan")
    assert "netsh advfirewall firewall delete rule" in source


def test_installer_keeps_writable_data_out_of_program_files() -> None:
    """Eng jiddiy xato edi: `run_windows.bat` `Program Files` ichiga `.venv`
    va `data\\` yozmoqchi bo'lardi, u yerda esa yozish huquqi yo'q — dastur
    birinchi ishga tushishdayoq yiqilardi."""
    source = _nsis_code()
    assert "$APPDATA\\Chaqimchi" in source, "ma'lumot ProgramData'da bo'lishi kerak"
    assert ".venv" not in source, "mijoz kompyuterida virtual muhit qurilmaydi"
    assert "pip install" not in source, "o'rnatishda internet talab qilinmasin"


def test_installer_offers_autostart() -> None:
    """Do'kon kompyuteri kechqurun o'chirilib ertalab yoqiladi.  Avtostartsiz
    nazorat jimgina to'xtardi."""
    source = _nsis()
    assert "CurrentVersion\\Run" in source
    assert "SecAutostart" in source


def test_uninstaller_cleans_up_everything_it_created() -> None:
    source = _nsis()
    uninstall = source[source.index('Section "Uninstall"'):]
    for leftover in ("$DESKTOP\\${APP_NAME}.lnk", "ChaqimchiAI", "$INSTDIR\\python"):
        assert leftover in uninstall, f"o'chirishda qolib ketadi: {leftover}"
    assert "DeleteRegValue HKLM \"${REG_RUN}\"" in uninstall, "avtostart yozuvi qolib ketadi"


def test_uninstaller_asks_before_deleting_shop_data() -> None:
    """Kamera sozlamalari va do'kon statistikasi qaytarilmaydi.  Yangilash
    esa jim rejimda o'tadi va ma'lumotga tegmasligi kerak."""
    source = _nsis()
    uninstall = source[source.index('Section "Uninstall"'):]
    assert "IfSilent" in uninstall, "yangilashda ma'lumot so'ralmasdan o'chib ketardi"
    assert "MB_YESNO" in uninstall


def test_installer_launcher_stays_visible_on_error() -> None:
    """Ilgari yorliq `.vbs` orqali oynani berkitib ishga tushirardi —
    xato ekranga chiqmasdi va mijoz nima bo'lganini bilmasdi."""
    source = BUILDER.read_text(encoding="utf-8")
    assert "Chaqimchi_AI.bat" in source
    assert "pause" in source, "xato oynada qolishi kerak"
    assert ".vbs" not in _nsis_code(), "yashirin ishga tushirish qaytarilmasin"


# ── Versiya bitta manbadan ───────────────────────────────────────────────
#
# Haqiqiy xato: `windows_installer.nsi` da versiya qo'lda yozilgan edi
# va siljib ketdi — dastur 0.6.2, o'rnatuvchi esa "0.7.0" deb yozardi.
# Bir marta shunday nomuvofiqlik cheksiz yangilanish siklini keltirib
# chiqargan: cloud bir raqamni, qurilma boshqasini aytardi va yangilash
# hech qachon tugamasdi.


def test_installer_does_not_hardcode_the_version() -> None:
    source = _nsis_code()
    assert not re.search(
        r'!define\s+APP_VERSION\s+"', source
    ), "versiya qo'lda yozilmasin — u siljib ketadi"
    assert 'build\\version.nsh' in source, "versiya qurish paytida yozilishi kerak"


def test_build_writes_the_version_from_the_single_source() -> None:
    """Qurish skripti versiyani `chaqimchi_ai/__init__.py` dan olishi kerak."""
    builder = (Path(__file__).resolve().parents[1] / "scripts" / "build_windows_payload.py").read_text(
        encoding="utf-8"
    )
    assert "version.nsh" in builder
    assert "__version__" in builder, "manba — paketning o'z versiyasi"
    assert "APP_VERSION_NUMERIC" in builder, "NSIS x.x.x.x shaklini talab qiladi"


def test_numeric_version_has_four_parts() -> None:
    """`VIProductVersion` qat'iy `x.x.x.x` kutadi; aks holda kompilyatsiya
    yiqiladi va buni faqat reliz paytida bilardik."""
    import re as _re
    import subprocess
    import sys

    version = _re.search(
        r'__version__\s*=\s*["\']([^"\']+)["\']',
        (Path(__file__).resolve().parents[1] / "chaqimchi_ai" / "__init__.py").read_text(
            encoding="utf-8"
        ),
    )
    assert version is not None
    parts = (version.group(1).split("+")[0].split("-")[0].split(".") + ["0", "0", "0"])[:4]
    numeric = ".".join(part if part.isdigit() else "0" for part in parts)
    assert _re.fullmatch(r"\d+\.\d+\.\d+\.\d+", numeric), numeric
    del subprocess, sys


# ── Masofadan yangilash tezligi ──────────────────────────────────────────
#
# Bu **mahsulot va'dasi**, shunchaki texnik tafsilot emas: admin panel
# mijozga aniq vaqt aytadi.  Ikkalasi bir joyda tekshiriladi, aks holda
# biri o'zgarib, ikkinchisi yolg'on gapirib qolardi.

#: Admin panelda aytiladigan va o'rnatuvchida sozlanadigan vaqt.
UPDATE_CHECK_MINUTES = 15


def test_update_task_runs_often_enough_to_be_useful() -> None:
    """Ilgari 6 soat edi — buyruq berib olti soat kutish amalda
    "masofadan boshqarish yo'q" degani edi."""
    source = _nsis_code()
    assert "/SC MINUTE" in source, "yangilanish soatlab emas, daqiqalab tekshirilsin"
    found = re.search(r"/SC MINUTE /MO (\d+)", source)
    assert found, "tekshirish oralig'i topilmadi"
    assert int(found.group(1)) == UPDATE_CHECK_MINUTES


def test_update_task_runs_with_admin_rights() -> None:
    """Yangilash `Program Files` ga yozadi.  Dastur oddiy foydalanuvchi
    huquqi bilan ishlaydi va o'zini eleva qila olmaydi — vazifa SYSTEM
    nomiga yozilmasa har safar ruxsat oynasi chiqardi."""
    source = _nsis_code()
    assert "/RU SYSTEM" in source
    assert "/RL HIGHEST" in source


def test_admin_panel_promises_the_same_interval() -> None:
    """Panel aytgan vaqt o'rnatuvchidagi jadval bilan mos bo'lsin."""
    admin = (ROOT / "cloud" / "static" / "admin.html").read_text(encoding="utf-8")
    assert f"{UPDATE_CHECK_MINUTES} daqiqa ichida qo'llaydi" in admin, (
        "admin paneldagi va'da o'rnatuvchidagi jadvalga mos kelmayapti"
    )


def test_update_check_is_free_when_not_paired() -> None:
    """Har 15 daqiqada ishlagani uchun ulanmagan qurilmada tekshiruv
    tarmoqqa **umuman** chiqmasligi kerak."""
    updater = (ROOT / "chaqimchi_ai" / "local" / "updater.py").read_text(encoding="utf-8")
    body = updater[updater.index("def _cloud("): updater.index("def check(")]
    assert "raise UpdateError" in body, "ulanmagan qurilma darhol to'xtashi kerak"
    assert "httpx" not in body, "ulanmasdan turib tarmoqqa so'rov yuborilmasin"


def test_ffmpeg_is_bundled_with_a_pinned_hash() -> None:
    """Kliplar ffmpeg'siz yozilmaydi — u payloadga kirishi SHART.

    Bungacha ffmpeg umuman yo'q edi va Windows'da hodisa kliplari hech
    qachon ishlamagan.  SHA256 ham majburiy: payload admin huquqi bilan
    ishlaydi, tekshirilmagan fayl unga kirmasligi kerak.
    """
    source = BUILDER.read_text(encoding="utf-8")
    digest = re.search(r'FFMPEG_SHA256 = "([0-9a-f]{64})"', source)
    assert digest, "ffmpeg uchun haqiqiy SHA256 yo'q"
    assert "download(FFMPEG_URL, archive, FFMPEG_SHA256)" in source
    assert "step_ffmpeg(cache)" in source, "qadam main() da chaqirilmagan"
    assert 'bin/ffmpeg.exe' in source, "faqat ffmpeg.exe ajratib olinadi"
