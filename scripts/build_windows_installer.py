#!/usr/bin/env python3
"""Windows Setup (.exe) o'rnatuvchisini kompilyatsiya qilish yordamchisi."""

import shutil
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = BASE_DIR / "dist"
ISS_SCRIPT = BASE_DIR / "scripts" / "windows_installer.iss"


def build_installer():
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 60)
    print("  Chaqimchi AI - Windows O'rnatuvchisini Qurish")
    print("=" * 60)

    # Inno Setup kompyuterda bormi?
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
        print(f"[1/2] Inno Setup topildi: {iscc_path}")
        cmd = [iscc_path, str(ISS_SCRIPT)]
        print(f"[2/2] Kompilyatsiya boshlanmoqda: {' '.join(cmd)}")
        result = subprocess.run(cmd, cwd=str(BASE_DIR))
        if result.returncode == 0:
            print("\n[OK] Chaqimchi_AI_Setup.exe muvaffaqiyatli tayyorlandi -> dist/ papkasida!")
            return 0
        else:
            print("\n[XATO] Inno Setup kompilyatsiyasida xatolik yuz berdi.")
            return 1
    else:
        print("\n[OGOHLANTIRISH] Kompyuterda 'ISCC' (Inno Setup 6) o'rnatilmagan.")
        print("Biroq 'scripts/windows_installer.iss' fayli to'liq tayyorlangan.")
        print("Inno Setup 6 o'rnatilgach, ushbu skript orqali to'g'ridan-to'g'ri .exe quriladi.")
        return 0


if __name__ == "__main__":
    sys.exit(build_installer())
