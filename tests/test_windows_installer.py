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
    download_block = source[
        source.index("download_cmd = [") : source.index("subprocess.run(download_cmd")
    ]
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


def test_builder_bundles_the_ai_models_from_the_manifest() -> None:
    """Model ro'yxati manifestdan o'qiladi — bitta manba.

    Ilgari URL/sha256 builderda takrorlanardi va yangi model qo'shilganda
    ikki joydan biri unutilishi aniq edi.
    """
    import json

    source = BUILDER.read_text(encoding="utf-8")
    assert "retail_manifest.json" in source, "builder manifestdan o'qisin"
    manifest = json.loads(
        (BUILDER.parent.parent / "models" / "retail_manifest.json").read_text(encoding="utf-8")
    )
    files = manifest["files"]
    for name in (
        "person-detection-retail-0013.xml",
        "person-detection-retail-0013.bin",
        "face-detection-retail-0004.xml",
        "age-gender-recognition-retail-0013.xml",
    ):
        assert name in files, f"{name} manifestda bo'lsin"
    for meta in files.values():
        assert re.fullmatch(r"[0-9a-f]{64}", meta["sha256"]), "sha256 majburiy"
        assert str(meta["url"]).startswith("https://"), "faqat HTTPS"


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

    # localport ATAYLAB yo'q: WS-Discovery javobi dastur so'rov yuborgan
    # tasodifiy (ephemeral) portga keladi — 3702 ga qotirilgan qoida
    # haqiqiy javobni o'tkazmasdi va tugma baribir bo'sh qaytarardi.
    # Torlik endi remoteip + profile + program uchligidan keladi.
    assert "localport=" not in source, "javob porti oldindan noma'lum — portga qotirilmasin"
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
    uninstall = source[source.index('Section "Uninstall"') :]
    for leftover in ("$DESKTOP\\${APP_NAME}.lnk", "ChaqimchiAI", "$INSTDIR\\python"):
        assert leftover in uninstall, f"o'chirishda qolib ketadi: {leftover}"
    assert 'DeleteRegValue HKLM "${REG_RUN}"' in uninstall, "avtostart yozuvi qolib ketadi"


def test_uninstaller_asks_before_deleting_shop_data() -> None:
    """Kamera sozlamalari va do'kon statistikasi qaytarilmaydi.  Yangilash
    esa jim rejimda o'tadi va ma'lumotga tegmasligi kerak."""
    source = _nsis()
    uninstall = source[source.index('Section "Uninstall"') :]
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
    assert not re.search(r'!define\s+APP_VERSION\s+"', source), (
        "versiya qo'lda yozilmasin — u siljib ketadi"
    )
    assert "build\\version.nsh" in source, "versiya qurish paytida yozilishi kerak"


def test_build_writes_the_version_from_the_single_source() -> None:
    """Qurish skripti versiyani `chaqimchi_ai/__init__.py` dan olishi kerak."""
    builder = (
        Path(__file__).resolve().parents[1] / "scripts" / "build_windows_payload.py"
    ).read_text(encoding="utf-8")
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
    body = updater[updater.index("def _cloud(") : updater.index("def check(")]
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
    assert "bin/ffmpeg.exe" in source, "faqat ffmpeg.exe ajratib olinadi"


# ── Cloud manzili paket ichida ──────────────────────────────────────────
#
# Haqiqiy nosozlik: CI `CHAQIMCHI_DEFAULT_CLOUD_URL` siz ishlagan va
# GitHub Releases'ga cloud manzili BO'SH `.exe` chiqib ketgan.  Bunday
# paket auto-pair qila olmaydi — sehrgar do'kon egasidan server manzilini
# so'raydi, u esa uni bilmaydi.  Qurish skripti faqat `log.warning`
# yozardi, CI logini esa hech kim o'qimaydi.

WORKFLOW = ROOT / ".github" / "workflows" / "windows-installer.yml"


def test_ci_gives_the_build_a_cloud_address() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "CHAQIMCHI_DEFAULT_CLOUD_URL:" in workflow, (
        "CI qurishga cloud manzilini bermasa, reliz cloudsiz chiqadi"
    )
    assert "https://api.chaqimchi.uz" in workflow, "zaxira qiymat bo'lsin"


