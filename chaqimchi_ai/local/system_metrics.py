"""Do'kon kompyuterining jonli ko'rsatkichlari: CPU, xotira, disk, harorat.

`hardware.py` dan farqi: u SIG'IMNI o'lchaydi (nechta yadro, qancha
xotira) va sehrgarda bir marta ishlatiladi.  Bu modul esa HOZIRGI
bandlikni beradi va har heartbeat bilan bulutga ketadi.

Nega kerak: bulut allaqachon bu maydonlarni qabul qiladi
(`EdgeHeartbeatBody`) va Linux qutilari ularni yuboradi, Windows esa
yubormasdi.  Natijada do'kon kompyuteri qizib ketsa yoki xotirasi tugab
qolsa, buni na mijoz, na biz bilardik — kompyuter shunchaki
sekinlashardi va oxirida o'chib qolardi.

Yangi bog'liqlik YO'Q (`psutil` ham).  Payload internetsiz o'rnatiladi
va `pip` u yerda umuman ishlamaydi, ya'ni har bir yangi paket
o'rnatuvchining hajmini va buzilish ehtimolini oshiradi.  Kerakli
hamma narsa `ctypes` va standart kutubxona bilan olinadi.

**Faqat haqiqiy o'lchov.**  O'lchab bo'lmagan ko'rsatkich `None`
qaytaradi va heartbeat'ga umuman kirmaydi.  Masalan Windows'da harorat
administrator huquqisiz o'qilmaydi — panelda "0°C" ko'rsatgandan ko'ra
qatorni umuman chizmagan yaxshiroq.
"""

from __future__ import annotations

import logging
import os
import shutil
import time
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

#: Oxirgi CPU namunasi: `(band, jami)`.
#:
#: Foiz ikki o'lchov orasidagi FARQdan chiqadi — bir martalik o'qish
#: yuklanishdan beri o'rtachani berardi va u kun bo'yi o'zgarmasdi.
#: Heartbeat halqasi har 20 soniyada aylanadi, ya'ni oyna tabiiy hosil
#: bo'ladi.  Birinchi chaqiruvda solishtiradigan narsa yo'q — `None`.
_last_cpu: Optional[Tuple[int, int]] = None
_last_percent: Optional[float] = None


def _windows_cpu_sample() -> Optional[Tuple[int, int]]:
    """`GetSystemTimes` orqali `(band, jami)`.

    Muhim tuzoq: `kernel` vaqti `idle` ni O'Z ICHIGA oladi (Microsoft
    hujjatida shunday).  Shuning uchun band vaqt `kernel + user - idle`,
    jami esa `kernel + user`.  Buni e'tiborsiz qoldirsa, bo'sh turgan
    kompyuter ham 100% band ko'rinardi.
    """
    import ctypes

    class _FileTime(ctypes.Structure):
        _fields_ = [
            ("dwLowDateTime", ctypes.c_uint32),
            ("dwHighDateTime", ctypes.c_uint32),
        ]

    def _value(item: "_FileTime") -> int:
        return (item.dwHighDateTime << 32) | item.dwLowDateTime

    idle, kernel, user = _FileTime(), _FileTime(), _FileTime()
    ok = ctypes.windll.kernel32.GetSystemTimes(
        ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
    )
    if not ok:
        return None
    total = _value(kernel) + _value(user)
    return total - _value(idle), total


def _posix_cpu_percent() -> Optional[float]:
    """Linux/macOS uchun zaxira: yuklama yadrolar soniga nisbatan.

    Aniq emas (yuklama diskni kutayotgan jarayonlarni ham sanaydi),
    lekin ishlab chiqish muhitida va Sotqin qutisida yetarli — u yerda
    asosiy o'lchov baribir `retail/pressure.py` dan keladi.
    """
    try:
        load = os.getloadavg()[0]
    except (AttributeError, OSError):  # pragma: no cover - qo'llab-quvvatlanmaydi
        return None
    cores = os.cpu_count() or 1
    return max(0.0, min(100.0, load / cores * 100))


def cpu_percent() -> Optional[float]:
    """Oxirgi chaqiruvdan beri o'rtacha protsessor bandligi."""
    global _last_cpu, _last_percent

    if os.name != "nt":
        return _posix_cpu_percent()

    try:
        sample = _windows_cpu_sample()
    except Exception as exc:  # noqa: BLE001 — platformaga xos chaqiruv
        logger.debug("Protsessor bandligi o'qilmadi: %s", exc)
        return None
    if sample is None:
        return None

    previous = _last_cpu
    _last_cpu = sample
    if previous is None:
        return None
    busy_delta = sample[0] - previous[0]
    total_delta = sample[1] - previous[1]
    if total_delta <= 0:
        return _last_percent
    _last_percent = max(0.0, min(100.0, busy_delta / total_delta * 100))
    return _last_percent


def ram_percent() -> Optional[float]:
    """Band xotira foizi."""
    if os.name == "nt":
        try:
            import ctypes

            class _MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = _MemoryStatus()
            status.dwLength = ctypes.sizeof(_MemoryStatus)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return None
            # `dwMemoryLoad` — Windows o'zi hisoblagan band foiz.
            return float(max(0, min(100, int(status.dwMemoryLoad))))
        except Exception as exc:  # noqa: BLE001 — platformaga xos
            logger.debug("Xotira bandligi o'qilmadi: %s", exc)
            return None

    from chaqimchi_ai.retail.pressure import read_memory_ratio

    ratio = read_memory_ratio()
    return ratio * 100 if ratio else None


def disk_percent(path: Optional[str] = None) -> Optional[float]:
    """Ma'lumotlar diski qanchalik to'lgan."""
    target = path
    if target is None:
        from chaqimchi_ai.local import paths

        target = str(paths.data_dir())
    try:
        usage = shutil.disk_usage(target)
    except OSError:
        return None
    if not usage.total:
        return None
    return usage.used / usage.total * 100


def temperature_c() -> Optional[float]:
    """Protsessor harorati, agar o'qish mumkin bo'lsa.

    Windows'da odatda **mumkin emas**: WMI'ning `MSAcpi_ThermalZone`
    sinfi ko'p noutbuk va ish stoli platalarida umuman to'ldirilmaydi,
    haqiqiy datchiklar esa administrator huquqi va vendor drayveri
    talab qiladi.  O'shanda `None` qaytadi va harorat heartbeat'ga
    KIRMAYDI — bu halol xatti-harakat.
    """
    if os.name == "nt":
        return None
    from chaqimchi_ai.retail.pressure import read_temperature_c

    return read_temperature_c()


def uptime_sec() -> Optional[float]:
    """Kompyuter yonganidan beri o'tgan vaqt."""
    if os.name == "nt":
        try:
            import ctypes

            # `GetTickCount64` — millisekundlarda, 49 kunda toshmaydi
            # (eski `GetTickCount` toshib ketardi).
            ticks = ctypes.windll.kernel32.GetTickCount64()
            return float(ticks) / 1000
        except Exception as exc:  # noqa: BLE001 — platformaga xos
            logger.debug("Uptime o'qilmadi: %s", exc)
            return None
    try:
        with open("/proc/uptime", encoding="utf-8") as handle:
            return float(handle.read().split()[0])
    except (OSError, ValueError, IndexError):
        # macOS: dastur ishga tushganidan beri — taxminiy, lekin
        # ishlab chiqishda yetarli.
        return time.monotonic()


__all__ = ["cpu_percent", "disk_percent", "ram_percent", "temperature_c", "uptime_sec"]
