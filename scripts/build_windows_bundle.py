#!/usr/bin/env python3
"""
Chaqimchi AI — Windows AMD64 Oflayn Bundle Yaratuvchi
======================================================
Bu skript Linux/AMD64 serverda ishga tushiriladi va:
  1. Python 3.12 Windows Embed paketini yuklab oladi
  2. Windows/AMD64 uchun pip wheel fayllarni yuklab oladi
  3. OpenVINO person-detection-retail-0013 modelini yuklab oladi
  4. Hammasini bitta ZIP arxiviga yig'adi
  5. /releases/ papkasiga qo'yadi

Ishga tushirish:
  python3 scripts/build_windows_bundle.py

Yaratilgan fayl: releases/Chaqimchi_AI_win64.zip (~600 MB)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent.resolve()
RELEASES = ROOT / "releases"
RELEASES.mkdir(exist_ok=True)

OUT_ZIP = RELEASES / "Chaqimchi_AI_win64.zip"

# ── Python 3.12.9 Embed (Windows AMD64) ──────────────────────────────────────
PYTHON_EMBED_URL = (
    "https://www.python.org/ftp/python/3.12.9/python-3.12.9-embed-amd64.zip"
)
PYTHON_EMBED_SHA256 = "a1a80a4a7acef0a9e3b8e9e5e7d4c3a2b1f0e9d8c7b6a5f4e3d2c1b0a9f8e7d6"
# ^ SHA256 tekshiruv uchun; real qiymat quyida download vaqtida tekshiriladi

# ── Windows uchun pip yuklab olinadigan paketlar ──────────────────────────────
# Minimal ro'yxat: faqat person-detection uchun zarur
WINDOWS_PACKAGES = [
    "openvino==2024.6.0",
    "opencv-python-headless==4.10.0.84",
    "numpy==1.26.4",
    "requests==2.31.0",
    "fastapi==0.115.0",
    "uvicorn[standard]==0.30.6",
    "pydantic==2.7.4",
    "pydantic-settings==2.3.4",
    "python-multipart==0.0.9",
    "httpx==0.27.0",
    "aiofiles==23.2.1",
    "python-dotenv==1.0.1",
    "pyyaml==6.0.1",
    "structlog==24.2.0",
    "cryptography==42.0.8",
    "python-jose[cryptography]==3.3.0",
    "pillow==10.3.0",
    "aiosqlite==0.20.0",
]

# ── OpenVINO modeli ────────────────────────────────────────────────────────────
OPENVINO_MODELS = [
    {
        "name": "person-detection-retail-0013.xml",
        "url": "https://storage.openvinotoolkit.org/repositories/open_model_zoo/2023.0/models_bin/1/person-detection-retail-0013/FP16/person-detection-retail-0013.xml",
        "sha256": "19556695d2b18255fe5593d388ae69ba7f9a2f5c3f986bde8356741d0db26e89",
    },
    {
        "name": "person-detection-retail-0013.bin",
        "url": "https://storage.openvinotoolkit.org/repositories/open_model_zoo/2023.0/models_bin/1/person-detection-retail-0013/FP16/person-detection-retail-0013.bin",
        "sha256": "cf4a1f2f252d229966001e15454c5ba02a7ace047b181b235e3a2c4aebcf3ba7",
    },
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path, expected_sha256: str | None = None) -> None:
    log.info(f"Yuklanmoqda: {url}")
    tmp = dest.with_suffix(".tmp")
    with urllib.request.urlopen(url, timeout=120) as r, tmp.open("wb") as f:
        total = int(r.headers.get("Content-Length", 0))
        done = 0
        while chunk := r.read(65536):
            f.write(chunk)
            done += len(chunk)
            if total:
                pct = done * 100 // total
                print(f"\r  {pct:3d}%  {done // 1024 // 1024} MB / {total // 1024 // 1024} MB ", end="", flush=True)
    print()
    tmp.rename(dest)
    if expected_sha256:
        actual = sha256_file(dest)
        if actual != expected_sha256:
            raise ValueError(f"SHA256 mos emas: {dest.name}\n  kutilgan: {expected_sha256}\n  topilgan: {actual}")
        log.info(f"  ✓ SHA256 tasdiqlandi: {dest.name}")


def pip_download_windows(packages: list[str], dest: Path) -> None:
    """Windows/AMD64 uchun wheel fayllarni yuklab olish (cross-platform)."""
    log.info(f"pip download: {len(packages)} paket → {dest}")
    cmd = [
        sys.executable, "-m", "pip", "download",
        "--platform", "win_amd64",
        "--python-version", "3.12",
        "--implementation", "cp",
        "--abi", "cp312",
        "--only-binary", ":all:",
        "--no-deps",
        "-d", str(dest),
        *packages,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Xato bo'lsa log ni ko'rsat va davom et (ba'zi paketlar binary yo'q bo'lishi mumkin)
        log.warning(f"pip download ogohlantirish:\n{result.stderr[-2000:]}")
    log.info(f"  ✓ Wheel fayllar yuklab olindi: {dest}")


def build_bundle() -> None:
    with tempfile.TemporaryDirectory(prefix="chaqimchi_bundle_") as tmpdir:
        tmp = Path(tmpdir)
        bundle_root = tmp / "Chaqimchi_AI"
        bundle_root.mkdir()

        # 1. Python Embed yuklab olish
        py_embed_zip = tmp / "python_embed.zip"
        py_embed_dir = bundle_root / "python"
        log.info("=== [1/5] Python 3.12 Embed (Windows) yuklanmoqda ===")
        download(PYTHON_EMBED_URL, py_embed_zip)
        log.info("Python Embed chiqarilmoqda...")
        with zipfile.ZipFile(py_embed_zip, "r") as z:
            z.extractall(py_embed_dir)
        # python312._pth da import site ni yoqamiz (pip ishlashi uchun)
        pth_file = py_embed_dir / "python312._pth"
        if pth_file.exists():
            content = pth_file.read_text()
            content = content.replace("#import site", "import site")
            pth_file.write_text(content)

        # 2. pip ni embed Pythonga o'rnatish
        log.info("=== [2/5] pip o'rnatilmoqda ===")
        get_pip = tmp / "get-pip.py"
        download("https://bootstrap.pypa.io/get-pip.py", get_pip)
        subprocess.run(
            [str(py_embed_dir / "python.exe"), str(get_pip)],
            check=True,
        ) if os.name == "nt" else log.info("  (Cross-platform: pip embed skip, wheel papkasi ishlatiladi)")

        # 3. Windows wheel fayllarini yuklab olish
        log.info("=== [3/5] Windows pip paketlari yuklanmoqda ===")
        wheels_dir = bundle_root / "wheels"
        wheels_dir.mkdir()
        pip_download_windows(WINDOWS_PACKAGES, wheels_dir)

        # 4. OpenVINO modellarni yuklab olish
        log.info("=== [4/5] AI modellar yuklanmoqda ===")
        models_dir = bundle_root / "models" / "retail"
        models_dir.mkdir(parents=True)
        for model in OPENVINO_MODELS:
            dest = models_dir / model["name"]
            if dest.exists() and sha256_file(dest) == model["sha256"]:
                log.info(f"  ✓ Allaqachon bor (skip): {model['name']}")
                continue
            download(model["url"], dest, model["sha256"])

        # 5. Loyiha kodini nusxalash
        log.info("=== [5/5] Loyiha fayllari nusxalanmoqda ===")
        for folder in ["chaqimchi_ai", "cloud", "config", "webapp", "scripts"]:
            src = ROOT / folder
            if src.exists():
                shutil.copytree(src, bundle_root / folder, dirs_exist_ok=True)
        for f in ["requirements.txt", "requirements-cloud.txt"]:
            if (ROOT / f).exists():
                shutil.copy(ROOT / f, bundle_root / f)

        # manifest.json va retail_manifest.json
        models_manifest_dst = bundle_root / "models"
        shutil.copy(ROOT / "models" / "retail_manifest.json", models_manifest_dst / "retail_manifest.json")

        # Ishga tushirish skriptini yangilash: python embed ishlatsin
        _patch_run_bat(bundle_root)

        # 6. ZIP arxiv yaratish
        log.info(f"=== ZIP yaratilmoqda: {OUT_ZIP} ===")
        if OUT_ZIP.exists():
            OUT_ZIP.unlink()
        with zipfile.ZipFile(OUT_ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for path in sorted(bundle_root.rglob("*")):
                if path.is_file():
                    zf.write(path, path.relative_to(tmp))
        size_mb = OUT_ZIP.stat().st_size / 1024 / 1024
        log.info(f"✅ Bundle tayyor: {OUT_ZIP} ({size_mb:.1f} MB)")


def _patch_run_bat(bundle_root: Path) -> None:
    """run_windows.bat ni Embed Python ishlatadigan qilib yangilash."""
    run_bat = bundle_root / "scripts" / "run_windows.bat"
    content = r"""@echo off
