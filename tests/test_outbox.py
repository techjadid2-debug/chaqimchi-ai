import sqlite3
from pathlib import Path

from chaqimchi_ai.event_models import EdgeEvent
from chaqimchi_ai.outbox import (
    BASE_RETRY_DELAY_SEC,
    MAX_ATTEMPTS,
    MAX_RETRY_DELAY_SEC,
    SENT_KEEP_DAYS,
    EventOutbox,
    retry_delay,
)


def test_outbox_roundtrip_and_idempotency(tmp_path: Path) -> None:
    image = tmp_path / "event.jpg"
    image.write_bytes(b"jpeg")
    event = EdgeEvent(
        event_type="zone_entered",
        severity="warning",
        camera_id="cam-1",
        zone="ombor",
        snapshot_path=str(image),
    )
    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=10_000)
    outbox.enqueue(event)
    outbox.enqueue(event)

    rows = outbox.pending()
    assert len(rows) == 1
    assert rows[0]["payload"]["event_id"] == event.event_id
    assert rows[0]["payload"]["has_snapshot"] is True
    assert outbox.stats()["pending"] == 1
    assert outbox.acknowledge([event.event_id]) == 1
    assert outbox.pending() == []


def test_outbox_attaches_clip_after_initial_event(tmp_path: Path) -> None:
    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=100_000)
    event = EdgeEvent(
        event_id="event-with-late-clip",
        event_type="after_hours_presence",
        severity="critical",
        camera_id="cam",
    )
    outbox.enqueue(event)
    clip = tmp_path / "event.mp4"
    clip.write_bytes(b"video")
    event.clip_path = str(clip)
    outbox.enqueue(event)

    row = outbox.pending()[0]
    assert row["clip_path"] == str(clip)
    assert row["payload"]["has_clip"] is True
    assert "clip_path" not in row["payload"]
    assert outbox.clip_path(event.event_id) == str(clip)


def test_outbox_enforces_size_limit(tmp_path: Path) -> None:
    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=800)
    for number in range(10):
        outbox.enqueue(
            EdgeEvent(
                event_type="person_detected",
                camera_id="cam",
                metadata={"padding": "x" * 200, "number": number},
            )
        )
    assert outbox.stats()["bytes"] <= 800
    assert outbox.stats()["pending"] < 10


def test_outbox_keeps_critical_events_before_batch_events_when_disk_is_full(tmp_path: Path) -> None:
    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=700)
    for number in range(3):
        outbox.enqueue(
            EdgeEvent(
                event_type="person_detected",
                severity="info",
                camera_id="cam",
                metadata={"padding": "x" * 180, "number": number},
            )
        )
    critical = EdgeEvent(
        event_type="zone_entered",
        severity="critical",
        camera_id="cam",
        metadata={"padding": "x" * 180},
    )
    outbox.enqueue(critical)

    rows = outbox.pending()
    assert rows[0]["event_id"] == critical.event_id
    assert any(row["event_id"] == critical.event_id for row in rows)


# ── Backoff va umidsiz hodisalar ─────────────────────────────────────────


def _event(event_id: str = "evt-1", **kwargs) -> EdgeEvent:
    return EdgeEvent(event_id=event_id, event_type="line_crossed", camera_id="camera-01", **kwargs)


def test_a_rejected_event_stops_blocking_the_batch(tmp_path: Path) -> None:
    """Butun tuzatishning sababi.

    Cloud biror hodisani doimiy rad etsa (eski sxema, buzuq maydon), u
    har 5 soniyada qayta yuborilar va batch o'rnini egallab turardi —
    ortidagi yaxshi hodisalar esa kutib qolardi.
    """
    from datetime import datetime, timedelta, timezone

    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=10**7)
    outbox.enqueue(_event("yomon"))
    outbox.enqueue(_event("yaxshi"))
    moment = datetime.now(timezone.utc)

    outbox.fail("yomon", "cloud rad etdi", now=moment)

    # Yomoni navbatdan chiqdi, yaxshisi qoldi.
    assert [row["event_id"] for row in outbox.pending(now=moment)] == ["yaxshi"]
    assert outbox.stats()["waiting"] == 1
    # Kutish tugagach yana urinib ko'riladi.
    later = moment + timedelta(seconds=retry_delay(1) + 1)
    assert sorted(row["event_id"] for row in outbox.pending(now=later)) == ["yaxshi", "yomon"]


