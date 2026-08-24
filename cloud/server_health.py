"""Bulut serverining o'z holati: CPU, xotira, disk, yuklama, harorat.

Nega kerak: bugungacha VPS o'zini deyarli o'lchamasdi — faqat disk
kuzatilardi (`cloud/alerts.py:plan_disk_alert`).  Ya'ni xotira tugab
konteyner o'lib qolsa yoki protsessor doim 100% da tursa, buni birinchi
bo'lib **mijoz** sezardi: panel sekinlashardi, hodisa kechikardi.

Nega `psutil` emas: bu modul konteyner ichida ishlaydi va u yerdagi
har bir yangi bog'liqlik xavfsizlik yangilanishi talab qiladigan
qo'shimcha yuk.  Kerakli hamma narsa `/proc` da bor va u standart
kutubxona bilan o'qiladi.

**Faqat haqiqiy o'lchov.**  O'lchab bo'lmagan ko'rsatkich `None`
qaytaradi va `snapshot()` javobiga UMUMAN kirmaydi.  Nol yoki "0%"
yozish eng yomon variant bo'lardi: panelda ishonchli ko'ringan, lekin
yolg'on raqam turadi va uni hech kim tekshirmaydi.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

PROC_STAT = Path("/proc/stat")
PROC_MEMINFO = Path("/proc/meminfo")
THERMAL_ROOT = Path("/sys/class/thermal")

#: Oxirgi `/proc/stat` namunasi: `(band, jami)` jiffies.
#:
#: CPU foizi ikkita namuna orasidagi FARQdan chiqadi — bir martalik
#: o'qish yuklanishdan beri o'rtachani beradi va u haftalab o'zgarmaydi.
#: Fon vazifasi ham, so'rov ichida `sleep` ham kerak emas: admin paneli
#: `/api/v1/admin/dashboard` ni har 15 soniyada so'raydi, ya'ni oyna
#: tabiiy ravishda hosil bo'ladi.  Birinchi chaqiruvda solishtiradigan
#: narsa yo'q — `None` qaytadi va panel "yig'ilmoqda" deb ko'rsatadi.
_last_sample: Optional[Tuple[int, int]] = None
_last_percent: Optional[float] = None


def _read(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        # Linux bo'lmagan muhit (ishlab chiqish uchun macOS) yoki
        # cheklangan konteyner — bu xato emas, shunchaki ma'lumot yo'q.
        return None


def _parse_proc_stat(text: str) -> Optional[Tuple[int, int]]:
    """`/proc/stat` ning birinchi `cpu` qatoridan `(band, jami)`.

    `idle` va `iowait` bo'sh vaqt hisoblanadi: ikkalasida ham protsessor
    ish bajarmayapti.  `iowait` ni band deb sanash diskka qaraydigan
    serverda CPU'ni doim 90% ko'rsatardi.
    """
    for line in text.splitlines():
        if not line.startswith("cpu "):
            continue
        try:
            values = [int(part) for part in line.split()[1:]]
        except ValueError:
            return None
        if len(values) < 5:
            return None
        total = sum(values)
        idle = values[3] + values[4]
        return total - idle, total
    return None


def cpu_percent() -> Optional[float]:
    """Oxirgi chaqiruvdan beri o'rtacha protsessor bandligi."""
    global _last_sample, _last_percent

    text = _read(PROC_STAT)
    if text is None:
        return None
    sample = _parse_proc_stat(text)
    if sample is None:
        return None

    previous = _last_sample
    _last_sample = sample
    if previous is None:
        return None

    busy_delta = sample[0] - previous[0]
    total_delta = sample[1] - previous[1]
    if total_delta <= 0:
        # Ikki chaqiruv bitta jiffy ichida bo'ldi (yoki hisoblagich
        # qayta boshlandi) — yangi ma'lumot yo'q, oxirgisini beramiz.
        return _last_percent
    _last_percent = max(0.0, min(100.0, busy_delta / total_delta * 100))
    return _last_percent


