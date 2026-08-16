"""Windows dasturini cloudga ulash.

Ulanmagan dastur to'liq ishlaydi, lekin **yolg'iz**: hodisalar lokal
navbatda qoladi, mijoz panelida hech nima ko'rinmaydi va Telegram
ogohlantirishlari kelmaydi.  Shuning uchun bu yerda tekshiriladigan
narsa — pairing natijasi `config.yaml` ga **haqiqatan** yozildimi.

Eng xavfli holat — **yarim ulangan** config: `enabled: true` turadi-yu
token yo'q.  Bunda dastur cloudga urinaveradi, hech qachon ulanmaydi va
sababi hech qayerda ko'rinmaydi.  Shuning uchun har bir xato yo'lida
config o'zgarmasligi alohida tekshiriladi.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Dict

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient

CLOUD = "https://cloud.example.uz"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("CHAQIMCHI_LOCAL_DIR", str(tmp_path))
    from chaqimchi_ai.local import app as app_module
    from chaqimchi_ai.local import cloud_link, config_store, paths, supervisor

    for module in (paths, config_store, cloud_link, supervisor, app_module):
        importlib.reload(module)
    return TestClient(app_module.app)


def _cloud_sync(tmp_path: Path) -> Dict[str, Any]:
    """Configdagi `cloud_sync` bo'limi.

    Fayl umuman yo'q bo'lishi ham to'g'ri natija: pairing kod noto'g'ri
    bo'lsa dastur configga **tegmaydi**.  Shuning uchun yo'qligi xato
    emas, bo'sh lug'at.
    """
    path = tmp_path / "config.yaml"
    if not path.is_file():
        return {}
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("cloud_sync") or {}


class _FakeResponse:
    def __init__(self, status_code: int, payload: Dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = str(self._payload)

    def json(self) -> Dict[str, Any]:
        return self._payload


# ── Muvaffaqiyatli ulanish ───────────────────────────────────────────────


def test_pairing_writes_every_identifier_the_sync_needs(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`CloudEventSync` uchtasini ham talab qiladi; bittasi yetishmasa
    hodisalar jimgina yuborilmay qoladi."""
    monkeypatch.setattr(
        "chaqimchi_ai.local.cloud_link.httpx.post",
        lambda *a, **k: _FakeResponse(
            200, {"site_id": "site-1", "device_id": "dev-1", "device_token": "tok-1"}
        ),
    )
    response = client.post("/api/setup/pair", json={"code": "A1B2C3", "cloud_url": CLOUD})
    assert response.status_code == 200

    saved = _cloud_sync(tmp_path)
    assert saved["enabled"] is True
    assert saved["url"] == CLOUD
    assert saved["site_id"] == "site-1"
    assert saved["device_id"] == "dev-1"
    assert saved["device_token"] == "tok-1"


def test_pairing_never_returns_the_device_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Token brauzerga chiqsa, uni ko'rgan har kim qurilma nomidan
    hodisa yubora oladi."""
    monkeypatch.setattr(
        "chaqimchi_ai.local.cloud_link.httpx.post",
        lambda *a, **k: _FakeResponse(
            200, {"site_id": "s", "device_id": "d", "device_token": "MAXFIY-TOKEN"}
        ),
    )
    client.post("/api/setup/pair", json={"code": "A1B2C3", "cloud_url": CLOUD})
    for path in ("/api/setup/cloud-status", "/api/status", "/api/setup/summary"):
        assert "MAXFIY-TOKEN" not in client.get(path).text, path


def test_code_is_accepted_in_the_shape_people_actually_type(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mijoz kodni kichik harf bilan yoki chiziqcha bilan ko'chiradi."""
    monkeypatch.setattr(
        "chaqimchi_ai.local.cloud_link.httpx.post",
        lambda *a, **k: _FakeResponse(
            200, {"site_id": "s", "device_id": "d", "device_token": "t"}
        ),
    )
    assert client.post(
        "/api/setup/pair", json={"code": " a1b2-c3 ", "cloud_url": "cloud.example.uz"}
    ).status_code == 200
    # `https://` qo'shilgan bo'lishi kerak: usiz `CloudEventSync` manzilni
    # ochib bo'lmaydigan holda saqlab qo'yardi.
    assert _cloud_sync(tmp_path)["url"] == "https://cloud.example.uz"


