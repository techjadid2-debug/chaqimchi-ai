"""Lokal o'rnatishda fayllar qayerda turadi.

Eng muhim qoida: **dastur papkasiga hech narsa yozilmaydi.**  Oldingi Windows
o'rnatuvchisi `Program Files` ichiga `.venv`, `data\\` va `install.log` yozishga
urinardi — u yerda esa oddiy foydalanuvchida yozish huquqi yo'q, shuning uchun
dastur birinchi ishga tushishdayoq jimgina yiqilardi.

Shuning uchun ikki joy qat'iy ajratilgan:

    Program Files\\ENES Monitoring    — kod, Python, AI modeli (faqat o'qish)
    %PROGRAMDATA%\\ENES       — config, log, hodisa bazasi, klip (yoziladi)

Rebrenddan oldin o'rnatilgan kompyuterda ikkinchi papka `%PROGRAMDATA%\\Chaqimchi`
deb ataladi va u YANGI nomga ko'chirilmaydi — `data_dir()` izohiga qarang.

`%PROGRAMDATA%` ataylab `%LOCALAPPDATA%` dan afzal: do'kon kompyuterida
tizimga kim kirganidan qat'i nazar bitta sozlama bo'lishi kerak, aks holda
kassir o'z hisobidan kirsa "kamera yo'q" degan bo'sh sehrgar ochilardi.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from enes.paths import is_windows

logger = logging.getLogger(__name__)

#: Testlar va ishlab chiqish uchun: hamma yo'llarni bitta papkaga ko'chiradi.
ENV_DATA_DIR = "ENES_LOCAL_DIR"

#: Papkaning "bu yerda haqiqiy o'rnatish bor" belgisi.
#:
#: Papkaning O'ZI belgi bo'la olmaydi: `data_dir()` uni har chaqiruvda
#: `mkdir` bilan yaratib qo'yadi, ya'ni yangi nomdagi bo'sh papka dastur
#: bir marta ishga tushishi bilan paydo bo'ladi.  Sozlama fayli esa faqat
#: sozlash sehrgari tugagandan keyin yoziladi.
_MARKER = "config.yaml"

#: Rebrenddan oldingi ma'lumot papkasi.
#:
#: 2026-09-09 da aynan shu ko'prik yo'qligi pilotni to'xtatib qo'ydi:
#: 0.6.30 avto-yangilanishi o'tdi, dastur esa bo'sh `ProgramData\ENES` ni
#: ko'rib o'zini YANGI kompyuter deb tanishtirdi — 15 soat davomida
#: `device-handover` so'rab turdi va do'kondan ma'lumot kelmadi.  Sozlama,
#: kamera manzillari, chizmalar, outbox navbati va bufer eski papkada
#: qolgan edi.
#:
#: Nega KO'CHIRILMAYDI: bufer gigabaytlab bo'lishi mumkin va uni ishlab
#: turgan xizmat ostida ko'chirish yarim yo'lda uzilsa ikkala papka ham
#: buzilardi.  Eski papka bor bo'lsa o'sha ishlatiladi; yangi o'rnatish
#: yangi nomni oladi.  Xuddi shu qaror `enes/paths.py` da (Box yo'li) ham.
_LEGACY_WINDOWS_DIR = "Chaqimchi"
_LEGACY_POSIX_DIR = ".chaqimchi"

#: Tanlangan yo'l bir marta logga yoziladi — keyingi tashxis fayl
#: qidirishdan emas, logdan boshlansin.
_logged_legacy = False


def _pick(current: Path, legacy: Path) -> Path:
    """Eski papkada o'rnatish bor-u yangisida yo'q bo'lsa — eskisi."""
    global _logged_legacy
    if not (current / _MARKER).exists() and (legacy / _MARKER).exists():
        if not _logged_legacy:
            logger.warning(
                "Ma'lumotlar eski papkadan o'qilyapti: %s (yangisi: %s)", legacy, current
            )
            _logged_legacy = True
        return legacy
    return current


def data_dir() -> Path:
    """Yoziladigan ma'lumotlar papkasi.  Yo'q bo'lsa yaratiladi."""
    override = os.environ.get(ENV_DATA_DIR, "").strip()
    if override:
        base = Path(override).expanduser()
    elif is_windows():
        root = os.environ.get("PROGRAMDATA") or os.environ.get("LOCALAPPDATA") or r"C:\ProgramData"
        base = _pick(Path(root) / "ENES", Path(root) / _LEGACY_WINDOWS_DIR)
    else:
        home = Path.home()
        base = _pick(home / ".enes", home / _LEGACY_POSIX_DIR)
    base.mkdir(parents=True, exist_ok=True)
    return base


def config_path() -> Path:
    return data_dir() / _MARKER


def logs_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def status_path() -> Path:
    """`retail.service` kameralarning haqiqiy holatini shu faylga yozadi."""
    return data_dir() / "retail-status.json"


def alive_marker_path() -> Path:
    """Panel jarayoni tirikligining diskdagi izi.

    Updater yangilashdan keyin dastur haqiqatan ishga tushganini shu
    fayldan biladi: `phase="starting"` — `main()` boshlandi,
    `phase="running"` — panel ishlab turibdi (har daqiqa yangilanadi).
    Cloud heartbeat buning o'rnini bosolmaydi: updater SYSTEM sifatida
    lokal ishlaydi va internetga qaramasligi kerak.
    """
    return data_dir() / "app-alive.json"


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


def rules_path() -> Path:
    """Do'kon qoidalari fayli (suppression, sovutish, save_clip).

    O'rnatuvchi uni dastur papkasiga qo'yadi (`config/rules.yaml`).
    Ishlab chiqishda repo ildizidagi o'sha fayl ishlatiladi.
    """
    return app_root() / "config" / "rules.yaml"


def model_path() -> Path:
    """OpenVINO odam detektori modeli.

    O'rnatuvchi uni dastur papkasiga qo'yadi.  Ishlab chiqish mashinasida esa
    repo ildizidagi `models/retail/` ishlatiladi — ikkalasi bir xil nom.
    """
    override = os.environ.get("ENES_RETAIL_MODEL", "").strip()
    if override:
        return Path(override)
    return app_root() / "models" / "retail" / "person-detection-retail-0013.xml"


def face_model_path() -> Path:
    """Demografiya uchun yuz detektori — person modeli bilan BIR joyda.

    Absolyut yo'l muhim: xizmat `--base-dir` sifatida ProgramData oladi,
    modellar esa o'rnatish papkasida.  Nisbiy yo'l ProgramData'dan izlanib
    hech qachon topilmasdi — demografiya Windows'da jimgina o'chiq edi.
    """
    return app_root() / "models" / "retail" / "face-detection-retail-0004.xml"


def age_gender_model_path() -> Path:
    """Yosh/jins modeli — `face_model_path` izohiga qarang."""
    return app_root() / "models" / "retail" / "age-gender-recognition-retail-0013.xml"
