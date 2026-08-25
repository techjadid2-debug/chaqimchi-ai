"""Owner va managerlarga Asia/Tashkent bo'yicha Telegram hisobotlar.

Uch xil hisobot:
- **Kunlik** — har kuni kechqurun (standart 21:00): bugungi raqamlar.
- **Haftalik** — dushanba ertalab (09:00): o'tgan hafta xulosasi,
  kunlar grafigi, taqqos va kamera uptime.
- **Oylik smena** — oyning 1-kuni (10:00): o'tgan oyda kim qancha
  kechikdi va necha kun kelmadi.  Faqat davomat yoqilgan do'konda.

Uslub `cloud/botfmt.py`da — bot xabarlari bir xil ko'rinishda bo'lsin.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

from cloud import botfmt, trust_score, value
from cloud.event_store import EventStore
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


def _duration(seconds: float) -> str:
    return f"{int(seconds // 60)} daq" if seconds >= 60 else f"{int(seconds)} s"


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

    # Birinchi qator — KUNNING HOLATI, hisobot sarlavhasi emas.
    #
    # Do'kon egasi telefonda xabarning faqat birinchi qatorini ko'radi
    # (bildirishnoma shuni ko'rsatadi).  "kunlik hisobot" unga hech narsa
    # aytmaydi; "Bugun: 94 — A'lo kun" esa xabarni ochmasdan ham javob
    # beradi.  Ball yo'q bo'lsa eski sarlavha qoladi.
    if score and score.get("available"):
        headline = f"🏪 {botfmt.header(site_name)} — Bugun: <b>{score['total']}</b>"
        subtitle = trust_score.label(score["total"])
    elif score:
        headline = f"🏪 {botfmt.header(site_name)}"
        subtitle = str(score.get("reason") or "")
    else:
        headline = f"📊 {botfmt.header(site_name)} — kunlik hisobot"
        subtitle = ""

    lines = [headline, botfmt.day_title(day + "T12:00:00+05:00") or day]
    if subtitle:
        lines.append(subtitle)
    lines += ["", f"👥 Kirdi: <b>{botfmt.number(traffic['entered'])}</b> kishi"]

    change = traffic.get("change_percent")
    if change is not None:
        arrow = "▲" if change >= 0 else "▼"
        lines.append(
            f"Kechagiga nisbatan: {arrow} {abs(change)}% (kecha {traffic['entered_yesterday']})"
        )
    busiest = traffic.get("busiest_hour")
    if busiest:
        lines.append(f"Gavjum soat: {busiest['hour']:02d}:00 — {busiest['entered']} kishi")

    # Demografiya — faqat ma'lumot yig'ilgan kunda (xodimlar hisobga
    # kirmaydi, ular davomatda).
    demografiya = report.get("demografiya") or {}
    if demografiya.get("hisoblangan"):
        jins = demografiya.get("jins") or {}
        yosh = demografiya.get("yosh") or {}
        line = f"🚻 {jins.get('ayol', 0)}% ayol · {jins.get('erkak', 0)}% erkak"
        if any(yosh.values()):
            top_age = max(yosh, key=lambda key: yosh[key])
            line += f" · asosan {top_age} yosh"
        lines.append(line)

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
            mark = " ⚠️ kechikish" if late else ""
            lines.append(f"🕘 Ochilish: {opened} (jadval: {open_from}){mark}")

    queue = report["queue"]
    if queue["alerts"]:
        parts = [f"{queue['alerts']} marta chegaradan oshdi"]
        if queue.get("average"):
            parts.append(f"o'rtacha {queue['average']} kishi")
        parts.append(f"eng uzuni {queue['longest']} kishi ({queue['longest_at']})")
        lines.append("🧾 Navbat: " + ", ".join(parts))
        # Navbat raqami o'z-o'zidan hech narsa aytmaydi — "5 marta uzun
        # bo'ldi" do'kon egasiga NIMA turishini bildirmaydi.  Mijoz
        # kunlik savdosini aytgan bo'lsa, o'sha raqam so'mga aylanadi.
        # Aytmagan bo'lsa qator umuman chiqmaydi (`daily_line` -> None).
        money = value.daily_line(report, daily_revenue_uzs)
        if money:
            lines.append(money)
    if report["dwell"]:
        top = report["dwell"][0]
        lines.append(
            f"📍 Ko'p to'xtalgan zona: {botfmt.escape(top['zone'])} — {top['count']} marta, "
            f"o'rtacha {_duration(top['average_sec'])}"
        )

    security = report["security"]
    alarms = []
    if security["camera_tampered"]:
        alarms.append(f"{security['camera_tampered']} marta kamera buzilgan")
    if security["after_hours_presence"]:
        alarms.append(f"{security['after_hours_presence']} marta ish vaqtidan tashqari harakat")
    if security["restricted_zone"]:
        alarms.append(f"{security['restricted_zone']} marta taqiqlangan zona")
    if security.get("loitering"):
        alarms.append(f"{security['loitering']} marta uzoq turish")
    if alarms:
        lines.append("⚠️ " + ", ".join(alarms))

    return "\n".join(lines)


def _minutes(clock_value: str) -> int:
    try:
        hours, minutes = str(clock_value).split(":", 1)
        return int(hours) * 60 + int(minutes)
    except (ValueError, AttributeError):
        return 0


def build_shifts(site_name: str, month_label: str, summary: Dict[str, Any]) -> str:
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
        f"🗓 {botfmt.header(site_name)} — {botfmt.escape(month_label)} smena hisoboti",
        "",
    ]
    if not late_minutes and not total.get("kelmagan_kunlar"):
        lines.append("✅ Kechikish ham, kelmagan kun ham yo'q.")
        return "\n".join(lines)

    hours, minutes = divmod(late_minutes, 60)
    total_label = f"{hours} soat {minutes} daq" if hours else f"{minutes} daq"
    lines.append(f"⏰ Jami kechikish: <b>{botfmt.escape(total_label)}</b>")
    if total.get("kelmagan_kunlar"):
        lines.append(f"🚫 Kelmagan kunlar: <b>{total['kelmagan_kunlar']}</b>")

    top = [row for row in (summary.get("rows") or []) if row.get("jami_kechikish_daq")][:3]
    if top:
        lines.append("")
        for row in top:
            lines.append(
                f"• {botfmt.escape(row['employee_name'])} — "
                f"{row['kechikkan_kunlar']} kun, {row['jami_kechikish_daq']} daq"
            )
    lines.append("")
    lines.append("To'liq jadval va CSV — mijoz panelidagi «Xodimlar» bo'limida.")
    return "\n".join(lines)


def build_renewal(
    site_name: str,
    *,
    stage: str,
    days_left: int,
    monthly_uzs: int,
    grace_days: int,
) -> str:
    """Obuna tugashi haqida mijozga eslatma va yillik taklif.

    Bungacha obuna tugashini FAQAT xodim ko'rardi (admin panelidagi
    "e'tibor talab qiladi" ro'yxati).  Mijozga hech qanday xabar
    bormasdi — u to'lashni unutib, grace'ga tushib, keyin tizim
    o'chganda "buzildi" deb o'ylardi.

    Yillik summa `billable_months()` dan hisoblanadi — saytdagi
    "2 oy bepul" va'dasi, hisob-faktura va bu xabar bitta qoidadan
    chiqishi shart.
    """
    charged = billable_months(12)
    annual = monthly_uzs * charged
    saving = monthly_uzs * (12 - charged)

    if stage == "grace":
        lines = [
            f"⏳ {botfmt.header(site_name)} — obuna muddati tugadi",
            "",
            f"Tizim yana <b>{grace_days} kun</b> ishlaydi. Shu vaqt ichida "
            f"to'lov qilinmasa, tahlil va ogohlantirishlar to'xtaydi.",
        ]
    elif stage == "1":
        lines = [
            f"⚠️ {botfmt.header(site_name)} — obuna ertaga tugaydi",
            "",
            f"To'lovdan keyin ham <b>{grace_days} kun</b> muhlat bor — "
            f"tizim darrov o'chmaydi.",
        ]
    else:
        lines = [
            f"🔔 {botfmt.header(site_name)} — obuna tugashiga {days_left} kun qoldi",
            "",
            f"Oylik to'lov: <b>{botfmt.number(monthly_uzs)}</b> so'm",
        ]

    lines += [
        "",
        f"💡 Yillik to'lasangiz <b>{12 - charged} oy bepul</b>: "
        f"{botfmt.number(annual)} so'm "
        f"(<b>{botfmt.number(saving)}</b> so'm tejaysiz)",
        "",
        "To'lovni panelda ochasiz.",
    ]
    return "\n".join(lines)


def build_weekly(
    site_name: str,
    *,
    trend: Dict[str, Any],
    queue_alerts: int,
    queue_longest: int,
    uptime_percent: Optional[float],
) -> str:
    """Haftalik xulosa — dushanba ertalab.

    Kunlik raqamlar tez unutiladi; hafta yakuni esa "ish qanday ketyapti"
    savoliga javob beradi va o'tgan hafta bilan taqqoslaydi.
    """
    lines = [
        f"🗓 {botfmt.header(site_name)} — haftalik hisobot",
        "",
        f"👥 Hafta davomida kirdi: <b>{botfmt.number(trend.get('total', 0))}</b> kishi "
        f"(kuniga o'rtacha {trend.get('average', 0)})",
    ]
    change = trend.get("change_percent")
    if change is not None:
        arrow = "▲" if change >= 0 else "▼"
        lines.append(f"O'tgan haftaga nisbatan: {arrow} {abs(change)}%")

    daily = trend.get("daily") or []
    chart = botfmt.sparkline([float(item.get("entered", 0)) for item in daily])
    if chart.strip():
        labels = " ".join(str(item.get("weekday", ""))[:2] for item in daily)
        lines.append(f"<code>{chart}</code>")
        lines.append(f"<code>{labels}</code>")

    busiest = trend.get("busiest_day")
    if busiest:
        lines.append(f"Eng gavjum kun: {busiest['weekday']} — {busiest['entered']} kishi")

    if queue_alerts:
        lines.append(f"🧾 Navbat: {queue_alerts} marta chegaradan oshdi, eng uzuni {queue_longest}")

    if uptime_percent is not None:
        icon = "✅" if uptime_percent >= 99 else "⚠️"
        lines.append(f"{icon} Kameralar ishlashi: {uptime_percent}%")

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
    ) -> None:
        self.events = events
        self.sites = sites
        self.sender = sender
        self.hour = hour
        self.panel_url = panel_url.rstrip("/")

    async def _deliver(self, site_id: str, members: List[Dict[str, Any]], text: str) -> int:
        markup = botfmt.panel_button(self.panel_url) if self.panel_url else None
        sent = 0
        for member in members:
            # A'zo hisobotni o'chirib qo'ygan bo'lishi mumkin (panel
            # sozlamasi) — hurmat qilamiz.
            if member.get("digest_muted"):
                continue
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
        """Ma'lumotsiz sayt uchun ANIQ sabab matni; sabab noma'lum — None.

        Do'kon shunchaki yopiq bo'lishi ham mumkin — bunda jim qolamiz.
        Faqat tuzatsa bo'ladigan holat aytiladi: qurilma ulanmagan/oflayn
        yoki kirish chizig'i chizilmagan.
        """
        site_id = str(site["id"])
        connection = str(site.get("connection") or "")
        if connection == "not_paired":
            return (
                "ℹ️ <b>Hisobot kelmayapti — qurilma hali ulanmagan.</b>\n"
                "Do'kon kompyuterida Chaqimchi AI o'rnatilib bulutga ulansa, "
                "kunlik hisobot shu yerga kela boshlaydi."
            )
        if connection == "offline":
            return (
                "ℹ️ <b>Hisobot kelmayapti — do'kon kompyuteri ko'rinmayapti.</b>\n"
                "Kompyuter yoqilganini va internet borligini tekshiring."
            )
        try:
            config = self.events.get_site_config(site_id)["config"]
        except Exception:
            return None
        if not (config.get("lines") or []):
            return (
                "ℹ️ <b>Kirish-chiqish hali sanalmayapti — kirish chizig'i chizilmagan.</b>\n"
                "Paneldagi «Chiziq va zonalar» bo'limida eshik ustiga chiziq "
                "qo'yilsa, o'sha kundan boshlab mijozlar sanaladi."
            )
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
                        sent += await self._deliver(site_id, members, reason)
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
            text = build_digest(
                str(site["name"]),
                digest_date,
                stats,
                report,
                open_from=open_from,
                first_movement=first_movement,
                score=score,
                daily_revenue_uzs=int(site.get("avg_daily_revenue_uzs") or 0),
            )
            site_sent = await self._deliver(site_id, members, text)
            if site_sent:
                self.events.mark_digest_sent(site_id, digest_date)
                sent += site_sent
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
            text = build_renewal(
                str(site["name"]),
                stage=stage,
                days_left=max(0, int(days_left or 0)),
                monthly_uzs=int(site.get("monthly_price_uzs") or 0),
                grace_days=GRACE_DAYS,
            )
            site_sent = await self._deliver(site_id, owners, text)
            if site_sent:
                self.events.mark_digest_sent(site_id, marker)
                sent += site_sent
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
            text = build_weekly(
                str(site["name"]),
                trend=trend,
                queue_alerts=queue_alerts,
                queue_longest=queue_longest,
                uptime_percent=uptime,
            )
            site_sent = await self._deliver(site_id, members, text)
            if site_sent:
                self.events.mark_digest_sent(site_id, marker)
                sent += site_sent
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
            members = self.events.list_members(site_id)
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
            text = build_shifts(str(site["name"]), f"{first_day:%Y-%m}", summary)
            site_sent = await self._deliver(site_id, members, text)
            if site_sent:
                self.events.mark_digest_sent(site_id, marker)
                sent += site_sent
        return sent

    async def _monthly_value_once(self, now: datetime) -> int:
        """Oyning 1-kuni — «Chaqimchi o'zini qopladimi» cheki.

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
            text = value.monthly_receipt(
                site_name=str(site["name"]),
                month_label=f"{first_day:%Y-%m}",
                lost_uzs=cost["lost_uzs"],
                monthly_price_uzs=int(site.get("monthly_price_uzs") or 0),
            )
            site_sent = await self._deliver(site_id, members, text)
            if site_sent:
                self.events.mark_digest_sent(site_id, marker)
                sent += site_sent
        return sent

    async def run(self) -> None:
        while True:
            try:
                await self.check_once()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Hisobot siklida xato")
            await asyncio.sleep(60)
