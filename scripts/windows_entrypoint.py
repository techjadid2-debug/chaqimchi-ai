#!/usr/bin/env python3
"""Chaqimchi AI — Windows Standalone App Entrypoint.

Ushbu skript PyInstaller orqali .exe qilinganda ishga tushadi:
1. Lokal ma'lumotlar papkalarini hozirlaydi.
2. Web va AI xizmatini fonda ishga tushiradi.
3. Brauzerda avtomatik ravishda boshqaruv panelini ochadi.
"""

from __future__ import annotations

import os
import sys
import time
import webbrowser
from pathlib import Path

# PyInstaller bundle bo'lsa _MEIPASS ni sys.path ga qo'shish
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    bundle_dir = Path(sys._MEIPASS)
else:
    bundle_dir = Path(__file__).resolve().parent.parent

if str(bundle_dir) not in sys.path:
    sys.path.insert(0, str(bundle_dir))

# Ishchi papkani foydalanuvchi ma'lumotlari papkasiga yo'naltirish
appdata = os.environ.get("LOCALAPPDATA") or str(Path.home())
data_dir = Path(appdata) / "ChaqimchiAI" / "data"
data_dir.mkdir(parents=True, exist_ok=True)
(data_dir / "snapshots").mkdir(parents=True, exist_ok=True)
(data_dir / "clips").mkdir(parents=True, exist_ok=True)
(data_dir / "backup").mkdir(parents=True, exist_ok=True)

os.environ["CHAQIMCHI_DATA_DIR"] = str(data_dir)
os.environ["CHAQIMCHI_CLOUD_DB"] = str(data_dir / "cloud.db")
os.environ["CHAQIMCHI_EVENT_DB"] = str(data_dir / "events.db")

import uvicorn

from cloud.main import app


def open_browser_delayed(url: str, delay_sec: float = 1.5):
    """Server ishga tushgach brauzerni avtomatik ochish."""
    import threading

    def _open():
        time.sleep(delay_sec)
        webbrowser.open(url)

    t = threading.Thread(target=_open, daemon=True)
    t.start()


def main():
    port = 8750
    url = f"http://localhost:{port}"
    print("=" * 60)
    print("  Chaqimchi AI - Do'kon Analitikasi va Nazorati")
    print(f"  Boshqaruv paneli: {url}")
    print("=" * 60)

    open_browser_delayed(url, delay_sec=1.2)

    # Uvicorn serverni ishga tushirish
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
