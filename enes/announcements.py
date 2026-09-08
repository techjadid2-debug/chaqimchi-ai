"""Do'kon karnayidan yangraydigan iboralar — bulut va qurilma uchun bitta manba.

Do'kon kompyuterida karnay bor (yoki arzon karnay ulanadi).  Telegramdagi
tugma bosilganda o'sha karnay gapiradi: do'kon egasi uydan turib do'konda
**hozir** bo'ladi.  Verisure'da bu "Intervene" bosqichi va u uchun butun
qo'riqchilar kompaniyasi kerak — bizda esa allaqachon turgan kompyuter
buni bepul qiladi.

## Nega ERKIN MATN emas, qat'iy katalog

1. **Xodimga qarshi qurol bo'lib qolmasligi uchun.**  Egasi xohlagan
   gapini do'kon karnayidan aytdira olsa, bu tez orada xodimni
   haqoratlash vositasiga aylanadi.  Katalogda faqat ish bilan bog'liq
   uch ibora bor.
2. **Ishonchlilik.**  Oldindan yozilgan fayl har doim bir xil yangraydi;
   matndan ovoz (TTS) do'kondagi sekin kompyuterda kechikadi va o'zbek
   ovozi o'rnatilmagan bo'lsa tanib bo'lmaydigan narsa chiqadi.
3. **Tekshirilishi.**  Qat'iy ro'yxat testda qulflanadi.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass(frozen=True)
class Announcement:
    code: str
    #: Karnaydan eshitiladigan matn.  Oldindan yozilgan fayl yo'q bo'lsa
    #: qurilma shuni tizim ovozi bilan o'qiydi (zaxira yo'l).
    text: str
    #: Telegram tugmasidagi yozuv.
    button: str
    #: Do'kon egasiga panelda ko'rsatiladigan tushuntirish.
    hint: str


ANNOUNCEMENTS: Tuple[Announcement, ...] = (
    Announcement(
        code="deter",
        text="Diqqat! Do'kon kuzatuv ostida.",
        button="🔊 Ovoz bering",
        hint="O'g'rilikka o'xshash holatda — do'kon kuzatuv ostida ekanini eslatadi.",
    ),
    Announcement(
        code="till",
        text="Iltimos, kassaga qarang.",
        button="🔔 Kassaga chaqirish",
        hint="Kassada navbat yig'ilganda yoki kassa bo'sh qolganda xodimni chaqiradi.",
    ),
    Announcement(
        code="closing",
        text="Do'kon yopilmoqda. Xaridingiz uchun rahmat.",
        button="🕐 Yopilish e'loni",
        hint="Ish kuni tugaganda mijozlarga eslatma.",
    ),
)

BY_CODE: Dict[str, Announcement] = {item.code: item for item in ANNOUNCEMENTS}


def is_valid(code: str) -> bool:
    return code in BY_CODE


def text_for(code: str) -> str:
    """Karnaydan eshitiladigan matn.  Noma'lum kod — bo'sh satr."""
    item = BY_CODE.get(code)
    return item.text if item else ""
