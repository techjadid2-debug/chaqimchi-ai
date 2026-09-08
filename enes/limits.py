"""Mahsulot chegaralari — yagona haqiqat manbai.

Bitta do'kon uchun qabul qilingan profil: **4 kamera** (docs/DOKON_MVP.md).
Bu son ilgari uch joyda alohida yozilgan edi (local/app.py=4,
local/hardware.py=4, sotqin_profile.py=8) va bir joyda o'zgartirish
qolganlarini jimgina eskirtirardi.  Endi hammasi shu yerdan oladi.
"""

from __future__ import annotations

import math
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


# ── Davomat: yuz kesmasi geometriyasi ────────────────────────────────────
#
# Bu uch qiymat ilgari IKKI faylda alohida yozilgan edi va ular bir-biriga
# ZID bo'lib qolgan.  2026-08-28 jonli o'lchovi: qurilma 93 marta yuz
# kesmasini olishga urindi va **93 tasi ham** "juda mayda" deb tashlandi
# (`face_crops: {written: 0, too_small: 93}`) — davomat oylab ishlamadi
# va sababi hech qayerda ko'rinmadi.
#
# Matematika (640x360 tahlil oqimida):
#     ramka balandligi >= 0.28 * 360 = 101 px   <- scene_analytics ruxsat berdi
#     kesma            =  0.35 * 101 =  35 px   <- pipeline talab qildi >= 96
# Ya'ni chegara HECH QACHON o'ta olmasdi.  Bu "sozlash" masalasi emas edi,
# ikki son bir-birini inkor qilardi.
#
# Yechim: ikkalasi ham shu yerdan, bitta formuladan chiqadi.

#: Yuz kesmasining eng kam tomoni (piksel).
#:
#: `face-reidentification-retail-0095` 128x128 tekislangan yuz kutadi;
#: undan kichik kesmadan chiqadigan vektor — shovqin va u hech qachon
#: moslik chegarasidan o'tmaydi.  Ilgari 16 px turardi ("bo'sh kesma
#: bo'lmasin" himoyasi) va oqibati 4 606 ta yaroqsiz kadr bo'ldi —
#: o'rtacha 727 bayt, cloud ularning birortasini ham tanimadi.
FACE_MIN_CROP_PX = 96

#: Kesma odam ramkasining yuqori shu ulushidan olinadi (bosh).
FACE_CROP_RATIO = 0.35


def face_min_bbox_px() -> int:
    """Kesma chegarasidan o'tadigan eng kichik odam ramkasi (piksel).

    Oddiy bo'lish YETARLI EMAS: `pipeline` kesma balandligini
    `int(bbox * FACE_CROP_RATIO)` bilan oladi, ya'ni KESIB tashlaydi.
    96/0.35 = 274.3 va 274 px ramkadan `int(95.9) = 95` px chiqadi —
    bir piksel yetmagani uchun kesma baribir rad etilardi.  Shuning
    uchun natija taxmin qilinmaydi, TEKSHIRILADI.
    """
    height = math.ceil(FACE_MIN_CROP_PX / FACE_CROP_RATIO)
    while int(height * FACE_CROP_RATIO) < FACE_MIN_CROP_PX:
        height += 1
    return height


def face_min_bbox_ratio(frame_height: int) -> float:
    """Yuz kadri olinadigan eng kichik odam ramkasi (kadr ulushida).

    Qattiq son EMAS, chunki javob oqim sifatiga bog'liq: bir xil odam
    360p da 101 px, 720p da 202 px ramka beradi.  Chegarani qo'lda
    yozish aynan shu sababdan ikki fayl orasida ajralib ketgan edi.

    Natija: 360p -> 0.76, 720p -> 0.38, 1080p -> 0.25.

    360p dagi 0.76 amalda "imkonsiz" degani va bu ATAYLAB shunday:
    odam kadrning uchdan ikkisini egallamaguncha kesma baribir
    tashlanardi, faqat endi u bekorga OLINMAYDI ham.  Mijoz
    kamerasidagi substream sifati ko'tarilsa chegara o'zi pasayadi —
    qo'l bilan tuzatish kerak bo'lmaydi.
    """
    if frame_height <= 0:
        # Kadr o'lchami noma'lum — yuz kadri olinmasin.  Nolga bo'lishdan
        # ko'ra jim turish yaxshiroq: yaroqsiz kesma cloud byudjetini yeydi.
        return 1.0
    return face_min_bbox_px() / frame_height