def test_ci_checks_the_address_landed_in_the_package() -> None:
    """Env berilgani yetarli emas — u haqiqatan `.bat` ichiga tushishi kerak."""
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "build/payload/Chaqimchi_AI.bat" in workflow
    assert "^set CHAQIMCHI_DEFAULT_CLOUD_URL=https://" in workflow


def test_build_stops_without_a_cloud_address() -> None:
    """Manzilsiz qurish **to'xtashi** kerak, ogohlantirib o'tib ketmasin."""
    import os
    import subprocess
    import sys

    env = {k: v for k, v in os.environ.items() if k != "CHAQIMCHI_DEFAULT_CLOUD_URL"}
    result = subprocess.run(
        [sys.executable, str(BUILDER)],
        capture_output=True,
        text=True,
        env=env,
        cwd=ROOT,
        timeout=120,
    )
    assert result.returncode != 0, "manzilsiz qurish muvaffaqiyatli tugamasligi kerak"
    assert "CHAQIMCHI_DEFAULT_CLOUD_URL" in result.stderr + result.stdout


def test_build_rejects_a_plain_http_address() -> None:
    """`http://` bilan pairing tokeni ochiq kanaldan o'tardi."""
    import os
    import subprocess
    import sys

    env = dict(os.environ, CHAQIMCHI_DEFAULT_CLOUD_URL="http://api.chaqimchi.uz")
    result = subprocess.run(
        [sys.executable, str(BUILDER)],
        capture_output=True,
        text=True,
        env=env,
        cwd=ROOT,
        timeout=120,
    )
    assert result.returncode != 0
    assert "https://" in result.stderr + result.stdout


def test_local_only_build_is_still_possible() -> None:
    """Dasturchi cloudsiz qura olsin — lekin buni ataylab aytishi kerak."""
    source = BUILDER.read_text(encoding="utf-8")
    assert "--lokal-qurish" in source
    assert "allow_no_cloud" in source


# ── Kompyuter yonganda o'zi ishga tushsin ───────────────────────────────
#
# Haqiqiy nosozlik: avtostart `HKLM\...\Run` kaliti edi.  U kompyuter
# YONGANDA emas, kimdir tizimga KIRGANDA ishlaydi — do'kon kompyuteri
# yonib qulf ekranida tursa nazorat umuman boshlanmasdi.  Dastur esa
# kassirning ekranida qora oyna bo'lib turardi va yopilardi.


def _autostart_block() -> str:
    source = _nsis_code()
    start = source.index("Section \"Kompyuter yonganda")
    return source[start : source.index("SectionEnd", start)]


def test_autostart_runs_at_boot_not_at_logon() -> None:
    block = _autostart_block()
    assert "/SC ONSTART" in block, "vazifa kompyuter yonganda ishlasin"
    assert "/RU SYSTEM" in block, "tizimga kirish shart bo'lmasin"


def test_autostart_task_has_no_time_limit() -> None:
    """`schtasks` standart bo'yicha vazifani 72 soatdan keyin to'xtatadi.

    24/7 nazorat uchun bu jimgina o'chish degani — va aynan 72 soatlik
    barqarorlik sinovining oxirida.
    """
    block = _autostart_block()
    assert "ExecutionTimeLimit" in block and "PT0S" in block
    assert "RestartCount" in block, "yiqilsa qayta ko'tarilsin"


def test_the_run_key_is_only_a_fallback() -> None:
    block = _autostart_block()
    task = block.index("/SC ONSTART")
    run_key = block.index("${REG_RUN}")
    assert run_key > task, "Run kaliti faqat vazifa yaratilmagandagi zaxira bo'lsin"


def test_uninstall_removes_the_autostart_task() -> None:
    source = _nsis_code()
    uninstall = source[source.index('Section "Uninstall"') :]
    assert 'schtasks /Delete /F /TN "Chaqimchi AI"' in uninstall


