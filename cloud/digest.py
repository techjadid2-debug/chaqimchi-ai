"""Owner va managerlarga Asia/Tashkent bo'yicha Telegram hisobotlar.

Uch xil hisobot:
- **Kunlik** — har kuni kechqurun (standart 21:00): bugungi raqamlar.
- **Haftalik** — dushanba ertalab (09:00): o'tgan hafta xulosasi,
  kunlar grafigi, taqqos va kamera uptime.
- **Oylik smena** — oyning 1-kuni (10:00): o'tgan oyda kim qancha
  kechikdi va necha kun kelmadi.  Faqat davomat yoqilgan do'konda.

Uslub `cloud/botfmt.py`da — bot xabarlari bir xil ko'rinishda bo'lsin.

Til: har builder `lang` oladi va matnni `i18n` katalogidan (`digest.*`)
chizadi.  Xabar a'zoning O'Z tilida ketadi — `_deliver` uni tilga
qarab bir marta yasaydi.  `i18n.t()` bu yerda ISHLATILMAYDI: fon
vazifasi so'rov kontekstini meros oladi va xabar so'rov yuborganning
tilida ketib qolardi (batafsil `cloud/i18n.py`).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

from cloud import botfmt, chartimg, i18n, trust_score, value
from cloud.event_store import EventStore
from cloud.i18n import tg
from cloud.owner_auth import BIOMETRIC_ROLES
from cloud.payments.store import billable_months
from cloud.store import GRACE_DAYS

logger = logging.getLogger(__name__)

#: Haftalik hisobot yuboriladigan kun (0 = dushanba) va soat.
WEEKLY_WEEKDAY = 0
WEEKLY_HOUR = 9

#: Oylik smena hisoboti: oyning 1-kuni, haftalikdan KEYIN.
#: 1-yanvar dushanbaga to'g'ri kelsa ikkala xabar bir kunda ketadi —
#: bu normal, ular boshqa savolga javob beradi.
MONTHLY_DAY = 1
MONTHLY_HOUR = 10

#: Obuna eslatmasi yuboriladigan soat.  Ertalab emas: to'lov qilish uchun
#: mijoz do'konda va ish holatida bo'lishi kerak.
RENEWAL_HOUR = 11

#: Obuna tugashiga shuncha kun qolganda birinchi eslatma ketadi.
RENEWAL_FIRST_DAYS = 7

#: Demografiyani FOIZDA ko'rsatish uchun eng kam o'lchov soni.
#:
#: 27-avgust jonli o'lchovi: 207 ta kirishdan 9 tasida jins metadatasi
#: bor edi, lekin xabar "11% ayol · 89% erkak" deb FAKT sifatida
#: yozardi.  n=9 da bitta odam foizni 11 punktga siljitadi; 20 da —
#: 5 punktga.  Shundan pastda foiz o'lchov emas, tasodif — shuning
#: uchun qator foizsiz, faqat SON ko'rinishida chiqadi.
DEMOGRAPHY_MIN_SAMPLE = 20

#: ...va kirganlarning kamida shuncha ulushi o'lchangan bo'lsin.
#:
#: Qamrov sondan MUHIMROQ.  Past qamrovda o'lchanganlar tasodifiy
#: tanlanmagan: ular kameraga eng yaqin o'tgan odamlar, ya'ni natija
#: shovqinli emas — OG'GAN.  Bunday kunda ham foiz emas, son chiqadi
#: (`trust_score` ham o'lchanmagan qismni ballga qo'shmaydi — hisobot
#: ham shu intizomda bo'lsin).
DEMOGRAPHY_MIN_COVERAGE = 0.30

#: Tilga qarab matn yasaydigan funksiya — `_deliver` shuni oladi.
TextBuilder = Callable[[str], str]


def _demography_is_representative(
    demografiya: Dict[str, Any], traffic: Dict[str, Any]
) -> bool:
    """Foiz ko'rsatishga arziydigan o'lchov bormi."""
    counted = int(demografiya.get("hisoblangan") or 0)
    if counted < DEMOGRAPHY_MIN_SAMPLE:
        return False
    entered = int(traffic.get("entered") or 0)
    # Har o'lchov kirish kesishmasidan chiqadi, ya'ni `entered` noldan
    # katta bo'lishi shart; nolga bo'lishdan himoya baribir arzon.
    return bool(entered) and counted >= entered * DEMOGRAPHY_MIN_COVERAGE


def _is_monday(day: str) -> bool:
    """Sana matnidan hafta kuni.  Ochib bo'lmasa — eslatma chiqmaydi."""
    try:
        return date.fromisoformat(day[:10]).weekday() == 0
    except ValueError:
        return False


