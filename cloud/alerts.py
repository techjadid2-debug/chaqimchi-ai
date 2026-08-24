"""Telegram ogohlantirishlari — mijoz tizimi o‘chganda o‘zi xabar beradi.

Panelda aloqa holati ko‘rinadi (7.9), lekin uni ko‘rish uchun panelni ochish
kerak. Kunda bir marta ochilsa ham, do‘kon ertalab soat 9 da o‘chsa siz buni
kechqurun bilasiz. Shuning uchun cloud o‘zi Telegramga yozadi.

**Faqat holat o‘zgarganda** xabar ketadi (`alert_state` jadvali) — aks holda
har 15 daqiqada o‘sha xabar takrorlanib, siz uni o‘qishni tashlab qo‘yasiz.

Bu modul (va saytdan kelgan arizalar) **sotuv boti** orqali yozadi —
mijozlarga hisobot yuboradigan botdan alohida.  Sabab oddiy: ikkalasi bitta
botdan kelsa, ega uchun "yangi ariza" va "do'kon hisoboti" bir chatda
aralashib ketadi va ikkalasi ham e'tibordan qoladi.

Yoqish:

```bash
export CHAQIMCHI_SALES_TELEGRAM_TOKEN="123456:ABC..."   # sotuv boti
export CHAQIMCHI_CLOUD_TELEGRAM_CHAT_ID="-1001234567890"
make run-cloud
```

Ikkalasi ham bo‘lmasa modul jim turadi — cloud oddiy ishlashda davom etadi.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

#: Aloqa nazorati qanchalik tez-tez tekshiriladi (standart 15 daqiqa).
DEFAULT_INTERVAL_SEC = 900

#: Server diski shu foizdan oshsa admin ogohlantiriladi.  Pastga qaytish
#: chegarasi ataylab boshqa (histerezis) — 84.9/85.1 atrofida tebranish
#: har 15 daqiqada xabar/tiklandi juftini yubormasin.
DISK_ALERT_PERCENT = 85
DISK_OK_PERCENT = 80

#: `alert_state` jadvalida server ogohlantirishlari shu soxta sayt ID
#: ostida yuritiladi — jadval sxemasini o'zgartirmasdan.
SERVER_SITE_ID = "__server__"

#: Yangi ochilgan mijoz shu muddat ichida juftlanmasa — ogohlantiriladi.
#: Pairing kod 48 soat amal qiladi; shundan oldin xabar berish erta bo‘lardi
#: (o‘rnatuvchi hali yo‘lda).
PAIRING_GRACE_HOURS = 48

#: Ogohlantirish talab qiladigan holatlar.
PROBLEM_STATES = ("offline", "not_paired", "silent")

#: Qurilma shuncha soatdan ko'p jim qolsa — bu qisqa uzilish emas.
#:
#: `stale` (1-24 soat) ataylab jim edi: internetning bir-ikki daqiqalik
#: uzilishi odatiy hol va har safar xabar yuborish shovqin bo'lardi.
#: Lekin oraliq juda keng olingan — 23 soat jim turgan do'kon ham
#: "stale" bo'lib, HECH QANDAY ogohlantirish bermasdi.
#:
#: Jonli holat (2026-08-22): do'kon kompyuteri 05:38 da o'chgan va
#: 10 soatdan ko'p jim turgan — do'kon 08:30 da ochilgan bo'lsa ham.
#: Buni na mijoz, na biz bildik.
#:
#: Uch soat — "internet uzildi" bilan "kompyuter o'chgan" ni ajratadigan
#: chegara.  Kechasi ham xabar beriladi: tungi kuzatuv mahsulotning
#: asosiy qiymati, ya'ni o'chgan kompyuter kechasi ham muammo.
SILENT_ALERT_HOURS = 3

#: Qurilma shuncha kun bir xil versiyada qolsa — yangilanish qotib qolgan.
#:
#: Yangilash vazifasi har 15 daqiqada ishlaydi, ya'ni sog'lom do'kon
#: reliz chiqqan kuni yangilanadi.  Ikki kun — sekin internet va tunda
#: o'chirilgan kompyuter uchun ham yetarli zaxira.
#:
#: Jonli holat (2026-08-22): do'kon 0.6.8 da qolgan, bulut 0.6.12
#: taklif qilyapti — uch reliz o'tib ketgan.  Sababi qurilmadagi
#: `local/updater.py`: oldingi yangilanish taqdiri aniqlanmasa u
#: MUDDATSIZ "kutish" holatida qoladi va yangi versiyani umuman
#: tekshirmaydi.  Ya'ni tuzatishni qurilmaga yubora olmaymiz — u aynan
#: yangilanmayapti.  Shu sabab aniqlash BULUT tomonida.
UPDATE_STUCK_DAYS = 2


def is_silent(site: Dict[str, Any]) -> bool:
    """Sayt `SILENT_ALERT_HOURS` dan uzoq jim turibdimi.

    `stale` oralig'i (1-24 soat) juda keng: uning boshi odatiy internet
    uzilishi, oxiri esa o'chgan kompyuter.  Bu funksiya ikkisini ajratadi.

    Ikki xil ishlatiladi: aloqa xabarini YUBORISH uchun, va kamera /
    sog'liq xabarlarini SUSTLASH uchun — jim qurilmada ular ham jim, ya'ni
    bitta muammo haqida uchta xabar ketardi.
    """
    if site.get("connection") != "stale":
        return False
    minutes = site.get("minutes_since_seen")
    return isinstance(minutes, int) and minutes >= SILENT_ALERT_HOURS * 60


STATE_LABEL = {
    "online": "ishlayapti",
    "stale": "aloqa uzilgan",
    "offline": "ishlamayapti",
    "not_paired": "juftlanmagan",
}


@dataclass
class AlertConfig:
    token: Optional[str] = None
    chat_id: Optional[str] = None
    interval_sec: int = DEFAULT_INTERVAL_SEC

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    @staticmethod
    def from_env() -> "AlertConfig":
        raw_interval = os.environ.get("CHAQIMCHI_CLOUD_ALERT_INTERVAL_SEC", "").strip()
        try:
            interval = int(raw_interval) if raw_interval else DEFAULT_INTERVAL_SEC
        except ValueError:
            logger.warning("CHAQIMCHI_CLOUD_ALERT_INTERVAL_SEC son emas — standart qiymat")
            interval = DEFAULT_INTERVAL_SEC
        return AlertConfig(
            # Ichki xabarlar (arizalar va qurilma aloqasi) **sotuv boti**dan
            # ketadi: aks holda ular mijoz botidagi hisobotlar bilan bitta
            # chatda aralashib, ikkalasi ham o'qilmay qolardi.  Sotuv boti
            # sozlanmagan bo'lsa eski xatti-harakat saqlanadi.
            token=(
                os.environ.get("CHAQIMCHI_SALES_TELEGRAM_TOKEN", "").strip()
                or os.environ.get("CHAQIMCHI_CLOUD_TELEGRAM_TOKEN", "").strip()
                or os.environ.get("CHAQIMCHI_OWNER_TELEGRAM_TOKEN", "").strip()
                or None
            ),
            chat_id=os.environ.get("CHAQIMCHI_CLOUD_TELEGRAM_CHAT_ID", "").strip() or None,
            interval_sec=max(60, interval),
        )


@dataclass
class Alert:
    """Bitta yuboriladigan xabar."""

    site_id: str
    state: str
    text: str
    #: `alert_state` ga yoziladigan qiymat. `None` — yozuvni o‘chirish.
    remember: Optional[str]
    #: Ogohlantirish turi — har biri mustaqil kuzatiladi.
    kind: str = "connection"
    #: To'ldirilgan bo'lsa do'kon EGASIGA ham shu matn yuboriladi.
    #:
    #: Ichki chatdagi xabar texnik ("temperature_c 91"), egaga esa u
    #: hech narsa aytmaydi.  Shuning uchun ikkinchi, sodda matn —
    #: va faqat egasi O'ZI hal qila oladigan muammolar uchun.
    owner_text: Optional[str] = None


@dataclass
class AlertRun:
    """Bitta tekshiruv natijasi — `GET /api/v1/admin/alerts` shuni ko‘rsatadi."""

    checked: int = 0
    sent: int = 0
    failed: int = 0
    ran_at: Optional[str] = None
    messages: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checked": self.checked,
            "sent": self.sent,
            "failed": self.failed,
            "ran_at": self.ran_at,
            "messages": self.messages,
        }


def _since_label(minutes: Optional[int]) -> str:
    if minutes is None:
        return "hech qachon"
    if minutes < 60:
        return f"{minutes} daqiqa oldin"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} soat oldin"
    return f"{hours // 24} kun oldin"


def _silent_label(minutes: Optional[int]) -> str:
    """«10 soatdan beri» — davomiylik, «oldin» emas.

    `_since_label` voqea nuqtasini bildiradi ("oxirgi aloqa 10 soat
    oldin"); jim qolish esa davom etayotgan holat.
    """
    if minutes is None:
        return "boshidan beri"
    if minutes < 60:
        return f"{minutes} daqiqadan beri"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} soatdan beri"
    return f"{hours // 24} kundan beri"


def _site_age_hours(created_at: Optional[str], now: datetime) -> Optional[float]:
    if not created_at:
        return None
    try:
        created = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return (now - created).total_seconds() / 3600


def _problem_text(site: Dict[str, Any]) -> str:
    name = site.get("name", "?")
    phone = site.get("contact_phone")
    plan = str(site.get("plan", "")).capitalize()
    tail = f"\n📞 {phone}" if phone else ""

    if site["connection"] == "not_paired":
        return (
            f"⚠️ <b>{name}</b> — o‘rnatish tugallanmagan\n"
            f"Qurilma juftlanmagan (tarif: {plan}).\n"
            f"O‘rnatuvchi bilan bog‘laning.{tail}"
        )
    if site["connection"] == "stale":
        # Bu yerga faqat `SILENT_ALERT_HOURS` dan uzoq jim turgan qurilma
        # tushadi — qisqa uzilish bu yergacha yetib kelmaydi.
        return (
            f"🟠 <b>{name}</b> — {_silent_label(site.get('minutes_since_seen'))} jim\n"
            f"Hodisa ham, kamera holati ham kelmayapti (tarif: {plan}).\n"
            f"Do‘kon kompyuteri yoqilganini tekshiring.{tail}"
        )
    return (
        f"🔴 <b>{name}</b> — tizim ishlamayapti\n"
        f"Oxirgi aloqa: {_since_label(site.get('minutes_since_seen'))} "
        f"(tarif: {plan}).\n"
        f"Tok, internet yoki Mini PC ni tekshiring.{tail}"
    )


def owner_down_text(site: Dict[str, Any]) -> Optional[str]:
    """Do'kon egasiga: kuzatuv to'xtaganini FAQAT bulut ayta oladi.

    `camera_offline` xabarini qurilmaning o'zi yuboradi.  Kompyuter
    o'chgan bo'lsa u hech narsa yubora olmaydi — ya'ni aynan eng yomon
    holatda egasi hech narsa bilmaydi.  Bu bo'shliqni faqat shu yerdan
    to'ldirish mumkin.

    `None` — bu holat egasiga tegishli emas (masalan juftlanmagan yangi
    sayt: bu bizning o'rnatish ishimiz, mijozniki emas).
    """
    if site.get("connection") == "stale":
        return (
            f"🔴 <b>Kuzatuv to'xtadi</b>\n"
            f"Do'kon kompyuteri {_silent_label(site.get('minutes_since_seen'))} "
            f"javob bermayapti — kameralar yozilmayapti.\n"
            f"Kompyuter yoqilganini va internet borligini tekshiring."
        )
    if site.get("connection") == "offline":
        return (
            f"🔴 <b>Kuzatuv to'xtadi</b>\n"
            f"Tizimdan {_since_label(site.get('minutes_since_seen'))} xabar yo'q — "
            f"kameralar yozilmayapti.\n"
            f"Kompyuter yoqilganini va internet borligini tekshiring."
        )
    return None


def owner_recovery_text() -> str:
    return "✅ <b>Kuzatuv tiklandi</b>\nKameralar yana yozmoqda."


def _update_stuck_text(site: Dict[str, Any], version: str, latest: str, days: int) -> str:
    phone = site.get("contact_phone")
    tail = f"\n📞 {phone}" if phone else ""
    return (
        f"🧊 <b>{site.get('name', '?')}</b> — yangilanish yetib bormayapti\n"
        f"Do‘konda {version}, yangi versiya {latest}.\n"
        f"{days} kundan beri o‘zgarmagan (kanal: avto).\n"
        f"Do‘kon kompyuteridagi yangilash vazifasini tekshiring.{tail}"
    )


def _update_recovery_text(site: Dict[str, Any], version: str) -> str:
    return f"✅ <b>{site.get('name', '?')}</b> — yangilandi ({version})."


def _recovery_text(site: Dict[str, Any]) -> str:
    return f"✅ <b>{site.get('name', '?')}</b> — qayta ishga tushdi\nAloqa tiklandi."


def _camera_text(site: Dict[str, Any]) -> str:
    active = site.get("cameras_active", 0)
    expected = site.get("cameras_expected", 0)
    phone = site.get("contact_phone")
    tail = f"\n📞 {phone}" if phone else ""
    lost = expected - active
    return (
        f"📹 <b>{site.get('name', '?')}</b> — {lost} ta kamera ishlamayapti\n"
        f"{expected} tadan {active} tasi ulangan.\n"
        f"Kamera tokini, tarmoq kabelini yoki RTSP manzilini tekshiring.{tail}"
    )


def _camera_recovery_text(site: Dict[str, Any]) -> str:
    return (
        f"✅ <b>{site.get('name', '?')}</b> — kameralar tiklandi\n"
        f"Barcha {site.get('cameras_expected', 0)} kamera ishlayapti."
    )


def plan_camera_alerts(
    sites: List[Dict[str, Any]], previous: Dict[str, str]
) -> Tuple[List[Alert], List[str]]:
    """Kamera yo‘qolganini aniqlaydi.

    Mijoz 3 kamerali tarif uchun pul to‘lab, bittasi o‘chib qolsa — tizim
    “ishlayapti” bo‘lib turadi va buni hech kim sezmaydi. Bu jimgina buzilish
    aloqa uzilishidan ham xavfliroq: mijoz o‘zi ham bilmaydi.

    Faqat aloqasi bor saytlar tekshiriladi — tizim butunlay o‘chgan bo‘lsa
    kameralar haqida alohida yozish shovqin (aloqa ogohlantirishi allaqachon
    ketgan).
    """
    alerts: List[Alert] = []
    forget: List[str] = []

    for site in sites:
        site_id = site["id"]
        prev = previous.get(site_id)

        watched = (
            site.get("license_status") in ("active", "grace")
            and site.get("connection") in ("online", "stale")
            # Jim qurilma haqida aloqa xabari allaqachon ketgan.
            and not is_silent(site)
        )
        if not watched:
            if prev is not None:
                forget.append(site_id)
            continue

        expected = int(site.get("cameras_expected") or 0)
        active = int(site.get("cameras_active") or 0)
        if not expected:
            continue

        # Holat ataylab sonsiz ("missing:2" emas, shunchaki "missing"):
        # 2 kamera -> 1 kamera -> 2 kamera tebranishi har 15 daqiqada
        # yangi xabar tug'dirardi.  Nechta yo'qolgani xabar matnida
        # baribir yoziladi; qayta xabar esa faqat to'liq tiklangandan
        # keyingi yangi yo'qolishda ketadi.
        state = "ok" if active >= expected else "missing"

        if state == "missing":
            if prev != state:
                alerts.append(
                    Alert(site_id, state, _camera_text(site), remember=state, kind="cameras")
                )
        elif prev is not None:
            alerts.append(
                Alert(site_id, state, _camera_recovery_text(site), remember=None, kind="cameras")
            )

    return alerts, forget


def plan_update_stuck_alerts(
    sites: List[Dict[str, Any]],
    versions_by_site: Dict[str, Dict[str, Any]],
    latest_version: Optional[str],
    previous: Dict[str, str],
    *,
    now: Optional[datetime] = None,
) -> Tuple[List[Alert], List[str]]:
    """Yangilanish qurilmaga yetib bormayotganini aniqlaydi.

    Buni FAQAT bulut ko'ra oladi: qurilmadagi yangilovchi qotib qolsa u
    hech kimga hech narsa demaydi va tuzatish ham unga yetib bormaydi.
    Tashqaridan qaraganda esa manzara aniq — reliz chiqqan, kanal avto,
    do'kon onlayn, lekin versiya kunlab o'zgarmayapti.

    Kuzatilmaydi:
    - `hold` / `pin` kanallari — bu BIZNING qarorimiz, nosozlik emas;
    - jim qurilma — u yangilana olmaydi va u haqda aloqa ogohlantirishi
      allaqachon ketgan (`plan_alerts`);
    - sanasi noma'lum qurilma — o'lchab bo'lmaydi.
    """
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    alerts: List[Alert] = []
    forget: List[str] = []
    if not latest_version:
        # Nashr qilingan reliz yo'q — solishtiradigan narsa ham yo'q.
        return alerts, forget

    for site in sites:
        site_id = site["id"]
        prev = previous.get(site_id)
        watched = (
            site.get("license_status") in ("active", "grace")
            and site.get("connection") == "online"
            and not is_silent(site)
            and str(site.get("update_channel") or "auto") == "auto"
        )
        if not watched:
            if prev is not None:
                forget.append(site_id)
            continue

        entry = versions_by_site.get(site_id)
        if not entry or not entry.get("since"):
            continue

        if str(entry.get("version")) == latest_version:
            if prev is not None:
                alerts.append(
                    Alert(
                        site_id,
                        "ok",
                        _update_recovery_text(site, str(entry["version"])),
                        remember=None,
                        kind="update",
                    )
                )
            continue

        try:
            # `CloudStore._iso` formati — naiv UTC.
            since = datetime.strptime(str(entry["since"]), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        days = (now - since).days
        if days < UPDATE_STUCK_DAYS:
            continue

        # Holat ataylab SONSIZ ("stuck:0.6.8" emas): keyingi reliz
        # chiqqanda o'sha do'kon uchun ikkinchi xabar ketmasin.  Qaysi
        # versiya va necha kun — matnda baribir yoziladi.
        if prev != "stuck":
            alerts.append(
                Alert(
                    site_id,
                    "stuck",
                    _update_stuck_text(site, str(entry["version"]), latest_version, days),
                    remember="stuck",
                    kind="update",
                )
            )

    return alerts, forget


def disk_watch_path() -> Path:
    """Qaysi disk kuzatiladi.

    Docker'da `/app/data` — volume'lar turgan host fayl tizimini ko'rsatadi
    (statvfs bind mount orqali hostnikini qaytaradi).  Konteynersiz ishga
    tushirishda ham shu papka ishlaydi, bo'lmasa ildiz.
    """
    override = os.environ.get("CHAQIMCHI_DISK_WATCH_PATH", "").strip()
    if override:
        return Path(override)
    default = Path("/app/data")
    return default if default.exists() else Path("/")


def disk_usage_percent(path: Path) -> Optional[float]:
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return None
    if not usage.total:
        return None
    return usage.used / usage.total * 100


def _disk_text(percent: float) -> str:
    return (
        f"💾 <b>Cloud server</b> — disk {percent:.0f}% to'lgan\n"
        f"Media kvotasi ishlayapti, lekin joy baribir kamaymoqda.\n"
        f"Eski backuplarni ko'chiring yoki diskni kengaytiring."
    )


def _disk_recovery_text(percent: float) -> str:
    return f"✅ <b>Cloud server</b> — disk bo'shadi ({percent:.0f}%)."


def plan_disk_alert(
    percent: Optional[float], previous: Dict[str, str]
) -> Tuple[List[Alert], List[str]]:
    """Server diski uchun ogohlantirish (sof funksiya, histerezis bilan).

    Qurilma monitoringi mijoz tomonini qo'riqlaydi; bu esa VPS'ning o'zini.
    Disk to'lsa PostgreSQL o'qish rejimiga tushadi va snapshot yuklash 500
    qaytara boshlaydi — bu holatni mijozdan oldin bilishimiz kerak.
    """
    if percent is None:
        return [], []
    prev = previous.get(SERVER_SITE_ID)
    if percent >= DISK_ALERT_PERCENT:
        state = "full"
        if prev != state:
            return [
                Alert(SERVER_SITE_ID, state, _disk_text(percent), remember=state, kind="disk")
            ], []
        return [], []
    if prev is not None and percent <= DISK_OK_PERCENT:
        return [
            Alert(SERVER_SITE_ID, "ok", _disk_recovery_text(percent), remember=None, kind="disk")
        ], []
    return [], []


# ── Serverning protsessori, xotirasi va harorati ────────────────────────
#
# Diskdan farqli: bular vaqtincha ko'tarilib tushishi normal.  Shuning
# uchun har bir chegara **juftlik** bilan keladi — yonish chegarasi va
# undan pastroq o'chish chegarasi (histerezis).  Bittasi bilan qilinsa,
# 91,9 va 92,1 orasida tebranib turgan xotira har 15 daqiqada bir
# "muammo/tuzaldi" juftligini yuborardi va chat ishonchini yo'qotardi.

#: Xotira: 92% — bu yerda OOM-killer konteynerni o'ldirishi mumkin.
SERVER_RAM_ALERT_PERCENT = 92.0
SERVER_RAM_OK_PERCENT = 85.0

#: Protsessor: 95%.  Yuqori chegara ataylab — tekshiruv 15 daqiqada bir
#: marta yuradi, ya'ni bu allaqachon "bir zumlik cho'qqi emas" degani.
SERVER_CPU_ALERT_PERCENT = 95.0
SERVER_CPU_OK_PERCENT = 80.0

#: Harakat: virtual serverda odatda o'lchanmaydi (termal zona yo'q),
#: lekin o'z temiriga ko'chsak tayyor tursin.
SERVER_TEMP_ALERT_C = 80.0
SERVER_TEMP_OK_C = 70.0


def _server_problem(snapshot: Dict[str, Any], previous: Optional[str]) -> Optional[Tuple[str, str]]:
    """Serverdagi eng og'ir muammo — `(holat, tavsif)`.

    Bitta xabar — bitta muammo, `_device_problem` bilan bir xil qoida.
    Histerezis shu yerda: agar shu muammo allaqachon aytilgan bo'lsa, u
    pastki chegaraga tushmaguncha "hali ham shu" deb qaytariladi.
    """
    temp = snapshot.get("temperature_c")
    if isinstance(temp, (int, float)):
        ceiling = SERVER_TEMP_OK_C if previous == "temp" else SERVER_TEMP_ALERT_C
        if temp >= ceiling:
            return "temp", f"server qizib ketdi ({temp:.0f}°C)"

    ram = snapshot.get("ram_percent")
    if isinstance(ram, (int, float)):
        ceiling = SERVER_RAM_OK_PERCENT if previous == "ram" else SERVER_RAM_ALERT_PERCENT
        if ram >= ceiling:
            return "ram", f"xotira tugayapti ({ram:.0f}% band)"

    cpu = snapshot.get("cpu_percent")
    if isinstance(cpu, (int, float)):
        ceiling = SERVER_CPU_OK_PERCENT if previous == "cpu" else SERVER_CPU_ALERT_PERCENT
        if cpu >= ceiling:
            return "cpu", f"protsessor to'lib ishlayapti ({cpu:.0f}%)"

    return None


def _server_health_text(detail: str) -> str:
    return (
        f"🖥 <b>Cloud server</b> — {detail}\n"
        f"Panel sekinlashishi va hodisalar kechikishi mumkin.\n"
        f"Serverni tekshiring: `docker stats` va `docker compose logs cloud`."
    )


def plan_server_health_alert(
    snapshot: Dict[str, Any], previous: Dict[str, str]
) -> Tuple[List[Alert], List[str]]:
    """Server resurslari uchun ogohlantirish (sof funksiya).

    O'lchanmagan ko'rsatkich (masalan virtual serverda harorat)
    `snapshot` ga umuman kirmaydi va shu sabab hech qachon yolg'on
    ogohlantirish bermaydi.
    """
    prev = previous.get(SERVER_SITE_ID)
    problem = _server_problem(snapshot, prev)

    if problem is not None:
        state, detail = problem
        if prev == state:
            return [], []
        return [
            Alert(
                SERVER_SITE_ID,
                state,
                _server_health_text(detail),
                remember=state,
                kind="server",
            )
        ], []

    if prev is not None:
        return [
            Alert(
                SERVER_SITE_ID,
                "ok",
                "✅ <b>Cloud server</b> — resurslar me'yorga qaytdi.",
                remember=None,
                kind="server",
            )
        ], []
    return [], []


# ── Do'kon kompyuterining sog'ligi ──────────────────────────────────────
#
# Eng xavfli buzilish — tizim yashil ko'rinib, hodisa yozmay qo'yishi.
# Aloqa uzilishini darhol ko'ramiz; buni esa faqat oy oxirida "hisobot
# nega bo'sh?" degan savoldan bilib qolardik.

#: Shundan kam bo'sh joy qolganda navbat va kliplar sig'may boshlaydi.
DEVICE_DISK_LOW_BYTES = 3 * 1024**3

#: Xato ulushi shundan oshsa tahlil zanjiri buzilgan hisoblanadi.
ANALYSIS_ERROR_RATIO = 0.5

#: Bundan kam kadr — bu hali statistika emas (dastur endi ko'tarildi).
ANALYSIS_MIN_SAMPLE = 200

#: Do'kon kompyuteri shu haroratdan oshsa — apparat xavf ostida.
#:
#: 85°C `chaqimchi_ai/retail/pressure.py:TEMP_CEILING_C` bilan bir xil:
#: N100 va shunga o'xshash protsessorlar ~90°C da tezlikni o'zi
#: pasaytiradi, ya'ni 85 allaqachon chegara.  Chang bosgan korpus yoki
#: to'xtagan ventilyator aynan shunday ko'rinadi va uni do'kon egasi
#: hech qachon o'zi sezmaydi.
DEVICE_TEMP_ALERT_C = 85.0
#: Sovigan deb hisoblash chegarasi (histerezis).
DEVICE_TEMP_OK_C = 75.0


def _device_problem(
    health: Dict[str, Any], previous: Optional[str] = None
) -> Optional[Tuple[str, str]]:
    """Eng og'ir muammoni qaytaradi: `(holat, tavsif)`.

    Bitta xabar — bitta muammo.  Uchalasi bir vaqtda bo'lsa (disk to'ldi →
    navbat yiqildi → tahlil ham xato bera boshladi) uchta alohida xabar
    chatni ko'mib tashlaydi va eng muhimi ko'rinmay ketadi.
    """
    if int(health.get("queue_errors") or 0) > 0:
        # Eng og'iri: hodisa diskka ham yozilmadi, ya'ni butunlay yo'qoldi.
        # Uni keyin tiklab bo'lmaydi.
        return "queue", "hodisalar saqlanmayapti va yo'qolyapti"

    # Haroratning o'rni ataylab ikkinchi: navbat yiqilsa hodisa ALLAQACHON
    # yo'qolyapti, qizish esa temirni hali buzayotgan bo'ladi — lekin
    # ikkalasi ham tahlil xatosi va disk to'lishidan og'irroq.
    temperature = health.get("temperature_c")
    if isinstance(temperature, (int, float)):
        # Histerezis: bir marta aytilgan bo'lsa, 75°C ga tushmaguncha
        # "hali ham qizigan" deb hisoblanadi.  Usiz 84,9/85,1 atrofida
        # tebranish har 15 daqiqada xabar/tiklandi juftini yuborardi.
        ceiling = DEVICE_TEMP_OK_C if previous == "temp" else DEVICE_TEMP_ALERT_C
        if temperature >= ceiling:
            return "temp", f"kompyuter qizib ketdi ({temperature:.0f}°C)"

    analyzed = int(health.get("analyzed") or 0)
    errors = int(health.get("analysis_errors") or 0)
    if analyzed >= ANALYSIS_MIN_SAMPLE and errors >= analyzed * ANALYSIS_ERROR_RATIO:
        return "analysis", "tahlil ishlamayapti — kadrlar qayta ishlanmayapti"

    free = int(health.get("disk_free_bytes") or 0)
    if 0 < free < DEVICE_DISK_LOW_BYTES:
        return "disk", f"kompyuterda joy tugayapti ({free / 1024**3:.1f} GB qoldi)"
    return None


def _device_text(site: Dict[str, Any], description: str) -> str:
    return (
        f"🔴 <b>{site.get('name', '?')}</b> — {description}\n"
        f"Tizim tashqaridan sog'lom ko'rinadi, lekin hisobot to'planmayapti.\n"
        f"Do'kon kompyuterini tekshirish kerak."
    )


def _device_recovery_text(site: Dict[str, Any]) -> str:
    return (
        f"✅ <b>{site.get('name', '?')}</b> — do'kon kompyuteri tuzaldi, hisobot yana to'planyapti."
    )


#: Egaga yuboriladigan matn — texnik atamasiz.
#:
#: "temperature_c 91" degan xabar do'kon egasiga hech narsa aytmaydi.
#: Bu yerda esa u aynan nima qilishi kerakligi yozilgan.
_OWNER_TEMP_ALERT = (
    "🌡 <b>Kompyuter qizib ketyapti</b>\n"
    "Nazorat hozircha ishlayapti, lekin kompyuter o'zini himoya qilib "
    "sekinlashishi yoki o'chib qolishi mumkin.\n\n"
    "Nima qilish kerak:\n"
    "• kompyuter yonidagi havo yo'lini bo'shating;\n"
    "• changini tozalang (ayniqsa ventilyatorni);\n"
    "• quyosh tushmaydigan, salqinroq joyga qo'ying."
)

_OWNER_TEMP_OK = "✅ Kompyuter sovidi — harorat me'yorga qaytdi."


def plan_device_health_alerts(
    sites: List[Dict[str, Any]],
    health_by_site: Dict[str, Dict[str, Any]],
    previous: Dict[str, str],
) -> Tuple[List[Alert], List[str]]:
    """Qurilma heartbeat'idagi sog'liq belgilarini tekshiradi.

    `health_by_site` — sayt bo'yicha oxirgi heartbeat.  Aloqasi yo'q
    saytlar tekshirilmaydi: ularning heartbeat'i eskirgan va aloqa
    ogohlantirishi allaqachon ketgan.
    """
    alerts: List[Alert] = []
    forget: List[str] = []

    for site in sites:
        site_id = site["id"]
        prev = previous.get(site_id)
        watched = (
            site.get("license_status") in ("active", "grace")
            and site.get("connection") in ("online", "stale")
            # Jim qurilma haqida aloqa xabari allaqachon ketgan.
            and not is_silent(site)
        )
        health = health_by_site.get(site_id)
        if not watched or health is None:
            if prev is not None:
                forget.append(site_id)
            continue

        problem = _device_problem(health, prev)
        if problem is None:
            if prev is not None:
                alerts.append(
                    Alert(
                        site_id,
                        "ok",
                        _device_recovery_text(site),
                        remember=None,
                        kind="device",
                        # Egaga faqat u xabar olgan muammo bo'yicha
                        # tiklanish aytiladi.
                        owner_text=_OWNER_TEMP_OK if prev == "temp" else None,
                    )
                )
            continue
        state, description = problem
        if prev != state:
            alerts.append(
                Alert(
                    site_id,
                    state,
                    _device_text(site, description),
                    remember=state,
                    kind="device",
                    # Qizish — egasi O'ZI hal qila oladigan yagona
                    # muammo: chang tozalash, shamollatish, quyoshdan
                    # olib qo'yish.  Qolganlari biz uchun texnik signal.
                    owner_text=_OWNER_TEMP_ALERT if state == "temp" else None,
                )
            )

    return alerts, forget


def plan_alerts(
    sites: List[Dict[str, Any]],
    previous: Dict[str, str],
    *,
    now: Optional[datetime] = None,
) -> Tuple[List[Alert], List[str]]:
    """Qaysi xabarlar yuborilishi kerakligini hisoblaydi (tarmoqsiz, sof funksiya).

    Qaytaradi: (yuboriladigan xabarlar, holati tozalanishi kerak bo‘lgan sayt ID lari).

    Qoidalar:

    - Faqat **to‘lovi joyida** (active/grace) mijozlar kuzatiladi. O‘zimiz
      to‘xtatgan sayt jim turishi — normal holat, u haqda yozish shovqin.
    - Xabar faqat holat **o‘zgarganda** ketadi.
    - Yangi mijoz `PAIRING_GRACE_HOURS` ichida juftlanmasa ham jim — o‘rnatuvchi
      hali bormagan bo‘lishi mumkin.
    - Qisqa `stale` uchun xabar yo‘q (internet uzilishi odatiy hol), lekin
      `SILENT_ALERT_HOURS` dan uzoq jimlik — xabar beriladi.
    """
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    alerts: List[Alert] = []
    forget: List[str] = []

    for site in sites:
        site_id = site["id"]
        prev = previous.get(site_id)

        if site.get("license_status") not in ("active", "grace"):
            # Kuzatuvdan chiqadi. Keyin qayta yoqilganda toza sahifadan
            # boshlanadi — eski holat bo'yicha yolg'on "tiklandi" ketmaydi.
            if prev is not None:
                forget.append(site_id)
            continue

        state = site.get("connection", "offline")

        if state == "not_paired":
            age = _site_age_hours(site.get("created_at"), now)
            if age is not None and age < PAIRING_GRACE_HOURS:
                continue

        # Uzoq jim turgan `stale` ham muammo.  Holat nomi alohida
        # (`silent`), aks holda qurilma qaytib `stale` ga tushganda
        # "tiklandi" deb yolg'on xabar ketardi.
        if is_silent(site):
            state = "silent"

        if state in PROBLEM_STATES:
            if prev != state:
                alerts.append(Alert(site_id, state, _problem_text(site), remember=state))
        elif prev in PROBLEM_STATES:
            # Muammo hal bo'ldi. `stale` ham tiklanish deb qaraladi: tizim
            # yana xabar bera boshlagan.
            alerts.append(Alert(site_id, state, _recovery_text(site), remember=None))
        elif prev is not None:
            forget.append(site_id)

    return alerts, forget


class TelegramSender:
    """Telegramga xabar yuborish. Xato bo‘lsa cloud to‘xtamaydi — log yoziladi."""

    def __init__(self, config: AlertConfig) -> None:
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None

    async def send(self, text: str, reply_markup: Optional[Dict[str, Any]] = None) -> bool:
        if not self.config.chat_id:
            return False
        return await self.send_to(self.config.chat_id, text, reply_markup=reply_markup)

    async def send_to(
        self, chat_id: str, text: str, reply_markup: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Bitta ishonchli chatga xabar yuboradi.

        Leadlar uchun bir nechta ichki sales guruhini qo'llash kerak bo'lishi
        mumkin. Token yagona bo'ladi, qabul qiluvchi esa alohida beriladi.
        """
        if not self.config.token or not chat_id:
            return False
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=15.0)
        url = f"https://api.telegram.org/bot{self.config.token}/sendMessage"
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            resp = await self._client.post(url, json=payload)
            if resp.status_code != 200:
                logger.warning("Telegram javobi %s: %s", resp.status_code, resp.text[:200])
                return False
            return True
        except Exception as e:
            logger.warning("Telegram xabar yuborilmadi: %s", e)
            return False

    async def aclose(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            finally:
                self._client = None


def _latest_health() -> Dict[str, Dict[str, Any]]:
    """Qurilma heartbeat'lari hodisa bazasida (cloud DB'da emas).

    Import shu yerda: `alerts` moduli hodisa bazasidan mustaqil bo'lib
    qolsin, testlarda esa uni almashtirish oson bo'lsin.
    """
    from cloud.main import get_event_store

    return get_event_store().latest_health_by_site()


def _latest_release_version() -> Optional[str]:
    """Bulut hozir qaysi Windows versiyasini taklif qilyapti.

    Import shu yerda — `alerts` moduli `cloud.main` dan mustaqil qolsin
    (`_latest_health` bilan bir xil sabab).
    """
    from cloud.main import latest_windows_release

    release = latest_windows_release()
    return str(release["version"]) if release else None


async def run_check(
    store: Any,
    sender: TelegramSender,
    owner_notify: Optional[Callable[[str, str], Awaitable[None]]] = None,
) -> AlertRun:
    """Bir marta tekshirish: holatlarni solishtirib, o‘zgarganlarini yuboradi.

    `owner_notify(site_id, text)` berilsa, tizim to'xtagani/tiklangani
    haqida **do'kon egasiga** ham xabar ketadi.  Berilmasa (masalan
    testlarda) faqat ichki chatga yoziladi.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    run = AlertRun(ran_at=now.strftime("%Y-%m-%d %H:%M:%S"))

    sites = store.list_sites()
    run.checked = len(sites)

    conn_alerts, conn_forget = plan_alerts(sites, store.alert_states("connection"), now=now)
    cam_alerts, cam_forget = plan_camera_alerts(sites, store.alert_states("cameras"))
    disk_alerts, _ = plan_disk_alert(
        disk_usage_percent(disk_watch_path()), store.alert_states("disk")
    )
    # Serverning protsessori va xotirasi.  `/proc` o'qilmasa (Linux
    # bo'lmagan muhit) bo'sh lug'at qaytadi va hech qanday ogohlantirish
    # chiqmaydi — qolgan tekshiruvlar esa ishlayveradi.
    server_alerts: List[Alert] = []
    try:
        from cloud import server_health

        server_alerts, _ = plan_server_health_alert(
            server_health.snapshot(), store.alert_states("server")
        )
    except Exception:  # noqa: BLE001 — server o'lchovi qolganini to'xtatmasin
        logger.exception("Server resurslari tekshirilmadi")
    # Qurilma sog'ligi hodisa bazasida — u yerdan bitta so'rov bilan
    # olinadi.  Bazaga yetib bo'lmasa qolgan ogohlantirishlar baribir
    # ketishi kerak.
    device_alerts: List[Alert] = []
    device_forget: List[str] = []
    try:
        device_alerts, device_forget = plan_device_health_alerts(
            sites, _latest_health(), store.alert_states("device")
        )
    except Exception:  # noqa: BLE001
        logger.exception("Qurilma sog'ligi tekshirilmadi")

    for site_id in conn_forget:
        store.clear_alert_state(site_id, kind="connection")
    for site_id in cam_forget:
        store.clear_alert_state(site_id, kind="cameras")
    # Yangilanish qotib qolganini ham shu yerda tekshiramiz: reliz
    # ro'yxati diskdan o'qiladi, ya'ni xato bo'lsa qolgan
    # ogohlantirishlar to'xtab qolmasligi kerak.
    update_alerts: List[Alert] = []
    update_forget: List[str] = []
    try:
        # Global to'xtatuvchi yoqilgan bo'lsa hech kim yangilanmaydi —
        # bu bizning qarorimiz, nosozlik emas.
        if not store.updates_paused():
            update_alerts, update_forget = plan_update_stuck_alerts(
                sites,
                store.device_versions(),
                _latest_release_version(),
                store.alert_states("update"),
                now=now,
            )
    except Exception:  # noqa: BLE001
        logger.exception("Yangilanish holati tekshirilmadi")

    for site_id in device_forget:
        store.clear_alert_state(site_id, kind="device")
    for site_id in update_forget:
        store.clear_alert_state(site_id, kind="update")

    sites_by_id = {site["id"]: site for site in sites}

    for alert in (
        conn_alerts + cam_alerts + device_alerts + update_alerts + disk_alerts + server_alerts
    ):
        if await sender.send(alert.text):
            run.sent += 1
            run.messages.append(alert.text)
            if owner_notify is not None and alert.kind == "connection":
                await _notify_owner(owner_notify, alert, sites_by_id.get(alert.site_id))
            elif owner_notify is not None and alert.owner_text:
                # Egaga tayyor, sodda matn.  Aloqa xabari o'z shablonini
                # ishlatadi (`_notify_owner`), bu esa muammoning o'ziga
                # yozilgan matn — masalan qizish bo'yicha maslahat.
                try:
                    await owner_notify(alert.site_id, alert.owner_text)
                except Exception:  # noqa: BLE001 — ichki xabar allaqachon ketdi
                    logger.warning("Egaga xabar yuborilmadi: %s", alert.site_id, exc_info=True)
            # Holat faqat xabar **yetib borgandan keyin** yoziladi: aks holda
            # tarmoq uzilganda muammo "xabar berilgan" deb belgilanib,
            # ogohlantirish butunlay yo'qolardi.
            if alert.remember is None:
                store.clear_alert_state(alert.site_id, kind=alert.kind)
            else:
                store.set_alert_state(alert.site_id, alert.remember, kind=alert.kind)
        else:
            run.failed += 1

    if run.sent or run.failed:
        logger.info("Aloqa ogohlantirishi: %d yuborildi, %d xato", run.sent, run.failed)
    return run


async def _notify_owner(
    owner_notify: Callable[[str, str], Awaitable[None]],
    alert: Alert,
    site: Optional[Dict[str, Any]],
) -> None:
    """Egaga xabar — ichki chatdan ALOHIDA va xatosi yutiladi.

    Mijozga yuborish muvaffaqiyatsiz bo'lsa ham ichki xabar allaqachon
    ketgan va `alert_state` yozilishi kerak: aks holda muammo har
    tekshiruvda qaytadan "yangi" bo'lib, ichki chatga bo'ron bo'lardi.
    """
    if site is None:
        return
    text = owner_recovery_text() if alert.remember is None else owner_down_text(site)
    if not text:
        return
    try:
        await owner_notify(alert.site_id, text)
    except Exception:  # noqa: BLE001
        logger.warning("Egaga uzilish xabari yuborilmadi: %s", alert.site_id, exc_info=True)


class AlertService:
    """Fon vazifasi + oxirgi natija (admin panel uchun)."""

    def __init__(
        self,
        store: Any,
        config: Optional[AlertConfig] = None,
        owner_notify: Optional[Callable[[str, str], Awaitable[None]]] = None,
    ) -> None:
        self.store = store
        self.config = config or AlertConfig.from_env()
        self.sender = TelegramSender(self.config)
        self.owner_notify = owner_notify
        self.last_run: Optional[AlertRun] = None
        self._task: Optional[asyncio.Task] = None

    async def check_once(self) -> AlertRun:
        self.last_run = await run_check(self.store, self.sender, self.owner_notify)
        return self.last_run

    async def _loop(self) -> None:
        while True:
            try:
                await self.check_once()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.warning("Aloqa tekshiruvida xato", exc_info=True)
            await asyncio.sleep(self.config.interval_sec)

    def start(self) -> None:
        if not self.config.enabled:
            logger.info(
                "Telegram ogohlantirishi o‘chiq "
                "(CHAQIMCHI_CLOUD_TELEGRAM_TOKEN yoki OWNER token / _CHAT_ID berilmagan)"
            )
            return
        if self._task is None:
            self._task = asyncio.create_task(self._loop())
            logger.info("Aloqa nazorati yoqildi — har %d soniyada", self.config.interval_sec)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
        await self.sender.aclose()

    def status(self) -> Dict[str, Any]:
        return {
            "enabled": self.config.enabled,
            "interval_sec": self.config.interval_sec,
            "chat_id_set": bool(self.config.chat_id),
            "token_set": bool(self.config.token),
            "pairing_grace_hours": PAIRING_GRACE_HOURS,
            "running": self._task is not None,
            "last_run": self.last_run.to_dict() if self.last_run else None,
        }


def test_message() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        "🔔 <b>Chaqimchi Cloud</b>\n"
        "Ogohlantirish sozlandi — mijoz tizimi o‘chsa shu yerga xabar keladi.\n"
        f"<i>{stamp}</i>"
    )


__all__ = [
    "Alert",
    "AlertConfig",
    "AlertRun",
    "AlertService",
    "DEVICE_TEMP_ALERT_C",
    "DISK_ALERT_PERCENT",
    "SERVER_CPU_ALERT_PERCENT",
    "SERVER_RAM_ALERT_PERCENT",
    "SERVER_TEMP_ALERT_C",
    "PAIRING_GRACE_HOURS",
    "SILENT_ALERT_HOURS",
    "UPDATE_STUCK_DAYS",
    "TelegramSender",
    "disk_usage_percent",
    "disk_watch_path",
    "plan_alerts",
    "plan_camera_alerts",
    "plan_disk_alert",
    "plan_server_health_alert",
    "plan_update_stuck_alerts",
    "run_check",
    "test_message",
]