def test_the_service_launcher_never_opens_a_browser_or_pauses() -> None:
    """Avtostart launcheri SYSTEM nomidan ishlaydi.

    `pause` bo'lsa yiqilgan dastur "hali ishlayapti" bo'lib ko'rinardi va
    vazifa uni qayta ko'tarmasdi; brauzer esa SYSTEM sessiyasida ochilib
    osilib qolardi.
    """
    source = BUILDER.read_text(encoding="utf-8")
    start = source.index("SERVICE_LAUNCHER = ")
    launcher = source[start : source.index('"""', source.index('"""', start) + 3)]
    assert "CHAQIMCHI_LOCAL_NO_BROWSER=1" in launcher
    assert "pause" not in launcher
    assert "CHAQIMCHI_DEFAULT_CLOUD_URL=__CLOUD_URL__" in launcher, (
        "xizmat launcheri ham cloud manzilini bilishi kerak"
    )
    assert "Chaqimchi_AI_xizmat.bat" in source, "launcher payloadga yozilsin"


def test_the_autostart_task_runs_the_service_launcher() -> None:
    assert "Chaqimchi_AI_xizmat.bat" in _autostart_block()


# ── Masofadan yangilash fayllarni band holda topmasin ───────────────────
#
# Nazorat endi rejalashtirilgan vazifa orqali, SYSTEM nomidan, OYNASIZ
# ishlaydi.  Yangi o'rnatuvchi `.onInit` da eskisini `/S` bilan chaqiradi,
# eski o'chiruvchi esa jarayonni oyna sarlavhasi bo'yicha qidirardi —
# oynasiz jarayonda bunday sarlavha yo'q.  Topilmasa `python.exe` band
# bo'lib qoladi, yangi versiya fayllarni ustiga yoza olmaydi va
# masofadan yangilanish JIMGINA ishlamay qo'yadi.


def _uninstall_block() -> str:
    source = _nsis_code()
    return source[source.index('Section "Uninstall"') :]


def test_the_task_is_stopped_before_the_process() -> None:
    """Teskari tartibda vazifa o'ldirilgan dasturni qayta ko'tarardi."""
    block = _uninstall_block()
    assert block.index('schtasks /End /TN "Chaqimchi AI"') < block.index("Stop-Process"), (
        "avval vazifa to'xtatilsin, keyin jarayon"
    )


def test_processes_are_matched_by_path_not_window_title() -> None:
    block = _uninstall_block()
    assert "Get-Process python" in block and "$INSTDIR" in block, (
        "jarayon o'rnatish papkasi bo'yicha topilsin"
    )
    # Eski usul zaxira sifatida qolishi mumkin, lekin yagona yo'l bo'lmasin.
    assert block.index("Stop-Process") < block.index("WINDOWTITLE"), (
        "yo'l bo'yicha to'xtatish birinchi bo'lsin"
    )


def test_the_updater_task_is_also_stopped() -> None:
    """O'chirilgan dasturni qayta o'rnatishga urinmasin."""
    block = _uninstall_block()
    assert 'schtasks /Delete /F /TN "Chaqimchi AI Update"' in block


# ── Avtostartni dastur o'zi tiklaydi ────────────────────────────────────


def test_autostart_task_name_matches_the_installer() -> None:
    """Nom farq qilsa ikkita vazifa paydo bo'lardi — dastur ikki nusxada.

    O'rnatuvchi vazifani `Chaqimchi AI` deb yaratadi; dastur esa
    yo'qligini tekshirib o'zi yaratadi (0.6.7 gacha o'rnatilgan
    kompyuterlarda avtostart `Run` kaliti bo'lib, tokdan keyin nazorat
    umuman boshlanmasdi).
    """
    from chaqimchi_ai.local import autostart

    assert f'/TN "{autostart.TASK_NAME}"' in NSIS.read_text(encoding="utf-8")


def test_autostart_uses_the_windowless_launcher() -> None:
    """Kassirning ekranida qora oyna turmasin (u yopiladi)."""
    from chaqimchi_ai.local import autostart

    nsis = NSIS.read_text(encoding="utf-8")
    assert autostart.SERVICE_LAUNCHER in nsis
    builder = BUILDER.read_text(encoding="utf-8")
    assert autostart.SERVICE_LAUNCHER in builder