def build_digest(
    site_name: str,
    day: str,
    stats: Dict[str, Any],
    report: Dict[str, Any],
    *,
    open_from: Optional[str] = None,
    first_movement: Optional[str] = None,
    score: Optional[Dict[str, Any]] = None,
    daily_revenue_uzs: int = 0,
    receipts: Optional[int] = None,
    lang: str = i18n.DEFAULT_LANG,
) -> str:
    """Kunlik xabar matni.

    Xom hodisa sanog'i ("person_detected: 412") do'kon egasiga hech narsa
    aytmaydi.  Xabar uning savollariga javob beradi: nechta odam kirdi,
    kecha bilan taqqoslaganda qanday, qaysi soat gavjum, navbat qancha
    bo'ldi, do'kon o'z vaqtida ochildimi.

    Xavfsizlik hodisalari **oxirida va faqat bo'lsa** yoziladi — har kuni
    "0 ta buzilish" deb yozish xabarni uzaytiradi va o'qilmay qoladi.
    """
    traffic = report["traffic"]
    site = botfmt.header(site_name)

    # Birinchi qator — KUNNING HOLATI, hisobot sarlavhasi emas.
    #
    # Do'kon egasi telefonda xabarning faqat birinchi qatorini ko'radi
    # (bildirishnoma shuni ko'rsatadi).  "kunlik hisobot" unga hech narsa
    # aytmaydi; "Bugun: 94 — A'lo kun" esa xabarni ochmasdan ham javob
    # beradi.  Ball yo'q bo'lsa eski sarlavha qoladi.
    if score and score.get("available"):
        headline = tg(lang, "digest.daily.headline_score", site=site, score=score["total"])
        subtitle = trust_score.label(score["total"], lang=lang)
    elif score:
        headline = tg(lang, "digest.daily.headline_plain", site=site)
        subtitle = str(score.get("reason") or "")
    else:
        headline = tg(lang, "digest.daily.headline_report", site=site)
        subtitle = ""

    lines = [headline, botfmt.day_title(day + "T12:00:00+05:00", lang) or day]
    if subtitle:
        lines.append(subtitle)
    lines += [
        "",
        tg(lang, "digest.daily.entered", count=botfmt.number(traffic["entered"], lang)),
    ]

    change = traffic.get("change_percent")
    if change is not None:
        arrow = "▲" if change >= 0 else "▼"
        lines.append(
            tg(
                lang,
                "digest.daily.vs_yesterday",
                arrow=arrow,
                percent=abs(change),
                yesterday=traffic["entered_yesterday"],
            )
        )
    busiest = traffic.get("busiest_hour")
    if busiest:
        lines.append(
            tg(
                lang,
                "digest.daily.busiest_hour",
                hour=f"{busiest['hour']:02d}",
                count=busiest["entered"],
            )
        )

    # Konversiya — «nechta kirdi» ni «nechta sotib oldi» bilan bog'laydigan
    # yagona qator.  Chek sonini ega O'ZI kiritadi (kassa integratsiyasi
    # yo'q), shuning uchun kiritilmagan kunda qator o'rniga QANDAY
    # kiritish ko'rsatiladi: eslatmasiz ega bunday imkoniyat borligini
    # bilmaydi va raqam hech qachon yig'ilmaydi.
    entered_today = int(traffic.get("entered") or 0)
    conversion = value.conversion_line(receipts=receipts, entered=entered_today, lang=lang)
    if conversion:
        lines.append(conversion)
    elif entered_today >= value.MIN_VISITORS_FOR_CONVERSION and _is_monday(day):
        # Eslatma HAFTASIGA BIR MARTA (dushanba).  Har kuni takrorlansa u
        # «0 ta buzilish» qatorining taqdirini takrorlaydi — xabar uzayadi
        # va o'qilmay qoladi.  Dushanba `_quiet_reason` uchun tanlangan
        # kun bilan bir xil, ya'ni yangi qoida emas.
        #
        # Kam odam kirgan kunda umuman so'ralmaydi: 12 kishilik kunning
        # konversiyasi o'lchov emas, tasodif.
        lines.append(tg(lang, "digest.daily.ask_receipts"))

    # Demografiya — ma'lumot yig'ilgan har kunda chiqadi (xodimlar
    # hisobga kirmaydi, ular davomatda).  Ega bu qatorni kutadi
    # (2026-08-29 qarori: butunlay yashirish mahsulotni kambag'allashtirdi);
    # halollik FORMAT bilan saqlanadi — o'lchov vakillik qilsa foiz,
    # qilmasa faqat SON, chunki kichik namunadan chiqarilgan foiz
    # o'lchov emas, tasodif.  Chegaralar yuqorida, sabab bilan.
    demografiya = report.get("demografiya") or {}
    counted = int(demografiya.get("hisoblangan") or 0)
    if _demography_is_representative(demografiya, traffic):
        jins = demografiya.get("jins") or {}
        yosh = demografiya.get("yosh") or {}
        params = {"female": jins.get("ayol", 0), "male": jins.get("erkak", 0)}
        if any(yosh.values()):
            top_age = max(yosh, key=lambda key: yosh[key])
            lines.append(tg(lang, "digest.daily.demography_percent_age", age=top_age, **params))
        else:
            lines.append(tg(lang, "digest.daily.demography_percent", **params))
    elif counted:
        soni = demografiya.get("jins_soni") or {}
        lines.append(
            tg(
                lang,
                "digest.daily.demography_counts",
                count=counted,
                female=int(soni.get("ayol") or 0),
                male=int(soni.get("erkak") or 0),
            )
        )

    # Soatlik oqim mini-grafigi (08:00–23:00 oralig'i — tungi nol
    # ustunlar grafikni cho'zib yuborardi).
    hourly = traffic.get("hourly") or []
    window = [item for item in hourly if 8 <= int(item.get("hour", 0)) <= 22]
    chart = botfmt.sparkline([float(item.get("entered", 0)) for item in window])
    if chart.strip():
        lines.append(f"<code>08 {chart} 22</code>")

    # Ochilish nazorati: jadval kiritilgan bo'lsa va birinchi harakat
    # ma'lum bo'lsa.
    if open_from and first_movement:
        opened = botfmt.clock(first_movement)
        if opened:
            late = _minutes(opened) - _minutes(open_from) > 20
            key = "digest.daily.opening_late" if late else "digest.daily.opening"
            lines.append(tg(lang, key, opened=opened, scheduled=open_from))

    queue = report["queue"]
    if queue["alerts"]:
        parts = [tg(lang, "digest.daily.queue_exceeded", count=queue["alerts"])]
        if queue.get("average"):
            parts.append(tg(lang, "digest.daily.queue_average", count=queue["average"]))
        parts.append(
            tg(
                lang,
                "digest.daily.queue_longest",
                count=queue["longest"],
                time=queue["longest_at"],
            )
        )
        lines.append(tg(lang, "digest.daily.queue", details=", ".join(parts)))
        # Navbat raqami o'z-o'zidan hech narsa aytmaydi — "5 marta uzun
        # bo'ldi" do'kon egasiga NIMA turishini bildirmaydi.  Mijoz
        # kunlik savdosini aytgan bo'lsa, o'sha raqam so'mga aylanadi.
        # Aytmagan bo'lsa qator umuman chiqmaydi (`daily_line` -> None).
        money = value.daily_line(report, daily_revenue_uzs, lang)
        if money:
            lines.append(money)
    if report["dwell"]:
        top = report["dwell"][0]
        lines.append(
            tg(
                lang,
                "digest.daily.dwell",
                zone=botfmt.escape(top["zone"]),
                count=top["count"],
                duration=botfmt.duration(top["average_sec"], lang),
            )
        )

    security = report["security"]
    # Tungi hodisalar alohida qator — faqat BO'LSA.  Ega uchun «tunda
    # nima bo'ldi?» kunduzgi navbat va uzoq turishdan boshqa savol.
    night = int(security.get("after_hours_presence") or 0) + int(security.get("night_motion") or 0)
    if night:
        lines.append(tg(lang, "digest.daily.night", count=night))
    alarms = []
    for field, key in (
        ("camera_tampered", "digest.daily.alarm.camera_tampered"),
        ("after_hours_presence", "digest.daily.alarm.after_hours"),
        ("restricted_zone", "digest.daily.alarm.restricted_zone"),
        ("loitering", "digest.daily.alarm.loitering"),
        ("checkout_unattended", "digest.daily.alarm.checkout_unattended"),
    ):
        if security.get(field):
            alarms.append(tg(lang, key, count=security[field]))
    if alarms:
        lines.append(tg(lang, "digest.daily.alarms", details=", ".join(alarms)))

    return "\n".join(lines)


