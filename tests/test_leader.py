"""Fon vazifalari FAQAT bitta jarayonda yursin.

`lifespan` har uvicorn worker'ida oltita fon vazifasini ochadi.  Bitta
worker'da bu to'g'ri edi; `--workers 2` bilan mijoz kunlik hisobotni ikki
marta olardi, tozalash esa ikki jarayondan bir vaqtda o'chirardi.

Bu yerda ikki qatlam sinaladi: ijara (kim ishlaydi) va kunlik hisobotning
"avval belgila, keyin yubor" navbati (ijara almashsa ham ikki marta
ketmasin).
"""

from __future__ import annotations

import asyncio
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import List
from zoneinfo import ZoneInfo

import pytest

from cloud.digest import DailyDigestService
from cloud.event_store import EventStore
from cloud.leader import LeaderLease
from enes.event_models import EdgeEvent

DATABASE_URL = os.environ.get("ENES_TEST_DATABASE_URL", "").strip()
needs_postgres = pytest.mark.skipif(
    not DATABASE_URL, reason="ENES_TEST_DATABASE_URL qo'yilmagan"
)


# ── Ijara ────────────────────────────────────────────────────────────────


def _store(tmp_path: Path) -> EventStore:
    return EventStore(sqlite_path=tmp_path / "events.db")


