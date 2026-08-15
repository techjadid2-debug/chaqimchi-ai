"""Reliz fayllari qurilmagacha yetib boradimi.

Bu testlar umuman yo'q edi — aynan shu sababdan `docker-compose.prod.yml`
da `./releases` mount yo'qligi sezilmay qolgan: `deploy_cloud.sh` standart
holda o'sha faylni ishlatadi, ya'ni har `/releases/*.tar.gz` so'rovi 404
qaytarardi va bir buyruqli o'rnatish umuman mavjud emas edi.

Ikkita darajada tekshiriladi: HTTP (fayl beriladimi, xavfsizmi) va
deploy artefaktlari (mount va env o'rnida turibdimi).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = "chaqimchi-sotqin-0.6.0.tar.gz"
MANIFEST = "chaqimchi-sotqin-0.6.0.json"


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    import cloud.main as main

    monkeypatch.setenv("CHAQIMCHI_CLOUD_ADMIN_KEY", "test-admin")
    monkeypatch.setenv("CHAQIMCHI_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "cloud.db")
    monkeypatch.setattr(main, "_store", None)
    monkeypatch.setattr(main, "_event_store", None)
    monkeypatch.setattr(main, "_event_store_key", None)
    # `BASE_DIR` — `/releases` shu yerdan o'qiydi.
    monkeypatch.setattr(main, "BASE_DIR", tmp_path)
    releases = tmp_path / "releases"
    releases.mkdir()
    (releases / ARCHIVE).write_bytes(b"soxta-arxiv")
    (releases / MANIFEST).write_text('{"version":"0.6.0"}', encoding="utf-8")
    with TestClient(main.app) as test_client:
        yield test_client


# ── Fayllarni berish ─────────────────────────────────────────────────────


def test_archive_is_served(client: TestClient) -> None:
    response = client.get(f"/releases/{ARCHIVE}")

    assert response.status_code == 200
    assert response.content == b"soxta-arxiv"
    assert response.headers["content-type"] == "application/gzip"
    assert "immutable" in response.headers["cache-control"]


def test_manifest_is_served_as_json(client: TestClient) -> None:
    """Qurilma imzolangan manifestni shu yerdan oladi — `--fetch-version`
    rejimi shunga tayanadi."""
    response = client.get(f"/releases/{MANIFEST}")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    # Manifest keshlanmaydi: kalit almashtirilsa bir xil versiya qayta
    # imzolanishi mumkin.
    assert response.headers["cache-control"] == "no-cache"


def test_both_files_are_public(client: TestClient) -> None:
    """Autentifikatsiya qo'yib bo'lmaydi: `bootstrap_sotqin.sh` arxivni
    pairing'dan **oldin** oladi.  Xavfsizlik imzodan keladi."""
    for name in (ARCHIVE, MANIFEST):
        assert client.get(f"/releases/{name}").status_code == 200


# ── Xavfsizlik ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "../.env.production",
        "../../etc/passwd",
        "sotqin.env",
        "chaqimchi-sotqin-0.6.0.tar.gz.bak",
        "boshqa-mahsulot-1.0.tar.gz",
        "chaqimchi-sotqin-0.6.0.sh",
    ],
)
def test_only_release_files_are_served(client: TestClient, name: str) -> None:
    assert client.get(f"/releases/{name}").status_code == 404


def test_a_missing_release_is_not_an_error_page(client: TestClient) -> None:
    assert client.get("/releases/chaqimchi-sotqin-9.9.9.tar.gz").status_code == 404


# ── Deploy artefaktlari ──────────────────────────────────────────────────


def test_every_compose_file_mounts_releases() -> None:
    """Ikkala fayl ham mount qilishi shart.

    `deploy_cloud.sh:6` standart holda `docker-compose.prod.yml` ni oladi,
    lekin server `docker-compose.contabo.yml` bilan ko'tarilgan bo'lishi
    mumkin. Qaysi biri ishlayotganini bilmasdan ham reliz berilsin.
    """
    for name in ("docker-compose.prod.yml", "docker-compose.contabo.yml"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "./releases:/app/releases:ro" in text, name


def test_releases_stay_out_of_the_docker_image() -> None:
    """Arxiv image ichiga kirsa har build bilan eskirgan nusxa tarqalardi."""
    ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()

    assert "releases/" in [line.strip() for line in ignored]


def test_the_installer_endpoint_needs_a_published_release() -> None:
    """`CHAQIMCHI_SOTQIN_RELEASE_URL`/`_SHA256` to'ldirilmasa 503.

    Bu to'g'ri xatti-harakat: yarim sozlangan cloud ishlamaydigan
    o'rnatish buyrug'ini bermasligi kerak.
    """
    example = (ROOT / ".env.production.example").read_text(encoding="utf-8")

    assert "CHAQIMCHI_SOTQIN_RELEASE_URL=" in example
    assert "CHAQIMCHI_SOTQIN_RELEASE_SHA256=" in example