def test_the_delay_doubles_and_stops_at_the_ceiling() -> None:
    assert retry_delay(1) == BASE_RETRY_DELAY_SEC
    assert retry_delay(2) == BASE_RETRY_DELAY_SEC * 2
    assert retry_delay(3) == BASE_RETRY_DELAY_SEC * 4
    # Shiftga tegib to'xtaydi: cloud tiklanishi 5 daqiqadan uzoq
    # kutishga arzimaydi.
    assert retry_delay(50) == MAX_RETRY_DELAY_SEC
    # Nol yoki manfiy urinish ham xato bermasin.
    assert retry_delay(0) == BASE_RETRY_DELAY_SEC


def test_a_hopeless_event_is_dropped_but_not_lost(tmp_path: Path) -> None:
    """Nima uchun rad etilganini keyin ko'rish mumkin bo'lsin."""
    from datetime import datetime, timedelta, timezone

    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=10**7)
    outbox.enqueue(_event("umidsiz"))
    moment = datetime.now(timezone.utc)

    for attempt in range(MAX_ATTEMPTS):
        # `permanent=True` — cloud hodisaning O'ZINI rad etdi.  Faqat
        # shunday xato hisobga kiradi: tarmoq uzilishi hodisani
        # o'ldirmasligi kerak (pastdagi testlarga qarang).
        outbox.fail("umidsiz", f"{attempt}-urinish rad etildi", permanent=True, now=moment)
        moment += timedelta(seconds=MAX_RETRY_DELAY_SEC + 1)

    assert outbox.pending(now=moment) == []
    stats = outbox.stats()
    assert stats["pending"] == 0
    assert stats["poisoned"] == 1

    dropped = outbox.dead_letters()
    assert len(dropped) == 1
    assert dropped[0]["event_id"] == "umidsiz"
    assert dropped[0]["attempts"] == MAX_ATTEMPTS
    assert "rad etildi" in dropped[0]["last_error"]


def test_failing_an_unknown_event_is_harmless(tmp_path: Path) -> None:
    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=10**7)
    outbox.fail("yo-q", "xato")  # xato bermasligi kerak
    assert outbox.stats()["poisoned"] == 0


def test_a_new_payload_gets_a_fresh_chance(tmp_path: Path) -> None:
    """Klip tayyor bo'lganda hodisa qayta yoziladi — bu yangi imkoniyat.

    Lekin `attempts` saqlanadi: umidsiz hodisa klip orqali cheksiz qayta
    urinaverishi mumkin bo'lmasin.
    """
    from datetime import datetime, timezone

    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=10**7)
    clip = tmp_path / "klip.mp4"
    clip.write_bytes(b"mp4")
    outbox.enqueue(_event("evt-1"))
    moment = datetime.now(timezone.utc)
    outbox.fail("evt-1", "tarmoq yo'q", now=moment)
    assert outbox.pending(now=moment) == []

    outbox.enqueue(_event("evt-1", clip_path=str(clip)))

    row = outbox.pending(now=moment)[0]
    assert row["event_id"] == "evt-1"
    assert row["attempts"] == 1  # hisob nolga tushmadi
    assert row["clip_path"] == str(clip)


def test_successful_delivery_clears_everything(tmp_path: Path) -> None:
    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=10**7)
    outbox.enqueue(_event("evt-1"))
    outbox.fail("evt-1", "vaqtincha xato")

    assert outbox.acknowledge(["evt-1"]) == 1
    assert outbox.stats() == {"pending": 0, "bytes": 0, "waiting": 0, "poisoned": 0}