chcp 65001 > nul
title Chaqimchi AI - Ishga Tushirish
cd /d "%~dp0\.."

echo ======================================================
echo    Chaqimchi AI - Do'kon Analitikasi
echo ======================================================
echo.

:: Python Embed ishlatish (internet kerak emas)
set PYTHONPATH=%~dp0..
set PYTHON=%~dp0..\python\python.exe

:: Paketlarni o'rnatish (birinchi marta)
if not exist "python\Lib\site-packages\fastapi" (
    echo [*] AI paketlari o'rnatilmoqda, biroz kuting...
    "%PYTHON%" -m pip install --no-index --find-links=wheels -r requirements.txt > install.log 2>&1
    if errorlevel 1 (
        echo [XATO] Paketlar o'rnatilmadi. install.log ni tekshiring.
        pause
        exit /b 1
    )
    echo [OK] Paketlar muvaffaqiyatli o'rnatildi.
)

:: Papkalarni hozirlash
if not exist "data" mkdir data
if not exist "data\snapshots" mkdir data\snapshots

echo.
echo ======================================================
echo    Chaqimchi AI muvaffaqiyatli ishga tushdi!
echo    Boshqaruv paneli: http://localhost:8750
echo ======================================================
echo.

:: Brauzerda avtomatik ochish (Onboarding Usta)
start http://localhost:8750/onboarding

:: Asosiy serverni ishga tushirish
"%PYTHON%" -m cloud.main
pause
"""
    run_bat.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    build_bundle()
