"""Mijozga Telegram xabarini yig'ib, tormozlab yuborish.

Bungacha har `warning`/`critical` event uchun alohida xabar ketardi. Bitta
batch 500 tagacha event ko'taradi, obyektda esa bir necha a'zo bo'ladi — ya'ni
bitta so'rov 1500 tagacha Telegram chaqiruvini tug'dirardi. Telegram sekundiga
~30 tasini qabul qiladi, qolganida bot cheklanadi va **hech kim** xabar olmay
qoladi. Ya'ni ko'p xabar yuborish aslida xabarni butunlay yo'qotish edi.

Endi ikki qoida ishlaydi:

1. Bitta batch — bitta xabar (turlar bo'yicha yig'ib).
2. Bitta (obyekt, tur, kamera) uchligi uchun 10 daqiqada bir marta. Kamera
   soatlab bir xil ogohlantirishni qaytarsa mijoz telefonini o'chirib qo'ymaydi.

Tormoz xotirada — jarayon qayta ishga tushsa birinchi xabar o'tadi. Ogohlantirish
uchun bu to'g'ri tomonga xato qilish: kechikkanidan ko'ra takrorlangani yaxshi.
"""

from __future__ import annotations

import threading
import time
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from chaqimchi_ai.event_models import EdgeEvent
from cloud import i18n

#: Bir xil ogohlantirish shuncha soniyada bir martadan ko'p yuborilmaydi.
DEFAULT_THROTTLE_SEC = 600

#: Xabarga sig'adigan tur soni — qolgani "va yana N ta" bo'lib qisqaradi.
MAX_LINES = 6

#: MINIMAL rejim (foydalanuvchi qarori, 2026-08-16): botga faqat KRITIK
#: hodisalar boradi — kamera buzilishi/o'chishi, tungi harakat, taqiqlangan
#: zona.  Navbat va loitering kabi `warning` hodisalar faqat panelda
#: ko'rinadi; ular botga oqsa mijoz botni o'chirib qo'yadi va keyin haqiqiy
#: xavfni ham o'tkazib yuboradi.
ALERT_SEVERITIES = frozenset({"critical"})

#: Obyekt sozlamasidagi `telegram_min_severity` qiymatlari.
#:
#: Minimal rejim standart bo'lib qoladi, lekin endi u QULF emas: 2026-08-26
#: da sinov do'konida 449 hodisadan 9 tasi botga bordi va ega "bot buzilgan"
#: deb o'yladi — chunki bu tanlov hech qayerda aytilmagan edi.  Endi u
#: panelda ko'rinadi va egasi o'zi qaror qiladi.
TELEGRAM_SEVERITY_LEVELS: Dict[str, frozenset] = {
    "critical": frozenset({"critical"}),
    "warning": frozenset({"critical", "warning"}),
    "all": frozenset({"critical", "warning", "info"}),
}

#: Sozlama yo'q yoki noma'lum bo'lsa — hozirgi xatti-harakat.
DEFAULT_TELEGRAM_LEVEL = "critical"


def severities_for(level: Optional[str]) -> frozenset:
    """Tanlangan darajaga mos severity to'plami."""
    return TELEGRAM_SEVERITY_LEVELS.get(
        str(level or "").strip().lower(), TELEGRAM_SEVERITY_LEVELS[DEFAULT_TELEGRAM_LEVEL]
    )


#: "Buzildi" xabarining "tiklandi" jufti — severity past bo'lsa ham boradi.
#: Usiz mijoz faqat muammolarni ko'rar, tizim o'zini "doim buzuq" qilib
#: ko'rsatar edi.
RECOVERY_EVENTS = frozenset({"camera_recovered"})

#: Mijoz `zone_entered` ni tushunmaydi; xabar odam tilida bo'lishi kerak.
#:
#: Matnlar 2026-09-07 da `i18n/{uz,ru,en}.json` ga ko'chirildi — kalit
#: `event.<tur>`.  Nega: bir xil nom panelda ham, Telegramda ham, CSV'da
#: ham chiqadi va u endi uch tilda kerak.  Ro'yxat shu yerda qolsa,
#: tarjima ikkinchi nusxaga aylanardi.
#:
#: Yangi hodisa turi qo'shsangiz katalogga ham qo'shing:
#: `tests/test_i18n_catalogue.py` har `EventType` uchun kalit borligini
#: tekshiradi va unutilgan turni darhol ko'rsatadi.


