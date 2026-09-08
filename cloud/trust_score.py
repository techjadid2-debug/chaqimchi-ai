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

## Til

`score()` va `label()` tilni ANIQ oladi (`lang`), `i18n.t()` ishlatmaydi.
Sabab: ikkalasi ham panel so'rovidan (`/api/v1/owner/trust-score`) ham,
kunlik Telegram xabaridan (`cloud/digest.py`) ham chaqiriladi.  Digest —
fon vazifasi, unda so'rov konteksti yo'q va `t()` hech kimning tilini
bermasdi.  Panel yo'li `lang=i18n.current_lang()` deb uzatadi.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from cloud import i18n
from cloud.alerts import SILENT_ALERT_HOURS

#: Har qism uchun eng yuqori ball.  Foizga aylantirish `score()` da.
PART_MAX = 20

#: Birorta qism juda past bo'lsa ball shundan yuqoriga chiqmaydi.
#: `label()` bo'yicha bu "E'tibor talab qiladi" — ya'ni raqamning o'zi
#: mijozni muammoga qaratadi.
CONCERN_CAP = 70


def _part(
    code: str,
    points: Optional[int],
    note: str = "",
    *,
    lang: str,
) -> Dict[str, Any]:
    """Bitta qism.  `points=None` — bu qism o'lchanmayapti, ballga kirmaydi.

    Nomi kodidan keladi (`trust.part.<code>`): qism nomi va kodi bir
    joyda tug'ilsin, ikkitasi ajralib ketmasin.
    """
    return {
        "code": code,
        "label": i18n.tg(lang, f"trust.part.{code}"),
        "points": points,
        "max": PART_MAX if points is not None else None,
        "measured": points is not None,
        "note": note,
    }


# ── Qismlar ──────────────────────────────────────────────────────────────


def _traffic_part(traffic: Dict[str, Any], *, lang: str) -> Dict[str, Any]:
    """Mijoz oqimi odatdagidanmi.

    Kutilmagan TUSHISH signal: eshik yopiqmi, kamera burilganmi, ko'chada
    ta'mirmi.  O'sish esa har doim yaxshi — uni jazolamaymiz.
    """
    entered = int(traffic.get("entered") or 0)
    yesterday = int(traffic.get("entered_yesterday") or 0)

    if not entered and not yesterday:
        return _part("traffic", None, i18n.tg(lang, "trust.traffic.no_data"), lang=lang)
    if not entered:
        return _part("traffic", 0, i18n.tg(lang, "trust.traffic.none_today"), lang=lang)
    if not yesterday:
        # Birinchi kun — taqqoslashga asos yo'q, lekin mijoz kelgan.
        return _part("traffic", 15, i18n.tg(lang, "trust.traffic.no_yesterday"), lang=lang)

    change = (entered - yesterday) * 100 / yesterday
    percent = abs(round(change))
    if change >= -10:
        return _part("traffic", 20, i18n.tg(lang, "trust.traffic.normal"), lang=lang)
    if change >= -25:
        return _part("traffic", 14, i18n.tg(lang, "trust.traffic.down", percent=percent), lang=lang)
    if change >= -50:
        return _part("traffic", 8, i18n.tg(lang, "trust.traffic.down", percent=percent), lang=lang)
    return _part(
        "traffic", 3, i18n.tg(lang, "trust.traffic.down_check", percent=percent), lang=lang
    )


def _queue_part(queue: Dict[str, Any], *, configured: bool, lang: str) -> Dict[str, Any]:
    """Navbat sog'ligi.

    `configured=False` bo'lsa qism ballga UMUMAN kirmaydi: zonasiz navbat
    o'lchanmaydi va nol signal "mukammal" degani emas.
    """
    alerts = int(queue.get("alerts") or 0)
    # Hodisa BOR bo'lsa o'lchov ham bor — bulut sozlamasi nima deyishidan
    # qat'i nazar.  Zona qurilmaning O'Z sozlamasida (lokal sehrgarda)
    # chizilgan bo'lishi mumkin va u bulutga yetib bormagan bo'ladi.
    # Jonli pilotda aynan shunday chiqdi: bulutda zona yo'q, lekin bir
    # kunda 14 ta navbat hodisasi kelgan.
    if not configured and not alerts:
        return _part("queue", None, i18n.tg(lang, "trust.queue.not_configured"), lang=lang)

    longest = int(queue.get("longest") or 0)
    if alerts == 0:
        return _part("queue", 20, i18n.tg(lang, "trust.queue.ok"), lang=lang)
    suffix = i18n.tg(lang, "trust.queue.longest", longest=longest) if longest else ""
    if alerts <= 2:
        points = 16
    elif alerts <= 5:
        points = 11
    elif alerts <= 10:
        points = 6
    else:
        return _part(
            "queue",
            2,
            i18n.tg(lang, "trust.queue.long_understaffed", alerts=alerts, suffix=suffix),
            lang=lang,
        )
    return _part(
        "queue", points, i18n.tg(lang, "trust.queue.long", alerts=alerts, suffix=suffix), lang=lang
    )


