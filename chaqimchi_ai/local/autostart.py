"""Windows'da kompyuter yonganda dastur o'zi ishga tushishini ta'minlaydi.

Nima uchun alohida modul kerak bo'ldi.  Avtostart o'rnatuvchida
qo'yiladi (`scripts/windows_installer.nsi`), lekin **0.6.7 gacha** u
`HKLM\\...\\Run` kaliti edi — u kompyuter yonganda emas, kimdir tizimga
**kirganda** ishlaydi.  Do'kon kompyuteri kechasi tok o'chib qayta
yonsa qulf ekranida turadi va nazorat umuman boshlanmaydi: ertalab
kelib "dasturni o'chirib yoqish" kerak bo'ladi.

Muhimi: **masofadan yangilash o'rnatuvchini qayta ishlatmaydi.**  Ya'ni
eski usulda o'rnatilgan kompyuter 0.6.9 ga yangilangandan keyin ham eski
Run kaliti bilan qolaveradi.  Shuning uchun dastur buni o'zi tekshiradi
va bir marta to'g'irlaydi.

Vazifa SYSTEM nomidan yaratiladi, ya'ni bu kod administrator huquqi bilan
ishlaganda (masalan 15 daqiqalik `updater` vazifasi ichida) bajariladi.
Huquq yetmasa jimgina o'tkazib yuboriladi — dastur baribir ishlayveradi.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple

from chaqimchi_ai.local import paths

logger = logging.getLogger(__name__)

#: O'rnatuvchi qo'yadigan nom bilan AYNAN bir xil bo'lishi shart, aks
#: holda ikkita vazifa paydo bo'lardi va dastur ikki nusxada ochilardi.
TASK_NAME = "Chaqimchi AI"

#: Eski avtostart usuli — vazifa ishlagach o'chiriladi.
RUN_KEY = r"HKLM\Software\Microsoft\Windows\CurrentVersion\Run"
RUN_KEY_VALUE = "ChaqimchiAI"

#: Brauzersiz, `pause`siz ishga tushirgich (`build_windows_payload.py`).
SERVICE_LAUNCHER = "Chaqimchi_AI_xizmat.bat"

#: Kompyuter yongandan keyin shuncha kutiladi: tarmoq va NVR ko'tarilsin.
START_DELAY = "0000:30"

_TUNE_PS = (
    "$t = Get-ScheduledTask -TaskName '{name}'; "
    # `schtasks` standarti 72 soat — aynan 72 soatlik sinov oxirida
    # vazifa jimgina to'xtardi.
    "$t.Settings.ExecutionTimeLimit = 'PT0S'; "
    "$t.Settings.RestartCount = 3; "
    "$t.Settings.RestartInterval = 'PT1M'; "
    "$t.Settings.DisallowStartIfOnBatteries = $false; "
    "$t.Settings.StopIfGoingOnBatteries = $false; "
    "Set-ScheduledTask -InputObject $t | Out-Null"
)


def _run(command: List[str], *, timeout: int = 60) -> Tuple[int, str]:
    """Buyruqni oynasiz bajaradi.  `(kod, chiqish)` qaytaradi."""
    try:
        proc = subprocess.run(  # noqa: S603 — buyruq qat'iy, foydalanuvchi kiritmaydi
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)
    return proc.returncode, f"{proc.stdout or ''}{proc.stderr or ''}".strip()


def launcher_path() -> Path:
    return paths.app_root() / SERVICE_LAUNCHER


def task_exists() -> bool:
    if os.name != "nt":
        return False
    code, _out = _run(["schtasks", "/Query", "/TN", TASK_NAME])
    return code == 0


def ensure() -> Dict[str, Any]:
    """Avtostart vazifasi borligini kafolatlaydi.

    Qaytaradi: `{"ok", "created", "reason"}` — panel va jurnal uchun.
    Hech qachon istisno ko'tarmaydi: avtostart tuzatilmagani dasturning
    ishlashiga to'sqinlik qilmasligi kerak.
    """
    if os.name != "nt":
        return {"ok": True, "created": False, "reason": "Windows emas"}

    launcher = launcher_path()
    if not launcher.is_file():
        # Ishlab chiqish muhiti yoki noto'liq o'rnatish — vazifa yaratsak
        # u har yonganda xato beradi.
        return {"ok": False, "created": False, "reason": f"{SERVICE_LAUNCHER} topilmadi"}

    if task_exists():
        _drop_run_key()
        return {"ok": True, "created": False, "reason": "vazifa allaqachon bor"}

    code, out = _run(
        [
            "schtasks",
            "/Create",
            "/F",
            "/TN",
            TASK_NAME,
            "/TR",
            f'"{launcher}"',
            "/SC",
            "ONSTART",
            "/DELAY",
            START_DELAY,
            "/RU",
            "SYSTEM",
            "/RL",
            "HIGHEST",
        ]
    )
    if code != 0:
        # Odatda sabab: huquq yetmaydi (dastur oddiy foydalanuvchi
        # nomidan ishlayapti).  15 daqiqalik `updater` vazifasi SYSTEM
        # nomidan ishlaydi va o'sha yerda muvaffaqiyatli bo'ladi.
        logger.info("Avtostart vazifasi yaratilmadi: %s", out[:200])
        return {"ok": False, "created": False, "reason": out[:200] or "schtasks xatosi"}

    tune_code, tune_out = _run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            _TUNE_PS.format(name=TASK_NAME),
        ]
    )
    if tune_code != 0:
        logger.warning("Avtostart vazifasi sozlanmadi: %s", tune_out[:200])

    _drop_run_key()
    logger.info("Avtostart vazifasi yaratildi: %s", TASK_NAME)
    return {"ok": True, "created": True, "reason": ""}


def _drop_run_key() -> None:
    """Eski `Run` kalitini olib tashlaydi — dastur ikki marta ochilmasin.

    Faqat vazifa ishlaydigan holatda chaqiriladi, aks holda kompyuterni
    avtostartsiz qoldirgan bo'lardik.
    """
    code, out = _run(["reg", "query", RUN_KEY, "/v", RUN_KEY_VALUE])
    if code != 0:
        return
    code, out = _run(["reg", "delete", RUN_KEY, "/v", RUN_KEY_VALUE, "/f"])
    if code == 0:
        logger.info("Eski avtostart kaliti olib tashlandi (%s)", RUN_KEY_VALUE)
    else:
        logger.info("Eski avtostart kaliti o'chirilmadi: %s", out[:200])
