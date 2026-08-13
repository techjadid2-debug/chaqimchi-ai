"""AI ko'rigi (8.3): hodisadan keyin kadr ko'rish agentiga ketadi.

Hech bir test tarmoqqa chiqmaydi va pul sarflamaydi — Claude klienti soxta.
Eng ko'p e'tibor **tormozlarga** (oraliq, limit, navbat): ular ishlamasa
hisob bo'shab qoladi, ya'ni xato mijozning pulida ko'rinadi.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, List, Optional, Tuple

import pytest

from chaqimchi_ai.event_models import EdgeEvent
from chaqimchi_ai.retail.vision_review import (
    QUESTIONS,
    VisionReviewer,
    question_for,
    review_event,
)
from chaqimchi_ai.vision_agent import (
    UsageStore,
    VisionAgent,
    VisionConfig,
    VisionResult,
)

# ── Soxta Claude klienti ─────────────────────────────────────────────────


class _Block:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _Usage:
    def __init__(self, inp: int, out: int, cached: int) -> None:
        self.input_tokens = inp
        self.output_tokens = out
        self.cache_read_input_tokens = cached


class _Response:
    def __init__(self, payload: Any, *, inp: int = 800, out: int = 120, cached: int = 400):
        text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        self.content = [_Block(text)]
        self.usage = _Usage(inp, out, cached)
        self.stop_reason = "end_turn"


class FakeClient:
    def __init__(self, responses: Optional[List[Any]] = None) -> None:
        self.calls: List[dict] = []
        self._responses = list(responses or [])
        self.messages = self

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self._responses:
            nxt = self._responses.pop(0)
            if isinstance(nxt, Exception):
                raise nxt
            return nxt
        return _Response(
            {
                "tavsif": "Kassa oldida ikki kishi janjallashmoqda.",
                "odamlar": 2,
                "ogohlantirish": True,
                "sabab": "Janjal",
            }
        )


class Sink:
    """`OutboxSink` o'rniga: yozilgan hodisalarni ushlab qoladi."""

    def __init__(self) -> None:
        self.events: List[Tuple[str, EdgeEvent]] = []
        self.arrived = threading.Event()

    def __call__(self, action: str, event: EdgeEvent) -> None:
        self.events.append((action, event))
        self.arrived.set()


FRAME = object()  # kadr shu testlarda hech qachon ochilmaydi


def build(
    tmp_path: Path,
    *,
    responses: Optional[List[Any]] = None,
    min_interval_sec: int = 300,
    max_calls_per_day: int = 100,
    queue_size: int = 8,
) -> Tuple[VisionReviewer, Sink, FakeClient]:
    client = FakeClient(responses)
    agent = VisionAgent(
        VisionConfig(
            enabled=True,
            min_interval_sec=min_interval_sec,
            max_calls_per_day=max_calls_per_day,
            max_calls_per_month=10_000,
        ),
        UsageStore(tmp_path / "vision.db"),
        client=client,
    )
    sink = Sink()
    reviewer = VisionReviewer(
        agent,
        sink,
        queue_size=queue_size,
        # Kadrni JPEG ga o'girish uchun cv2 kerak; tormozlarni tekshirishda u
        # ortiqcha, shuning uchun kodlash almashtiriladi.
        encode=lambda frame, **kwargs: b"soxta-jpeg",
    )
    return reviewer, sink, client


def tampered(camera_id: str = "kassa-01", severity: str = "critical") -> EdgeEvent:
    return EdgeEvent(
        event_type="camera_tampered", camera_id=camera_id, severity=severity
    )


# ── Xulosadan hodisa ─────────────────────────────────────────────────────


def result(*, alert: bool = True, people: int = 2) -> VisionResult:
    return VisionResult(
        tavsif="Kassa oldida ikki kishi janjallashmoqda.",
        odamlar=people,
        ogohlantirish=alert,
        sabab="Janjal" if alert else "",
        camera_id="kassa-01",
        cost_usd=0.008,
    )


def test_alert_raises_an_info_event_to_warning() -> None:
    """AI ogohlantirsa hodisa telefon jiringlaydigan darajaga ko'tariladi."""
    event = review_event(tampered(severity="info"), result(alert=True))

    assert event.event_type == "ai_review"
    assert event.severity == "warning"
    assert event.metadata["sabab"] == "Janjal"
    assert event.occupancy == 2


def test_critical_source_is_never_downgraded() -> None:
    """Kamera yopilgani — fakt; AI "oddiy holat" desa ham u yo'qolmaydi.

    Lekin xulosaning **o'zi** past darajada qoladi: mijoz allaqachon
    `camera_tampered` uchun xabar olgan, ikkinchisi shovqin bo'lardi.
    """
    confirmed = review_event(tampered(severity="critical"), result(alert=True))
    assert confirmed.severity == "critical"

    denied = review_event(tampered(severity="critical"), result(alert=False))
    assert denied.severity == "info"


def test_calm_scene_stays_quiet() -> None:
    """AI "hammasi joyida" desa hodisa arxivga tushadi, xabar ketmaydi."""
    event = review_event(tampered(severity="info"), result(alert=False))

    assert event.severity == "info"
    assert event.metadata["ogohlantirish"] is False


def test_source_event_is_linked() -> None:
    """Xulosa qaysi hodisadan tug'ilgani ko'rinib turishi kerak."""
    source = tampered()
    event = review_event(source, result())

    assert event.metadata["source_event_id"] == source.event_id
    assert event.metadata["source_event_type"] == "camera_tampered"


