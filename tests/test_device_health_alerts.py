"""Do'kon kompyuteri jimgina ishlamay qolmasin.

Bu mahsulotdagi eng xavfli buzilish turi: tizim **yashil ko'rinadi** —
qurilma aloqada, kameralar ulangan, panel ochiladi — lekin hodisa
yozilmayapti.  Aloqa uzilishini mijoz ham, biz ham darhol ko'ramiz; buni
esa faqat oy oxirida "hisobot nega bo'sh?" degan savoldan bilib qolamiz.

Uch yo'l bor edi va uchalasi ham jim edi:

1. `analyze()` har kadrda xato tashlaydi (model buzilgan yoki OpenVINO
   yangilanishi mos kelmagan) — hisoblagich bor edi, lekin u holat
   faylida ham, heartbeat'da ham yo'q edi.
2. Disk to'ladi — navbatga yozish xatosi yutilardi, `outbox_pending`
   esa o'smasdi (yozuv umuman qo'shilmaydi), ya'ni hammasi tinch
   ko'rinardi.
3. Cloud `disk_free_bytes` ni qabul qilardi va hech qachon qaramasdi.
"""

from __future__ import annotations

from cloud.alerts import plan_device_health_alerts

GB = 1024**3


def _site(**kwargs) -> dict:
    return {
        "id": "s1",
        "name": "Oq Saroy",
        "license_status": kwargs.get("license_status", "active"),
        "connection": kwargs.get("connection", "online"),
    }


def _health(**kwargs) -> dict:
    """Qurilmadan kelgan oxirgi heartbeat."""
    return {
        "analyzed": kwargs.get("analyzed", 5_000),
        "analysis_errors": kwargs.get("analysis_errors", 0),
        "queue_errors": kwargs.get("queue_errors", 0),
        "disk_free_bytes": kwargs.get("disk_free_bytes", 40 * GB),
    }


# ── Tahlil zanjiri yiqilgan ──────────────────────────────────────────────


def test_a_failing_analyzer_is_reported_even_though_everything_looks_green() -> None:
    """Har kadr xato: kamera ulangan, uptime o'sib boradi, hodisa nol."""
    alerts, _ = plan_device_health_alerts(
        [_site()], {"s1": _health(analyzed=4_000, analysis_errors=3_900)}, {}
    )

    assert len(alerts) == 1
    assert alerts[0].kind == "device"
    assert "tahlil" in alerts[0].text.lower()
    assert "Oq Saroy" in alerts[0].text


def test_a_few_errors_are_normal_and_stay_quiet() -> None:
    """Bitta-ikkita xato (kadr buzildi, kamera uzildi) — bu odatiy hol.
    Har mayda xatoga xabar yuborilsa, chat shovqinga to'ladi va haqiqiy
    ogohlantirish ko'rinmay ketadi."""
    alerts, _ = plan_device_health_alerts(
        [_site()], {"s1": _health(analyzed=5_000, analysis_errors=20)}, {}
    )
    assert alerts == []


def test_a_fresh_start_is_not_judged_too_early() -> None:
    """Dastur endi ishga tushdi: 3 kadrdan 2 tasi xato — bu statistika
    emas.  Yetarli namuna to'plangunicha jim turiladi."""
    alerts, _ = plan_device_health_alerts(
        [_site()], {"s1": _health(analyzed=3, analysis_errors=2)}, {}
    )
    assert alerts == []


# ── Hodisalar saqlanmayapti ──────────────────────────────────────────────


def test_events_that_cannot_be_queued_are_the_loudest_alarm() -> None:
    """Disk to'lganda navbatga yozish yiqiladi va hodisa BUTUNLAY
    yo'qoladi — uni keyin tiklab bo'lmaydi."""
    alerts, _ = plan_device_health_alerts([_site()], {"s1": _health(queue_errors=12)}, {})

    assert len(alerts) == 1
    assert "yo'qolyapti" in alerts[0].text or "saqlanmayapti" in alerts[0].text


def test_the_most_serious_problem_is_reported_first() -> None:
    """Bir vaqtda uchalasi ham bo'lsa — bitta xabar, eng og'iri haqida.
    Uchta alohida xabar chat'ni ko'mib tashlaydi."""
    alerts, _ = plan_device_health_alerts(
        [_site()],
        {"s1": _health(analyzed=4_000, analysis_errors=3_900, queue_errors=5, disk_free_bytes=GB)},
        {},
    )
    assert len(alerts) == 1
    assert "yo'qolyapti" in alerts[0].text or "saqlanmayapti" in alerts[0].text


# ── Do'kon kompyuterida joy tugayapti ────────────────────────────────────


