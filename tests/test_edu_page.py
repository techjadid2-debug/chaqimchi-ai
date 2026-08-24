"""Chaqimchi Edu sahifasi va uning bulut bilan shartnomasi.

Sahifa kalkulyatorni brauzerda hisoblaydi — har bosishda so'rov
yuborish uni sekin va cheklovlarga bog'liq qilardi.  Lekin RAQAMLAR
serverdan keladi, aks holda narx ikki joyda saqlanib, biri eskirib
qolardi va sayt yolg'on summa ko'rsatardi.

Bu fayl aynan shu chegarani qo'riqlaydi.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

STATIC = Path(__file__).resolve().parents[1] / "cloud" / "static"
EDU_HTML = STATIC / "edu.html"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("CHAQIMCHI_APP_URL", "https://app.chaqimchi.test")
    monkeypatch.setenv("CHAQIMCHI_PUBLIC_URL", "https://chaqimchi.test")
    monkeypatch.setattr("cloud.main.DB_PATH", tmp_path / "cloud.db")
    monkeypatch.setattr("cloud.main._store", None)
    monkeypatch.setattr("cloud.main._event_store", None)
    monkeypatch.setattr("cloud.main._event_store_key", None)
    from cloud.main import app

    return TestClient(app)


# ── Endpoint ─────────────────────────────────────────────────────────


def test_the_calculator_gets_its_numbers_from_the_server(client: TestClient) -> None:
    response = client.get("/api/v1/public/edu-pricing")

    assert response.status_code == 200
    data = response.json()
    assert {item["code"] for item in data["institutions"]} == {"markaz", "maktab", "oliygoh"}
    assert data["round_to_uzs"] == 10_000


def test_the_public_catalog_matches_the_module(client: TestClient) -> None:
    """Endpoint konstantalarni qayta yozmasin — u faqat uzatadi."""
    from chaqimchi_ai.licensing import edu

    assert client.get("/api/v1/public/edu-pricing").json() == edu.catalog()


# ── Sahifa ───────────────────────────────────────────────────────────


def test_the_page_is_served_with_the_real_panel_address(client: TestClient) -> None:
    response = client.get("/edu")

    assert response.status_code == 200
    assert "__APP_URL__" not in response.text


def test_the_page_opens_by_explaining_the_whole_product() -> None:
    """Bu sahifaga to'g'ridan-to'g'ri kelgan maktab direktori
    kompaniyani umuman bilmasligi mumkin."""
    html = EDU_HTML.read_text(encoding="utf-8")

    assert "Chaqimchi AI nima" in html
    assert "Chaqimchi Retail" in html


def test_the_page_never_writes_a_price_into_its_own_script() -> None:
    """Narx sahifaga yozilsa, u o'zgarganda sayt eskisini ko'rsatib
    turaverardi va buni hech kim sezmasdi.

    `<noscript>` bundan mustasno: u JavaScript ishlamaganda ko'rinadi
    va bazaviy narxni matn sifatida aytadi.
    """
    html = EDU_HTML.read_text(encoding="utf-8")
    script = html[html.index("<script>") : html.index("</script>")]

    # Narx darajasidagi raqamlar (5 xonadan katta) skriptda bo'lmasin.
    numbers = [int(item) for item in re.findall(r"\b\d{5,}\b", script)]

    assert not numbers, f"skriptga narx yozilgan: {numbers}"


def test_the_wizard_starts_from_people_not_cameras() -> None:
    """Mijozdan kamera sonini so'rash noto'g'ri boshlanish bo'lardi:
    u "nechta kamerangiz bor?" degan savolga 32 deb javob beradi va
    narx keraksiz qimmat chiqadi."""
    html = EDU_HTML.read_text(encoding="utf-8")

    people_at = html.index('for="people"')
    cameras_at = html.index('for="cameras"')
    assert people_at < cameras_at


def test_the_owner_can_correct_the_camera_estimate() -> None:
    html = EDU_HTML.read_text(encoding="utf-8")

    assert 'id="cameras"' in html
    assert "syncCameraEstimate" in html


def test_the_device_price_stays_out_of_the_monthly_total() -> None:
    """Bir martalik qurilma narxi oylik obunaga qo'shilsa, taqqoslash
    butunlay noto'g'ri chiqardi."""
    html = EDU_HTML.read_text(encoding="utf-8")

    assert "oylik obunaga kirmaydi" in html
    assert 'id="ownPc"' in html


def test_the_lead_carries_the_whole_calculation() -> None:
    """Ariza faqat telefon raqami bo'lsa, sotuvchi mijozdan hammasini
    qaytadan so'rashi kerak bo'lardi."""
    html = EDU_HTML.read_text(encoding="utf-8")

    assert '"EDU | "' in html
    assert "/api/v1/public/leads" in html


def test_the_page_says_the_prices_are_provisional() -> None:
    """Narxlar pilot mijozlar bilan tekshirilmagan boshlang'ich
    model — buni yashirish keyin noqulay suhbatga olib kelardi."""
    html = EDU_HTML.read_text(encoding="utf-8")

    assert "mo‘ljal" in html


def test_the_page_states_the_rules_for_childrens_biometrics() -> None:
    """Maktab bilan ishlaganda Face ID ni shunchaki yoqib qo'yib
    bo'lmaydi — sahifa buni o'zi aytishi kerak."""
    html = EDU_HTML.read_text(encoding="utf-8")

    assert "ota-ona" in html.lower()
    assert "RFID" in html
    assert "ixtiyoriy modul" in html


# ── Saytga ulanishi ──────────────────────────────────────────────────


def test_the_main_site_points_schools_to_the_edu_page() -> None:
    """Maktab direktori narx bo'limida do'kon tariflarini ko'rib,
    "bu menga emas ekan" deb ketib qolmasin."""
    html = (STATIC / "site.html").read_text(encoding="utf-8")

    assert 'href="/edu"' in html


def test_the_main_site_design_still_has_three_shop_plans() -> None:
    """Edu qo'shildi, lekin do'kon narx bo'limi TEGILMAGAN: u
    kartalarni serverdan oladi va uchtaligicha qoladi."""
    html = (STATIC / "site.html").read_text(encoding="utf-8")

    assert 'id="planGrid"' in html
    assert html.count("<form") == 2, "asosiy sahifada uchinchi forma paydo bo'lgan"


def test_search_engines_are_told_about_the_page(client: TestClient) -> None:
    response = client.get("/sitemap.xml", headers={"Host": "chaqimchi.test"})

    assert "/edu" in response.text