def test_question_depends_on_the_event() -> None:
    """Aniq savol aniqroq javob beradi — kontekstsiz so'ramaymiz."""
    assert question_for("camera_tampered") == QUESTIONS["camera_tampered"]
    assert "yopiq" in question_for("after_hours_presence")
    assert question_for("line_crossed")  # noma'lum tur uchun ham savol bor


# ── Tormozlar ────────────────────────────────────────────────────────────


def test_second_event_within_the_interval_is_refused(tmp_path: Path) -> None:
    """Eng qimmat xato shu bo'lardi: ketma-ket hodisa — ketma-ket hisob."""
    reviewer, _sink, _client = build(tmp_path, min_interval_sec=300)

    assert reviewer.submit(tampered(), FRAME, now=1000.0) is True
    assert reviewer.submit(tampered(), FRAME, now=1100.0) is False
    assert reviewer.submit(tampered(), FRAME, now=1301.0) is True

    stats = reviewer.stats()
    assert stats["queued"] == 2
    assert stats["throttled"] == 1


def test_interval_is_reserved_before_the_answer_arrives(tmp_path: Path) -> None:
    """Oraliq navbatga qo'yishda boshlanadi.

    Javobni kutib turib hisoblansa, AI sekin javob bergan paytda o'nlab
    hodisa o'tib ketardi va har biri yangi chaqiruv bo'lardi.
    """
    reviewer, sink, _client = build(tmp_path, min_interval_sec=300)

    reviewer.submit(tampered(), FRAME, now=1000.0)
    # Hech qanday tahlil bajarilmadi (oqim ishga tushmagan), lekin ikkinchi
    # so'rov baribir to'siladi.
    assert sink.events == []
    assert reviewer.submit(tampered(), FRAME, now=1010.0) is False


def test_each_camera_has_its_own_interval(tmp_path: Path) -> None:
    reviewer, _sink, _client = build(tmp_path, min_interval_sec=300)

    assert reviewer.submit(tampered("kassa-01"), FRAME, now=1000.0) is True
    assert reviewer.submit(tampered("ombor-02"), FRAME, now=1000.0) is True


def test_daily_limit_stops_new_requests(tmp_path: Path) -> None:
    """Limit tugagach kadr navbatga ham tushmaydi — kodlash ham bekor."""
    reviewer, _sink, _client = build(
        tmp_path, min_interval_sec=10, max_calls_per_day=1
    )

    reviewer.submit(tampered(), FRAME, now=1000.0)
    reviewer._review(tampered(), b"soxta-jpeg")  # hisob to'ldi

    assert reviewer.submit(tampered(), FRAME, now=2000.0) is False
    assert reviewer.stats()["over_budget"] == 1


def test_full_queue_drops_the_frame(tmp_path: Path) -> None:
    """Navbat to'lsa kadr tashlanadi — xotira o'sib qurilmani yiqitmasin."""
    reviewer, _sink, _client = build(tmp_path, min_interval_sec=0, queue_size=1)

    assert reviewer.submit(tampered("kassa-01"), FRAME, now=1000.0) is True
    assert reviewer.submit(tampered("ombor-02"), FRAME, now=1000.0) is False
    assert reviewer.stats()["dropped"] == 1


def test_encoding_uses_the_configured_size(tmp_path: Path) -> None:
    """Kadr o'lchami — narxning asosiy sozlamasi; u yo'lda yo'qolmasin."""
    seen: List[dict] = []
    reviewer, _sink, _client = build(tmp_path)
    reviewer._encode = lambda frame, **kwargs: (seen.append(kwargs), b"j")[1]

    reviewer.submit(tampered(), FRAME, now=1000.0)

    assert seen == [{"max_side": 768, "quality": 80}]


# ── Chaqiruv va natija ───────────────────────────────────────────────────


def test_review_writes_the_conclusion_to_the_sink(tmp_path: Path) -> None:
    reviewer, sink, client = build(tmp_path)

    reviewer._review(tampered(), b"soxta-jpeg")

    assert len(sink.events) == 1
    action, event = sink.events[0]
    assert action == "cloud_sync"
    assert event.event_type == "ai_review"
    assert event.metadata["tavsif"].startswith("Kassa oldida")
    assert event.metadata["model"] == "claude-opus-5"
    assert event.metadata["cost_usd"] > 0
    # Savol hodisa turiga mos kelgan.
    assert QUESTIONS["camera_tampered"] in json.dumps(
        client.calls[0]["messages"], ensure_ascii=False
    )


def test_failed_call_writes_nothing(tmp_path: Path) -> None:
    """AI javob bermasa analitika ishlashda davom etadi, hodisa yaralmaydi."""
    reviewer, sink, _client = build(tmp_path, responses=[RuntimeError("tarmoq yo'q")])

    reviewer._review(tampered(), b"soxta-jpeg")

    assert sink.events == []
    assert reviewer.stats()["failed"] == 1


def test_worker_thread_handles_the_queue(tmp_path: Path) -> None:
    """To'liq yo'l: submit → oqim → sink."""
    reviewer, sink, _client = build(tmp_path)
    reviewer.start()
    try:
        assert reviewer.submit(tampered(), FRAME, now=1000.0) is True
        assert sink.arrived.wait(timeout=5.0), "xulosa kelmadi"
    finally:
        reviewer.stop(timeout=5.0)

    assert sink.events[0][1].event_type == "ai_review"
    assert reviewer.stats()["completed"] == 1


def test_stop_is_safe_without_start(tmp_path: Path) -> None:
    reviewer, _sink, _client = build(tmp_path)
    reviewer.stop()  # xato bermasin


@pytest.mark.parametrize("event_type", sorted(QUESTIONS))
def test_every_question_is_a_real_question(event_type: str) -> None:
    assert QUESTIONS[event_type].strip().endswith("?")
