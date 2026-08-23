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
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

TASHKENT = ZoneInfo("Asia/Tashkent")

#: Blok-grafik pog'onalari (bo'sh joy — nol uchun).
_BARS = " ▁▂▃▄▅▆▇█"

_MONTHS = ("yan", "fev", "mar", "apr", "may", "iyn", "iyl", "avg", "sen", "okt", "noy", "dek")

_WEEKDAYS = ("Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba")


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


def stamp(value: Any) -> str:
    """ "17:32, 17-avg" — soat va sana."""
    moment = to_tashkent(value)
    if not moment:
        return ""
    return f"{moment:%H:%M}, {moment.day}-{_MONTHS[moment.month - 1]}"


def day_title(value: Any) -> str:
    """ "17-avg, Yakshanba" — hisobot sarlavhasi uchun."""
    moment = to_tashkent(value)
    if not moment:
        return str(value)
    return f"{moment.day}-{_MONTHS[moment.month - 1]}, {_WEEKDAYS[moment.weekday()]}"


def number(value: Any) -> str:
    """1234567 → "1 234 567" — katta raqam o'qiladigan bo'lsin."""
    try:
        return f"{int(value):,}".replace(",", " ")
    except (TypeError, ValueError):
        return str(value)


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


def alert_buttons(base_url: str, *, speak_phrase: str = "") -> Dict[str, Any]:
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
    rows.append([{"text": "✅ Ko'rdim", "callback_data": "ack"}])
    if base_url:
        rows.append(
            [{"text": "📊 Panelda ochish", "web_app": {"url": f"{base_url.rstrip('/')}/owner"}}]
        )
    return {"inline_keyboard": rows}


def panel_button(base_url: str) -> Dict[str, Any]:
    """Telegram ichida haqiqiy Mini App sifatida owner panelini ochadi."""
    return {
        "inline_keyboard": [
            [{"text": "📊 Panelda ochish", "web_app": {"url": f"{base_url.rstrip('/')}/owner"}}]
        ]
    }