# ── Xato yo'llari: config o'zgarmasligi shart ────────────────────────────


@pytest.mark.parametrize(
    "code",
    ["", "12345", "1234567", "GHIJKL", "A1B2C"],
    ids=["bo'sh", "qisqa", "uzun", "hex-emas", "besh-belgi"],
)
def test_a_bad_code_changes_nothing(client: TestClient, tmp_path: Path, code: str) -> None:
    client.post("/api/setup/pair", json={"code": code or "x", "cloud_url": CLOUD})
    assert _cloud_sync(tmp_path).get("enabled") is not True


def test_plain_http_is_refused(client: TestClient, tmp_path: Path) -> None:
    """Qurilma tokeni shu ulanish orqali uzatiladi — ochiq HTTP'da uni
    yo'lda o'qib olish mumkin."""
    response = client.post(
        "/api/setup/pair", json={"code": "A1B2C3", "cloud_url": "http://cloud.example.uz"}
    )
    assert response.status_code == 422
    assert "https" in response.json()["detail"].lower()
    assert _cloud_sync(tmp_path).get("enabled") is not True


def test_rejected_code_leaves_no_half_connected_state(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cloud kodni rad etsa (muddati o'tgan/ishlatilgan) config toza qolsin."""
    monkeypatch.setattr(
        "chaqimchi_ai.local.cloud_link.httpx.post",
        lambda *a, **k: _FakeResponse(400, {"detail": "Pairing kod topilmadi"}),
    )
    response = client.post("/api/setup/pair", json={"code": "A1B2C3", "cloud_url": CLOUD})
    assert response.status_code == 422
    assert "kod" in response.json()["detail"].lower()
    assert _cloud_sync(tmp_path).get("enabled") is not True


def test_network_failure_leaves_no_half_connected_state(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*args, **kwargs):
        raise httpx.ConnectError("tarmoq yo'q")

    monkeypatch.setattr("chaqimchi_ai.local.cloud_link.httpx.post", _boom)
    response = client.post("/api/setup/pair", json={"code": "A1B2C3", "cloud_url": CLOUD})
    assert response.status_code == 422
    assert _cloud_sync(tmp_path).get("enabled") is not True


def test_incomplete_cloud_response_is_rejected(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`device_token`siz javob — yarim ulanish; qabul qilinmasligi kerak."""
    monkeypatch.setattr(
        "chaqimchi_ai.local.cloud_link.httpx.post",
        lambda *a, **k: _FakeResponse(200, {"site_id": "s", "device_id": "d"}),
    )
    assert client.post(
        "/api/setup/pair", json={"code": "A1B2C3", "cloud_url": CLOUD}
    ).status_code == 422
    assert _cloud_sync(tmp_path).get("enabled") is not True


# ── Ulanishni uzish ──────────────────────────────────────────────────────


def test_unpair_removes_the_token_not_just_the_flag(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dastur boshqa kompyuterga ko'chirilsa eski obyektga hodisa
    yuborib qo'ymasligi kerak."""
    monkeypatch.setattr(
        "chaqimchi_ai.local.cloud_link.httpx.post",
        lambda *a, **k: _FakeResponse(
            200, {"site_id": "s", "device_id": "d", "device_token": "t"}
        ),
    )
    client.post("/api/setup/pair", json={"code": "A1B2C3", "cloud_url": CLOUD})

    response = client.post("/api/setup/unpair")
    assert response.status_code == 200
    assert response.json()["connected"] is False

    saved = _cloud_sync(tmp_path)
    assert saved["enabled"] is False
    assert not saved.get("device_token")
    assert not saved.get("site_id")


def test_status_is_honest_before_pairing(client: TestClient) -> None:
    body = client.get("/api/setup/cloud-status").json()
    assert body["connected"] is False
    assert body["site_id"] is None
    assert body["owner_url"] is None