def _minutes(clock_value: str) -> int:
    try:
        hours, minutes = str(clock_value).split(":", 1)
        return int(hours) * 60 + int(minutes)
    except (ValueError, AttributeError):
        return 0


def build_shifts(
    site_name: str,
    month_label: str,
    summary: Dict[str, Any],
    lang: str = i18n.DEFAULT_LANG,
) -> str:
    """Oylik smena xulosasi.

    Kunlik davomat jadvalini hech kim oxirigacha o'qimaydi.  Oy yakunida
    bitta savol qoladi: kim kechikyapti va bu qancha vaqtga tushdi.

    Ismlar ATAYLAB ko'rsatiladi — bu xabar do'kon egasiga boradi va
    aynan shu ma'lumot uchun kerak.  Lekin faqat uchtasi: to'liq
    ro'yxat xabarni o'qib bo'lmaydigan qiladi, u panelda turadi.
    """
    total = summary.get("jami") or {}
    late_minutes = int(total.get("kechikish_daq") or 0)
    lines = [
        tg(
            lang,
            "digest.shifts.title",
            site=botfmt.header(site_name),
            month=botfmt.escape(month_label),
        ),
        "",
    ]
    if not late_minutes and not total.get("kelmagan_kunlar"):
        lines.append(tg(lang, "digest.shifts.clean"))
        return "\n".join(lines)

    lines.append(
        tg(
            lang,
            "digest.shifts.total_late",
            duration=botfmt.escape(botfmt.minutes_label(late_minutes, lang)),
        )
    )
    if total.get("kelmagan_kunlar"):
        lines.append(tg(lang, "digest.shifts.absent_days", count=total["kelmagan_kunlar"]))

    top = [row for row in (summary.get("rows") or []) if row.get("jami_kechikish_daq")][:3]
    if top:
        lines.append("")
        for row in top:
            lines.append(
                tg(
                    lang,
                    "digest.shifts.row",
                    name=botfmt.escape(row["employee_name"]),
                    days=row["kechikkan_kunlar"],
                    minutes=row["jami_kechikish_daq"],
                )
            )
    lines.append("")
    lines.append(tg(lang, "digest.shifts.footer"))
    return "\n".join(lines)