def test_low_disk_on_the_shop_pc_is_reported_before_it_fills() -> None:
    """To'lgandan keyin ogohlantirish kech: hodisalar allaqachon
    yo'qolgan bo'ladi."""
    alerts, _ = plan_device_health_alerts([_site()], {"s1": _health(disk_free_bytes=GB)}, {})

    assert len(alerts) == 1
    assert "joy" in alerts[0].text.lower()


def test_plenty_of_disk_stays_quiet() -> None:
    alerts, _ = plan_device_health_alerts([_site()], {"s1": _health(disk_free_bytes=40 * GB)}, {})
    assert alerts == []


# ── Shovqin nazorati ─────────────────────────────────────────────────────


def test_the_same_problem_is_not_repeated_every_check() -> None:
    """Tekshiruv har 15 daqiqada — takroriy xabar shovqin."""
    health = {"s1": _health(queue_errors=12)}
    alerts, _ = plan_device_health_alerts([_site()], health, {"s1": "queue"})
    assert alerts == []


def test_recovery_is_announced_once() -> None:
    """«Tuzaldi» xabari ham kerak: aks holda muammo hali ham bormi yoki
    yo'qmi — bilib bo'lmaydi."""
    alerts, forget = plan_device_health_alerts([_site()], {"s1": _health()}, {"s1": "queue"})

    assert len(alerts) == 1
    assert alerts[0].remember is None
    assert "tuzaldi" in alerts[0].text.lower() or "joyida" in alerts[0].text.lower()


def test_an_offline_device_is_left_to_the_connection_alert() -> None:
    """Aloqa yo'q bo'lsa heartbeat ham eskirgan — u haqda alohida yozish
    ikki karra shovqin, aloqa ogohlantirishi allaqachon ketgan."""
    alerts, forget = plan_device_health_alerts(
        [_site(connection="offline")], {"s1": _health(queue_errors=99)}, {}
    )
    assert alerts == []


def test_a_suspended_site_is_not_watched() -> None:
    alerts, _ = plan_device_health_alerts(
        [_site(license_status="suspended")], {"s1": _health(queue_errors=99)}, {}
    )
    assert alerts == []


def test_a_site_that_never_reported_is_not_guessed_about() -> None:
    """Heartbeat hali kelmagan — bu muammo emas, ma'lumot yo'qligi."""
    alerts, _ = plan_device_health_alerts([_site()], {}, {})
    assert alerts == []


# ── Uchdan-uchgacha: heartbeat → ogohlantirish ───────────────────────────


class _FakeSender:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, text: str) -> bool:
        self.sent.append(text)
        return True

    async def aclose(self) -> None:
        pass


def test_a_broken_shop_pc_reaches_telegram(tmp_path, monkeypatch) -> None:
    """Butun zanjir: qurilma heartbeat yuboradi → cloud saqlaydi →
    tekshiruv tsikli o'qiydi → Telegramga xabar ketadi.

    Rejalashtiruvchining o'zi to'g'ri ishlashi yetarli emas: ilgari ham
    hisoblagichlar mavjud edi, lekin ular heartbeat'ga umuman
    chiqmasdi va hech kim ularga qaramasdi.
    """
    import asyncio

    from cloud import alerts as alerts_module
    from cloud.alerts import run_check
    from cloud.event_store import EventStore
    from cloud.store import CloudStore

    store = CloudStore(tmp_path / "cloud.db")
    events = EventStore(sqlite_path=tmp_path / "events.db")
    monkeypatch.setattr(alerts_module, "_latest_health", events.latest_health_by_site)

    site = store.create_site("Oq Saroy", "business", contact_phone="+998901112233")
    claimed = store.claim_device(site["pairing_code"])
    store.heartbeat(
        site_id=claimed["site_id"], device_token=claimed["device_token"], active_cameras=3
    )
    store.set_cameras_expected(site["site_id"], 3)
    sender = _FakeSender()

    # Sog'lom qurilma — jim.
    events.record_health(
        site["site_id"], claimed["device_id"], {"analyzed": 5_000, "analysis_errors": 0}
    )
    assert asyncio.run(run_check(store, sender)).sent == 0

    # Disk to'ldi: hodisalar navbatga yozilmayapti.
    events.record_health(
        site["site_id"],
        claimed["device_id"],
        {"analyzed": 6_000, "analysis_errors": 0, "queue_errors": 14},
    )
    run = asyncio.run(run_check(store, sender))
    assert run.sent == 1
    assert "Oq Saroy" in sender.sent[-1]
    assert "saqlanmayapti" in sender.sent[-1]

    # Takrorlanmaydi.
    assert asyncio.run(run_check(store, sender)).sent == 0

    # Tuzaldi — bir marta xabar.
    events.record_health(
        site["site_id"],
        claimed["device_id"],
        {"analyzed": 7_000, "analysis_errors": 0, "queue_errors": 0},
    )
    run = asyncio.run(run_check(store, sender))
    assert run.sent == 1
    assert "tuzaldi" in sender.sent[-1].lower()