def test_delivered_events_stay_readable_for_the_local_panel(tmp_path: Path) -> None:
    """Yuborilgan hodisa navbatdan chiqadi, lekin bazadan **o'chmaydi**.

    Do'kon kompyuteridagi panel kunlik hisobotni shu bazadan o'qiydi.
    Ilgari yuborilgan yozuv darhol o'chirilardi va do'kon internetda
    bo'lsa panel kun bo'yi nol ko'rsatardi.
    """
    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=10**7)
    outbox.enqueue(_event("evt-1"))
    outbox.acknowledge(["evt-1"])

    assert outbox.pending() == [], "qayta yuborilmasin"
    assert outbox.stats()["pending"] == 0

    with sqlite3.connect(tmp_path / "outbox.db") as conn:
        rows = conn.execute("SELECT event_id, sent_at FROM outbox").fetchall()
    assert len(rows) == 1 and rows[0][1], "yozuv qoldi va yuborilgan deb belgilandi"


def test_a_late_clip_is_sent_even_after_the_event_was_delivered(tmp_path: Path) -> None:
    """Klip hodisadan keyin tayyor bo'ladi.  Yozuv o'chirilmagani uchun
    endi u yangilanadi — va qaytadan yuborilishi kerak."""
    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=10**7)
    event = _event("evt-1")
    outbox.enqueue(event)
    outbox.acknowledge(["evt-1"])

    clip = tmp_path / "klip.mp4"
    clip.write_bytes(b"video")
    event.clip_path = str(clip)
    outbox.enqueue(event)

    rows = outbox.pending()
    assert len(rows) == 1 and rows[0]["clip_path"] == str(clip)


def test_delivered_events_do_not_pile_up_forever(tmp_path: Path) -> None:
    """Ular faqat bugungi hisobot uchun kerak — arxiv uchun emas."""
    from datetime import datetime, timedelta, timezone

    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=10**7)
    outbox.enqueue(_event("eski"))
    outbox.acknowledge(["eski"])
    old = (datetime.now(timezone.utc) - timedelta(days=SENT_KEEP_DAYS + 1)).isoformat()
    with sqlite3.connect(tmp_path / "outbox.db") as conn:
        conn.execute("UPDATE outbox SET sent_at=?", (old,))

    outbox.prune()

    with sqlite3.connect(tmp_path / "outbox.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 0


def test_a_full_disk_drops_delivered_events_before_unsent_ones(tmp_path: Path) -> None:
    """Yuborilgani cloudda saqlangan; yuborilmagani esa faqat shu yerda.
    Disk to'lganda avval xavfsizrog'i tashlanadi."""
    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=10**7)
    outbox.enqueue(_event("yuborilgan-1"))
    outbox.enqueue(_event("yuborilgan-2"))
    outbox.acknowledge(["yuborilgan-1", "yuborilgan-2"])
    outbox.enqueue(_event("yuborilmagan-1"))
    one_event = outbox.stats()["bytes"]
    outbox.enqueue(_event("yuborilmagan-2"))

    outbox.max_bytes = one_event  # faqat bittasiga joy qoldi
    outbox.prune()

    with sqlite3.connect(tmp_path / "outbox.db") as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM outbox WHERE sent_at IS NOT NULL"
        ).fetchone()[0] == 0, "yuborilganlari birinchi bo'lib tashlansin"
    assert len(outbox.pending()) == 1, "yuborilmaganidan biri saqlanib qoldi"


def test_dead_letters_do_not_pile_up_forever(tmp_path: Path) -> None:
    """Ular diagnostika uchun, arxiv uchun emas."""
    from datetime import datetime, timedelta, timezone

    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=10**7, retention_days=1)
    outbox.enqueue(_event("eski"))
    old = datetime.now(timezone.utc) - timedelta(days=5)
    for _ in range(MAX_ATTEMPTS):
        outbox.fail("eski", "rad etildi", permanent=True, now=old)

    assert outbox.stats()["poisoned"] == 1
    outbox.prune()
    assert outbox.stats()["poisoned"] == 0


