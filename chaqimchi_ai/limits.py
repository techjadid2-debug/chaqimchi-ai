"""Mahsulot chegaralari — yagona haqiqat manbai.

Bitta do'kon uchun qabul qilingan profil: **4 kamera** (docs/DOKON_MVP.md).
Bu son ilgari uch joyda alohida yozilgan edi (local/app.py=4,
local/hardware.py=4, sotqin_profile.py=8) va bir joyda o'zgartirish
qolganlarini jimgina eskirtirardi.  Endi hammasi shu yerdan oladi.
"""

from __future__ import annotations

#: Bitta do'kon (site) uchun sotiladigan/qo'llab-quvvatlanadigan kamera soni.
#: Sehrgar ham, tarif ham, qurilma bahosi ham shu chegarada to'xtaydi.
SHOP_MAX_CAMERAS = 4

#: NVR kanallarini skanerlashda nechtagacha qarab chiqiladi.  Limitdan
#: kattaroq: mijozning kamerasi 5-6-kanalda turgan bo'lishi mumkin —
#: skaner uni ko'rsatadi, tanlov esa baribir SHOP_MAX_CAMERAS bilan
#: cheklanadi.
NVR_SCAN_CHANNELS = 8