def build_renewal(
    site_name: str,
    *,
    stage: str,
    days_left: int,
    monthly_uzs: int,
    grace_days: int,
    pay_url: str = "",
    lang: str = i18n.DEFAULT_LANG,
) -> str:
    """Obuna tugashi haqida mijozga eslatma va yillik taklif.

    Bungacha obuna tugashini FAQAT xodim ko'rardi (admin panelidagi
    "e'tibor talab qiladi" ro'yxati).  Mijozga hech qanday xabar
    bormasdi — u to'lashni unutib, grace'ga tushib, keyin tizim
    o'chganda "buzildi" deb o'ylardi.

    Yillik summa `billable_months()` dan hisoblanadi — saytdagi
    "2 oy bepul" va'dasi, hisob-faktura va bu xabar bitta qoidadan
    chiqishi shart.

    `pay_url` — hisob-fakturaning to'lov sahifasi.  Bo'sh bo'lsa eski
    matn qoladi ("To'lovni panelda ochasiz").  Havola BERILGANDA u
    o'sha o'rinni egallaydi: ega uchun eslatma bilan to'lov orasida
    endi qidiruv yo'q — ilgari unga "panelni oching" deyilardi va
    to'lov shu yerda uzilardi.
    """
    charged = billable_months(12)
    annual = monthly_uzs * charged
    saving = monthly_uzs * (12 - charged)
    site = botfmt.header(site_name)

    if stage == "grace":
        lines = [
            tg(lang, "digest.renewal.grace_title", site=site),
            "",
            tg(lang, "digest.renewal.grace_body", days=grace_days),
        ]
    elif stage == "1":
        lines = [
            tg(lang, "digest.renewal.tomorrow_title", site=site),
            "",
            tg(lang, "digest.renewal.tomorrow_body", days=grace_days),
        ]
    else:
        lines = [
            tg(lang, "digest.renewal.soon_title", site=site, days=days_left),
            "",
            tg(lang, "digest.renewal.monthly", amount=botfmt.number(monthly_uzs, lang)),
        ]

    lines += [
        "",
        tg(
            lang,
            "digest.renewal.annual",
            free_months=12 - charged,
            annual=botfmt.number(annual, lang),
            saving=botfmt.number(saving, lang),
        ),
        "",
        tg(lang, "digest.renewal.pay_link", url=pay_url)
        if pay_url
        else tg(lang, "digest.renewal.footer"),
    ]
    return "\n".join(lines)


def _trend_weekday(item: Dict[str, Any], lang: str) -> str:
    """Kun nomi qabul qiluvchi tilida.

    `traffic_trend` nomni o'zbekcha beradi (panel va CSV shuni
    ishlatadi); qatorda sana ham bor — undan indeks olinadi va nom
    katalogdan chiqadi.  Sana o'qilmasa tayyor nom qoladi.
    """
    try:
        index = date.fromisoformat(str(item.get("date") or "")[:10]).weekday()
    except ValueError:
        return str(item.get("weekday") or "")
    return botfmt.weekday_name(index, lang)


def build_weekly(
    site_name: str,
    *,
    trend: Dict[str, Any],
    queue_alerts: int,
    queue_longest: int,
    uptime_percent: Optional[float],
    lang: str = i18n.DEFAULT_LANG,
) -> str:
    """Haftalik xulosa — dushanba ertalab.

    Kunlik raqamlar tez unutiladi; hafta yakuni esa "ish qanday ketyapti"
    savoliga javob beradi va o'tgan hafta bilan taqqoslaydi.
    """
    lines = [
        tg(lang, "digest.weekly.title", site=botfmt.header(site_name)),
        "",
        tg(
            lang,
            "digest.weekly.entered",
            count=botfmt.number(trend.get("total", 0), lang),
            average=trend.get("average", 0),
        ),
    ]
    change = trend.get("change_percent")
    if change is not None:
        arrow = "▲" if change >= 0 else "▼"
        lines.append(tg(lang, "digest.weekly.vs_previous", arrow=arrow, percent=abs(change)))

    daily = trend.get("daily") or []
    chart = botfmt.sparkline([float(item.get("entered", 0)) for item in daily])
    if chart.strip():
        labels = " ".join(_trend_weekday(item, lang)[:2] for item in daily)
        lines.append(f"<code>{chart}</code>")
        lines.append(f"<code>{labels}</code>")

    busiest = trend.get("busiest_day")
    if busiest:
        lines.append(
            tg(
                lang,
                "digest.weekly.busiest_day",
                weekday=_trend_weekday(busiest, lang),
                count=busiest["entered"],
            )
        )

    if queue_alerts:
        lines.append(
            tg(lang, "digest.weekly.queue", count=queue_alerts, longest=queue_longest)
        )

    if uptime_percent is not None:
        icon = "✅" if uptime_percent >= 99 else "⚠️"
        lines.append(tg(lang, "digest.weekly.uptime", icon=icon, percent=uptime_percent))

    return "\n".join(lines)


