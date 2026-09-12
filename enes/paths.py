"""Platformaga bog'liq yo'llar — bitta joyda.

Sotqin ikkita joyda ishlaydi: biz sotadigan Intel N100 qutisida (Ubuntu) va
mijozning o'z Windows kompyuterida.  Ikkalasida ham bir xil kod aylanadi,
lekin fayllar boshqa joyda turadi:

| | Linux | Windows |
|---|---|---|
| Dastur | `/opt/enes` | `%PROGRAMFILES%\\ENES\\Sotqin` |
| Sozlama va sirlar | `/etc/enes` | `%PROGRAMDATA%\\ENES\\Sotqin` |

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
_WINDOWS_VENDOR = ("ENES", "Sotqin")

#: Rebrenddan oldingi papka.  O'rnatilgan kompyuterda sozlama, token va
#: bufer shu yerda turadi va yangi nomga KO'CHIRILMAYDI: ko'chirish
#: yangilanish o'rtasida uzilsa ikkala papka ham yarim bo'lardi.  Eski
#: papkada O'RNATISH bo'lsa (bo'sh papka emas — `_has_installation`) u
#: ishlatiladi; yangi o'rnatish yangi nomni oladi.
_LEGACY_WINDOWS_VENDOR = ("Chaqimchi", "Sotqin")

#: Linux (Box) uchun ham xuddi shu qoida.
_LINUX_LEGACY = {"/opt/enes": "/opt/chaqimchi", "/etc/enes": "/etc/chaqimchi"}


def is_windows() -> bool:
    """`sys.platform` emas, `os.name` — monkeypatch qilish oson va u
    `pair_sotqin.py` da allaqachon shu tarzda test qilingan."""
    return os.name == "nt"


def _has_installation(path: Path) -> bool:
    """Shu papkada HAQIQIY o'rnatish bormi.

    Papkaning BORLIGI belgi emas.  Bo'sh papka yon ta'sir sifatida paydo
    bo'ladi — deploy skripti `mkdir -p` qilsa, o'rnatuvchi yarim yo'lda
    uzilsa, yoki arxiv ochilsa.  Shundan keyin ko'prik eski o'rnatishni
    HECH QACHON tanlamaydi va qurilma o'zini yangi mashina deb
    tanishtiradi.  Do'kon dasturidagi egizak modulda aynan shu bo'ldi:
    bo'sh `ProgramData\\ENES` paydo bo'ldi va pilot 15 soat
    `device-handover` so'rab turdi (`enes/local/paths.py` dagi `_MARKER`
    izohi).  U yerda ko'prik nom bo'yicha belgiga (`config.yaml`)
    o'tkazilgan edi, bu yerda esa yozilmay qolgan.

    Nega bu yerda nom bo'yicha belgi emas: ikki daraxtning ichi
    butunlay boshqa — `install_root()` da `current`/`releases`/`venv`,
    `config_dir()` da `sotqin.env`/`update-public.pem`.  Bitta fayl
    nomini tanlash ikkalasi uchun ham noto'g'ri bo'lardi va yangi fayl
    qo'shilganda jimgina eskirardi.  Shuning uchun belgi — papkaning
    BO'SH EMASLIGI: o'rnatuvchi u yerga nimadir yozgan bo'lsa,
    o'rnatish bor.
    """
    try:
        return any(path.iterdir())
    except OSError:
        # Papka yo'q, fayl, yoki o'qish huquqi yo'q.  Hammasida "o'rnatish
        # yo'q" deymiz: yangi nomni noto'g'ri tanlash qaytariladigan xato
        # (papka bo'sh, ma'lumot yo'qolmaydi), eski papkani noto'g'ri
        # tanlash esa yangi o'rnatishni begona ma'lumotga bog'lab qo'yadi.
        return False


def _windows_dir(base_env: str, fallback: str) -> Path:
    """Yangi nomdagi papka, lekin eski o'rnatish topilsa — o'sha."""
    base = PureWindowsPath(os.environ.get(base_env, fallback))
    current = Path(base.joinpath(*_WINDOWS_VENDOR))
    legacy = Path(base.joinpath(*_LEGACY_WINDOWS_VENDOR))
    if not _has_installation(current) and _has_installation(legacy):
        return legacy
    return current


def _linux_dir(path: str) -> Path:
    """`/opt/enes` — lekin eski `/opt/chaqimchi` turgan qurilmada o'sha."""
    current = Path(path)
    legacy = _LINUX_LEGACY.get(path)
    if legacy and not _has_installation(current) and _has_installation(Path(legacy)):
        return Path(legacy)
    return current


def install_root() -> Path:
    """Dastur o'rnatilgan papka (`releases/`, `current`, `venv` shu yerda)."""
    override = os.environ.get("ENES_INSTALL_ROOT", "").strip()
    if override:
        return Path(override)
    if is_windows():
        return _windows_dir("PROGRAMFILES", r"C:\Program Files")
    return _linux_dir("/opt/enes")


def config_dir() -> Path:
    """Sozlama va sirlar papkasi.

    Windows'da `%PROGRAMDATA%` tanlangani ataylab: `%PROGRAMFILES%` ostiga
    xizmat yoza olmaydi (UAC), va sozlama yangilanishdan keyin ham joyida
    qolishi kerak.
    """
    override = os.environ.get("ENES_CONFIG_DIR", "").strip()
    if override:
        return Path(override)
    if is_windows():
        return _windows_dir("PROGRAMDATA", r"C:\ProgramData")
    return _linux_dir("/etc/enes")


def data_dir() -> Path:
    """Relizlar orasida saqlanadigan holat: outbox, klip, buffer, loglar."""
    override = os.environ.get("ENES_DATA_DIR", "").strip()
    if override:
        return Path(override)
    if is_windows():
        return _windows_dir("PROGRAMDATA", r"C:\ProgramData") / "shared" / "data"
    return _linux_dir("/opt/enes") / "shared" / "data"


def logs_dir() -> Path:
    override = os.environ.get("ENES_LOGS_DIR", "").strip()
    if override:
        return Path(override)
    if is_windows():
        return _windows_dir("PROGRAMDATA", r"C:\ProgramData") / "shared" / "logs"
    return _linux_dir("/opt/enes") / "shared" / "logs"


def env_file() -> Path:
    """Pairing sirlari saqlanadigan fayl."""
    override = os.environ.get("ENES_ENV_FILE", "").strip()
    if override:
        return Path(override)
    return config_dir() / "sotqin.env"


def update_key_file() -> Path:
    """OTA ochiq kaliti — o'rnatishda bir marta qotiriladi."""
    override = os.environ.get("ENES_UPDATE_KEY", "").strip()
    if override:
        return Path(override)
    return config_dir() / "update-public.pem"


def config_file() -> Path:
    override = os.environ.get("ENES_CONFIG", "").strip()
    if override:
        return Path(override)
    return install_root() / "current" / "config" / "sotqin.yaml"


#: Xizmat nomlari.  Linux'da systemd unit, Windows'da Service nomi.
SERVICES = {
    "agent": ("enes-sotqin.service", "EnesSotqin"),
    "retail": ("enes-retail.service", "EnesRetail"),
    "attendance": ("enes-attendance.service", "EnesAttendance"),
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