def test_only_one_process_becomes_the_leader(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = LeaderLease(store, holder="worker-1")
    second = LeaderLease(store, holder="worker-2")

    assert first.acquire()
    assert not second.acquire()
    assert first.leading and not second.leading


def test_the_leader_keeps_its_lease_while_it_renews(tmp_path: Path, monkeypatch) -> None:
    store = _store(tmp_path)
    clock = {"now": 1_000}
    monkeypatch.setattr("cloud.leader.time.time", lambda: clock["now"])
    first = LeaderLease(store, holder="worker-1", ttl_sec=90)
    second = LeaderLease(store, holder="worker-2", ttl_sec=90)
    assert first.acquire()

    clock["now"] += 60
    assert first.acquire(), "o'z ijarasini uzaytira olsin"
    assert not second.acquire(), "tirik ijarani birov tortib olmasin"


def test_a_dead_leader_hands_over_after_the_ttl(tmp_path: Path, monkeypatch) -> None:
    """Yetakchi qulasa fon ishi to'xtab qolmasin — hech kim aralashmasdan."""
    store = _store(tmp_path)
    clock = {"now": 1_000}
    monkeypatch.setattr("cloud.leader.time.time", lambda: clock["now"])
    first = LeaderLease(store, holder="worker-1", ttl_sec=90)
    second = LeaderLease(store, holder="worker-2", ttl_sec=90)
    assert first.acquire()

    # worker-1 qulaydi: uzaytirmaydi.
    clock["now"] += 91
    assert second.acquire()
    assert store.lease_holder("background", now=clock["now"]) == "worker-2"


def test_release_frees_the_lease_at_once(tmp_path: Path) -> None:
    """Qayta ishga tushgan server 90 soniya kutib turmasin."""
    store = _store(tmp_path)
    first = LeaderLease(store, holder="worker-1")
    second = LeaderLease(store, holder="worker-2")
    assert first.acquire()

    first.release()

    assert not first.leading
    assert second.acquire()


def test_without_a_store_every_process_is_the_leader() -> None:
    """Bitta jarayonli ish (lokal server, testlar) avvalgidek yursin."""
    lease = LeaderLease()

    assert lease.leading
    assert lease.acquire()


def test_a_broken_database_does_not_take_leadership_away(tmp_path: Path) -> None:
    """Baza tushganda fon ishi bekorga to'xtamasin.

    Raqib ham ayni bazaga tegolmaydi, ya'ni ikki nusxa xavfi yo'q.
    """

    class _Sinmoq:
        def claim_lease(self, *args, **kwargs):
            raise RuntimeError("baza yo'q")

    store = _store(tmp_path)
    lease = LeaderLease(store, holder="worker-1")
    assert lease.acquire()

    lease.store = _Sinmoq()

    assert lease.acquire(), "yetakchi yetakchiligicha qolsin"


def test_a_broken_database_does_not_promote_a_follower(tmp_path: Path) -> None:
    class _Sinmoq:
        def claim_lease(self, *args, **kwargs):
            raise RuntimeError("baza yo'q")

    store = _store(tmp_path)
    first = LeaderLease(store, holder="worker-1")
    second = LeaderLease(store, holder="worker-2")
    assert first.acquire()
    assert not second.acquire()

    second.store = _Sinmoq()

    assert not second.acquire(), "ergashuvchi xato tufayli yetakchi bo'lib qolmasin"


@needs_postgres
def test_the_lease_works_on_postgres() -> None:
    """Haqiqiy baza: `ON CONFLICT ... DO UPDATE ... WHERE` shu yerda sinaladi."""
    store = EventStore(database_url=DATABASE_URL)
    store.release_lease("sinov", "worker-1")
    store.release_lease("sinov", "worker-2")
    first = LeaderLease(store, name="sinov", holder="worker-1")
    second = LeaderLease(store, name="sinov", holder="worker-2")

    assert first.acquire()
    assert not second.acquire()
    first.release()
    assert second.acquire()
    second.release()


# ── Kunlik hisobot ikki marta ketmasin ───────────────────────────────────


DAY = date(2026, 9, 8)


def _moment(hour: int, minute: int) -> str:
    local = datetime(DAY.year, DAY.month, DAY.day, hour, minute, tzinfo=ZoneInfo("Asia/Tashkent"))
    return local.astimezone(timezone.utc).isoformat()


def _evening() -> datetime:
    return datetime(DAY.year, DAY.month, DAY.day, 21, 30, tzinfo=ZoneInfo("Asia/Tashkent"))


def _busy_store(tmp_path: Path) -> EventStore:
    store = EventStore(sqlite_path=tmp_path / "events.db")
    store.ingest(
        "site-1",
        "device-1",
        [
            EdgeEvent(
                event_type="line_crossed",
                camera_id="eshik-01",
                direction="in",
                line="eshik",
                occurred_at=_moment(10, index),
            )
            for index in range(5)
        ],
    )
    store.add_member("site-1", "111", role="owner")
    return store


def _service(store: EventStore, sent: List, *, is_leader=None) -> DailyDigestService:
    async def sender(chat_id, text):
        sent.append((chat_id, text))

    return DailyDigestService(
        store,
        lambda: [{"id": "site-1", "name": "Oq Saroy"}],
        sender,
        is_leader=is_leader,
    )


async def _one_pass(service: DailyDigestService) -> None:
    """Halqani bitta aylanishga qo'yib yuboradi.

    `run()` predikatni tekshiradi va keyin 60 soniya uxlaydi — ya'ni
    bir necha event-loop navbatidan keyin uni bekor qilsa bo'ladi.
    """
    task = asyncio.create_task(service.run())
    for _ in range(10):
        await asyncio.sleep(0)
    task.cancel()


def test_a_follower_does_not_run_the_digest_check(tmp_path: Path) -> None:
    """Ergashuvchi worker'da halqa yuradi, ish esa bajarilmaydi.

    Testning tishi bor: AYNI harness yetakchi bilan tekshiruvni chaqiradi.
    """

    def passes(is_leader) -> int:
        calls: List = []
        service = _service(tmp_path and _busy_store(tmp_path), [], is_leader=is_leader)

        async def spy(now=None):
            calls.append(1)
            return 0

        service.check_once = spy
        asyncio.run(_one_pass(service))
        return len(calls)

    assert passes(lambda: False) == 0
    assert passes(lambda: True) == 1


def test_two_workers_send_the_digest_only_once(tmp_path: Path) -> None:
    """Ijara almashgan lahzada ham mijozga bitta xabar ketsin.

    Belgi YUBORISHDAN OLDIN qo'yiladi (`ON CONFLICT DO NOTHING`), ya'ni
    ikkinchi jarayon "men birinchi emasman" deb o'tib ketadi.  Ilgari
    tartib teskari edi va ikkalasi ham "yuborilmagan" deb ko'rardi.
    """
    store = _busy_store(tmp_path)
    sent: List = []
    first = _service(store, sent)
    second = _service(store, sent)

    asyncio.run(first.check_once(_evening()))
    asyncio.run(second.check_once(_evening()))

    assert len(sent) == 1


def test_a_failed_delivery_is_retried_next_time(tmp_path: Path) -> None:
    """Telegram yiqilsa belgi ochilsin — kunlik hisobot yo'qolmasin."""
    store = _busy_store(tmp_path)
    attempts = {"count": 0}

    async def flaky(chat_id, text):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("Telegram javob bermadi")

    service = DailyDigestService(
        store, lambda: [{"id": "site-1", "name": "Oq Saroy"}], flaky
    )

    asyncio.run(service.check_once(_evening()))
    assert not store.digest_was_sent("site-1", DAY.isoformat()), "belgi ochilsin"

    asyncio.run(service.check_once(_evening()))

    assert attempts["count"] == 2
    assert store.digest_was_sent("site-1", DAY.isoformat())
