"""Platformaga bog'liq yo'llar — bitta joyda.

Sotqin ikkita joyda ishlaydi: biz sotadigan Intel N100 qutisida (Ubuntu) va
mijozning o'z Windows kompyuterida.  Ikkalasida ham bir xil kod aylanadi,
lekin fayllar boshqa joyda turadi:

| | Linux | Windows |
|---|---|---|
| Dastur | `/opt/chaqimchi` | `%PROGRAMFILES%\\Chaqimchi\\Sotqin` |
| Sozlama va sirlar | `/etc/chaqimchi` | `%PROGRAMDATA%\\Chaqimchi\\Sotqin` |

Bu modul `scripts/pair_sotqin.py` da allaqachon ishlagan `os.name == "nt"`
naqshini umumlashtiradi — u yagona to'g'ri qilingan joy edi, qolgan hamma
yerda yo'llar qattiq yozilgan.

Har bir funksiya **avval muhit o'zgaruvchisiga qaraydi**: qurilmada
o'rnatuvchi ularni `sotqin.env` ga yozadi, testda esa monkeypatch qilinadi.
Shuning uchun bu yerdagi standart qiymatlar faqat oxirgi chora.
"""

from __future__ import annotations

import os
from pathlib import Path, PureWindowsPath

#: Windows'da barcha fayllar shu ikki papka ostida.
_WINDOWS_VENDOR = ("Chaqimchi", "Sotqin")


def is_windows() -> bool:
    """`sys.platform` emas, `os.name` — monkeypatch qilish oson va u
    `pair_sotqin.py` da allaqachon shu tarzda test qilingan."""
    return os.name == "nt"


def _windows_dir(base_env: str, fallback: str) -> Path:
    base = os.environ.get(base_env, fallback)
    return Path(PureWindowsPath(base).joinpath(*_WINDOWS_VENDOR))


def install_root() -> Path:
    """Dastur o'rnatilgan papka (`releases/`, `current`, `venv` shu yerda)."""
    override = os.environ.get("CHAQIMCHI_INSTALL_ROOT", "").strip()
    if override:
        return Path(override)
    if is_windows():
        return _windows_dir("PROGRAMFILES", r"C:\Program Files")
    return Path("/opt/chaqimchi")


def config_dir() -> Path:
    """Sozlama va sirlar papkasi.

    Windows'da `%PROGRAMDATA%` tanlangani ataylab: `%PROGRAMFILES%` ostiga
    xizmat yoza olmaydi (UAC), va sozlama yangilanishdan keyin ham joyida
    qolishi kerak.
    """
    override = os.environ.get("CHAQIMCHI_CONFIG_DIR", "").strip()
    if override:
        return Path(override)
    if is_windows():
        return _windows_dir("PROGRAMDATA", r"C:\ProgramData")
    return Path("/etc/chaqimchi")


def data_dir() -> Path:
    """Relizlar orasida saqlanadigan holat: outbox, klip, buffer, loglar."""
    override = os.environ.get("CHAQIMCHI_DATA_DIR", "").strip()
    if override:
        return Path(override)
    if is_windows():
        return _windows_dir("PROGRAMDATA", r"C:\ProgramData") / "shared" / "data"
    return Path("/opt/chaqimchi/shared/data")


def logs_dir() -> Path:
    override = os.environ.get("CHAQIMCHI_LOGS_DIR", "").strip()
    if override:
        return Path(override)
    if is_windows():
        return _windows_dir("PROGRAMDATA", r"C:\ProgramData") / "shared" / "logs"
    return Path("/opt/chaqimchi/shared/logs")


def env_file() -> Path:
    """Pairing sirlari saqlanadigan fayl."""
    override = os.environ.get("CHAQIMCHI_ENV_FILE", "").strip()
    if override:
        return Path(override)
    return config_dir() / "sotqin.env"


def update_key_file() -> Path:
    """OTA ochiq kaliti — o'rnatishda bir marta qotiriladi."""
    override = os.environ.get("CHAQIMCHI_UPDATE_KEY", "").strip()
    if override:
        return Path(override)
    return config_dir() / "update-public.pem"


def config_file() -> Path:
    override = os.environ.get("CHAQIMCHI_CONFIG", "").strip()
    if override:
        return Path(override)
    return install_root() / "current" / "config" / "sotqin.yaml"


#: Xizmat nomlari.  Linux'da systemd unit, Windows'da Service nomi.
SERVICES = {
    "agent": ("chaqimchi-sotqin.service", "ChaqimchiSotqin"),
    "retail": ("chaqimchi-retail.service", "ChaqimchiRetail"),
    "attendance": ("chaqimchi-attendance.service", "ChaqimchiAttendance"),
}


def service_name(key: str) -> str:
    unit, windows_name = SERVICES[key]
    return windows_name if is_windows() else unit


def restart_command(key: str) -> list[str]:
    """Xizmatni qayta ishga tushirish buyrug'i."""
    name = service_name(key)
    if is_windows():
        # `sc.exe stop` darhol qaytadi, shuning uchun PowerShell'ning
        # `Restart-Service` i ishlatiladi — u to'xtashini kutadi.
        return ["powershell", "-NoProfile", "-Command", f"Restart-Service {name}"]
    return ["systemctl", "restart", name]


def status_command(key: str) -> list[str]:
    name = service_name(key)
    if is_windows():
        return [
            "powershell",
            "-NoProfile",
            "-Command",
            f"(Get-Service {name}).Status",
        ]
    return ["systemctl", "is-active", name]


def restart_hint(key: str = "agent") -> str:
    """Foydalanuvchiga ko'rsatiladigan buyruq matni."""
    name = service_name(key)
    return f"Restart-Service {name}" if is_windows() else f"sudo systemctl restart {name}"