def _parse_meminfo(text: str) -> Optional[float]:
    """`MemAvailable` asosida band xotira foizi.

    `MemFree` EMAS: Linux bo'sh xotirani kesh uchun ishlatadi va u
    "band" ko'rinadi, lekin kerak bo'lganda bir zumda bo'shatiladi.
    `MemAvailable` aynan shuni hisobga oladi — ya'ni bu haqiqiy tanqislik
    o'lchovi.  Xuddi shu mulohaza qurilma tomonida ham qo'llanadi
    (`chaqimchi_ai/retail/pressure.py`), lekin u modul ATAYLAB import
    qilinmaydi: bulut qurilma paketiga bog'lanib qolmasin.
    """
    total = available = None
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        if parts[0] == "MemTotal:":
            total = _to_int(parts[1])
        elif parts[0] == "MemAvailable:":
            available = _to_int(parts[1])
        if total is not None and available is not None:
            break
    if not total or available is None:
        return None
    return max(0.0, min(100.0, (total - available) / total * 100))


def _to_int(raw: str) -> Optional[int]:
    try:
        return int(raw)
    except ValueError:
        return None


def ram_percent() -> Optional[float]:
    text = _read(PROC_MEMINFO)
    return _parse_meminfo(text) if text is not None else None


def load_1m() -> Optional[Tuple[float, int]]:
    """Bir daqiqalik yuklama va yadrolar soni.

    Ikkalasi birga qaytadi, chunki yuklama yolg'iz o'zi hech narsa
    aytmaydi: 4.0 — to'rt yadroli serverda to'liq band, o'n olti
    yadrolida esa bemalol.
    """
    try:
        value = os.getloadavg()[0]
    except (AttributeError, OSError):  # pragma: no cover - Windows/macOS
        return None
    return value, os.cpu_count() or 1


def temperature_c() -> Optional[float]:
    """Eng issiq termal zona.

    Virtual serverda (Contabo KVM) termal zona odatda UMUMAN bo'lmaydi —
    o'shanda `None` qaytadi va panelda harorat qatori chizilmaydi.  Bu
    to'g'ri xatti-harakat: mehmon mashina hostning haroratini bilmaydi.
    """
    if not THERMAL_ROOT.is_dir():
        return None
    hottest: Optional[float] = None
    try:
        zones = sorted(THERMAL_ROOT.glob("thermal_zone*/temp"))
    except OSError:  # pragma: no cover - sysfs o'qilmadi
        return None
    for zone in zones:
        raw = _read(zone)
        if raw is None:
            continue
        value = _to_int(raw.strip())
        if value is None:
            continue
        celsius = value / 1000 if value > 1000 else float(value)
        if hottest is None or celsius > hottest:
            hottest = celsius
    return hottest


def disk_percent() -> Optional[float]:
    """Disk bandligi — `alerts.py` bilan AYNAN bir xil diskda.

    Ikki joyda ikki xil yo'l kuzatilsa, panel «disk joyida» deb turgan
    payt alert «disk to'ldi» deb yozardi va qaysi biriga ishonishni hech
    kim bilmasdi.
    """
    from cloud.alerts import disk_usage_percent, disk_watch_path

    return disk_usage_percent(disk_watch_path())


def free_disk_gb() -> Optional[float]:
    try:
        from cloud.alerts import disk_watch_path

        return shutil.disk_usage(disk_watch_path()).free / 1024**3
    except OSError:  # pragma: no cover - disk o'qilmadi
        return None


def snapshot() -> Dict[str, Any]:
    """Panelga beriladigan holat.

    Faqat HAQIQATAN o'lchangan ko'rsatkichlar kiradi.  Bo'sh lug'at —
    "server o'zini o'lchay olmadi" degani va panel kartani umuman
    chizmaydi.

    Eslatma: Docker standart holatda konteynerga host protsessorini
    ko'rsatadi (`docker-compose.chaqimchi.yml` da `cpus:` chegarasi
    yo'q), ya'ni bu raqamlar VPS'ning o'zi haqida.
    """
    data: Dict[str, Any] = {}

    cpu = cpu_percent()
    if cpu is not None:
        data["cpu_percent"] = round(cpu, 1)

    ram = ram_percent()
    if ram is not None:
        data["ram_percent"] = round(ram, 1)

    disk = disk_percent()
    if disk is not None:
        data["disk_percent"] = round(disk, 1)
        free = free_disk_gb()
        if free is not None:
            data["free_disk_gb"] = round(free, 1)

    load = load_1m()
    if load is not None:
        data["load_1m"] = round(load[0], 2)
        data["cores"] = load[1]

    temp = temperature_c()
    if temp is not None:
        data["temperature_c"] = round(temp, 1)

    return data


__all__ = [
    "cpu_percent",
    "disk_percent",
    "free_disk_gb",
    "load_1m",
    "ram_percent",
    "snapshot",
    "temperature_c",
]