#: Qurilma qaysi hodisaga rasm/klip ILADI.
#:
#: Haqiqiy manba — `chaqimchi_ai/retail/pipeline.py: SECURITY_MEDIA_EVENTS`,
#: lekin `cloud` uni import qila olmaydi: o'sha modul `cv2` va `numpy`
#: tortadi va ular serverda o'rnatilmagan.  Shuning uchun ro'yxat shu
#: yerda TAKRORLANADI, tenglik esa test bilan qulflanadi
#: (`tests/test_media_policy_contract.py`).
#:
#: Panelga bu nima uchun kerak: rasmi yo'q kartochka "rasm hali
#: yuklanmagan" deb turishi mumkin, holbuki bu turdagi hodisaga rasm
#: umuman OLINMAYDI.  Ikkalasi bir xil ko'rinishi — ega uchun jimgina
#: yolg'on.
MEDIA_EVENT_TYPES = frozenset(
    {"camera_tampered", "after_hours_presence", "zone_entered"}
)

#: AI izohi shuncha belgidan uzun bo'lsa qisqartiriladi.  Telegram xabari
#: telefonda bir qarashda o'qiladigan bo'lishi kerak.
MAX_NOTE_CHARS = 160


def event_label(event_type: str, lang: str = i18n.DEFAULT_LANG) -> str:
    """Hodisa turining odam o'qiydigan nomi.

    Katalogda kalit bo'lmasa turning O'ZI qaytadi (`ai_review` kabi
    yangi tur qo'shilib, tarjimasi unutilgan holat): panelda xom kod
    ko'rinadi, lekin bo'sh joy qolmaydi va hodisa yo'qolmaydi.
    """
    key = f"event.{event_type}"
    label = i18n.tg(lang, key)
    return event_type if label == key else label


def event_note(event: EdgeEvent) -> Optional[str]:
    """Hodisaning odam o'qiydigan izohi — hozircha faqat AI xulosasi.

    Qolgan turlar uchun tur nomi va kamera yetarli ("Navbat uzun — kassa-01").
    `ai_review` esa aynan **matn** uchun mavjud: usiz xabar "AI ko'rdi —
    kassa-01" bo'lib qolardi va do'kon egasiga hech narsa aytmasdi.
    """
    if event.event_type != "ai_review":
        return None
    metadata = event.metadata or {}
    text = str(metadata.get("sabab") or metadata.get("tavsif") or "").strip()
    if not text:
        return None
    if len(text) > MAX_NOTE_CHARS:
        text = text[: MAX_NOTE_CHARS - 1].rstrip() + "…"
    return text


class AlertThrottle:
    """(obyekt, tur, kamera) bo'yicha takroriy xabarni to'sadi."""

    def __init__(self, window_sec: int = DEFAULT_THROTTLE_SEC) -> None:
        self.window_sec = window_sec
        self._sent: Dict[Tuple[str, str, str], float] = {}
        self._lock = threading.Lock()

    def allow(self, site_id: str, event_type: str, camera_id: str) -> bool:
        key = (site_id, event_type, camera_id)
        now = time.monotonic()
        with self._lock:
            last = self._sent.get(key)
            if last is not None and now - last < self.window_sec:
                return False
            self._sent[key] = now
            # Muddati o'tgan yozuvlar kerak emas — xotira o'smasin.
            if len(self._sent) > 10_000:
                self._sent = {
                    stored_key: stamp
                    for stored_key, stamp in self._sent.items()
                    if now - stamp < self.window_sec
                }
            return True

    def reset(self) -> None:
        with self._lock:
            self._sent.clear()


_throttle = AlertThrottle()


def throttle() -> AlertThrottle:
    return _throttle


