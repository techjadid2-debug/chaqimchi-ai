"""Ko‘rish agenti testlari.

Hech bir test tarmoqqa chiqmaydi va pul sarflamaydi — Claude klienti soxta.
Eng ko‘p e’tibor **tormozlarga**: limit va oraliq ishlamasa hisob bo‘shab
qoladi, shuning uchun ular alohida qamrab olingan.
"""

import json
from pathlib import Path

import pytest

from chaqimchi_ai.vision_agent import (
    BudgetExceeded,
    UsageStore,
    VisionAgent,
    VisionAgentError,
    VisionConfig,
    call_cost_usd,
    encode_frame,
    estimate_monthly_usd,
    image_tokens,
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
    def __init__(self, payload, *, inp=800, out=120, cached=400, stop_reason="end_turn"):
        text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        self.content = [_Block(text)]
        self.usage = _Usage(inp, out, cached)
        self.stop_reason = stop_reason


class FakeClient:
    """`client.messages.create(...)` ni taqlid qiladi."""

    def __init__(self, responses=None) -> None:
        self.calls: list[dict] = []
        self._responses = list(responses or [])
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._responses:
            nxt = self._responses.pop(0)
            if isinstance(nxt, Exception):
                raise nxt
            return nxt
        return _Response(
            {"tavsif": "Kassada ikki xaridor turibdi.", "odamlar": 2,
             "ogohlantirish": False, "sabab": ""}
        )


@pytest.fixture
def agent(tmp_path: Path) -> VisionAgent:
    return VisionAgent(
        VisionConfig(enabled=True, max_calls_per_day=5, max_calls_per_month=10),
        UsageStore(tmp_path / "vision.db"),
        client=FakeClient(),
    )


JPEG = b"\xff\xd8\xff\xe0soxta-jpeg"


# ── Narx hisobi ──────────────────────────────────────────────────────────


def test_image_tokens_scale_with_area() -> None:
    small = image_tokens(768, 432)
    big = image_tokens(1920, 1080)
    assert big > small * 5  # olti barobarga yaqin


def test_cached_tokens_are_ten_times_cheaper() -> None:
    fresh = call_cost_usd(input_tokens=1000, output_tokens=0)
    cached = call_cost_usd(input_tokens=0, output_tokens=0, cached_tokens=1000)
    assert cached == pytest.approx(fresh * 0.1)


def test_output_tokens_cost_five_times_input() -> None:
    assert call_cost_usd(0, 1000) == pytest.approx(call_cost_usd(1000, 0) * 5)


def test_smaller_frames_cost_less() -> None:
    assert estimate_monthly_usd(100, max_side=512) < estimate_monthly_usd(100, max_side=1536)


def test_monthly_estimate_is_in_expected_range() -> None:
    """Kuniga 100 tahlil oyiga bir necha dollar bo‘lishi kerak."""
    monthly = estimate_monthly_usd(100, max_side=768)
    assert 1 < monthly < 100


# ── Kadrni tayyorlash ────────────────────────────────────────────────────


def test_encode_frame_shrinks_large_image() -> None:
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")

    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    blob = encode_frame(frame, max_side=768)

    decoded = cv2.imdecode(np.frombuffer(blob, np.uint8), cv2.IMREAD_COLOR)
    assert max(decoded.shape[:2]) == 768


def test_encode_frame_keeps_small_image() -> None:
    np = pytest.importorskip("numpy")
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    cv2 = pytest.importorskip("cv2")

    blob = encode_frame(frame, max_side=768)

    decoded = cv2.imdecode(np.frombuffer(blob, np.uint8), cv2.IMREAD_COLOR)
    assert decoded.shape[:2] == (240, 320)


def test_encode_frame_rejects_empty() -> None:
    np = pytest.importorskip("numpy")
    with pytest.raises(VisionAgentError):
        encode_frame(np.zeros((0, 0, 3), dtype=np.uint8))


# ── Tahlil ───────────────────────────────────────────────────────────────


def test_analyze_parses_uzbek_result(agent: VisionAgent) -> None:
    result = agent.analyze(JPEG, camera_id="Kirish-1")

    assert result.tavsif == "Kassada ikki xaridor turibdi."
    assert result.odamlar == 2
    assert result.ogohlantirish is False
    assert result.camera_id == "Kirish-1"
    assert result.cost_usd > 0


def test_analyze_sends_image_and_system_prompt(agent: VisionAgent) -> None:
    agent.analyze(JPEG)

    call = agent._client.calls[0]
    assert call["model"] == "claude-opus-5"
    blocks = call["messages"][0]["content"]
    assert blocks[0]["type"] == "image"
    assert blocks[0]["source"]["media_type"] == "image/jpeg"
    # Tizim ko'rsatmasi keshlanadi — aks holda har chaqiruvda to'liq to'lanadi.
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    # Javob sxema bilan chegaralangan.
    assert call["output_config"]["format"]["type"] == "json_schema"


def test_custom_question_is_passed(agent: VisionAgent) -> None:
    agent.analyze(JPEG, question="Kassada necha kishi navbatda?")
    text_block = agent._client.calls[0]["messages"][0]["content"][1]
    assert text_block["text"] == "Kassada necha kishi navbatda?"


def test_alert_result(tmp_path: Path) -> None:
    client = FakeClient([
        _Response({"tavsif": "Bir odam yerda yotibdi.", "odamlar": 1,
                   "ogohlantirish": True, "sabab": "Odam yiqilgan"})
    ])
    agent = VisionAgent(VisionConfig(enabled=True), UsageStore(tmp_path / "v.db"), client=client)

    result = agent.analyze(JPEG)

    assert result.ogohlantirish is True
    assert result.sabab == "Odam yiqilgan"


def test_empty_frame_rejected(agent: VisionAgent) -> None:
    with pytest.raises(VisionAgentError, match="bo‘sh"):
        agent.analyze(b"")


def test_refusal_does_not_crash(tmp_path: Path) -> None:
    """Xavfsizlik klassifikatori rad etsa `content` bo‘sh bo‘ladi."""
    resp = _Response({"tavsif": "x", "odamlar": 0, "ogohlantirish": False, "sabab": ""})
    resp.content = []
    resp.stop_reason = "refusal"
    agent = VisionAgent(
        VisionConfig(enabled=True), UsageStore(tmp_path / "v.db"), client=FakeClient([resp])
    )

    with pytest.raises(VisionAgentError, match="bosh tortdi"):
        agent.analyze(JPEG)


def test_broken_json_reported(tmp_path: Path) -> None:
    agent = VisionAgent(
        VisionConfig(enabled=True),
        UsageStore(tmp_path / "v.db"),
        client=FakeClient([_Response("bu json emas")]),
    )
    with pytest.raises(VisionAgentError, match="JSON emas"):
        agent.analyze(JPEG)


def test_api_error_wrapped(tmp_path: Path) -> None:
    agent = VisionAgent(
        VisionConfig(enabled=True),
        UsageStore(tmp_path / "v.db"),
        client=FakeClient([RuntimeError("tarmoq yo'q")]),
    )
    with pytest.raises(VisionAgentError, match="muvaffaqiyatsiz"):
        agent.analyze(JPEG)


# ── Tormozlar: limit ─────────────────────────────────────────────────────


def test_daily_limit_stops_calls(agent: VisionAgent) -> None:
    for _ in range(5):
        agent.analyze(JPEG)

    with pytest.raises(BudgetExceeded, match="Kunlik"):
        agent.analyze(JPEG)


def test_monthly_limit_stops_calls(tmp_path: Path) -> None:
    agent = VisionAgent(
        VisionConfig(enabled=True, max_calls_per_day=100, max_calls_per_month=3),
        UsageStore(tmp_path / "v.db"),
        client=FakeClient(),
    )
    for _ in range(3):
        agent.analyze(JPEG)

    with pytest.raises(BudgetExceeded, match="Oylik"):
        agent.analyze(JPEG)


def test_budget_survives_restart(tmp_path: Path) -> None:
    """Limit diskda — tez-tez restart qilib limitni aylanib o‘tib bo‘lmaydi."""
    db = tmp_path / "v.db"
    first = VisionAgent(
        VisionConfig(enabled=True, max_calls_per_day=2), UsageStore(db), client=FakeClient()
    )
    first.analyze(JPEG)
    first.analyze(JPEG)

    # "Server qayta ishga tushdi" — yangi agent, o'sha baza.
    second = VisionAgent(
        VisionConfig(enabled=True, max_calls_per_day=2), UsageStore(db), client=FakeClient()
    )
    with pytest.raises(BudgetExceeded):
        second.analyze(JPEG)


def test_zero_limit_blocks_everything(tmp_path: Path) -> None:
    agent = VisionAgent(
        VisionConfig(enabled=True, max_calls_per_day=0),
        UsageStore(tmp_path / "v.db"),
        client=FakeClient(),
    )
    with pytest.raises(BudgetExceeded):
        agent.analyze(JPEG)


def test_budget_left_reports_usage(agent: VisionAgent) -> None:
    agent.analyze(JPEG)
    left = agent.budget_left()
    assert left["today_calls"] == 1
    assert left["today_left"] == 4
    assert left["today_cost_usd"] > 0


# ── Tormozlar: oraliq ────────────────────────────────────────────────────


def test_interval_blocks_rapid_repeat(agent: VisionAgent) -> None:
    """Kamera sekundiga 25 kadr beradi — oraliq bo‘lmasa hisob bir kunda tugaydi."""
    assert agent.should_analyze("cam1", now=1000.0) is True
    agent.analyze(JPEG, camera_id="cam1", now=1000.0)

    assert agent.should_analyze("cam1", now=1010.0) is False
    assert agent.should_analyze("cam1", now=1000.0 + 300) is True


def test_interval_is_per_camera(agent: VisionAgent) -> None:
    agent.analyze(JPEG, camera_id="cam1", now=1000.0)
    assert agent.should_analyze("cam2", now=1000.0) is True


# ── Sarf tarixi ──────────────────────────────────────────────────────────


def test_recent_calls_recorded(agent: VisionAgent) -> None:
    agent.analyze(JPEG, camera_id="Kirish-1")
    rows = agent.usage.recent()
    assert len(rows) == 1
    assert rows[0]["camera_id"] == "Kirish-1"
    assert rows[0]["cost_usd"] > 0


def test_status_shape(agent: VisionAgent) -> None:
    status = agent.status()
    assert status["enabled"] is True
    assert status["model"] == "claude-opus-5"
    assert status["limits"]["per_day"] == 5
    assert status["estimated_monthly_usd"] > 0


# ── API ──────────────────────────────────────────────────────────────────


def _client(tmp_path: Path, *, enabled: bool = True, fake=None):
    from fastapi.testclient import TestClient

    from chaqimchi_ai.audit import AuditLog
    from chaqimchi_ai.events import EventLog
    from chaqimchi_ai.runtime.container import AppContainer
    from chaqimchi_ai.settings import AppSettings
    from webapp.main import create_app

    settings = AppSettings()
    settings.vision.enabled = enabled
    settings.vision.max_calls_per_day = 5
    container = AppContainer(
        tmp_path,
        settings=settings,
        events=EventLog(tmp_path / "events.db"),
        audit=AuditLog(tmp_path / "audit.db"),
    )
    if enabled:
        # Konteyner agentni qurgach, klientni soxtaga almashtiramiz.
        container.vision._client = fake or FakeClient()
    return TestClient(create_app(container)), container


def test_api_status_when_enabled(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    body = client.get("/api/vision/status").json()
    assert body["enabled"] is True
    assert body["model"] == "claude-opus-5"
    assert body["usage"]["today_calls"] == 0


def test_api_status_when_disabled(tmp_path: Path) -> None:
    client, _ = _client(tmp_path, enabled=False)
    body = client.get("/api/vision/status").json()
    assert body["enabled"] is False


def test_api_analyze_returns_uzbek_text(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)

    r = client.post(
        "/api/vision/analyze",
        files={"file": ("kadr.jpg", JPEG, "image/jpeg")},
        data={"camera_id": "Kirish-1"},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tavsif"] == "Kassada ikki xaridor turibdi."
    assert body["camera_id"] == "Kirish-1"
    assert body["cost_usd"] > 0


def test_api_analyze_disabled_returns_503(tmp_path: Path) -> None:
    client, _ = _client(tmp_path, enabled=False)
    r = client.post("/api/vision/analyze", files={"file": ("k.jpg", JPEG, "image/jpeg")})
    assert r.status_code == 503


def test_api_analyze_over_budget_returns_429(tmp_path: Path) -> None:
    client, container = _client(tmp_path)
    for _ in range(5):
        client.post("/api/vision/analyze", files={"file": ("k.jpg", JPEG, "image/jpeg")})

    r = client.post("/api/vision/analyze", files={"file": ("k.jpg", JPEG, "image/jpeg")})

    assert r.status_code == 429
    assert "limit" in r.json()["error"].lower()


def test_api_analyze_empty_file(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    r = client.post("/api/vision/analyze", files={"file": ("k.jpg", b"", "image/jpeg")})
    assert r.status_code == 400


def test_api_analyze_requires_key_when_enabled(tmp_path: Path) -> None:
    client, container = _client(tmp_path)
    sec = container.settings.security
    sec.api_key_enabled = True
    sec.api_key = "maxfiy"
    try:
        r = client.post("/api/vision/analyze", files={"file": ("k.jpg", JPEG, "image/jpeg")})
        assert r.status_code == 401
        ok = client.post(
            "/api/vision/analyze",
            files={"file": ("k.jpg", JPEG, "image/jpeg")},
            headers={"X-API-Key": "maxfiy"},
        )
        assert ok.status_code == 200
    finally:
        sec.api_key_enabled = False
        sec.api_key = None


def test_api_recent_lists_calls(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    client.post("/api/vision/analyze", files={"file": ("k.jpg", JPEG, "image/jpeg")})

    body = client.get("/api/vision/recent").json()

    assert body["ok"] is True
    assert len(body["calls"]) == 1
