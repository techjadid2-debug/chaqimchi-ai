"""Lokal o'rnatishda fayllar qayerda turadi.

Eng muhim qoida: **dastur papkasiga hech narsa yozilmaydi.**  Oldingi Windows
o'rnatuvchisi `Program Files` ichiga `.venv`, `data\\` va `install.log` yozishga
urinardi — u yerda esa oddiy foydalanuvchida yozish huquqi yo'q, shuning uchun
dastur birinchi ishga tushishdayoq jimgina yiqilardi.

Shuning uchun ikki joy qat'iy ajratilgan:

    Program Files\\Chaqimchi AI    — kod, Python, AI modeli (faqat o'qish)
    %PROGRAMDATA%\\Chaqimchi       — config, log, hodisa bazasi, klip (yoziladi)

`%PROGRAMDATA%` ataylab `%LOCALAPPDATA%` dan afzal: do'kon kompyuterida
tizimga kim kirganidan qat'i nazar bitta sozlama bo'lishi kerak, aks holda
kassir o'z hisobidan kirsa "kamera yo'q" degan bo'sh sehrgar ochilardi.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Testlar va ishlab chiqish uchun: hamma yo'llarni bitta papkaga ko'chiradi.
ENV_DATA_DIR = "CHAQIMCHI_LOCAL_DIR"


def data_dir() -> Path:
    """Yoziladigan ma'lumotlar papkasi.  Yo'q bo'lsa yaratiladi."""
    override = os.environ.get(ENV_DATA_DIR, "").strip()
    if override:
        base = Path(override).expanduser()
    elif os.name == "nt":
        root = os.environ.get("PROGRAMDATA") or os.environ.get("LOCALAPPDATA") or r"C:\ProgramData"
        base = Path(root) / "Chaqimchi"
    else:
        base = Path.home() / ".chaqimchi"
    base.mkdir(parents=True, exist_ok=True)
    return base


def config_path() -> Path:
    return data_dir() / "config.yaml"


def logs_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def status_path() -> Path:
    """`retail.service` kameralarning haqiqiy holatini shu faylga yozadi."""
    return data_dir() / "retail-status.json"


def outbox_path() -> Path:
    """Hodisalar navbati.

    Yo'l `retail.service` ichida `base_dir / "data" / "outbox.db"` deb
    qotirilgan, shuning uchun bu yerda ham aynan shunday hisoblanadi —
    ikkalasi bir xil faylni ko'rmasa panel bo'sh turardi.
    """
    return data_dir() / "data" / "outbox.db"


def app_root() -> Path:
    """Kod va birga kelgan modellar papkasi (faqat o'qish uchun)."""
    return Path(__file__).resolve().parents[2]


def model_path() -> Path:
    """OpenVINO odam detektori modeli.

    O'rnatuvchi uni dastur papkasiga qo'yadi.  Ishlab chiqish mashinasida esa
    repo ildizidagi `models/retail/` ishlatiladi — ikkalasi bir xil nom.
    """
    override = os.environ.get("CHAQIMCHI_RETAIL_MODEL", "").strip()
    if override:
        return Path(override)
    return app_root() / "models" / "retail" / "person-detection-retail-0013.xml"
