"""Marshrutlar ONNX modelisiz testlanadi.

Bu Faza 0 ning butun maqsadi. Bungacha `webapp/main.py` handlerlari
`get_db()` / `get_engine()` ni to'g'ridan-to'g'ri chaqirar edi, shuning uchun
`app.dependency_overrides` ishlamas va marshrutga umuman murojaat qilib
bo'lmasdi — `tests/test_webapp_routes.py` faqat yo'l ro'yxatini tekshirardi.

Endi har bir handler `Depends()` orqali oladi, demak CI 400 MB `buffalo_l`
modelini yuklamasdan haqiqiy so'rov yubora oladi.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from chaqimchi_ai.audit import AuditLog
from chaqimchi_ai.database import FaceDatabase
from chaqimchi_ai.events import EventLog
from chaqimchi_ai.runtime.container import AppContainer
from chaqimchi_ai.settings import AppSettings
from webapp.deps import get_engine
from webapp.main import create_app

EMBED_DIM = 512


class FakeEngine:
    """`FaceEngine` o'rniga — ONNX yuklamaydi."""

    model_name = "fake"
    det_size = (640, 640)
    recognition_ready = True
    providers = ["CPUExecutionProvider"]

    def __init__(self, *, faces: int = 1) -> None:
        self.faces = faces
        self.analyze_calls = 0

    def analyze_frame(self, img):
        self.analyze_calls += 1
        return (
            [{"bbox": [0, 0, 10, 10], "det_score": 0.99} for _ in range(self.faces)],
            1.5,
        )

    def extract_primary_embedding(self, img):
        if not self.faces:
            return None
        vec = np.zeros(EMBED_DIM, dtype=np.float32)
        vec[0] = 1.0
        return vec


def _png_bytes() -> bytes:
    """Haqiqiy dekodlanadigan kichik PNG (cv2.imdecode uni o'qishi shart)."""
    cv2 = pytest.importorskip("cv2")
    ok, buf = cv2.imencode(".png", np.zeros((8, 8, 3), dtype=np.uint8))
    assert ok
    return buf.tobytes()


@pytest.fixture
def container(tmp_path: Path) -> AppContainer:
    """Soxta engine + haqiqiy (lekin vaqtinchalik) omborlar bilan konteyner."""
    settings = AppSettings()
    return AppContainer(
        tmp_path,
        settings=settings,
        engine=FakeEngine(),
        db=FaceDatabase(tmp_path / "db"),
        events=EventLog(tmp_path / "events.db"),
        audit=AuditLog(tmp_path / "audit.db"),
    )


@pytest.fixture
def client(container: AppContainer) -> TestClient:
    # `with` ishlatilmaydi — lifespan ishga tushmasin (kameralar, litsenziya).
    return TestClient(create_app(container))


def test_app_boots_without_onnx_model(client: TestClient, container: AppContainer) -> None:
    """TestClient haqiqiy modelsiz ko'tariladi va /health javob beradi."""
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["engine"]["model_name"] == "fake"
    assert body["db_size"] == 0


def test_health_reports_starting_when_engine_not_built(tmp_path: Path) -> None:
    """Bo'sh konteynerda /health 503 beradi va modelni **qurmaydi**."""
    empty = AppContainer(tmp_path, settings=AppSettings())
    c = TestClient(create_app(empty))
    r = c.get("/health")
    assert r.status_code == 503
    assert r.json()["status"] == "starting"
    # Eng muhimi: /health chaqiruvi 3-8 soniyalik model yuklashni
    # boshlab yubormagan.
    assert empty.engine_or_none is None


def test_dependency_override_replaces_engine(client: TestClient) -> None:
    """`app.dependency_overrides[get_engine]` rostdan ishlaydi."""
    other = FakeEngine(faces=3)
    client.app.dependency_overrides[get_engine] = lambda: other
    try:
        r = client.post("/api/analyze", files={"file": ("x.png", _png_bytes(), "image/png")})
        assert r.status_code == 200
        assert len(r.json()["faces"]) == 3
        assert other.analyze_calls == 1
    finally:
        client.app.dependency_overrides.clear()


def test_person_add_and_identify_roundtrip(client: TestClient) -> None:
    """Yozish/qidirish oqimi to'liq — soxta engine bilan."""
    img = _png_bytes()
    r = client.post(
        "/api/persons/add",
        data={"name": "Test Odam"},
        files={"file": ("x.png", img, "image/png")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["person"]["name"] == "Test Odam"

    assert len(client.get("/api/persons").json()) == 1

    r = client.post("/api/identify", files={"file": ("x.png", img, "image/png")})
    assert r.status_code == 200
    assert r.json()["matches"][0]["name"] == "Test Odam"


def test_no_face_returns_400(tmp_path: Path) -> None:
    blind = AppContainer(
        tmp_path,
        settings=AppSettings(),
        engine=FakeEngine(faces=0),
        db=FaceDatabase(tmp_path / "db"),
        audit=AuditLog(tmp_path / "audit.db"),
    )
    c = TestClient(create_app(blind))
    r = c.post(
        "/api/persons/add",
        data={"name": "X"},
        files={"file": ("x.png", _png_bytes(), "image/png")},
    )
    assert r.status_code == 400
    assert r.json()["ok"] is False


def test_events_limit_is_bounded(client: TestClient) -> None:
    """`?limit` cheklangan — bungacha butun jadvalni tortish mumkin edi."""
    assert client.get("/api/events?limit=50").status_code == 200
    assert client.get("/api/events?limit=100000").status_code == 422
    assert client.get("/api/events?limit=0").status_code == 422


def test_oversized_upload_rejected(client: TestClient) -> None:
    """Katta fayl 413 bilan rad etiladi, xotiraga to'liq o'qilmaydi."""
    from webapp.imaging import MAX_UPLOAD_BYTES

    big = io.BytesIO(b"\x00" * (MAX_UPLOAD_BYTES + 1024))
    r = client.post("/api/analyze", files={"file": ("big.png", big, "image/png")})
    assert r.status_code == 413
    assert r.json()["ok"] is False


def test_error_envelope_is_consistent(client: TestClient) -> None:
    """Har bir xato `{"ok": false, "error": ...}` shaklida.

    Bungacha `HTTPException` faqat `{"detail": ...}` berardi va frontend
    uni "Xato: undefined" deb ko'rsatardi.
    """
    r = client.delete("/api/persons/yoq-bunday-id")
    assert r.status_code == 404
    body = r.json()
    assert body["ok"] is False
    assert body["error"]
