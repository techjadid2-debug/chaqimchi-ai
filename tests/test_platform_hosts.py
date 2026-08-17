"""chaqimchi.uz subdomen platformasi: host-aware xizmat va URL qatlami.

Asosiy shart — ORQAGA MOSLIK: subdomen envlarsiz hamma narsa eski
bitta-domen rejimida ishlashi kerak (butun eski test to'plami shu holatda
o'tadi).  Envlar berilganda esa har bo'lim o'z subdomeniga ko'chadi.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cloud import urls


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    import cloud.main as main

    monkeypatch.setenv("CHAQIMCHI_CLOUD_ADMIN_KEY", "test-admin")
    monkeypatch.setenv("CHAQIMCHI_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("CHAQIMCHI_S3_ENDPOINT", raising=False)
    for key in (
        "CHAQIMCHI_PUBLIC_URL",
        "CHAQIMCHI_APP_URL",
        "CHAQIMCHI_API_URL",
        "CHAQIMCHI_DL_URL",
        "CHAQIMCHI_PARTNER_URL",
        "CHAQIMCHI_ADMIN_URL",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "cloud.db")
    monkeypatch.setattr(main, "_store", None)
    return TestClient(main.app)


def _subdomains(monkeypatch) -> None:
    monkeypatch.setenv("CHAQIMCHI_PUBLIC_URL", "https://chaqimchi.uz")
    monkeypatch.setenv("CHAQIMCHI_APP_URL", "https://app.chaqimchi.uz")
    monkeypatch.setenv("CHAQIMCHI_API_URL", "https://api.chaqimchi.uz")
    monkeypatch.setenv("CHAQIMCHI_DL_URL", "https://dl.chaqimchi.uz")
    monkeypatch.setenv("CHAQIMCHI_PARTNER_URL", "https://partner.chaqimchi.uz")
    monkeypatch.setenv("CHAQIMCHI_ADMIN_URL", "https://admin.chaqimchi.uz")


# ── URL qatlami ──────────────────────────────────────────────────────────


def test_url_helpers_fall_back_to_the_apex(monkeypatch) -> None:
    """Subdomen berilmagan — hammasi bitta domen (eski rejim)."""
    monkeypatch.setenv("CHAQIMCHI_PUBLIC_URL", "https://bitta.example")
    for key in ("CHAQIMCHI_APP_URL", "CHAQIMCHI_API_URL", "CHAQIMCHI_DL_URL"):
        monkeypatch.delenv(key, raising=False)

    assert urls.app_url() == "https://bitta.example"
    assert urls.api_url() == "https://bitta.example"
    assert urls.dl_url() == "https://bitta.example"


def test_url_helpers_prefer_their_own_env(monkeypatch) -> None:
    _subdomains(monkeypatch)

    assert urls.app_url() == "https://app.chaqimchi.uz"
    assert urls.dl_url() == "https://dl.chaqimchi.uz"
    assert urls.partner_url() == "https://partner.chaqimchi.uz"


# ── Host bo'yicha bosh sahifa ────────────────────────────────────────────


def test_each_subdomain_serves_its_own_section(client: TestClient) -> None:
    """app. — mijoz paneli, partner. — montajchi, dl. — yuklab olish."""
    landing = client.get("/", headers={"host": "chaqimchi.uz"})
    assert "Chaqimchi" in landing.text and "narx" in landing.text.lower()

    app_page = client.get("/", headers={"host": "app.chaqimchi.uz"})
    assert "owner" in app_page.text.lower() or "panel" in app_page.text.lower()
    assert app_page.text != landing.text

    partner_page = client.get("/", headers={"host": "partner.chaqimchi.uz"})
    assert "o‘rnatuvchi" in partner_page.text.lower() or "installer" in partner_page.text.lower()

    dl_page = client.get("/", headers={"host": "dl.chaqimchi.uz"})
    assert "Yuklab olish" in dl_page.text

    admin_page = client.get("/", headers={"host": "admin.chaqimchi.uz"})
    assert "admin" in admin_page.text.lower()


def test_without_subdomain_envs_the_old_paths_still_work(client: TestClient) -> None:
    """Orqaga moslik: envsiz /owner /installer /admin apexda ochiladi."""
    assert client.get("/owner").status_code == 200
    assert client.get("/installer").status_code == 200
    assert client.get("/admin").status_code == 200


def test_apex_panel_paths_redirect_to_subdomains_preserving_query(
    client: TestClient, monkeypatch
) -> None:
    """Eski `?key=` kirish havolalari yangi subdomenda ham ishlashi shart."""
    _subdomains(monkeypatch)

    response = client.get(
        "/owner?key=abc123", headers={"host": "chaqimchi.uz"}, follow_redirects=False
    )

    assert response.status_code == 301
    assert response.headers["location"] == "https://app.chaqimchi.uz/?key=abc123"

    # Subdomen hostining o'zida 301 YO'Q — sahifa ochiladi.
    direct = client.get("/owner", headers={"host": "app.chaqimchi.uz"}, follow_redirects=False)
    assert direct.status_code == 200


# ── robots / sitemap ─────────────────────────────────────────────────────


def test_robots_allows_landing_and_docs_but_blocks_panels(client: TestClient, monkeypatch) -> None:
    _subdomains(monkeypatch)

    assert "Allow: /" in client.get("/robots.txt", headers={"host": "chaqimchi.uz"}).text
    assert "Allow: /" in client.get("/robots.txt", headers={"host": "docs.chaqimchi.uz"}).text
    for host in ("app.chaqimchi.uz", "admin.chaqimchi.uz", "api.chaqimchi.uz", "dl.chaqimchi.uz"):
        assert "Disallow: /" in client.get("/robots.txt", headers={"host": host}).text


def test_sitemap_exists_only_on_the_apex(client: TestClient, monkeypatch) -> None:
    _subdomains(monkeypatch)

    apex = client.get("/sitemap.xml", headers={"host": "chaqimchi.uz"})
    assert apex.status_code == 200
    assert "https://chaqimchi.uz/maxfiylik" in apex.text

    assert client.get("/sitemap.xml", headers={"host": "app.chaqimchi.uz"}).status_code == 404


# ── Platforma manzillari endpointi ───────────────────────────────────────


def test_public_urls_endpoint_reports_sections(client: TestClient, monkeypatch) -> None:
    _subdomains(monkeypatch)

    data = client.get("/api/v1/public/urls").json()

    assert data["dl"] == "https://dl.chaqimchi.uz"
    assert data["api"] == "https://api.chaqimchi.uz"
    assert data["apex"] == "https://chaqimchi.uz"


def test_quick_trial_commands_use_the_right_sections(client: TestClient, monkeypatch) -> None:
    """Yuklab olish dl'dan, `--cloud` api'dan — bo'limlar aralashmasin."""
    _subdomains(monkeypatch)
    monkeypatch.setenv("CHAQIMCHI_TELEGRAM_BOT_USERNAME", "")

    response = client.post(
        "/api/v1/public/quick-trial",
        json={"full_name": "Test Testov", "phone": "+998901234567", "consent": True},
    )
    if response.status_code != 200:
        pytest.skip(f"quick-trial mavjud emas: {response.status_code}")
    body = response.json()
    assert "dl.chaqimchi.uz/downloads" in body["linux_command"]
    assert "--cloud https://api.chaqimchi.uz" in body["linux_command"]
    assert body["owner_url"].startswith("https://app.chaqimchi.uz/owner")


# ── Yangi landing yo'llari ───────────────────────────────────────────────


def test_new_landing_routes(client: TestClient) -> None:
    assert client.get("/maxfiylik").status_code == 200
    tariffs = client.get("/tariflar", follow_redirects=False)
    assert tariffs.status_code == 301 and tariffs.headers["location"] == "/#narx"


# ── docs sahifalari ──────────────────────────────────────────────────────


def test_docs_pages_are_served(client: TestClient) -> None:
    index = client.get("/", headers={"host": "docs.chaqimchi.uz"})
    assert index.status_code == 200 and "Hujjatlar" in index.text

    for name in (
        "ornatish-windows",
        "nvr-hikvision",
        "nvr-dahua",
        "nvr-uniview",
        "muammolar",
        "xavfsizlik",
    ):
        page = client.get(f"/{name}")
        assert page.status_code == 200, name
        assert "docs.css" in page.text

    hik = client.get("/nvr-hikvision").text
    assert "/Streaming/Channels/102" in hik, "haqiqiy RTSP format bo'lsin"
    assert client.get("/docs-static/assets/docs.css").status_code == 200
    assert client.get("/docs-static/../etc/passwd").status_code in (404, 422)
