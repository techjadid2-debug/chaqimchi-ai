"""Owner va managerlarga Asia/Tashkent bo'yicha kundalik Telegram hisobot."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List
from zoneinfo import ZoneInfo

from cloud.event_store import EventStore

logger = logging.getLogger(__name__)


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
            by_type = stats["by_type"]
            text = (
                f"📊 Chaqimchi AI — {site['name']}\n"
                f"Sana: {digest_date}\n"
                f"Jami hodisa: {stats['total']}\n"
                f"Odam: {by_type.get('person_detected', 0)}\n"
                f"Xodim: {by_type.get('employee_seen', 0)}\n"
                f"Zona: {by_type.get('zone_entered', 0)}\n"
                f"Uzoq turish: {by_type.get('loitering', 0)}\n"
                f"Limit oshishi: {by_type.get('occupancy_exceeded', 0)}"
            )
            site_sent = 0
            for member in members:
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
