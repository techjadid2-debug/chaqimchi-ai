"""Jarayondan omon qoladigan hisoblagichlar.

Nega alohida fayl kerak: 72 soatlik barqarorlik sinovining asosiy mezoni —
**"kutilmagan qayta ishga tushish 0"**.  Uni o'lchaydigan yagona son
`RetailSupervisor._crashes` edi, u esa xotirada (`deque(maxlen=3)`) va
aynan qayta ishga tushish paytida yo'qolardi.  Ya'ni sinov natijasi
"restart bo'lmadi" emas, "restart bo'lganini eslay olmadik" degani edi.

Ikkita son yozamiz va ular ataylab ajratilgan:

* `chain_starts`  — AI zanjiri necha marta ishga tushirilgan (mijoz
  sozlamani o'zgartirsa ham oshadi, bu **normal**);
* `chain_crashes` — zanjir **o'zi** to'xtab, kuzatuvchi uni qayta
  ko'targan holatlar.  Qabul mezonida aynan shu son 0 bo'lishi kerak;
* `panel_boots`   — panel jarayonining o'zi necha marta ko'tarilgan
  (kompyuter qayta yonishi ham shu yerda ko'rinadi).

Yozuv atomik: `.tmp` ga yozilib, keyin joyiga surilib qo'yiladi.  Elektr
uzilishida yarim yozilgan JSON qolib, hisoblagich butunlay nolga
qaytmasligi kerak.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict

from chaqimchi_ai.local import paths

logger = logging.getLogger(__name__)

FILE_NAME = "counters.json"

#: Sinov hisobotida kutiladigan sonlar.  Fayl yo'q bo'lsa hammasi 0.
KNOWN = ("chain_starts", "chain_crashes", "panel_boots")


def _path():
    return paths.data_dir() / FILE_NAME


def read() -> Dict[str, Any]:
    """Barcha hisoblagichlar.  Fayl yo'q yoki buzuq bo'lsa — nollar."""
    empty: Dict[str, Any] = {name: 0 for name in KNOWN}
    empty["since"] = None
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return empty
    if not isinstance(data, dict):
        return empty
    out = dict(empty)
    for key, value in data.items():
        if key == "since":
            out["since"] = value
        else:
            try:
                out[key] = int(value)
            except (TypeError, ValueError):
                continue
    return out


def bump(name: str, *, amount: int = 1) -> int:
    """Hisoblagichni oshiradi va yangi qiymatini qaytaradi.

    Diskka yozib bo'lmasa (fayl band, disk to'la) **xato ko'tarmaydi**:
    hisoblagich sabab nazorat to'xtashi mumkin emas.
    """
    data = read()
    data[name] = int(data.get(name) or 0) + amount
    if not data.get("since"):
        data["since"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    data["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    path = _path()
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False)
            # Tok o'chganda yarim yozilgan fayl qolmasin: hisoblagich
            # buzilsa 72 soatlik sinovning "qayta ishga tushish soni"
            # mezoni o'lchanmay qolardi.
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError:
        logger.warning("Hisoblagich yozilmadi: %s", name, exc_info=True)
    return int(data[name])


def reset() -> None:
    """Sinovni noldan boshlashda ishlatiladi."""
    try:
        _path().unlink(missing_ok=True)
    except OSError:  # pragma: no cover
        logger.warning("Hisoblagichlar tozalanmadi", exc_info=True)
