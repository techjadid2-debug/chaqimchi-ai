"""Owner va managerlarga Asia/Tashkent bo'yicha Telegram hisobotlar.

Ikki xil hisobot:
- **Kunlik** — har kuni kechqurun (standart 21:00): bugungi raqamlar.
- **Haftalik** — dushanba ertalab (09:00): o'tgan hafta xulosasi,
  kunlar grafigi, taqqos va kamera uptime.

Uslub `cloud/botfmt.py`da — bot xabarlari bir xil ko'rinishda bo'lsin.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

from cloud import botfmt
from cloud.event_store import EventStore

logger = logging.getLogger(__name__)

#: Haftalik hisobot yuboriladigan kun (0 = dushanba) va soat.
WEEKLY_WEEKDAY = 0
WEEKLY_HOUR = 9


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
    lines = [
        f"📊 {botfmt.header(site_name)} — kunlik hisobot",
        botfmt.day_title(day + "T12:00:00+05:00") or day,
        "",
        f"👥 Kirdi: <b>{botfmt.number(traffic['entered'])}</b> kishi",
    ]

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

    async def check_once(self, now: datetime | None = None) -> int:
        now = now or datetime.now(ZoneInfo("Asia/Tashkent"))
        if now.tzinfo is None:
            now = now.replace(tzinfo=ZoneInfo("Asia/Tashkent"))
        sent = 0
        sent += await self._weekly_once(now)
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
            traffic = (report.get("traffic") or {}) if isinstance(report, dict) else {}
            if not stats.get("total") and not traffic.get("entered"):
                self.events.mark_digest_sent(site_id, digest_date)
                continue
            open_from = None
            try:
                config = self.events.get_site_config(site_id)["config"]
                open_from = config.get("open_from") or None
            except Exception:
                open_from = None
            first_movement = (
                self.events.first_movement_time(site_id, day=now.date()) if open_from else None
            )
            text = build_digest(
                str(site["name"]),
                digest_date,
                stats,
                report,
                open_from=open_from,
                first_movement=first_movement,
            )
            site_sent = await self._deliver(site_id, members, text)
            if site_sent:
                self.events.mark_digest_sent(site_id, digest_date)
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

    async def run(self) -> None:
        while True:
            try:
                await self.check_once()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Hisobot siklida xato")
            await asyncio.sleep(60)
