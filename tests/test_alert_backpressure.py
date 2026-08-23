"""Ogohlantirish to'plami butun bulutni to'xtatib qo'ymasin.

2026-08-23 da jonli nosozlik bo'ldi.  Qurilma uzoq uzilishdan keyin
3587 ta eski hodisani qayta yubordi; ularning katta qismi
ogohlantirishga arziydigan turda edi.  Har biri fon vazifasi ochdi va
har vazifa rasm kelishini kutib bazaga o'nta SINXRON so'rov yubordi.

Postgres ulanishi hodisa halqasida ochiladi — u CPU yemaydi, lekin
halqani to'xtatadi.  Natijada butun bulut 20-45 soniyaga javob bermay
qoldi (CPU atigi 10% edi) va Caddy hamma so'rovni uzdi.
"""

from __future__ import annotations

import asyncio
import inspect
import time

import cloud.main as main


def test_alerts_are_capped_so_the_loop_can_breathe() -> None:
    """Bir vaqtda cheklangan sondagi ogohlantirish tayyorlanadi."""
    assert main.ALERT_CONCURRENCY >= 1

    async def exercise() -> int:
        peak = 0
        current = 0
        lock = asyncio.Lock()

        async def fake_once(site_id, events):
            nonlocal peak, current
            async with lock:
                current += 1
                peak = max(peak, current)
            await asyncio.sleep(0.05)
            async with lock:
                current -= 1

        original = main._notify_alert_once
        main._notify_alert_once = fake_once
        try:
            await asyncio.gather(*(main._notify_alert("s", []) for _ in range(30)))
        finally:
            main._notify_alert_once = original
        return peak

    peak = asyncio.run(exercise())
    assert peak <= 3, f"bir vaqtda {peak} ta ogohlantirish ishladi — to'siq ishlamayapti"


def test_the_snapshot_wait_never_queries_the_database_on_the_loop() -> None:
    """Rasm kutish sikli sinxron baza so'rovini halqada bajarmasin.

    Aynan shu joy nosozlikning markazi edi: har ogohlantirish uchun
    o'ntagacha `get_event_store().event(...)` chaqiruvi.
    """
    source = inspect.getsource(main._notify_alert_once)
    assert "get_event_store().event(" not in source, (
        "baza so'rovi to'g'ridan-to'g'ri chaqirilyapti — `asyncio.to_thread` orqali bo'lsin"
    )
    assert "asyncio.to_thread" in source


def test_a_slow_alert_does_not_delay_unrelated_work() -> None:
    """Sekin ogohlantirish paytida boshqa ish darhol bajarilsin."""

    async def exercise() -> float:
        async def slow_once(site_id, events):
            await asyncio.sleep(0.4)

        original = main._notify_alert_once
        main._notify_alert_once = slow_once
        try:
            alerts = [asyncio.create_task(main._notify_alert("s", [])) for _ in range(10)]
            await asyncio.sleep(0)  # ular boshlanib ulgursin
            tick = time.monotonic()
            await asyncio.sleep(0.01)
            elapsed = time.monotonic() - tick
            await asyncio.gather(*alerts)
            return elapsed
        finally:
            main._notify_alert_once = original

    assert asyncio.run(exercise()) < 0.2, "halqa ogohlantirishlar bilan band bo'lib qoldi"


def test_the_gate_is_per_event_loop() -> None:
    """Modul darajasidagi bitta semafor birinchi halqaga bog'lanib qolardi.

    Test buni ushladi: ikkinchi `asyncio.run()` da
    "bound to a different event loop" xatosi chiqardi.  Production'da
    halqa bitta, lekin bu yashirin tuzoq — `_live_wakeups` da ham
    xuddi shu sabab bor.
    """

    async def gate_id() -> int:
        return id(main._alert_gate())

    first, second = asyncio.run(gate_id()), asyncio.run(gate_id())
    assert first != second, "semafor halqalar orasida ulashilyapti"
