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
        # Harorat ixtiyoriy: Windows qurilmalar uni yubormaydi.
        **({"temperature_c": kwargs["temperature_c"]} if "temperature_c" in kwargs else {}),
        # Soat farqi ham ixtiyoriy: eski qurilma uni yubormaydi va
        # "yubormadi" bilan "farq yo'q" bir narsa emas.
        **({"clock_skew_sec": kwargs["clock_skew_sec"]} if "clock_skew_sec" in kwargs else {}),
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


# ── Kompyuter qizib ketishi ─────────────────────────────────────────────
#
# Chang bosgan korpus yoki to'xtagan ventilyator — do'konda eng ko'p
# uchraydigan apparat nosozligi.  Uni egasining O'ZI hal qila oladi
# (tozalash, joyini almashtirish), lekin biz aytmasak hech qachon
# bilmaydi: kompyuter sekinlashadi, keyin o'chib qoladi va buni
# "dastur buzildi" deb tushunadi.


def test_an_overheating_shop_computer_is_reported() -> None:
    alerts, _ = plan_device_health_alerts([_site()], {"s1": _health(temperature_c=91.0)}, {})

    assert len(alerts) == 1
    assert alerts[0].state == "temp"
    assert "91" in alerts[0].text


def test_a_warm_but_healthy_computer_stays_quiet() -> None:
    """84°C — issiq, lekin hali chegara emas.  Yozda deyarli har
    kompyuter shu darajada isiydi va har biriga xabar yuborish
    ogohlantirishlarni ma'nosiz qilardi."""
    alerts, _ = plan_device_health_alerts([_site()], {"s1": _health(temperature_c=84.0)}, {})

    assert alerts == []


def test_the_temperature_stays_reported_until_it_really_drops() -> None:
    """Histerezis: 84,9/85,1 atrofida tebranish har 15 daqiqada
    "qizidi/sovidi" juftini yubormasin."""
    alerts, _ = plan_device_health_alerts(
        [_site()], {"s1": _health(temperature_c=80.0)}, {"s1": "temp"}
    )

    # Hali sovimagan (75 dan yuqori) — holat o'zgarmadi, xabar ham yo'q.
    assert alerts == []


def test_cooling_down_is_announced_once() -> None:
    alerts, _ = plan_device_health_alerts(
        [_site()], {"s1": _health(temperature_c=60.0)}, {"s1": "temp"}
    )

    assert len(alerts) == 1
    assert alerts[0].remember is None


def test_a_lost_event_outranks_a_hot_computer() -> None:
    """Navbat yiqilsa hodisa ALLAQACHON yo'qolyapti — uni keyin
    tiklab bo'lmaydi.  Qizish esa hali zarar yetkazmagan."""
    alerts, _ = plan_device_health_alerts(
        [_site()], {"s1": _health(temperature_c=95.0, queue_errors=3)}, {}
    )

    assert alerts[0].state == "queue"


def test_a_hot_computer_outranks_a_filling_disk() -> None:
    alerts, _ = plan_device_health_alerts(
        [_site()], {"s1": _health(temperature_c=95.0, disk_free_bytes=1 * GB)}, {}
    )

    assert alerts[0].state == "temp"


def test_a_device_that_cannot_measure_temperature_never_overheats() -> None:
    """Windows kompyuterlari haroratni umuman yubormaydi (uni
    administrator huquqisiz o'qib bo'lmaydi).  Yo'q ko'rsatkich
    hech qachon ogohlantirish bermasligi kerak."""
    alerts, _ = plan_device_health_alerts([_site()], {"s1": _health()}, {})

    assert alerts == []


def test_the_owner_is_told_about_heat_in_plain_words() -> None:
    """Ichki chatdagi matn texnik; egaga esa u hech narsa aytmaydi.

    Egaga aynan NIMA QILISH kerakligi yoziladi — bu u o'zi hal qila
    oladigan yagona muammo turi.
    """
    alerts, _ = plan_device_health_alerts([_site()], {"s1": _health(temperature_c=90.0)}, {})

    owner_text = alerts[0].owner_text
    assert owner_text
    assert "chang" in owner_text.lower()


def test_technical_problems_stay_out_of_the_owners_chat() -> None:
    """«tahlil ishlamayapti» — bizning ishimiz, egasi uni tuzata
    olmaydi.  Uni mijozga yuborish faqat tashvish qo'shardi."""
    alerts, _ = plan_device_health_alerts(
        [_site()], {"s1": _health(analyzed=4_000, analysis_errors=3_900)}, {}
    )

    assert alerts[0].owner_text is None