def test_autostart_is_a_no_op_outside_windows() -> None:
    """Linux/mac'da (CI va ishlab chiqish) hech narsa qilinmasin."""
    import os

    from chaqimchi_ai.local import autostart

    if os.name == "nt":  # pragma: no cover - CI Linux/mac
        pytest.skip("bu test Windows bo'lmagan tizim uchun")
    answer = autostart.ensure()
    assert answer == {"ok": True, "created": False, "reason": "Windows emas"}


def test_the_installer_stops_copies_started_from_another_folder() -> None:
    """Boshqa papkadagi eski nusxa ham to'xtatilsin.

    O'chirish bo'limi jarayonlarni faqat `$INSTDIR` yo'li bo'yicha
    filtrlaydi.  Do'konda aynan shu bo'shliq ochildi: 0.6.9 o'rnatilgach
    eski nusxa (boshqa papkadan) tirik qoldi, ikkita AI zanjiri bitta
    kamerani o'qidi va cloudga ikki xil versiyadan heartbeat keldi.
    """
    nsis = NSIS.read_text(encoding="utf-8")

    assert "Win32_Process" in nsis, "buyruq qatori bo'yicha filtr shart"
    assert "chaqimchi_ai.(local.app|retail.service)" in nsis
    # Yangilovchi FILTRGA tushmasin: u o'rnatuvchini ishga tushirgan
    # jarayon, o'zini o'ldirsa rollback belgisi yozilmay qolardi.
    # (Izohda nomi tilga olinadi — shuning uchun aynan filtr tekshiriladi.)
    pattern = "chaqimchi_ai.(local.app|retail.service)"
    assert "updater" not in pattern


def test_the_stale_copy_check_runs_on_upgrade_not_only_on_uninstall() -> None:
    """Tekshiruv `.onInit` da bo'lsin.

    Yangilanishda ESKI o'rnatuvchining o'chirish bo'limi ishlaydi
    (`ExecWait '$R0 /S ...'`), ya'ni o'sha bo'limga qo'shilgan tuzatish
    faqat KEYINGI relizda kuchga kirardi.  `.onInit` esa yangi
    o'rnatuvchining o'zidan bajariladi — shu sababli darhol ishlaydi.
    """
    nsis = NSIS.read_text(encoding="utf-8")
    on_init = nsis.split("Function .onInit")[1].split("FunctionEnd")[0]

    assert "Win32_Process" in on_init


def test_eski_nusxa_avval_ota_jarayondan_o_ldiriladi() -> None:
    """`local.app` `retail.service` dan OLDIN to'xtatilishi shart.

    `local.app` ichidagi kuzatuvchi har 2 soniyada tekshiradi va zanjir
    20 soniyadan ko'p ishlagan bo'lsa uni darhol qayta ko'taradi
    (`chaqimchi_ai/local/supervisor.py`: `time.sleep(2)`,
    `CRASH_WINDOW_SEC = 20`).

    Agar ikkalasi bitta o'tishda o'ldirilsa va `retail.service` birinchi
    tushsa, kuzatuvchi 2 soniyada yangi zanjir ko'taradi.  Natijada yangi
    o'rnatmadan keyin bitta RTSP oqimida IKKITA zanjir qoladi — o'rnatuvchi
    izohining o'zi bu holatni tasvirlaydi: *"ikkita AI zanjiri bitta
    kamerani o'qidi va kamera soni 4 dan 2 ga tushdi"*.

    Ota jarayon birinchi o'lsa, qayta ko'taradigan hech kim qolmaydi.
    """
    text = NSIS.read_text(encoding="utf-8")
    app = text.find("Kill-Match $\\\"chaqimchi_ai.local.app")
    service = text.find("Kill-Match $\\\"chaqimchi_ai.retail.service")
    assert app != -1, "local.app alohida to'xtatilmayapti"
    assert service != -1, "retail.service alohida to'xtatilmayapti"
    assert app < service, (
        "retail.service local.app dan oldin o'ldirilyapti — kuzatuvchi "
        "zanjirni 2 soniyada qayta ko'taradi va ikkita nusxa qoladi"
    )


