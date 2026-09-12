"""Yaroqsiz chizma chizgan odamga DARHOL aytilsin.

Nega bu test bor.  Juda kichik chiziq yoki zona muvaffaqiyatli
saqlanadi, revizya ko'tariladi va qurilma uni qabul qiladi — faqat
hodisa hech qachon chiqmaydi.  Pilot do'konida 4 piksellik chiziq va
29x20 piksellik zona shu holda oylab turgan; `zone_entered` nol edi va
nosozlik FAQAT admin mijoz kartasida ko'rinardi, ya'ni chizmani chizgan
odam (usta yoki ega) hech narsa bilmasdi.

Tekshiruvning o'zi allaqachon bor edi (`cloud/config_health.py`) — u
shunchaki chizayotgan odamga ko'rsatilmasdi.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ENES_CLOUD_ADMIN_KEY", "test-admin")
    monkeypatch.setenv("ENES_OWNER_JWT_SECRET", "o" * 64)
    monkeypatch.setenv("ENES_PORTAL_JWT_SECRET", "p" * 64)
    monkeypatch.setenv("ENES_PUBLIC_URL", "https://enes.test")
    monkeypatch.setattr("cloud.main.DB_PATH", tmp_path / "cloud.db")
    monkeypatch.setattr("cloud.main._store", None)
    monkeypatch.setattr("cloud.main._event_store", None)
    monkeypatch.setattr("cloud.main._event_store_key", None)
    from cloud.main import app

    return TestClient(app)


@pytest.fixture
def owner(client: TestClient) -> Dict[str, Any]:
    trial = client.post(
        "/api/v1/public/quick-trial",
        json={
            "phone": "+998 90 123 45 67",
            "full_name": "Ega Egayev",
            "company": "Namuna do'kon",
            "username": "dokonchi",
            "password": "parol12345",
            "consent": True,
        },
    ).json()
    login = client.post(
        "/api/v1/auth/login", json={"username": "dokonchi", "password": "parol12345"}
    ).json()
    return {
        "site_id": trial["site_id"],
        "headers": {"Authorization": f"Bearer {login['access_token']}"},
    }


def _save(client: TestClient, owner: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    base = client.get("/api/v1/owner/config", headers=owner["headers"]).json()["config"]
    response = client.put(
        "/api/v1/owner/config", headers=owner["headers"], json={**base, **config}
    )
    assert response.status_code == 200, response.text
    return response.json()


def _problems(payload: Dict[str, Any]) -> List[str]:
    return [item["problem"] for item in payload.get("geometry_problems") or []]


# ── Chizmani chizgan odam javob olsin ───────────────────────────────────


def test_a_too_short_line_is_reported_back(client: TestClient, owner: Dict[str, Any]) -> None:
    """Pilotdagi aynan holat: 4 piksellik chiziq."""
    saved = _save(
        client,
        owner,
        {"lines": [{"name": "Kirish", "camera_id": "camera-01", "start": [0.5, 0.5], "end": [0.506, 0.5]}]},
    )

    problems = _problems(saved)
    assert problems, "qisqa chiziq haqida hech narsa aytilmadi"
    assert "juda qisqa" in problems[0]
    assert "piksel" in problems[0], "o'lchov ko'rsatilsin — usta nimani tuzatishni bilsin"


def test_a_too_small_zone_is_reported_back(client: TestClient, owner: Dict[str, Any]) -> None:
    """Pilotdagi aynan holat: 29x20 piksellik zona."""
    saved = _save(
        client,
        owner,
        {
            "zones": [
                {
                    "name": "Navbat",
                    "camera_id": "camera-01",
                    "polygon": [[0.5, 0.5], [0.52, 0.5], [0.52, 0.53], [0.5, 0.53]],
                    "queue": True,
                }
            ]
        },
    )

    assert any("kichik" in item or "ensiz" in item for item in _problems(saved))


def test_a_good_drawing_reports_nothing(client: TestClient, owner: Dict[str, Any]) -> None:
    """Yashil holat ham tekshiriladi: ogohlantirish shovqinga aylanmasin."""
    saved = _save(
        client,
        owner,
        {
            "lines": [
                {"name": "Kirish", "camera_id": "camera-01", "start": [0.2, 0.5], "end": [0.8, 0.5]}
            ],
            "zones": [
                {
                    "name": "Navbat",
                    "camera_id": "camera-01",
                    "polygon": [[0.2, 0.2], [0.6, 0.2], [0.6, 0.6], [0.2, 0.6]],
                    "queue": True,
                }
            ],
        },
    )

    assert _problems(saved) == []


def test_the_saved_config_is_still_returned(client: TestClient, owner: Dict[str, Any]) -> None:
    """Tekshiruv javobni buzmasin — panel `config` ni o'qiydi."""
    saved = _save(
        client,
        owner,
        {"lines": [{"name": "Kirish", "camera_id": "camera-01", "start": [0.2, 0.5], "end": [0.8, 0.5]}]},
    )

    assert saved["config"]["lines"][0]["name"] == "Kirish"
    assert saved["revision"] >= 1


# ── Uchinchi (va to'rtinchi) endpoint ham unutilmasin ───────────────────


def test_every_config_endpoint_checks_the_drawing() -> None:
    """Chizmani UCH xil odam saqlaydi: ega, admin va o'rnatuvchi.

    Uchtasi alohida endpoint va bu loyihada aynan shunday tarqalgan
    tekshiruv bir marta jimgina eskirgan edi (funksiya darvozasi uch
    joyda). Shuning uchun qulf strukturaviy: `update_site_config()` ni
    chaqirgan har endpoint javobni `_with_geometry_problems()` dan
    o'tkazishi shart.
    """
    tree = ast.parse((ROOT / "cloud" / "main.py").read_text(encoding="utf-8"))

    # Chizmani QABUL QILADIGAN endpoint — `SiteConfigBody` olgani.
    # `update_site_config()` ni bo'lak sozlamalarni yozadigan
    # funksiyalar ham chaqiradi (kamera inventari, funksiya qoralamasi,
    # davomat rollari) — u yerda odam chizma chizmaydi va ogohlantirish
    # shovqin bo'lardi.
    saqlovchilar: List[str] = []
    missing: List[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        takes_drawing = any(
            isinstance(argument.annotation, ast.Name)
            and argument.annotation.id == "SiteConfigBody"
            for argument in node.args.args
        )
        dump = ast.dump(node)
        # Faqat SAQLAYDIGANI: `_validate_site_config()` ham
        # `SiteConfigBody` oladi, lekin javob qaytarmaydi.
        if not takes_drawing or "'update_site_config'" not in dump:
            continue
        saqlovchilar.append(node.name)
        if "'_with_geometry_problems'" not in dump:
            missing.append(node.name)

    assert len(saqlovchilar) >= 3, (
        f"ega, admin va o'rnatuvchi yo'llari topilmadi: {saqlovchilar}"
    )
    assert missing == [], (
        f"chizmani qabul qiladi, lekin tekshirmaydi: {missing} — javobni "
        "`_with_geometry_problems()` dan o'tkazing"
    )