def test_a_cool_computer_never_hides_a_hot_one(tmp_path) -> None:
    """Bir do'konda ikki qurilma bo'lsa eng yomon ko'rsatkich olinadi.

    Bungacha apparat ko'rsatkichlari umuman qo'shilmasdi — birinchi
    qatordagi qiymat qolib ketardi.  Ya'ni sovuq kompyuter qizib
    ketganini YASHIRARDI va ogohlantirish hech qachon chiqmasdi.
    """
    from cloud.event_store import EventStore

    events = EventStore(sqlite_path=tmp_path / "events.db")
    events.record_health("s1", "dev-cool", {"temperature_c": 45.0, "cpu_percent": 10.0})
    events.record_health("s1", "dev-hot", {"temperature_c": 92.0, "cpu_percent": 97.0})

    merged = events.latest_health_by_site()["s1"]

    assert merged["temperature_c"] == 92.0
    assert merged["cpu_percent"] == 97.0


def test_an_unmeasured_value_never_replaces_a_measured_one(tmp_path) -> None:
    """`None` — "o'lchanmagan" degani.  U o'lchangan qiymatning
    o'rnini bosib, muammoni yashirib qo'ymasligi kerak."""
    from cloud.event_store import EventStore

    events = EventStore(sqlite_path=tmp_path / "events.db")
    events.record_health("s1", "dev-hot", {"temperature_c": 90.0})
    events.record_health("s1", "dev-windows", {"temperature_c": None})

    assert events.latest_health_by_site()["s1"]["temperature_c"] == 90.0


# ── Kompyuter soati adashgan ─────────────────────────────────────────────
#
# Bu ham "yashil ko'rinadigan" buzilish, lekin eng ayyori: hech qanday
# hisoblagich o'smaydi.  Qurilma sog'lom, kameralar ulangan, hodisalar
# yozilyapti — faqat ular NOTO'G'RI VAQTDA baholanadi.  Ish vaqti
# qoidalari qurilmaning lokal soatiga ishonadi
# (`chaqimchi_ai/retail/pipeline.py`), cloud esa faqat `occurred_at` ni
# tuzata oladi, qurilmaning QARORINI emas.


def test_a_drifted_clock_is_reported_because_night_watch_depends_on_it() -> None:
    """Soat olti soatga qochsa tungi nazorat kunduzi ishlaydi."""
    alerts, _ = plan_device_health_alerts(
        [_site()], {"s1": _health(clock_skew_sec=-6 * 3600)}, {}
    )

    assert len(alerts) == 1
    assert alerts[0].remember == "clock"
    assert "soati" in alerts[0].text.lower()
    # Egaga texnik atama emas, aniq harakat aytiladi.
    assert alerts[0].owner_text is not None
    assert "batareyka" in alerts[0].owner_text.lower()


def test_the_message_says_which_way_the_clock_is_wrong() -> None:
    """Orqada qolgan soat — o'lgan batareyka, oldinga ketgani — odatda
    noto'g'ri timezone.  Ustaga qaysi biri ekanini aytish kerak."""
    orqada, _ = plan_device_health_alerts([_site()], {"s1": _health(clock_skew_sec=-3600)}, {})
    oldinda, _ = plan_device_health_alerts([_site()], {"s1": _health(clock_skew_sec=3600)}, {})

    assert "orqada" in orqada[0].text
    assert "oldinda" in oldinda[0].text


def test_a_small_drift_stays_quiet() -> None:
    """NTP'siz mashina kuniga bir necha soniya qochadi — bu normal.
    Har soniyaga xabar yuborilsa chat shovqinga to'ladi."""
    alerts, _ = plan_device_health_alerts([_site()], {"s1": _health(clock_skew_sec=90)}, {})
    assert alerts == []


def test_an_old_device_that_sends_no_clock_is_not_accused() -> None:
    """Maydonni yubormagan qurilma "soati noto'g'ri" degan xabar
    olmasin — biz uning soatini BILMAYMIZ."""
    alerts, _ = plan_device_health_alerts([_site()], {"s1": _health()}, {})
    assert alerts == []


def test_losing_events_outranks_a_wrong_clock() -> None:
    """Bitta xabar — bitta muammo.  Hodisa yo'qolayotgan bo'lsa, soat
    haqida yozish eng muhimini ko'mib yuborardi."""
    alerts, _ = plan_device_health_alerts(
        [_site()], {"s1": _health(queue_errors=3, clock_skew_sec=-6 * 3600)}, {}
    )

    assert alerts[0].remember == "queue"


def test_the_owner_hears_when_the_clock_is_fixed() -> None:
    alerts, _ = plan_device_health_alerts([_site()], {"s1": _health()}, {"s1": "clock"})

    assert len(alerts) == 1
    assert alerts[0].state == "ok"
    assert "soati" in (alerts[0].owner_text or "").lower()
