"""Kompyuter nechta kamerani ko'taradi — halol baho.

Nega kerak.  Sotuv sahifasida "4 kamera" deb yozilgan, lekin mijozning
kompyuteri har xil bo'ladi.  Zaif mashinaga to'rtta kamera qo'shilsa
zanjir kadrlarni tashlab yuboradi va hisobot **jimgina** noto'g'ri
bo'ladi — bu eng yomon nosozlik turi, chunki hech kim sezmaydi.

Shuning uchun sehrgar kamera qo'shishdan oldin nimani ko'tarishini
aytadi.  Baho **taxminiy** va shundayligicha ko'rsatiladi: aniq raqamni
faqat ish jarayonidagi o'lchov beradi, uni esa zanjirning o'z byudjeti
avtomatik tuzatib boradi.

Sinov qilingan konfiguratsiya (mijoz kompyuteri): Intel Core i5-4590 —
4 yadro / 4 oqim, 8 GB DDR3, Intel HD Graphics 4600, NPU yo'q.  Bu
mashinada iGPU inferensga **yaramaydi** (pastdagi izohga qarang), ya'ni
hammasi protsessorda ketadi.
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass, field
from typing import Any, Dict, List

from chaqimchi_ai.limits import SHOP_MAX_CAMERAS

logger = logging.getLogger(__name__)

#: Bitta kamerani kuzatish uchun sekundiga shuncha inferens kerak.
#: Kirish-chiqishni sanash uchun 3-4 kadr yetarli: odam eshikdan
#: ~1 soniyada o'tadi va chiziqni kesib o'tgani shu tezlikda aniq
#: ko'rinadi.  Ko'proq kadr aniqlikni sezilarli oshirmaydi, protsessorni
#: esa chiziqli ravishda yuklaydi.
FPS_PER_CAMERA = 4.0

#: Bitta CPU yadrosi `person-detection-retail-0013` (2.3 GFLOPs, 320×544)
#: da sekundiga taxminan shuncha inferens beradi.  Haswell avlodidagi
#: o'lchovga asoslangan; yangi protsessorlarda ko'proq bo'ladi, ya'ni
#: baho **ehtiyotkor** tomonga xato qiladi.
INFERENCES_PER_CORE = 8.0

#: Bitta yadro RTSP dekodlash va tizim uchun qoldiriladi — aks holda
#: tasvir "sinadi" (`detector_ov._hints` bilan bir xil mulohaza).
RESERVED_CORES = 1

#: Har kamera oqimi va buferi uchun taxminiy xotira.
RAM_PER_CAMERA_MB = 350

#: Dastur o'zi (Python, OpenVINO, model) egallaydigan xotira.
BASE_RAM_MB = 900

#: Hodisa buferi uchun kamida shuncha bo'sh joy kerak.
MIN_FREE_DISK_GB = 20

#: Mahsulot va'da qilgan chegara — bahodan qat'i nazar oshirilmaydi.
#: Qiymat yagona manbadan: `chaqimchi_ai/limits.py`.
MAX_SUPPORTED_CAMERAS = SHOP_MAX_CAMERAS


@dataclass
class Capacity:
    cores: int = 0
    ram_mb: int = 0
    free_disk_gb: float = 0.0
    gpu_usable: bool = False
    gpu_name: str = ""
    #: Ishonch bilan tavsiya etiladigan kamera soni.
    recommended_cameras: int = 0
    #: Sabab bo'lgan cheklov: "cpu", "ram", "disk" yoki "" (cheklov yo'q).
    limited_by: str = ""
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "cores": self.cores,
            "ram_mb": self.ram_mb,
            "free_disk_gb": round(self.free_disk_gb, 1),
            "gpu_usable": self.gpu_usable,
            "gpu_name": self.gpu_name,
            "recommended_cameras": self.recommended_cameras,
            "limited_by": self.limited_by,
            "warnings": self.warnings,
            "summary": self.summary(),
        }

    def summary(self) -> str:
        if self.recommended_cameras <= 0:
            return "Kompyuter quvvati tekshirilmadi."
        engine = self.gpu_name if self.gpu_usable else "protsessor"
        return (
            f"Bu kompyuter {self.recommended_cameras} ta kamerani "
            f"ishonchli ko'taradi ({engine}da tahlil)."
        )


def total_ram_mb() -> int:
    """Umumiy operativ xotira, MB.  Aniqlanmasa 0."""
    # Windows'da `os.sysconf` yo'q, shuning uchun uch usul ketma-ket.
    try:
        if hasattr(os, "sysconf") and "SC_PAGE_SIZE" in os.sysconf_names:
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            if pages > 0:
                return int(pages * page_size / 1024**2)
    except (OSError, ValueError, AttributeError):
        pass

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
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            return int(status.ullTotalPhys / 1024**2)
        except Exception as exc:  # noqa: BLE001 — platformaga xos
            logger.debug("Xotira hajmi aniqlanmadi: %s", exc)
    return 0


def gpu_status() -> tuple[bool, str]:
    """iGPU inferens uchun **haqiqatan** yaraydimi.

    Ro'yxatda ko'rinishi yetarli emas: OpenVINO GPU plagini Intel Gen8
    (Broadwell) dan boshlab qo'llab-quvvatlaydi, mijozning HD Graphics
    4600 esa Gen7.5 (Haswell).  U `available_devices` da chiqishi
    mumkin, kompilyatsiya paytida esa yiqiladi.

    Shuning uchun bu yerda faqat ro'yxat emas, qurilma **nomi** ham
    tekshiriladi va shubhali holatda "yaramaydi" deb hisoblanadi —
    xato tomon xavfsiz.
    """
    try:
        from openvino import Core  # type: ignore[import-not-found]
    except ImportError:
        return False, ""

    try:
        core = Core()
        if "GPU" not in core.available_devices:
            return False, ""
        try:
            name = str(core.get_property("GPU", "FULL_DEVICE_NAME"))
        except Exception:  # noqa: BLE001 — xossa har versiyada bor emas
            name = "Intel GPU"
    except Exception as exc:  # noqa: BLE001 — drayver muammosi ham shu yerda
        logger.info("GPU tekshirilmadi: %s", exc)
        return False, ""

    lowered = name.lower()
    # Gen7.5 va undan eski oilalar — OpenVINO ularni qo'llab-quvvatlamaydi.
    unsupported = ("hd graphics 4", "hd graphics 5000", "hd graphics 2", "hd graphics 3")
    if any(marker in lowered for marker in unsupported):
        logger.info("iGPU (%s) OpenVINO uchun eski — tahlil protsessorda ketadi", name)
        return False, name
    return True, name


def measure(base_dir: str = ".") -> Capacity:
    """Kompyuterni baholaydi."""
    cores = os.cpu_count() or 2
    ram_mb = total_ram_mb()
    gpu_usable, gpu_name = gpu_status()

    try:
        free_disk_gb = shutil.disk_usage(base_dir).free / 1024**3
    except OSError:
        free_disk_gb = 0.0

    capacity = Capacity(
        cores=cores,
        ram_mb=ram_mb,
        free_disk_gb=free_disk_gb,
        gpu_usable=gpu_usable,
        gpu_name=gpu_name,
    )

    # ── Protsessor bo'yicha chegara ──────────────────────────────────
    if gpu_usable:
        # iGPU inferensni o'z zimmasiga oladi, protsessor faqat
        # dekodlaydi — chegara sezilarli yuqori.
        by_cpu = MAX_SUPPORTED_CAMERAS
    else:
        usable_cores = max(1, cores - RESERVED_CORES)
        by_cpu = int((usable_cores * INFERENCES_PER_CORE) // FPS_PER_CAMERA)

    # ── Xotira bo'yicha chegara ──────────────────────────────────────
    by_ram = MAX_SUPPORTED_CAMERAS
    if ram_mb:
        by_ram = int((ram_mb - BASE_RAM_MB) // RAM_PER_CAMERA_MB)

    limits = {"cpu": by_cpu, "ram": by_ram}
    best = min(limits.values())
    capacity.recommended_cameras = max(0, min(best, MAX_SUPPORTED_CAMERAS))
    if capacity.recommended_cameras < MAX_SUPPORTED_CAMERAS:
        capacity.limited_by = min(limits, key=lambda key: limits[key])

    # ── Ogohlantirishlar ─────────────────────────────────────────────
    if gpu_name and not gpu_usable:
        capacity.warnings.append(
            f"Video karta ({gpu_name}) tahlil uchun eski — hammasi protsessorda "
            "ishlaydi. Bu normal, faqat kamera soni cheklanadi."
        )
    if ram_mb and ram_mb < 4000:
        capacity.warnings.append("Operativ xotira 4 GB dan kam. Kamida 8 GB tavsiya etiladi.")
    if free_disk_gb and free_disk_gb < MIN_FREE_DISK_GB:
        capacity.warnings.append(
            f"Diskda {free_disk_gb:.0f} GB bo'sh joy qoldi. Video buferi uchun "
            f"kamida {MIN_FREE_DISK_GB} GB kerak."
        )
    if capacity.recommended_cameras <= 0:
        capacity.warnings.append(
            "Bu kompyuter tahlil uchun juda zaif. Kamera qo'shish mumkin, "
            "lekin hisobot to'liq bo'lmasligi mumkin."
        )

    logger.info(
        "Apparat: %d yadro, %d MB RAM, GPU=%s → %d kamera",
        cores,
        ram_mb,
        gpu_name or "yo'q",
        capacity.recommended_cameras,
    )
    return capacity
