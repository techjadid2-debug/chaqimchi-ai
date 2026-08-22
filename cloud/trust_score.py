"""«Ishonch balli» — do'kon kunining bitta raqami.

Panelda o'nlab grafik bor va do'kon egasi ularning birortasini ochmaydi:
dashboardni o'qish 10 daqiqalik ish, kuniga bitta raqamga qarash esa
30 soniyalik ish.  Har kuni qaraladigan narsa odat yaratadi, odat esa
mijozni ushlab qoladi.

Modul **sof**: bazaga ham, tarmoqqa ham chiqmaydi.  Kirish ma'lumoti
allaqachon mavjud funksiyalardan keladi (`EventStore.retail_report`,
`EventStore.shift_summary`, `CloudStore` dagi aloqa holati), shuning
uchun yangi ma'lumot yig'ilmaydi va test yozish oson.

## Ikkita qoida — ballning butun qiymati shularga bog'liq

**1. Ball hech qachon "hammasi joyida" deb YOLG'ON aytmaydi.**
Qurilma jim bo'lsa yoki bironta kamera ishlamasa, kunning ma'lumoti
to'liq emas — bunda ball umuman ko'rsatilmaydi.  Aks holda o'chib qolgan
do'kon har kuni "94" ko'rsatib turardi va bu mumkin bo'lgan eng yomon
nosozlik bo'lardi: mijoz mahsulot ishlayapti deb o'ylab yuradi.

**2. O'lchanmagan narsa ballga kirmaydi.**
Navbat zonasi chizilmagan bo'lsa `queue_threshold_exceeded` hodisasi
HECH QACHON chiqmaydi — ya'ni "0 ta navbat signali" mukammal navbat
degani emas, "biz navbatni umuman o'lchamayapmiz" degani.  Shuning
uchun har qism o'zi qo'llanadimi-yo'qmi deb belgilanadi va ball faqat
HAQIQATAN o'lchangan qismlardan foizga aylantiriladi.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from cloud.alerts import SILENT_ALERT_HOURS

#: Har qism uchun eng yuqori ball.  Foizga aylantirish `score()` da.
PART_MAX = 20

#: Birorta qism juda past bo'lsa ball shundan yuqoriga chiqmaydi.
#: `label()` bo'yicha bu "E'tibor talab qiladi" — ya'ni raqamning o'zi
#: mijozni muammoga qaratadi.
CONCERN_CAP = 70


def _part(
    code: str,
    label: str,
    points: Optional[int],
    note: str = "",
) -> Dict[str, Any]:
    """Bitta qism.  `points=None` — bu qism o'lchanmayapti, ballga kirmaydi."""
    return {
        "code": code,
        "label": label,
        "points": points,
        "max": PART_MAX if points is not None else None,
        "measured": points is not None,
        "note": note,
    }


# ── Qismlar ──────────────────────────────────────────────────────────────


def _traffic_part(traffic: Dict[str, Any]) -> Dict[str, Any]:
    """Mijoz oqimi odatdagidanmi.

    Kutilmagan TUSHISH signal: eshik yopiqmi, kamera burilganmi, ko'chada
    ta'mirmi.  O'sish esa har doim yaxshi — uni jazolamaymiz.
    """
    entered = int(traffic.get("entered") or 0)
    yesterday = int(traffic.get("entered_yesterday") or 0)

    if not entered and not yesterday:
        return _part("traffic", "Mijozlar oqimi", None, "Ikki kun ham mijoz sanalmadi")
    if not entered:
        return _part("traffic", "Mijozlar oqimi", 0, "Bugun bironta mijoz sanalmadi")
    if not yesterday:
        # Birinchi kun — taqqoslashga asos yo'q, lekin mijoz kelgan.
        return _part("traffic", "Mijozlar oqimi", 15, "Kecha bilan taqqoslash uchun ma'lumot yo'q")

    change = (entered - yesterday) * 100 / yesterday
    if change >= -10:
        return _part("traffic", "Mijozlar oqimi", 20, "Odatdagidek")
    if change >= -25:
        return _part("traffic", "Mijozlar oqimi", 14, f"Kechagidan {abs(round(change))}% kam")
    if change >= -50:
        return _part("traffic", "Mijozlar oqimi", 8, f"Kechagidan {abs(round(change))}% kam")
    return _part("traffic", "Mijozlar oqimi", 3, f"Kechagidan {abs(round(change))}% kam — tekshiring")