def test_eski_nusxa_o_lganini_tekshirmasdan_davom_etilmaydi() -> None:
    """Qat'iy `Sleep` yetarli emas — ro'yxat bo'shagani tekshirilsin.

    Bungacha o'ldirishdan keyin `Sleep 1500` turardi.  Sekin kompyuterda
    yoki qayta ko'tarilish holatida bu vaqt yetmasdi va o'rnatuvchi tirik
    jarayon ustiga o'rnatishni boshlardi.
    """
    text = NSIS.read_text(encoding="utf-8")
    assert "-not $$left" in text, (
        "o'ldirishdan keyin jarayonlar ro'yxati bo'shagani tekshirilmayapti"
    )
    assert "for ($$i = 0; $$i -lt 20" in text, "qayta tekshirish sikli yo'q"


# ── Mijoz bulut paneliga boradi, localhost'ga emas ──────────────────────
#
# O'rnatishdan keyingi sozlash bulutga ko'chdi.  O'rnatuvchi matnlari va
# yorliqlari ham shunga qarashi kerak — aks holda mijoz "hisobotim
# qayerda?" degan savol bilan qurilma sahifasiga tushib qolardi.


def test_the_installer_creates_two_shortcuts_for_two_questions() -> None:
    """«Hisobotim qayerda?» va «Dastur ishlayaptimi?» — ikki xil savol.

    Ilgari bitta yorliq bor edi va u localhost'ga ketardi.
    """
    source = _nsis_code()

    assert 'Boshqaruv paneli.lnk" "${APP_PANEL_URL}"' in source
    assert 'Qurilma holati.lnk" "${APP_URL}"' in source
    # O'chirishda ikkalasi ham tozalansin — qolgan yorliq keyingi
    # o'rnatishda ishlamaydigan havolaga aylanardi.
    assert 'Delete "$SMPROGRAMS\\${APP_NAME}\\Qurilma holati.lnk"' in source


def test_the_panel_address_comes_from_the_build_not_from_a_guess() -> None:
    """`version.nsh` uni `CHAQIMCHI_DEFAULT_CLOUD_URL` dan oladi.

    Cloudsiz sinov paketida esa lokal sahifaga tushadi — ishlamaydigan
    yorliq chiqmasin.
    """
    source = _nsis_code()
    builder = BUILDER.read_text(encoding="utf-8")

    assert "!ifndef APP_PANEL_URL" in source
    assert '!define APP_PANEL_URL "${APP_URL}"' in source
    assert "APP_PANEL_URL" in builder
    # Manba BITTA: `api.`→`app.` qoidasi ikki joyda ajralib ketmasin.
    assert "_panel_host" in builder


def test_the_finish_page_no_longer_promises_a_localhost_wizard() -> None:
    source = _nsis_code()
    finish = source[source.index("MUI_FINISHPAGE_TEXT") :].split("\n", 1)[0]

    assert "localhost" not in finish
    assert "panel" in finish.lower()


def test_the_readme_explains_the_cloud_flow_first() -> None:
    """`O'QING.txt` — mijoz o'qiydigan yagona hujjat.

    Unda birinchi bo'lib ro'yxatdan o'tish turishi kerak, lokal sehrgar
    emas: sehrgar endi zaxira yo'l.
    """
    source = BUILDER.read_text(encoding="utf-8")
    start = source.index("READ_ME = ")
    readme = source[start : source.index('"""', source.index('"""', start) + 3)]

    assert "ro'yxatdan o'ting" in readme.lower()
    # Internet uzilganda nazorat davom etishi AYTILISHI kerak — mijoz
    # aks holda kamera ham o'chgan deb o'ylaydi.
    assert "TO'XTAMAYDI" in readme
    # Qurilma sahifasi ham qoladi, lekin ikkinchi o'rinda.
    assert readme.index("ro'yxatdan o'ting") < readme.index("localhost")