def summarize(
    events: Sequence[EdgeEvent],
    *,
    site_name: Optional[str] = None,
    camera_labels: Optional[Dict[str, str]] = None,
    lang: str = i18n.DEFAULT_LANG,
) -> str:
    """Ruxsat berilgan eventlardan bitta o'qiladigan xabar.

    Qatorlar soni bo'yicha emas, **hodisa soni** bo'yicha tartiblanadi: eng
    ko'p takrorlangan muammo birinchi turadi.  Uslub `cloud/botfmt.py`da:
    do'kon nomi sarlavhada, kamera odam o'qiydigan nomi bilan, vaqt
    Toshkentcha.

    `lang` — QABUL QILUVCHINING tili, aniq uzatiladi.  Xabar fon
    vazifasida yasaladi (`BackgroundTasks`), u so'rov kontekstini meros
    oladi — ya'ni `i18n.t()` bu yerda qurilmaning emas, hech kimning
    tilini berardi.  Bir batch bir necha a'zoga ketadi: chaqiruvchi har
    til uchun alohida chaqiradi.
    """
    from cloud import botfmt

    groups: Dict[Tuple[str, str], int] = {}
    notes: Dict[Tuple[str, str], str] = {}
    latest: Dict[Tuple[str, str], str] = {}
    critical = 0
    for event in events:
        key = (event.event_type, event.camera_id)
        groups[key] = groups.get(key, 0) + 1
        if event.severity == "critical":
            critical += 1
        moment = botfmt.clock(event.occurred_at)
        if moment:
            latest[key] = moment
        # Birinchi izoh saqlanadi: takrorlangan hodisada eng eskisi
        # muammoning boshlanishini ko'rsatadi.
        note = event_note(event)
        if note and key not in notes:
            notes[key] = note

    head = "🔴" if critical else "⚠️"
    total = sum(groups.values())
    if site_name:
        title = botfmt.header(site_name, icon=head)
        if total > 1:
            title = i18n.tg(lang, "notify.title.site", header=title, count=total)
    else:
        title = i18n.tg(lang, "notify.title.plain", icon=head, count=total)
    lines = [title]
    ordered = sorted(groups.items(), key=lambda item: (-item[1], item[0]))
    for (event_type, camera_id), count in ordered[:MAX_LINES]:
        suffix = f" ×{count}" if count > 1 else ""
        camera = botfmt.escape(botfmt.camera_name(camera_id, camera_labels))
        when = f" · {latest[(event_type, camera_id)]}" if (event_type, camera_id) in latest else ""
        # Qator shakli katalogda emas: undagi yagona so'zlar hodisa nomi
        # (`event.*`) va kamera nomi, qolgani belgi — tarjima qiladigan
        # narsa yo'q.
        lines.append(f"• {event_label(event_type, lang)} — {camera}{suffix}{when}")
        note = notes.get((event_type, camera_id))
        if note:
            lines.append(f"   ↳ {note}")
    if len(ordered) > MAX_LINES:
        lines.append(i18n.tg(lang, "notify.more_types", count=len(ordered) - MAX_LINES))
    return "\n".join(lines)


def select_alert_events(
    site_id: str,
    events: Iterable[EdgeEvent],
    *,
    throttle_service: Optional[AlertThrottle] = None,
    level: Optional[str] = None,
) -> List[EdgeEvent]:
    """Batchdan botga chiqishi kerak bo'lgan hodisalar — tormoz bilan.

    Rasmli alert uchun tanlash matndan ajratildi: chaqiruvchi avval
    ro'yxatni oladi, snapshot kutadi, keyin matn/rasm yasaydi.
    """
    limiter = throttle_service or _throttle
    alerts = [event for event in events if wants_telegram(event, level)]
    if not alerts:
        return []
    seen: Dict[Tuple[str, str], bool] = {}
    allowed: List[EdgeEvent] = []
    for event in alerts:
        key = (event.event_type, event.camera_id)
        if key not in seen:
            seen[key] = limiter.allow(site_id, event.event_type, event.camera_id)
        if seen[key]:
            allowed.append(event)
    return allowed


def wants_telegram(event: EdgeEvent, level: Optional[str] = None) -> bool:
    """Hodisa botga yuborilsinmi.

    Ikki qatlam:

    1. Qurilma qoidasi (`rules.yaml` dagi `telegram_alert` harakati) —
       hodisa `metadata.alert` bayrog'i bilan keladi va bayroq yakuniy
       so'zga ega: qoida Telegram so'ramagan bo'lsa, severity qanday
       bo'lmasin xabar ketmaydi.
    2. Obyekt darajasi (`telegram_min_severity`, standart `critical`):
       bayroq bilan ham faqat tanlangan darajadagi hodisalar boradi.
       Standartda `warning` hodisalar panelda qoladi — ular botga oqsa
       mijoz botni o'chirib qo'yadi va keyin haqiqiy xavfni ham
       o'tkazib yuboradi.  Ega buni panelda o'zgartira oladi.

    Eski qurilma versiyalari bayroq yubormaydi — ular uchun faqat
    severity qaraladi.

    "Tiklandi" juftlari darajadan QAT'I NAZAR boradi: "buzildi" xabarini
    olgan mijoz "tuzaldi" xabarini ham olishi kerak.
    """
    allowed = severities_for(level)
    metadata = event.metadata or {}
    if "alert" in metadata:
        if not metadata.get("alert"):
            return False
        return event.severity in allowed or event.event_type in RECOVERY_EVENTS
    return event.severity in allowed or event.event_type in RECOVERY_EVENTS


def build_alert(
    site_id: str,
    events: Iterable[EdgeEvent],
    *,
    throttle_service: Optional[AlertThrottle] = None,
    level: Optional[str] = None,
    lang: str = i18n.DEFAULT_LANG,
) -> Optional[str]:
    """Batchdan yuboriladigan bitta xabar — yoki hech narsa.

    Tormoz shu yerda qo'llanadi: bir xil (tur, kamera) juftligi oynada
    allaqachon yuborilgan bo'lsa, uning **hamma** eventlari xabardan tushadi.
    """
    allowed = select_alert_events(site_id, events, throttle_service=throttle_service, level=level)
    if not allowed:
        return None
    return summarize(allowed, lang=lang)
