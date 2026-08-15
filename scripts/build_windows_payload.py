#!/usr/bin/env python3
"""Windows o'rnatuvchisi ichiga kiradigan payloadni yig'adi.

Natija: `build/payload/` — NSIS shu papkani `Program Files\\Chaqimchi AI` ga
ko'chiradi.  Ichida hamma narsa bor, mijoz kompyuterida **internet kerak
emas va `pip` ishlamaydi**:

    payload/
      python/                 Python 3.12 embed + oldindan o'rnatilgan paketlar
      chaqimchi_ai/           dastur kodi
      config/                 namuna konfiguratsiya
      models/retail/          OpenVINO odam detektori
      Chaqimchi_AI.bat        ishga tushirish

Nima uchun qayta yozildi (eski `build_windows_bundle.py` o'rniga):

* eski skript wheel'larni `--no-deps` bilan yuklab olardi, keyin mijoz
  kompyuterida `pip install -r requirements.txt` chaqirardi — u yerda esa
  `insightface`, `onnxruntime`, `psycopg` va o'nlab tranzitiv paketlar yo'q
  edi, ya'ni birinchi ishga tushirish **doim** xato bilan tugardi;
* `PYTHON_EMBED_SHA256` soxta qiymat edi va tekshiruvga umuman uzatilmasdi;
* payloadga butun `cloud/` (admin panel, to'lov callbacklari) kirardi.

Ishga tushirish (Linux/macOS/Windows — hammasida ishlaydi):

    python scripts/build_windows_payload.py
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import List

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("payload")

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
PAYLOAD = BUILD / "payload"

# ── Python 3.12 embed (Windows AMD64) ────────────────────────────────────
#
# SHA256 haqiqiy va tekshiriladi.  Bu shunchaki formalik emas: payload
# mijozning kompyuterida administrator huquqi bilan ishlaydi, ya'ni bu
# yerga tushgan har qanday fayl to'liq ishonchli bo'lishi kerak.
PYTHON_VERSION = "3.12.9"
PYTHON_EMBED_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
PYTHON_EMBED_SHA256 = "615861fb801e8b04c847598db4e1e46e4b046295017caa37cb5486dde72b5865"

# ── Wheel'lar Windows/CPython 3.12 uchun yuklanadi ───────────────────────
PIP_PLATFORM = ["--platform", "win_amd64", "--python-version", "3.12", "--implementation", "cp", "--abi", "cp312"]

REQUIREMENTS = ROOT / "requirements-windows-local.txt"

# ── OpenVINO odam detektori (Apache 2.0) ─────────────────────────────────
MODEL_BASE = (
    "https://storage.openvinotoolkit.org/repositories/open_model_zoo/2023.0/"
    "models_bin/1/person-detection-retail-0013/FP16/"
)
MODELS = [
    ("person-detection-retail-0013.xml", "19556695d2b18255fe5593d388ae69ba7f9a2f5c3f986bde8356741d0db26e89"),
    ("person-detection-retail-0013.bin", "cf4a1f2f252d229966001e15454c5ba02a7ace047b181b235e3a2c4aebcf3ba7"),
]

#: Payloadga **faqat** shular kiradi.  `cloud/` va `webapp/` ataylab yo'q:
#: mijoz kompyuterida admin paneli, lead API va to'lov callbacklari
#: ishlashi kerak emas.
CODE_DIRS = ["chaqimchi_ai"]

#: Kodni ko'chirishda tashlab ketiladigan narsalar.
CODE_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".DS_Store", "*.log")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, dest: Path, expected_sha256: str) -> None:
    """Faylni yuklab oladi va SHA256 ni **majburiy** tekshiradi."""
    if dest.is_file() and sha256_file(dest) == expected_sha256:
        log.info("  ✓ keshdan: %s", dest.name)
        return
    log.info("  ↓ %s", url)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=180) as response, tmp.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    actual = sha256_file(tmp)
    if actual != expected_sha256:
        tmp.unlink(missing_ok=True)
        raise SystemExit(
            f"SHA256 mos kelmadi: {dest.name}\n  kutilgan: {expected_sha256}\n  topilgan: {actual}"
        )
    tmp.replace(dest)
    log.info("  ✓ SHA256 tasdiqlandi: %s", dest.name)


def step_python(cache: Path) -> Path:
    log.info("[1/5] Python %s embed", PYTHON_VERSION)
    archive = cache / f"python-{PYTHON_VERSION}-embed-amd64.zip"
    download(PYTHON_EMBED_URL, archive, PYTHON_EMBED_SHA256)

    python_dir = PAYLOAD / "python"
    python_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(python_dir)

    # Embed Python standart holatda `site` modulini yoqmaydi va
    # `site-packages` ni ko'rmaydi — ya'ni o'rnatilgan paketlar topilmasdi.
    # Bir vaqtning o'zida dastur kodi turgan papka ham `sys.path` ga
    # qo'shilishi kerak, aks holda `import chaqimchi_ai` ishlamaydi.
    pth = python_dir / "python312._pth"
    if pth.is_file():
        lines = pth.read_text(encoding="utf-8").splitlines()
        lines = [line.replace("#import site", "import site") for line in lines]
        for extra in ("Lib\\site-packages", ".."):
            if extra not in lines:
                lines.insert(len(lines) - 1 if lines else 0, extra)
        pth.write_text("\n".join(lines) + "\n", encoding="utf-8")
        log.info("  ✓ python312._pth: site-packages va dastur papkasi qo'shildi")
    return python_dir


def step_packages(python_dir: Path, cache: Path) -> None:
    log.info("[2/5] Windows paketlari")
    wheels = cache / "wheels"
    wheels.mkdir(parents=True, exist_ok=True)

    # `--no-deps` YO'Q: tranzitiv paketlar ham kerak.  Eski skriptdagi
    # asosiy xato aynan shu edi — starlette, anyio, h11 tushmasdi.
    download_cmd = [
        sys.executable, "-m", "pip", "download",
        *PIP_PLATFORM, "--only-binary", ":all:",
        "-d", str(wheels), "-r", str(REQUIREMENTS),
    ]
    subprocess.run(download_cmd, check=True)

    site_packages = python_dir / "Lib" / "site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)
    files: List[Path] = sorted(wheels.glob("*.whl"))
    if not files:
        raise SystemExit("Wheel topilmadi — yuklab olish bajarilmadi")

    # Paketlarni payloadning o'ziga **oldindan** o'rnatamiz.  Mijoz
    # kompyuterida `pip` umuman chaqirilmaydi: u yerda internet ham,
    # kompilyator ham bo'lmasligi mumkin.
    #
    # `--platform` va boshqalar bu yerda ham kerak: usiz pip wheel'ni
    # **quruvchi** mashina (macOS/Linux) bo'yicha tekshiradi va
    # "not a supported wheel on this platform" deb rad etadi.  pip buni
    # faqat `--target` va `--no-deps` bilan birga ruxsat beradi.
    install_cmd = [
        sys.executable, "-m", "pip", "install",
        *PIP_PLATFORM, "--only-binary", ":all:",
        "--no-deps", "--no-compile", "--target", str(site_packages),
        *[str(item) for item in files],
    ]
    subprocess.run(install_cmd, check=True)
    log.info("  ✓ %d paket o'rnatildi → %s", len(files), site_packages)


def step_models(cache: Path) -> None:
    log.info("[3/5] AI modeli")
    models_dir = PAYLOAD / "models" / "retail"
    models_dir.mkdir(parents=True, exist_ok=True)
    for name, digest in MODELS:
        cached = cache / name
        download(MODEL_BASE + name, cached, digest)
        shutil.copy2(cached, models_dir / name)
    manifest = ROOT / "models" / "retail_manifest.json"
    if manifest.is_file():
        shutil.copy2(manifest, PAYLOAD / "models" / "retail_manifest.json")


def step_code() -> None:
    log.info("[4/5] Dastur kodi")
    for name in CODE_DIRS:
        source = ROOT / name
        if not source.is_dir():
            raise SystemExit(f"Papka topilmadi: {source}")
        shutil.copytree(source, PAYLOAD / name, ignore=CODE_IGNORE, dirs_exist_ok=True)

    # Namuna konfiguratsiya: lokal `config.yaml` ni dastur o'zi
    # `%PROGRAMDATA%` da yaratadi, lekin qoidalar fayli koddan o'qiladi.
    config_dst = PAYLOAD / "config"
    config_dst.mkdir(parents=True, exist_ok=True)
    for name in ("rules.yaml",):
        source = ROOT / "config" / name
        if source.is_file():
            shutil.copy2(source, config_dst / name)

    for name in ("LICENSE", "README.md"):
        source = ROOT / name
        if source.is_file():
            shutil.copy2(source, PAYLOAD / name)


LAUNCHER = """@echo off
chcp 65001 > nul
title Chaqimchi AI

