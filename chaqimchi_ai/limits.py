"""Mahsulot chegaralari — yagona haqiqat manbai.

Bitta do'kon uchun qabul qilingan profil: **4 kamera** (docs/DOKON_MVP.md).
Bu son ilgari uch joyda alohida yozilgan edi (local/app.py=4,
local/hardware.py=4, sotqin_profile.py=8) va bir joyda o'zgartirish
qolganlarini jimgina eskirtirardi.  Endi hammasi shu yerdan oladi.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

#: Bitta do'kon (site) uchun sotiladigan/qo'llab-quvvatlanadigan kamera soni.
#: Sehrgar ham, tarif ham, qurilma bahosi ham shu chegarada to'xtaydi.
SHOP_MAX_CAMERAS = 4

#: NVR kanallarini skanerlashda nechtagacha qarab chiqiladi.  Limitdan
#: kattaroq: mijozning kamerasi 5-6-kanalda turgan bo'lishi mumkin —
#: skaner uni ko'rsatadi, tanlov esa baribir SHOP_MAX_CAMERAS bilan
#: cheklanadi.
NVR_SCAN_CHANNELS = 8

#: Do'kon soati — O'zbekiston, UTC+5.
#:
#: Nega qat'iy offset va `zoneinfo` emas: Windows'da tz bazasi yo'q va
#: `tzdata` paketi `requirements-windows-local.txt` da ham yo'q, ya'ni
#: `ZoneInfo("Asia/Tashkent")` aynan do'kon kompyuterida yiqilardi.
#: O'zbekistonda yozgi vaqt YO'Q va UTC+5 o'zgarmagan, shuning uchun
#: offset to'liq to'g'ri javob beradi.  Naqsh panelda ham shu:
#: `frontend/src/api.ts:formatTimeUz` ayni shu sababdan `Intl`siz yozilgan.
#:
#: Nega umuman kerak: qurilma "ish vaqtidan tashqari odam" qarorini
#: MASHINANING lokal soatidan chiqarardi (`retail/pipeline.py`).
#: 2026-08-27 da sinov do'konining kompyuteri UTC+3 da turgani aniqlandi —
#: UTC to'g'ri edi, ya'ni soat nazorati (`clock_skew_sec`) buni ko'rmadi.
#: Oqibati ikki tomonlama va ikkalasi ham qimmat: ertalab 08:30–10:30
#: orasida do'kon OCHIQ bo'la turib kritik trevoga ketardi (bir kunda
#: 26 ta), kechqurun 22:00–00:00 orasida esa — o'g'rilik uchun eng
#: ehtimolli ikki soat — nazorat UMUMAN ishlamasdi.
STORE_UTC_OFFSET_HOURS = 5

#: Do'kon zonasi — `datetime` uchun tayyor obyekt.
STORE_TZ = timezone(timedelta(hours=STORE_UTC_OFFSET_HOURS), "Asia/Tashkent")


def store_now() -> datetime:
    """Do'kon devoridagi soat.

    `datetime.now()` EMAS: u mashinaning sozlamasiga ishonadi va noto'g'ri
    zonada turgan kompyuter butun tungi nazoratni jimgina buzadi.  Bu
    yerdan olingan vaqt kompyuter zonasidan mustaqil.
    """
    return datetime.now(STORE_TZ)
