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
EVENT_LABELS: Dict[str, str] = {
    "person_detected": "Odam aniqlandi",
    "employee_seen": "Xodim ko'rindi",
    "face_captured": "Yuz kadri (davomat)",
    "zone_entered": "Taqiqlangan zonaga kirish",
    "loitering": "Uzoq turish",
    "occupancy_exceeded": "Bandlik chegarasi oshdi",
    "line_crossed": "Kirish/chiqish",
    "dwell_exceeded": "Zonada uzoq turdi",
    "queue_threshold_exceeded": "Navbat uzun",
    # Detektor odamni topadi, kassirni emas — matn ham shunga mos:
    # "kassada hech kim yo'q" o'lchanadigan fakt, "kassir ketdi" taxmin.
    "checkout_unattended": "Kassada hech kim yo'q",
    "checkout_second_till": "Ikkinchi kassani oching",
    # "Bo'sh" emas, "bo'shab qolgan": o'lchanadigan narsa — javondagi
    # o'zgarish, mahsulotning aniq soni emas.
    "shelf_empty": "Javon bo'shab qolgan",
    "after_hours_presence": "Ish vaqtidan tashqari harakat",
    "camera_tampered": "Kamera yopildi yoki burildi",
    # Sog'liq hodisalari do'kon egasi uchun aniq tilda: u nima buzilganini
    # emas, **nima qilish kerakligini** bilishi kerak.
    "camera_offline": "Kamera javob bermayapti",
    "camera_recovered": "Kamera tiklandi",
    "stream_frozen": "Kamera tasviri qotib qoldi",
    "ai_review": "AI ko'rdi",
}

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


def event_label(event_type: str) -> str:
    return EVENT_LABELS.get(event_type, event_type)


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
) -> str:
    """Ruxsat berilgan eventlardan bitta o'qiladigan xabar.

    Qatorlar soni bo'yicha emas, **hodisa soni** bo'yicha tartiblanadi: eng
    ko'p takrorlangan muammo birinchi turadi.  Uslub `cloud/botfmt.py`da:
    do'kon nomi sarlavhada, kamera odam o'qiydigan nomi bilan, vaqt
    Toshkentcha.
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
            title += f" — {total} ta ogohlantirish"
    else:
        title = f"{head} {total} ta ogohlantirish"
    lines = [title]
    ordered = sorted(groups.items(), key=lambda item: (-item[1], item[0]))
    for (event_type, camera_id), count in ordered[:MAX_LINES]:
        suffix = f" ×{count}" if count > 1 else ""
        camera = botfmt.escape(botfmt.camera_name(camera_id, camera_labels))
        when = f" · {latest[(event_type, camera_id)]}" if (event_type, camera_id) in latest else ""
        lines.append(f"• {event_label(event_type)} — {camera}{suffix}{when}")
        note = notes.get((event_type, camera_id))
        if note:
            lines.append(f"   ↳ {note}")
    if len(ordered) > MAX_LINES:
        lines.append(f"• va yana {len(ordered) - MAX_LINES} ta turdagi hodisa")
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
) -> Optional[str]:
    """Batchdan yuboriladigan bitta xabar — yoki hech narsa.

    Tormoz shu yerda qo'llanadi: bir xil (tur, kamera) juftligi oynada
    allaqachon yuborilgan bo'lsa, uning **hamma** eventlari xabardan tushadi.
    """
    allowed = select_alert_events(site_id, events, throttle_service=throttle_service, level=level)
    if not allowed:
        return None
    return summarize(allowed)
