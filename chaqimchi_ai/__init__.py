"""Eski paket nomi — `enes` ga ko'prik.  FAQAT o'rnatilgan qurilmalar uchun.

Nega bor: 2026-09 rebrendida paket `chaqimchi_ai` → `enes` bo'ldi.
Lekin pilot kompyuterlarda o'rnatuvchi (NSIS) qo'ygan rejalashtirilgan
vazifa `python -m chaqimchi_ai.local.updater` deb turadi va u payload
yangilanganda ham o'zgarmaydi.  Bu papka bo'lmasa yangilanish
zanjirining o'zi uzilardi — ya'ni yangi versiya hech qachon kelmasdi.

Qanday ishlaydi: `__path__` `enes/` ga ko'rsatiladi, shuning uchun
`chaqimchi_ai.local.updater` import qilinganda `enes/local/updater.py`
fayli ochiladi.  Kod ichidagi importlar `enes.*` bo'lgani uchun asosiy
holat bitta nusxada qoladi; faqat kirish moduli ikki nom bilan
yuklanadi — `-m` uchun bu bezarar.

Cloud obraziga KIRMAYDI (`Dockerfile.cloud` faqat `enes` ni ko'chiradi);
Windows payloadiga kiradi (`build_windows_payload.py: CODE_DIRS`).
Qurilmalar yangi o'rnatuvchi bilan qayta o'rnatilgach olib tashlanadi.
"""

from pathlib import Path

import enes

__path__ = [str(Path(enes.__file__).parent)]
__version__ = enes.__version__
