"""Owner va managerlarga Asia/Tashkent bo'yicha kundalik Telegram hisobot."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List
from zoneinfo import ZoneInfo

from cloud.event_store import EventStore

logger = logging.getLogger(__name__)


def _duration(seconds: float) -> str:
    return f"{int(seconds // 60)} daq" if seconds >= 60 else f"{int(seconds)} s"


def build_digest(site_name: str, day: str, stats: Dict[str, Any], report: Dict[str, Any]) -> str:
    """Kunlik xabar matni.

    Xom hodisa sanog'i ("person_detected: 412") do'kon egasiga hech narsa
    aytmaydi.  Xabar uning savollariga javob beradi: nechta odam kirdi, kecha
    bilan taqqoslaganda qanday, qaysi soat gavjum, navbat qancha bo'ldi.

    Xavfsizlik hodisalari **oxirida va faqat bo'lsa** yoziladi — har kuni
    "0 ta buzilish" deb yozish xabarni uzaytiradi va o'qilmay qoladi.
    """
    traffic = report["traffic"]
    lines = [f"📊 {site_name} — {day}", f"Kirdi: {traffic['entered']} kishi"]

    change = traffic.get("change_percent")
    if change is not None:
        arrow = "▲" if change >= 0 else "▼"
        lines.append(f"Kechagiga nisbatan: {arrow} {abs(change)}% ({traffic['entered_yesterday']})")
    busiest = traffic.get("busiest_hour")
    if busiest:
        lines.append(f"Gavjum soat: {busiest['hour']:02d}:00 — {busiest['entered']} kishi")

    queue = report["queue"]
    if queue["alerts"]:
        lines.append(
            f"Navbat: {queue['alerts']} marta uzun, eng uzuni {queue['longest']} kishi "
            f"({queue['longest_at']})"
        )
    if report["dwell"]:
        top = report["dwell"][0]
        lines.append(
            f"Ko'p to'xtalgan zona: {top['zone']} — {top['count']} marta, "
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

    attendance = report.get("attendance") or {}
    if attendance.get("employees"):
        summary = attendance["summary"]
        lines.append(
            "👥 Davomat: "
            f"{summary['present']} keldi, {summary['absent']} kelmadi, "
            f"{summary['late']} kechikdi"
        )
        if summary.get("checkout_missing"):
            lines.append(f"Chiqishi aniqlanmagan: {summary['checkout_missing']} xodim")

    lines.append(f"Jami hodisa: {stats['total']}")
    return "\n".join(lines)


class DailyDigestService:
    def __init__(
        self,
        events: EventStore,
        sites: Callable[[], List[Dict[str, Any]]],
        sender: Callable[[str, str], Awaitable[None]],
        *,
        hour: int = 21,
    ) -> None:
        self.events = events
        self.sites = sites
        self.sender = sender
        self.hour = hour

    async def check_once(self, now: datetime | None = None) -> int:
        now = now or datetime.now(ZoneInfo("Asia/Tashkent"))
        if now.tzinfo is None:
            now = now.replace(tzinfo=ZoneInfo("Asia/Tashkent"))
        if now.hour < self.hour:
            return 0
        digest_date = now.date().isoformat()
        sent = 0
        for site in self.sites():
            site_id = str(site["id"])
            members = self.events.list_members(site_id)
            if not members:
                continue
            if self.events.digest_was_sent(site_id, digest_date):
                continue
            stats = self.events.stats(site_id, day=now.date())
            report = self.events.retail_report(site_id, day=now.date())
            report["attendance"] = self.events.attendance_report(
                site_id, start=now.date(), end=now.date(), now=now
            )
            # Bo'sh kun uchun "Kirdi: 0" xabari — shovqin: qurilma hali
            # ulanmagan yoki do'kon yopiq bo'lgan kunlarda bot bekorga
            # yozib turardi.  Ma'lumot yo'q — xabar ham yo'q.
            traffic = (report.get("traffic") or {}) if isinstance(report, dict) else {}
            if not stats.get("total") and not traffic.get("entered"):
                self.events.mark_digest_sent(site_id, digest_date)
                continue
            text = build_digest(str(site["name"]), digest_date, stats, report)
            site_sent = 0
            for member in members:
                # A'zo kunlik hisobotni o'chirib qo'ygan bo'lishi mumkin
                # (panel sozlamasi) — hurmat qilamiz.
                if member.get("digest_muted"):
                    continue
                try:
                    await self.sender(str(member["telegram_id"]), text)
                    sent += 1
                    site_sent += 1
                except Exception:
                    logger.warning(
                        "Kundalik hisobot yuborilmadi: site=%s member=%s",
                        site_id,
                        member["id"],
                        exc_info=True,
                    )
            if site_sent:
                self.events.mark_digest_sent(site_id, digest_date)
        return sent

    async def run(self) -> None:
        while True:
            try:
                await self.check_once()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Daily digest siklida xato")
            await asyncio.sleep(60)