cd /d "%~dp0"

if not exist "python\\python.exe" (
    echo [XATO] Dastur fayllari topilmadi.
    echo Chaqimchi AI ni qaytadan o'rnating.
    pause
    exit /b 1
)

echo.
echo   Chaqimchi AI ishga tushmoqda...
echo   Boshqaruv paneli brauzerda ochiladi: http://localhost:8760
echo.
echo   Bu oynani YOPMANG - yopilsa nazorat to'xtaydi.
echo.

"python\\python.exe" -m chaqimchi_ai.local.app

REM Bu yerga yetdik degani dastur to'xtadi.  Oyna ochiq qoladi: xato
REM matni ekranda ko'rinishi kerak.  Eski o'rnatuvchi buni yashirin
REM rejimda ishga tushirardi va mijoz nima bo'lganini umuman bilmasdi.
echo.
echo   Dastur to'xtadi. Yuqoridagi xabarni o'qing.
pause
"""

READ_ME = """Chaqimchi AI - do'kon nazorati
==============================

Ishga tushirish
---------------
Ish stolidagi "Chaqimchi AI" yorlig'ini bosing.
Brauzerda sozlash oynasi ochiladi: http://localhost:8760

Birinchi marta nima qilish kerak
--------------------------------
1. Kamerangiz yoki NVR manzilini kiriting (dastur o'zi ham qidiradi).
2. Tasvir kelganiga ishonch hosil qiling.
3. Kirish eshigi ustidan chiziq torting - shundan keyin odam sanaladi.
4. "Saqlash va ishga tushirish" tugmasini bosing.

Sozlamalar va jurnal qayerda
----------------------------
C:\\ProgramData\\Chaqimchi\\

Yordam
------
Telegram: @fibotai
"""


def step_launcher() -> None:
    log.info("[5/5] Ishga tushirish fayllari")
    (PAYLOAD / "Chaqimchi_AI.bat").write_text(LAUNCHER, encoding="utf-8")
    # Windows Notepad CRLF kutadi; LF bilan yozilsa matn bitta qatorga
    # yopishib qoladi va mijoz o'qiy olmaydi.
    (PAYLOAD / "O'QING.txt").write_text(READ_ME.replace("\n", "\r\n"), encoding="utf-8")
    icon = ROOT / "scripts" / "app.ico"
    if icon.is_file():
        shutil.copy2(icon, PAYLOAD / "app.ico")


def directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache",
        default=str(BUILD / "cache"),
        help="yuklab olingan fayllar keshi (qayta qurishda tezlashtiradi)",
    )
    parser.add_argument("--keep", action="store_true", help="eski payloadni o'chirmaslik")
    args = parser.parse_args()

    if not REQUIREMENTS.is_file():
        raise SystemExit(f"Topilmadi: {REQUIREMENTS}")

    if PAYLOAD.exists() and not args.keep:
        shutil.rmtree(PAYLOAD)
    PAYLOAD.mkdir(parents=True, exist_ok=True)

    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)

    python_dir = step_python(cache)
    step_packages(python_dir, cache)
    step_models(cache)
    step_code()
    step_launcher()

    # Xavfsizlik tekshiruvi: cloud kodi payloadga tushib qolmasin.
    for forbidden in ("cloud", "webapp"):
        if (PAYLOAD / forbidden).exists():
            raise SystemExit(f"Payload ichida bo'lmasligi kerak: {forbidden}/")

    size_mb = directory_size(PAYLOAD) / 1024 / 1024
    log.info("")
    log.info("✅ Payload tayyor: %s (%.0f MB)", PAYLOAD, size_mb)
    log.info("   Keyingi qadam: makensis scripts/windows_installer.nsi")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
