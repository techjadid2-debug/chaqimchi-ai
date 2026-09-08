"""Telegram xabarlari uchun yagona uslub.

Nega alohida modul: xabarlar uch joydan yuboriladi (alert, digest,
webhook buyruqlari) va har biri o'z formatini yasab, bot "har xil
odam yozganday" ko'rinardi.  Endi sarlavha, vaqt, raqam va grafik —
hammasi bitta joydan.

Qoidalar:
- Sarlavha: do'kon nomi qalin, birinchi qatorda.
- Vaqt: Toshkent vaqti, "17:32" yoki "17:32, 17-avg" (mijoz UTC bilmaydi).
- Kamera: `camera-03` emas — konfigdagi odam o'qiydigan nom.
- Grafik: blok belgilar (▁▂▃▄▅▆▇█) — matnli mini-diagramma, rasmsiz.

Til: matn chiqaradigan har yordamchi `lang` oladi va `i18n` katalogidan
o'qiydi.  Oy va hafta kunlari nomi ham shu yerda emas, katalogda —
panel bilan bitta manba, ya'ni "avg" bilan "авг" ajralib ketmaydi.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

from cloud import i18n
from cloud.i18n import tg

TASHKENT = ZoneInfo("Asia/Tashkent")

#: Blok-grafik pog'onalari (bo'sh joy — nol uchun).
_BARS = " ▁▂▃▄▅▆▇█"


def escape(value: Any) -> str:
    """Telegram HTML rejimi uchun xavfsiz matn."""
    return (
        str(value if value is not None else "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def to_tashkent(value: Any) -> Optional[datetime]:
    """ISO satr yoki datetime → Toshkent vaqti; o'qib bo'lmasa None."""
    if isinstance(value, datetime):
        moment = value
    else:
        try:
            moment = datetime.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(TASHKENT)


def clock(value: Any) -> str:
    """ "17:32" — faqat soat."""
    moment = to_tashkent(value)
    return moment.strftime("%H:%M") if moment else ""


def short_date(moment: datetime, lang: str = i18n.DEFAULT_LANG) -> str:
    """ "17-avg" / "17 авг" / "Aug 17" — shakl ham, oy nomi ham katalogdan."""
    months = i18n.t_list(lang, "format.months_short")
    month = months[moment.month - 1] if len(months) >= moment.month else str(moment.month)
    return tg(lang, "format.date.short", day=moment.day, month_short=month)


def weekday_name(index: int, lang: str = i18n.DEFAULT_LANG) -> str:
    """Hafta kuni nomi; 0 = dushanba (Python `weekday()` bilan bir xil)."""
    names = i18n.t_list(lang, "format.weekdays_title")
    return names[index % 7] if names else ""


def stamp(value: Any, lang: str = i18n.DEFAULT_LANG) -> str:
    """ "17:32, 17-avg" — soat va sana."""
    moment = to_tashkent(value)
    if not moment:
        return ""
    return tg(lang, "botfmt.stamp", time=f"{moment:%H:%M}", date=short_date(moment, lang))


def day_title(value: Any, lang: str = i18n.DEFAULT_LANG) -> str:
    """ "17-avg, Yakshanba" — hisobot sarlavhasi uchun."""
    moment = to_tashkent(value)
    if not moment:
        return str(value)
    return tg(
        lang,
        "botfmt.day_title",
        date=short_date(moment, lang),
        weekday=weekday_name(moment.weekday(), lang),
    )


def number(value: Any, lang: str = i18n.DEFAULT_LANG) -> str:
    """1234567 → "1 234 567" — katta raqam o'qiladigan bo'lsin.

    Minglik ajratgich tildan: o'zbek va rus yozuvida probel, inglizchada
    vergul.  Vergul o'zbekchada kasr belgisi — "1,234" boshqa son.
    """
    try:
        grouped = f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)
    return grouped.replace(",", tg(lang, "format.number.group"))


def decimal(value: Any, lang: str = i18n.DEFAULT_LANG, *, digits: int = 1) -> str:
    """3.2 → "3,2", 2.0 → "2" — kasr belgisi tildan, ortiqcha nol yo'q.

    Panelning `formatNumber` bilan bir xil yozuv: ilgari bot "3.2",
    panel "3,2" deb yozardi va bitta mijoz ikki xil sonni ko'rardi.
    """
    try:
        text = f"{float(value):.{digits}f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(value)
    whole, _, fraction = text.partition(".")
    result = number(whole, lang)
    if fraction:
        result += tg(lang, "format.number.decimal") + fraction
    return result


def duration(seconds: float, lang: str = i18n.DEFAULT_LANG) -> str:
    """ "5 daq" yoki "40 s" — qisqa davomiylik (dwell uchun)."""
    if seconds >= 60:
        return tg(lang, "botfmt.unit.min", count=int(seconds // 60))
    return tg(lang, "botfmt.unit.sec", count=int(seconds))


def minutes_label(total_minutes: int, lang: str = i18n.DEFAULT_LANG) -> str:
    """154 → "2 soat 34 daq", 40 → "40 daq" — jami kechikish uchun."""
    hours, minutes = divmod(int(total_minutes), 60)
    if hours:
        return tg(lang, "botfmt.unit.hours_minutes", hours=hours, minutes=minutes)
    return tg(lang, "botfmt.unit.min", count=minutes)


def sparkline(values: Sequence[float]) -> str:
    """Qiymatlar qatori → "▁▂▅█▃" blok-grafik.

    Hammasi nol bo'lsa bo'sh satr qaytadi — "tekis chiziq" ko'rsatishdan
    foyda yo'q.
    """
    peak = max(values, default=0)
    if peak <= 0:
        return ""
    line = ""
    for value in values:
        index = 0 if value <= 0 else max(1, round(value / peak * (len(_BARS) - 1)))
        line += _BARS[index]
    return line


def camera_name(camera_id: str, labels: Optional[Mapping[str, Any]] = None) -> str:
    """`camera-03` → "Kirish kamerasi" (konfigda nom bo'lsa)."""
    if labels:
        label = str(labels.get(camera_id) or "").strip()
        if label:
            return label
    return camera_id


def header(site_name: Any, *, icon: str = "") -> str:
    prefix = f"{icon} " if icon else ""
    return f"{prefix}<b>{escape(site_name)}</b>"


def alert_buttons(
    base_url: str, *, speak_phrase: str = "", lang: str = i18n.DEFAULT_LANG
) -> Dict[str, Any]:
    """Ogohlantirish ostidagi tugmalar.

    `speak_phrase` berilsa — «Ovoz bering»: do'kon karnayi darhol
    gapiradi.  Bu Verisure'ning "Intervene" bosqichi, faqat qo'riqchisiz:
    egasi telefonidan bosadi va do'konda HOZIR bo'ladi.

    «Ko'rdim» ataylab bor: egasi javob berganini bilmasak, uni bir xil
    hodisa bilan qayta-qayta bezovta qilamiz.
    """
    from chaqimchi_ai import announcements

    rows = []
    item = announcements.BY_CODE.get(speak_phrase)
    if item:
        rows.append([{"text": item.button, "callback_data": f"speak:{item.code}"}])
    rows.append([{"text": tg(lang, "botfmt.button.ack"), "callback_data": "ack"}])
    if base_url:
        rows.append(
            [
                {
                    "text": tg(lang, "botfmt.button.panel"),
                    "web_app": {"url": f"{base_url.rstrip('/')}/owner"},
                }
            ]
        )
    return {"inline_keyboard": rows}


def panel_button(base_url: str, lang: str = i18n.DEFAULT_LANG) -> Dict[str, Any]:
    """Telegram ichida haqiqiy Mini App sifatida owner panelini ochadi."""
    return {
        "inline_keyboard": [
            [
                {
                    "text": tg(lang, "botfmt.button.panel"),
                    "web_app": {"url": f"{base_url.rstrip('/')}/owner"},
                }
            ]
        ]
    }
