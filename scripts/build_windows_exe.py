#!/usr/bin/env python3
"""Chaqimchi AI — To'liq Windows Standalone .exe va Setup Installer yaratish skripti.

Ishga tushirish:
    python scripts/build_windows_exe.py

Natija:
    releases/Chaqimchi_AI_Setup.exe
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = BASE_DIR / "dist"
RELEASES_DIR = BASE_DIR / "releases"
SPEC_FILE = BASE_DIR / "scripts" / "chaqimchi_windows.spec"
ISS_FILE = BASE_DIR / "scripts" / "windows_installer.iss"


def run_cmd(cmd: list[str], step_name: str) -> bool:
    print(f"\n[+] {step_name}: {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=str(BASE_DIR))
    if res.returncode != 0:
        print(f"[XATO] {step_name} muvaffaqiyatsiz tugadi (kod: {res.returncode})")
        return False
    return True


def main():
    print("=" * 60)
    print("  Chaqimchi AI - Standalone Windows .exe Builder")
    print("=" * 60)

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    RELEASES_DIR.mkdir(parents=True, exist_ok=True)

    # 1. PyInstaller tekshiruvi
    pyinstaller = shutil.which("pyinstaller") or shutil.which("pyinstaller.exe")
    if not pyinstaller:
        print("[*] PyInstaller o'rnatilmoqda...")
        if not run_cmd(
            [sys.executable, "-m", "pip", "install", "pyinstaller"], "PyInstaller o'rnatish"
        ):
            return 1
        pyinstaller = "pyinstaller"

    # 2. Standalone App Bundle qurish
    if not run_cmd(
        [pyinstaller, "--clean", "-y", str(SPEC_FILE)], "PyInstaller Standalone Bundle qurish"
    ):
        return 1

    print("\n[OK] PyInstaller bundle tayyor -> dist/ChaqimchiAI papkasida")

    # 3. Inno Setup orqali Chaqimchi_AI_Setup.exe yaratish
    iscc_path = shutil.which("iscc") or shutil.which("ISCC")
    if not iscc_path and sys.platform == "win32":
        possible = [
            Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
            Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
        ]
        for p in possible:
            if p.is_file():
                iscc_path = str(p)
                break

    if iscc_path:
        if not run_cmd([iscc_path, str(ISS_FILE)], "Inno Setup .exe Installer qurish"):
            return 1
        print("\n" + "=" * 60)
        print("  🎉 MUVAFFAQITYATLI! Chaqimchi_AI_Setup.exe tayyorlandi:")
        print(f"  Joylashuv: {RELEASES_DIR / 'Chaqimchi_AI_Setup.exe'}")
        print("=" * 60)
    else:
        print("\n[ESLATMA] 'ISCC' (Inno Setup 6) o'rnatilgan Windows mashinasida:")
        print(f"  ISCC.exe {ISS_FILE}")
        print("buyrug'ini berish orqali yakuniy 'Chaqimchi_AI_Setup.exe' hosil qilinadi.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