def _queue_part(queue: Dict[str, Any], *, configured: bool) -> Dict[str, Any]:
    """Navbat sog'ligi.

    `configured=False` bo'lsa qism ballga UMUMAN kirmaydi: zonasiz navbat
    o'lchanmaydi va nol signal "mukammal" degani emas.
    """
    if not configured:
        return _part("queue", "Navbat", None, "Navbat zonasi chizilmagan — o'lchanmayapti")

    alerts = int(queue.get("alerts") or 0)
    longest = int(queue.get("longest") or 0)
    if alerts == 0:
        return _part("queue", "Navbat", 20, "Navbat chegaradan oshmadi")
    suffix = f", eng uzuni {longest} kishi" if longest else ""
    if alerts <= 2:
        return _part("queue", "Navbat", 16, f"{alerts} marta uzun bo'ldi{suffix}")
    if alerts <= 5:
        return _part("queue", "Navbat", 11, f"{alerts} marta uzun bo'ldi{suffix}")
    if alerts <= 10:
        return _part("queue", "Navbat", 6, f"{alerts} marta uzun bo'ldi{suffix}")
    return _part("queue", "Navbat", 2, f"{alerts} marta uzun bo'ldi{suffix} — kassa yetishmayapti")


def _staff_part(shifts: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Xodimlar vaqtida keldimi.

    Xodim qo'shilmagan do'konda bu qism o'lchanmaydi.
    """
    if not shifts or not int(shifts.get("employees") or 0):
        return _part("staff", "Xodimlar", None, "Xodim qo'shilmagan")

    # Xodim BOR, lekin ish kuni belgilanmagan — davomat umuman
    # o'lchanmagan.  Bunda "hammasi vaqtida keldi" deyish ballning yana
    # bir jimgina yolg'oni bo'lardi: nol kechikish nol o'lchovdan
    # kelib chiqadi, yaxshi ishdan emas.  Jonli do'konda aynan shu
    # holat topildi (`ish_kunlari: 0`, xodim rasmi yo'q).
    if not sum(int(row.get("ish_kunlari") or 0) for row in shifts.get("rows") or []):
        return _part("staff", "Xodimlar", None, "Ish jadvali belgilanmagan — davomat o'lchanmayapti")

    total = shifts.get("jami") or {}
    absent = int(total.get("kelmagan_kunlar") or 0)
    late_min = int(total.get("kechikish_daq") or 0)

    if absent:
        return _part("staff", "Xodimlar", 4, f"{absent} xodim kelmadi")
    if late_min == 0:
        return _part("staff", "Xodimlar", 20, "Hammasi vaqtida keldi")
    if late_min <= 15:
        return _part("staff", "Xodimlar", 16, f"Jami {late_min} daqiqa kechikish")
    if late_min <= 60:
        return _part("staff", "Xodimlar", 10, f"Jami {late_min} daqiqa kechikish")
    return _part("staff", "Xodimlar", 4, f"Jami {late_min} daqiqa kechikish")


def _security_part(security: Dict[str, Any]) -> Dict[str, Any]:
    """Xavfsizlik hodisalari.

    Kamera buzilishi va ish vaqtidan tashqari harakat — jiddiy toifa;
    uzoq turish va taqiqlangan zona esa e'tibor talab qiladi, lekin
    o'g'rilik darajasida emas.
    """
    critical = int(security.get("camera_tampered") or 0) + int(
        security.get("after_hours_presence") or 0
    )
    minor = int(security.get("loitering") or 0) + int(security.get("restricted_zone") or 0)

    if critical:
        return _part("security", "Xavfsizlik", 4, f"{critical} ta jiddiy hodisa — ko'ring")
    if minor > 5:
        return _part("security", "Xavfsizlik", 11, f"{minor} ta e'tibor talab qiladigan hodisa")
    if minor:
        return _part("security", "Xavfsizlik", 16, f"{minor} ta kichik hodisa")
    return _part("security", "Xavfsizlik", 20, "Hodisa bo'lmadi")


def _cameras_part(active: int, expected: int) -> Dict[str, Any]:
    """Kameralar sog'ligi — nechtasi kun davomida ishlab turdi."""
    if expected <= 0:
        return _part("cameras", "Kameralar", None, "Kamera qo'shilmagan")
    ratio = min(1.0, active / expected)
    points = round(ratio * PART_MAX)
    if active >= expected:
        return _part("cameras", "Kameralar", points, f"{active} ta kamera ishlayapti")
    return _part(
        "cameras",
        "Kameralar",
        points,
        f"{expected} tadan {active} tasi ishlayapti — {expected - active} tasi o'chiq",
    )


# ── Yig'ish ──────────────────────────────────────────────────────────────


def _unavailable(reason: str, parts: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    return {"available": False, "reason": reason, "total": None, "parts": parts or []}


def score(
    *,
    report: Dict[str, Any],
    shifts: Optional[Dict[str, Any]] = None,
    minutes_since_seen: Optional[int],
    cameras_active: int,
    cameras_expected: int,
    queue_configured: bool,
) -> Dict[str, Any]:
    """Kunning ballini hisoblaydi.

    Qaytaradi: `available` (ball ko'rsatsa bo'ladimi), `reason` (nega
    bo'lmasa), `total` (0-100) va `parts` (tushuntirish uchun).
    """
    # ── Ball ko'rsatib bo'lmaydigan holatlar ──
    #
    # Bular ataylab BALLDAN OLDIN tekshiriladi: ma'lumot to'liq emasligini
    # bilib turib raqam chiqarish — mijozni chalg'itish.
    if minutes_since_seen is None:
        return _unavailable("Qurilma hali ulanmagan")
    if minutes_since_seen >= SILENT_ALERT_HOURS * 60:
        hours = minutes_since_seen // 60
        return _unavailable(f"Do'kon kompyuteri {hours} soatdan beri jim — ma'lumot to'liq emas")
    if cameras_expected and cameras_active <= 0:
        return _unavailable("Bironta kamera ishlamayapti — ma'lumot yo'q")

    parts = [
        _traffic_part(report.get("traffic") or {}),
        _queue_part(report.get("queue") or {}, configured=queue_configured),
        _staff_part(shifts),
        _security_part(report.get("security") or {}),
        _cameras_part(cameras_active, cameras_expected),
    ]

    measured = [item for item in parts if item["measured"]]
    if not measured:
        return _unavailable("Hali o'lchanadigan ma'lumot yo'q", parts)

    earned = sum(int(item["points"]) for item in measured)
    possible = sum(int(item["max"]) for item in measured)
    total = round(earned * 100 / possible)

    # Bitta jiddiy muammo o'rtachada YUVILIB KETMASLIGI kerak.
    #
    # O'lchandi: mijoz oqimi 140 dan 40 ga tushgan kun (eshik yopiq yoki
    # kamera burilgan) qolgan to'rt qism a'lo bo'lgani uchun 83 — "yaxshi
    # kun" chiqardi.  Do'kon egasi uchun esa aynan o'sha tushish kunning
    # eng muhim xabari edi.  Xuddi shu narsa buzilgan kamerada ham bo'lardi.
    #
    # Shuning uchun: birorta qism o'z maksimumining chorak qismidan past
    # bo'lsa, ball "e'tibor talab qiladi" darajasidan yuqoriga chiqmaydi.
    if any(int(item["points"]) <= PART_MAX // 4 for item in measured):
        total = min(total, CONCERN_CAP)

    return {
        "available": True,
        "reason": None,
        "total": total,
        "parts": parts,
    }


def label(total: Optional[int]) -> str:
    """Ball ostidagi bitta so'z — raqamning o'zi hammaga tushunarli emas."""
    if total is None:
        return "Ma'lumot yo'q"
    if total >= 90:
        return "A'lo kun"
    if total >= 75:
        return "Yaxshi kun"
    if total >= 55:
        return "E'tibor talab qiladi"
    return "Muammo bor"