class DailyDigestService:
    def __init__(
        self,
        events: EventStore,
        sites: Callable[[], List[Dict[str, Any]]],
        sender: Callable[..., Awaitable[None]],
        *,
        hour: int = 21,
        panel_url: str = "",
        renewal_invoice: Optional[Callable[[str, str], str]] = None,
        is_leader: Optional[Callable[[], bool]] = None,
        photo_sender: Optional[Callable[..., Awaitable[None]]] = None,
    ) -> None:
        self.events = events
        self.sites = sites
        self.sender = sender
        # Rasmli xabar (`sendPhoto`).  Berilmasa hisobot avvalgidek faqat
        # matn — testlar va rasm chizilmaydigan muhit uchun.
        self.photo_sender = photo_sender
        self.hour = hour
        self.panel_url = panel_url.rstrip("/")
        # Halqa har worker'da yuradi, ish esa faqat YETAKCHIDA bajariladi
        # (`cloud/leader.py`).  Berilmasa — hammasi avvalgidek.
        self.is_leader = is_leader
        # `(site_id, davr) -> to'lov sahifasi manzili`.  Chaqiruv orqali,
        # chunki hisob-faktura `cloud/payments/` da va uni bu yerdan
        # import qilish aylanma bog'liqlik bo'lardi (`main` → `digest`).
        # Sozlanmagan bo'lsa eslatma avvalgidek, havolasiz ketadi.
        self.renewal_invoice = renewal_invoice

    async def _deliver(
        self,
        site_id: str,
        members: List[Dict[str, Any]],
        build: TextBuilder,
        *,
        image: Optional[Callable[[str], bytes]] = None,
        caption: Optional[TextBuilder] = None,
    ) -> int:
        """Har a'zoga O'Z tilida yuboradi.

        Matn tilga qarab BIR MARTA yasaladi va shu sayt doirasida
        keshlanadi: uchta o'zbek a'zoli do'kon uchun `build` uch marta
        emas, bir marta chaqiriladi.  Til a'zo qatoridan (`language`)
        keladi — so'rov kontekstidan emas, chunki bu fon vazifasi.

        `image` berilsa (va rasm yuboruvchi sozlangan bo'lsa) avval
        rasm + qisqa izoh ketadi, keyin to'liq matn.  Tartib ataylab:
        Telegram bildirishnomasida rasm ko'rinadi, matn esa 4096 belgigacha
        — rasm izohining 1024 chegarasiga sig'maydi.  Rasm chizilmasa yoki
        yuborilmasa matn BARIBIR ketadi: grafik qo'shimcha, hisobot emas.
        """
        sent = 0
        texts: Dict[str, str] = {}
        markups: Dict[str, Dict[str, Any]] = {}
        images: Dict[str, Optional[bytes]] = {}
        captions: Dict[str, str] = {}
        for member in members:
            # A'zo hisobotni o'chirib qo'ygan bo'lishi mumkin (panel
            # sozlamasi) — hurmat qilamiz.
            if member.get("digest_muted"):
                continue
            lang = i18n.normalize(member.get("language")) or i18n.DEFAULT_LANG
            if lang not in texts:
                texts[lang] = build(lang)
                if self.panel_url:
                    markups[lang] = botfmt.panel_button(self.panel_url, lang)
            if image is not None and self.photo_sender is not None and lang not in images:
                try:
                    # Chizish sinxron CPU ishi — halqani to'xtatmasin.
                    images[lang] = await asyncio.to_thread(image, lang)
                    captions[lang] = (caption(lang) if caption else "")[:1024]
                except Exception:  # noqa: BLE001 — rasm xabarni yiqitmasin
                    logger.warning("Hisobot grafigi chizilmadi: site=%s", site_id, exc_info=True)
                    images[lang] = None
            text = texts[lang]
            markup = markups.get(lang)
            photo = images.get(lang)
            if photo and self.photo_sender is not None:
                try:
                    await self.photo_sender(str(member["telegram_id"]), photo, captions.get(lang, ""))
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "Hisobot grafigi yuborilmadi: site=%s member=%s",
                        site_id,
                        member["id"],
                        exc_info=True,
                    )
            try:
                if markup:
                    await self.sender(str(member["telegram_id"]), text, reply_markup=markup)
                else:
                    await self.sender(str(member["telegram_id"]), text)
                sent += 1
            except Exception:
                logger.warning(
                    "Hisobot yuborilmadi: site=%s member=%s",
                    site_id,
                    member["id"],
                    exc_info=True,
                )
        return sent

    def _quiet_reason(self, site: Dict[str, Any]) -> Optional[str]:
        """Ma'lumotsiz sayt uchun ANIQ sabab KALITI; sabab noma'lum — None.

        Kalit qaytadi, matn emas: matn a'zoning tilida `_deliver` ichida
        yasaladi.

        Do'kon shunchaki yopiq bo'lishi ham mumkin — bunda jim qolamiz.
        Faqat tuzatsa bo'ladigan holat aytiladi: qurilma ulanmagan/oflayn
        yoki kirish chizig'i chizilmagan.
        """
        site_id = str(site["id"])
        connection = str(site.get("connection") or "")
        if connection == "not_paired":
            return "digest.quiet.not_paired"
        if connection == "offline":
            return "digest.quiet.offline"
        try:
            config = self.events.get_site_config(site_id)["config"]
        except Exception:
            return None
        # Lokal sehrgarda chizilgan chiziq cloud config'da ko'rinmaydi —
        # yaqinda sanash bo'lgan saytga "chizilmagan" deyish yolg'on.
        if not (config.get("lines") or []) and not self.events.has_recent_line_crossings(site_id):
            return "digest.quiet.no_line"
        return None

    async def check_once(self, now: datetime | None = None) -> int:
        now = now or datetime.now(ZoneInfo("Asia/Tashkent"))
        if now.tzinfo is None:
            now = now.replace(tzinfo=ZoneInfo("Asia/Tashkent"))
        sent = 0
        sent += await self._weekly_once(now)
        sent += await self._monthly_shifts_once(now)
        sent += await self._monthly_value_once(now)
        sent += await self._renewal_once(now)
        if now.hour < self.hour:
            return sent
        digest_date = now.date().isoformat()
        for site in self.sites():
            site_id = str(site["id"])
            members = self.events.list_members(site_id)
            if not members:
                continue
            if self.events.digest_was_sent(site_id, digest_date):
                continue
            stats = self.events.stats(site_id, day=now.date())
            report = self.events.retail_report(site_id, day=now.date())
            # Bo'sh kun uchun "Kirdi: 0" xabari — shovqin: qurilma hali
            # ulanmagan yoki do'kon yopiq bo'lgan kunlarda bot bekorga
            # yozib turardi.  Ma'lumot yo'q — xabar ham yo'q.
            #
            # LEKIN butunlay jim qolish ham xato edi: sabab ANIQ bo'lsa
            # (chiziq chizilmagan / qurilma ko'rinmayapti) ega buni
            # bilmasa, "mahsulot buzilgan" deb o'ylab qoladi.  Shunday
            # saytga haftada bir marta (dushanba) sabab tushuntiriladi.
            traffic = (report.get("traffic") or {}) if isinstance(report, dict) else {}
            if not stats.get("total") and not traffic.get("entered"):
                if now.weekday() == 0:
                    reason = self._quiet_reason(site)
                    if reason:
                        sent += await self._deliver(
                            site_id, members, lambda lang, key=reason: tg(lang, key)
                        )
                self.events.mark_digest_sent(site_id, digest_date)
                continue
            open_from = None
            queue_configured = False
            try:
                config = self.events.get_site_config(site_id)["config"]
                open_from = config.get("open_from") or None
                # Navbat zonasi chizilganmi — ball uchun SHART: zonasiz
                # `queue_threshold_exceeded` hech qachon chiqmaydi, ya'ni
                # "0 ta signal" mukammal navbat degani emas.
                queue_configured = any(
                    bool(zone.get("queue"))
                    for zone in (config.get("zones") or [])
                    if isinstance(zone, dict)
                )
            except Exception:
                open_from = None
            first_movement = (
                self.events.first_movement_time(site_id, day=now.date()) if open_from else None
            )
            # `list_sites()` aloqa holati va kamera sonini allaqachon
            # beradi — ball uchun qo'shimcha so'rov kerak emas.
            try:
                score = trust_score.score(
                    report=report,
                    shifts=self.events.shift_summary(
                        site_id, start=now.date(), end=now.date()
                    ),
                    minutes_since_seen=site.get("minutes_since_seen"),
                    cameras_active=int(site.get("cameras_active") or 0),
                    cameras_expected=int(site.get("cameras_expected") or 0),
                    queue_configured=queue_configured,
                )
            except Exception:  # noqa: BLE001 — ball xabarni yiqitmasin
                logger.exception("Ishonch ballini hisoblab bo'lmadi: %s", site_id)
                score = None
            receipts = (self.events.daily_sales(site_id, now.date()) or {}).get("receipts")

            def build(lang: str, *, site=site, stats=stats, report=report) -> str:
                return build_digest(
                    str(site["name"]),
                    digest_date,
                    stats,
                    report,
                    open_from=open_from,
                    first_movement=first_movement,
                    score=score,
                    daily_revenue_uzs=int(site.get("avg_daily_revenue_uzs") or 0),
                    receipts=receipts,
                    lang=lang,
                )

            # Belgi YUBORISHDAN OLDIN qo'yiladi.  `mark_digest_sent`
            # `ON CONFLICT DO NOTHING` bilan ishlaydi va "men birinchi
            # bo'ldim" ni qaytaradi, ya'ni atomik navbat.  Ilgari tartib
            # teskari edi (tekshir → yubor → belgila) va ikkita worker
            # bir vaqtda "yuborilmagan" deb ko'rib, mijozga kunlik
            # hisobot IKKI MARTA ketardi.
            #
            # Yuborish yiqilsa belgi ochiladi — keyingi aylanish qayta
            # uradi.  Yagona ochiq xavf: belgi qo'yilib, jarayon aynan
            # yuborish paytida qulasa o'sha kunlik hisobot yo'qoladi.
            # Bu oyna bir necha soniya va yetakchi qulfi (`cloud/leader.py`)
            # tufayli deyarli yopiq; ikki marta yuborishdan esa
            # bir marta yubormaslik afzal — takroriy xabar ishonchni
            # yo'qotadi, kechikkan xabar esa yo'q.
            if not self.events.mark_digest_sent(site_id, digest_date):
                continue

            def image(lang: str, *, site=site, report=report) -> bytes:
                return chartimg.daily_png(report, lang, site_name=str(site["name"]))

            def caption(lang: str, *, site=site, report=report) -> str:
                return tg(
                    lang,
                    "digest.daily.caption",
                    site=botfmt.header(str(site["name"])),
                    day=botfmt.day_title(digest_date + "T12:00:00+05:00", lang) or digest_date,
                    count=botfmt.number(int((report.get("traffic") or {}).get("entered") or 0), lang),
                )

            site_sent = await self._deliver(site_id, members, build, image=image, caption=caption)
            if site_sent:
                sent += site_sent
            else:
                self.events.unmark_digest_sent(site_id, digest_date)
        return sent

    async def _renewal_once(self, now: datetime) -> int:
        """Obuna tugashidan oldin mijozga eslatma.

        Belgi obuna TUGASH SANASIGA bog'lanadi (`renew-2026-09-20-7`), bugungi
        sanaga emas.  Sababi: mijoz to'lagach `extend_subscription` sanani
        siljitadi, ya'ni keyingi davr uchun belgilar O'ZI yangi bo'ladi va
        eslatmalar qaytadan ishlaydi.  Tozalash ishi ham, belgining muddati
        ham kerak emas.

        Faqat `owner` roliga yuboriladi: hisobni do'kon egasi to'laydi,
        sotuvchini bezovta qilishning ma'nosi yo'q.
        """
        if now.hour < RENEWAL_HOUR:
            return 0
        sent = 0
        for site in self.sites():
            status = str(site.get("license_status") or "")
            days_left = site.get("days_left")
            if status == "active" and isinstance(days_left, int):
                if days_left <= 1:
                    stage = "1"
                elif days_left <= RENEWAL_FIRST_DAYS:
                    # `days_left` — butun songa kesilgan farq, ya'ni bir qiymat
                    # tik chegarasida sakrab o'tishi mumkin.  Shuning uchun
                    # `<=`, `==` emas.
                    stage = "7"
                else:
                    continue
            elif status == "grace":
                stage = "grace"
            else:
                # expired/suspended — eslatma bermaymiz.  Bu bosqichda
                # gap avtomatik xabarda emas, qo'ng'iroqda.
                continue

            site_id = str(site["id"])
            until = str(site.get("subscription_until") or "")[:10]
            if not until:
                continue
            marker = f"renew-{until}-{stage}"
            if self.events.digest_was_sent(site_id, marker):
                continue
            owners = [m for m in self.events.list_members(site_id) if m.get("role") == "owner"]
            if not owners:
                continue

            # Hisob-faktura DAVR bo'yicha ochiladi (`until`), bosqich
            # bo'yicha emas: bitta obuna davri uchun uchta eslatma
            # ketadi (7 kun, 1 kun, grace) va uchalasi ham AYNAN bir
            # hisobga ishora qilishi kerak — aks holda ega uchta
            # boshqa-boshqa raqam ko'rib, qaysi birini to'lashni
            # bilmasdi.
            pay_url = ""
            if self.renewal_invoice is not None:
                try:
                    pay_url = self.renewal_invoice(site_id, until) or ""
                except Exception:
                    # To'lov qatlamidagi nosozlik eslatmani to'xtatmasin:
                    # havolasiz xabar havolasiz xabardan yaxshiroq emas,
                    # lekin xabarsizdan yaxshiroq.
                    logger.warning("Eslatma uchun hisob ochilmadi: site=%s", site_id, exc_info=True)

            def build(lang: str, *, site=site, stage=stage, days_left=days_left, pay_url=pay_url) -> str:
                return build_renewal(
                    str(site["name"]),
                    stage=stage,
                    days_left=max(0, int(days_left or 0)),
                    monthly_uzs=int(site.get("monthly_price_uzs") or 0),
                    grace_days=GRACE_DAYS,
                    pay_url=pay_url,
                    lang=lang,
                )

            if not self.events.mark_digest_sent(site_id, marker):
                continue
            site_sent = await self._deliver(site_id, owners, build)
            if site_sent:
                sent += site_sent
            else:
                self.events.unmark_digest_sent(site_id, marker)
        return sent

    async def _weekly_once(self, now: datetime) -> int:
        """Dushanba ertalab o'tgan hafta xulosasi.

        Belgilash mavjud `daily_digests` jadvalida `2026-W34` ko'rinishida —
        yangi jadval kerak emas (PK site+date mos keladi).
        """
        if now.weekday() != WEEKLY_WEEKDAY or now.hour < WEEKLY_HOUR:
            return 0
        week_start = now.date() - timedelta(days=7)  # o'tgan dushanba
        week_end = now.date() - timedelta(days=1)  # kecha (yakshanba)
        iso_year, iso_week, _ = week_end.isocalendar()
        marker = f"{iso_year}-W{iso_week:02d}"
        sent = 0
        for site in self.sites():
            site_id = str(site["id"])
            members = self.events.list_members(site_id)
            if not members:
                continue
            if self.events.digest_was_sent(site_id, marker):
                continue
            trend = self.events.traffic_trend(site_id, days=7, until=week_end)
            if not trend.get("total"):
                self.events.mark_digest_sent(site_id, marker)
                continue
            queue_alerts = 0
            queue_longest = 0
            for offset in range(7):
                report = self.events.retail_report(site_id, day=week_start + timedelta(days=offset))
                queue = report.get("queue") or {}
                queue_alerts += int(queue.get("alerts") or 0)
                queue_longest = max(queue_longest, int(queue.get("longest") or 0))
            uptime = self.events.camera_uptime_percent(site_id, start=week_start, end=week_end)

            def build(
                lang: str,
                *,
                site=site,
                trend=trend,
                queue_alerts=queue_alerts,
                queue_longest=queue_longest,
                uptime=uptime,
            ) -> str:
                return build_weekly(
                    str(site["name"]),
                    trend=trend,
                    queue_alerts=queue_alerts,
                    queue_longest=queue_longest,
                    uptime_percent=uptime,
                    lang=lang,
                )

            if not self.events.mark_digest_sent(site_id, marker):
                continue

            def image(lang: str, *, site=site, trend=trend) -> bytes:
                return chartimg.weekly_png(trend, lang, site_name=str(site["name"]))

            def caption(lang: str, *, site=site, trend=trend) -> str:
                return tg(
                    lang,
                    "digest.weekly.caption",
                    site=botfmt.header(str(site["name"])),
                    count=botfmt.number(int(trend.get("total") or 0), lang),
                )

            site_sent = await self._deliver(site_id, members, build, image=image, caption=caption)
            if site_sent:
                sent += site_sent
            else:
                self.events.unmark_digest_sent(site_id, marker)
        return sent

    async def _monthly_shifts_once(self, now: datetime) -> int:
        """Oyning 1-kuni — o'tgan oyning smena hisoboti.

        Belgilash mavjud `daily_digests` jadvalida `2026-07-smena`
        ko'rinishida: yangi jadval kerak emas va qayta yuborilmaydi.

        Davomat o'chirilgan yoki xodimi yo'q do'konga xabar KETMAYDI —
        bo'sh hisobot shovqin.
        """
        if now.day != MONTHLY_DAY or now.hour < MONTHLY_HOUR:
            return 0
        last_day = now.date().replace(day=1) - timedelta(days=1)
        first_day = last_day.replace(day=1)
        marker = f"{first_day:%Y-%m}-smena"
        sent = 0
        for site in self.sites():
            site_id = str(site["id"])
            # Smena hisobotida xodim ISMLARI va ularning kelish-ketish
            # vaqti bor — ya'ni `/owner/attendance` qulflaydigan narsaning
            # o'zi, faqat boshqa kanal orqali.  Marshrutni yopib bu yerni
            # ochiq qoldirish qulfni bezakka aylantirardi: menejer o'sha
            # jadvalni har oy Telegramda olaverardi.
            members = [
                member
                for member in self.events.list_members(site_id)
                if str(member.get("role") or "") in BIOMETRIC_ROLES
            ]
            if not members:
                continue
            if self.events.digest_was_sent(site_id, marker):
                continue
            try:
                summary = self.events.shift_summary(site_id, start=first_day, end=last_day)
            except Exception:
                logger.warning("Smena hisoboti hisoblanmadi: site=%s", site_id, exc_info=True)
                continue
            if not summary.get("employees"):
                self.events.mark_digest_sent(site_id, marker)
                continue

            def build(lang: str, *, site=site, summary=summary) -> str:
                return build_shifts(str(site["name"]), f"{first_day:%Y-%m}", summary, lang=lang)

            if not self.events.mark_digest_sent(site_id, marker):
                continue
            site_sent = await self._deliver(site_id, members, build)
            if site_sent:
                sent += site_sent
            else:
                self.events.unmark_digest_sent(site_id, marker)
        return sent

    async def _monthly_value_once(self, now: datetime) -> int:
        """Oyning 1-kuni — «ENES o'zini qopladimi» cheki.

        Obunani uzaytirish qarori aynan shu savolga bog'liq, shuning
        uchun bu xabar mahsulotning eng muhim xabarlaridan biri.

        Xabar FAQAT mijoz o'z savdosini aytgan bo'lsa ketadi — usiz
        yo'qotishni hisoblab bo'lmaydi va taxminan taxmin qilish
        yolg'on bo'lardi.
        """
        if now.day != MONTHLY_DAY or now.hour < MONTHLY_HOUR:
            return 0
        last_day = now.date().replace(day=1) - timedelta(days=1)
        first_day = last_day.replace(day=1)
        marker = f"{first_day:%Y-%m}-qiymat"
        sent = 0
        for site in self.sites():
            site_id = str(site["id"])
            revenue = int(site.get("avg_daily_revenue_uzs") or 0)
            if not revenue:
                continue
            members = self.events.list_members(site_id)
            if not members:
                continue
            if self.events.digest_was_sent(site_id, marker):
                continue
            try:
                inputs = self.events.value_inputs(site_id, start=first_day, end=last_day)
            except Exception:
                logger.warning("Oylik qiymat hisoblanmadi: site=%s", site_id, exc_info=True)
                continue
            days = (last_day - first_day).days + 1
            cost = value.queue_cost(
                queue_episodes=inputs["queue_episodes"],
                # Oylik savdo = kunlik savdo × kunlar; tashrif ham oylik.
                # Ya'ni "har tashrif o'rtacha X so'm" oy bo'yicha chiqadi.
                daily_revenue_uzs=revenue * days,
                visitors=inputs["visitors"],
            )
            if not cost:
                # Yo'qotish topilmadi — maqtanadigan narsa yo'q, jim
                # turamiz va belgini qo'yamiz (qayta urinmaslik uchun).
                self.events.mark_digest_sent(site_id, marker)
                continue

            def build(lang: str, *, site=site, cost=cost) -> str:
                return value.monthly_receipt(
                    site_name=str(site["name"]),
                    month_label=f"{first_day:%Y-%m}",
                    lost_uzs=cost["lost_uzs"],
                    monthly_price_uzs=int(site.get("monthly_price_uzs") or 0),
                    lang=lang,
                )

            if not self.events.mark_digest_sent(site_id, marker):
                continue
            site_sent = await self._deliver(site_id, members, build)
            if site_sent:
                sent += site_sent
            else:
                self.events.unmark_digest_sent(site_id, marker)
        return sent

    async def run(self) -> None:
        while True:
            try:
                if self.is_leader is None or self.is_leader():
                    await self.check_once()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Hisobot siklida xato")
            await asyncio.sleep(60)
