"""Ishlab turgan AI zanjiri jarayonlarini topish va to'xtatish.

NEGA ALOHIDA MODUL.  Bu mantiq ilgari faqat `windows_installer.nsi`
ichida, PowerShell satrlari ko'rinishida yashirin turardi — ya'ni uni
test qilib bo'lmasdi va natijasi hech qayerda tekshirilmasdi.

2026-08-26 da oqibati o'lchandi: do'kon kompyuterida **beshta** zanjir
bir vaqtda ishlayotgan edi (hodisalardagi `edge_version`: 0.6.13,
0.6.16, 0.6.17, 0.6.18, 0.6.19 — beshtasi ham o'sha daqiqada hodisa
yuborardi).  Har yangilanish ortida bitta tirik jarayon qoldirgan.
Oqibati: har chegara jarayonlar soniga ko'payib ketardi — yuz kadri
soatlik shifti, davomat kameralari ro'yxati, kamera byudjeti.  Shu
sabab bir necha reliz "ishlamayotgandek" ko'rindi.

Modul uchta joyga xizmat qiladi:

* `supervisor` — yangi zanjirdan oldin eskilarini tozalaydi;
* `cloud_jobs` — masofadan yuborilgan tozalash topshirig'i;
* heartbeat — nechta yetim topilgani cloudga aytiladi.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
from typing import Any, Dict, Iterable, List, Optional, Set

logger = logging.getLogger(__name__)

#: Zanjir jarayonini buyruq qatoridan taniymiz.
#:
#: Naqsh `windows_installer.nsi` dagi bilan BIR XIL bo'lishi shart —
#: ikkalasi ajralib ketsa o'rnatuvchi bir narsani, dastur boshqasini
#: o'ldiradi va farq faqat dala sharoitida bilinadi.
CHAIN_MODULE = "chaqimchi_ai.retail.service"

#: PowerShell so'rovi shuncha kutadi.  Jarayon ro'yxati kichik, lekin
#: yuklangan kompyuterda CIM sekin javob berishi mumkin.
QUERY_TIMEOUT_SEC = 20


def _powershell_pids() -> List[int]:
    """Windows: buyruq qatorida modulimiz bor `python.exe` larning PID'i."""
    script = (
        "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | "
        f"Where-Object {{ $_.CommandLine -like '*{CHAIN_MODULE}*' }} | "
        "Select-Object -ExpandProperty ProcessId | ConvertTo-Json -Compress"
    )
    try:
        out = subprocess.run(  # noqa: S603 — buyruq qat'iy, foydalanuvchi kiritmaydi
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            timeout=QUERY_TIMEOUT_SEC,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        # PowerShell yo'q yoki cheklangan.  Bu JIMGINA o'tmasligi kerak:
        # aynan shunday "jim muvaffaqiyatsizlik" beshta zanjirni
        # to'plagan edi.
        logger.warning("Jarayonlar ro'yxatini olib bo'lmadi: %s", exc)
        return []
    if not out:
        return []
    try:
        data = json.loads(out)
    except ValueError:
        logger.warning("Jarayonlar ro'yxati o'qilmadi: %r", out[:120])
        return []
    if isinstance(data, int):
        data = [data]
    return [int(item) for item in data if isinstance(item, int)]


def find_chains(exclude: Optional[Iterable[int]] = None) -> List[int]:
    """Ishlab turgan zanjir jarayonlari (o'zimiznikilarsiz)."""
    if os.name != "nt":
        # Linux/macOS'da zanjir systemd bilan boshqariladi va yetim
        # muammosi yo'q — u yerda hech narsa qidirmaymiz.
        return []
    skip: Set[int] = {int(pid) for pid in (exclude or ())} | {os.getpid()}
    return [pid for pid in _powershell_pids() if pid not in skip]


def kill_chains(exclude: Optional[Iterable[int]] = None) -> Dict[str, Any]:
    """Yetim zanjirlarni to'xtatadi va NATIJANI qaytaradi.

    Qaytadi: `{"found": N, "killed": N, "remaining": N, "pids": [...]}`.

    `remaining` noldan katta bo'lsa — o'ldirish ishlamadi (huquq
    yetmadi yoki jarayon qaytib keldi).  Bu son chaqiruvchiga
    qaytariladi va heartbeat orqali panelga chiqadi: shu paytgacha
    bunday nosozlik hech qayerda ko'rinmasdi.
    """
    targets = find_chains(exclude)
    killed = 0
    for pid in targets:
        try:
            os.kill(pid, signal.SIGTERM)
            killed += 1
            logger.warning("Eski zanjir to'xtatildi (pid %s)", pid)
        except (ProcessLookupError, PermissionError, OSError) as exc:
            logger.warning("Zanjirni to'xtatib bo'lmadi (pid %s): %s", pid, exc)
    remaining = find_chains(exclude)
    return {
        "found": len(targets),
        "killed": killed,
        "remaining": len(remaining),
        "pids": targets,
    }