def _staff_part(shifts: Optional[Dict[str, Any]], *, lang: str) -> Dict[str, Any]:
    """Xodimlar vaqtida keldimi.

    Xodim qo'shilmagan do'konda bu qism o'lchanmaydi.
    """
    if not shifts or not int(shifts.get("employees") or 0):
        return _part("staff", None, i18n.tg(lang, "trust.staff.none"), lang=lang)

    # Xodim BOR, lekin ish kuni belgilanmagan — davomat umuman
    # o'lchanmagan.  Bunda "hammasi vaqtida keldi" deyish ballning yana
    # bir jimgina yolg'oni bo'lardi: nol kechikish nol o'lchovdan
    # kelib chiqadi, yaxshi ishdan emas.  Jonli do'konda aynan shu
    # holat topildi (`ish_kunlari: 0`, xodim rasmi yo'q).
    if not sum(int(row.get("ish_kunlari") or 0) for row in shifts.get("rows") or []):
        return _part("staff", None, i18n.tg(lang, "trust.staff.no_schedule"), lang=lang)

    total = shifts.get("jami") or {}
    absent = int(total.get("kelmagan_kunlar") or 0)
    late_min = int(total.get("kechikish_daq") or 0)

    if absent:
        return _part("staff", 4, i18n.tg(lang, "trust.staff.absent", absent=absent), lang=lang)
    if late_min == 0:
        return _part("staff", 20, i18n.tg(lang, "trust.staff.on_time"), lang=lang)
    if late_min <= 15:
        points = 16
    elif late_min <= 60:
        points = 10
    else:
        points = 4
    return _part(
        "staff", points, i18n.tg(lang, "trust.staff.late", minutes=late_min), lang=lang
    )


def _security_part(security: Dict[str, Any], *, lang: str) -> Dict[str, Any]:
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
        return _part(
            "security", 4, i18n.tg(lang, "trust.security.critical", count=critical), lang=lang
        )
    if minor > 5:
        return _part(
            "security", 11, i18n.tg(lang, "trust.security.minor_many", count=minor), lang=lang
        )
    if minor:
        return _part("security", 16, i18n.tg(lang, "trust.security.minor", count=minor), lang=lang)
    return _part("security", 20, i18n.tg(lang, "trust.security.none"), lang=lang)


def _cameras_part(active: int, expected: int, *, lang: str) -> Dict[str, Any]:
    """Kameralar sog'ligi — nechtasi kun davomida ishlab turdi."""
    if expected <= 0:
        return _part("cameras", None, i18n.tg(lang, "trust.cameras.none"), lang=lang)
    ratio = min(1.0, active / expected)
    points = round(ratio * PART_MAX)
    if active >= expected:
        return _part(
            "cameras", points, i18n.tg(lang, "trust.cameras.all", active=active), lang=lang
        )
    return _part(
        "cameras",
        points,
        i18n.tg(
            lang,
            "trust.cameras.partial",
            expected=expected,
            active=active,
            lost=expected - active,
        ),
        lang=lang,
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
    lang: str = i18n.DEFAULT_LANG,
) -> Dict[str, Any]:
    """Kunning ballini hisoblaydi.

    Qaytaradi: `available` (ball ko'rsatsa bo'ladimi), `reason` (nega
    bo'lmasa), `total` (0-100) va `parts` (tushuntirish uchun).

    `lang` — matnlar (`reason`, `parts[].label`, `parts[].note`) shu
    tilda.  Raqamlar tilga bog'liq emas: bir kirish uchun har tilda
    bir xil ball chiqadi.
    """
    # ── Ball ko'rsatib bo'lmaydigan holatlar ──
    #
    # Bular ataylab BALLDAN OLDIN tekshiriladi: ma'lumot to'liq emasligini
    # bilib turib raqam chiqarish — mijozni chalg'itish.
    if minutes_since_seen is None:
        return _unavailable(i18n.tg(lang, "trust.unavailable.not_connected"))
    if minutes_since_seen >= SILENT_ALERT_HOURS * 60:
        hours = minutes_since_seen // 60
        return _unavailable(i18n.tg(lang, "trust.unavailable.silent", hours=hours))
    if cameras_expected and cameras_active <= 0:
        return _unavailable(i18n.tg(lang, "trust.unavailable.no_cameras"))

    parts = [
        _traffic_part(report.get("traffic") or {}, lang=lang),
        _queue_part(report.get("queue") or {}, configured=queue_configured, lang=lang),
        _staff_part(shifts, lang=lang),
        _security_part(report.get("security") or {}, lang=lang),
        _cameras_part(cameras_active, cameras_expected, lang=lang),
    ]

    measured = [item for item in parts if item["measured"]]
    if not measured:
        return _unavailable(i18n.tg(lang, "trust.unavailable.nothing_measured"), parts)

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


def label(total: Optional[int], lang: str = i18n.DEFAULT_LANG) -> str:
    """Ball ostidagi bitta so'z — raqamning o'zi hammaga tushunarli emas."""
    if total is None:
        return i18n.tg(lang, "trust.label.none")
    if total >= 90:
        return i18n.tg(lang, "trust.label.excellent")
    if total >= 75:
        return i18n.tg(lang, "trust.label.good")
    if total >= 55:
        return i18n.tg(lang, "trust.label.attention")
    return i18n.tg(lang, "trust.label.problem")