def test_the_schema_upgrades_an_existing_database(tmp_path: Path) -> None:
    """Ishlab turgan qurilmada baza allaqachon bor — yangi ustun
    qo'shilganda u yiqilmasligi kerak."""
    import sqlite3

    path = tmp_path / "outbox.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE outbox (event_id TEXT PRIMARY KEY, payload TEXT NOT NULL,"
            "snapshot_path TEXT, snapshot_size INTEGER NOT NULL DEFAULT 0,"
            "created_at TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT)"
        )
        conn.execute(
            "INSERT INTO outbox(event_id,payload,created_at) VALUES('eski','{}','2026-01-01T00:00:00+00:00')"
        )

    outbox = EventOutbox(path, max_bytes=10**7)

    assert outbox.stats()["pending"] == 1
    assert outbox.pending()[0]["event_id"] == "eski"
    outbox.fail("eski", "xato")
    assert outbox.stats()["waiting"] == 1


# ── Tarmoq uzilishi hodisani o'ldirmaydi ─────────────────────────────────
#
# 2026-08-27 da sinov do'konida `outbox_poisoned` 4 401 gacha chiqqan edi
# — do'kon jami yuborgan 7 227 hodisaning taxminan uchdan biri.  Eng ko'p
# uchragan sabab "All connection attempts failed" edi, ya'ni internet
# uzilishi.  Har muvaffaqiyatsizlik `MAX_ATTEMPTS` ni yeb borardi va 20
# urinish eksponensial kutish bilan ~3 soatga cho'zilardi: yarim kunlik
# nosozlik butun navbatni yo'q qilardi.


def test_a_network_outage_never_throws_events_away(tmp_path: Path) -> None:
    from datetime import datetime, timedelta, timezone

    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=10**7)
    outbox.enqueue(_event("uzilish"))
    moment = datetime.now(timezone.utc)

    # Ikki barobar ko'p urinish — baribir tirik.
    for _ in range(MAX_ATTEMPTS * 2):
        outbox.fail("uzilish", "All connection attempts failed", now=moment)
        moment += timedelta(seconds=MAX_RETRY_DELAY_SEC + 1)

    assert outbox.stats()["poisoned"] == 0
    assert [row["event_id"] for row in outbox.pending(now=moment)] == ["uzilish"]


def test_a_long_outage_still_backs_off(tmp_path: Path) -> None:
    """Urinishlar hisobga kirmasa ham kutish uzayishi kerak.

    Aks holda uzilish paytida navbat serverni har 5 soniyada urardi.
    """
    from datetime import datetime, timezone

    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=10**7)
    outbox.enqueue(_event("uzilish"))
    moment = datetime.now(timezone.utc)

    for _ in range(6):
        outbox.fail("uzilish", "tarmoq", now=moment)

    assert outbox.pending(now=moment) == []


def test_an_event_stuck_past_retention_is_counted_not_silently_deleted(tmp_path: Path) -> None:
    """Uzoq uzilishning yagona chegarasi — yosh, va u KO'RINISHI shart.

    Bungacha yoshi o'tgan yuborilmagan yozuv shunchaki `DELETE` bo'lardi
    va hisoblagichga tushmasdi: bir hafta internetsiz qolgan do'konning
    hodisalari yo'qolar, `outbox_poisoned` esa nol turaverardi.
    """
    from datetime import datetime, timedelta, timezone

    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=10**7, retention_days=7)
    outbox.enqueue(_event("qolib-ketgan"))
    old = datetime.now(timezone.utc) - timedelta(days=9)
    with sqlite3.connect(tmp_path / "outbox.db") as conn:
        conn.execute("UPDATE outbox SET created_at=?", (old.isoformat(),))

    outbox.fail("qolib-ketgan", "All connection attempts failed")
    outbox.prune()

    dropped = outbox.dead_letters()
    assert len(dropped) == 1
    assert "yuborilmadi" in dropped[0]["last_error"]


def test_the_reason_is_never_empty(tmp_path: Path) -> None:
    """Sababsiz raqamning foydasi yo'q.

    Jonli do'kondagi 3 375 ta tashlangan hodisaning 602 tasi "sabab
    yozilmagan" edi — `str(exc)` ba'zi httpx xatolarida bo'sh satr.
    """
    outbox = EventOutbox(tmp_path / "outbox.db", max_bytes=10**7)
    outbox.enqueue(_event("sababsiz"))

    outbox.fail("sababsiz", "")

    with sqlite3.connect(tmp_path / "outbox.db") as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT last_error FROM outbox").fetchone()
    assert row["last_error"]
