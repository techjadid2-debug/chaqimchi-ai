"""Til katalogi — to'liqlik va izchillik qulflari.

Bu testlar tarjimaning SIFATINI tekshirmaydi (buni odam qiladi), lekin
uch fayl bir-biridan ajralib ketishining oldini oladi: yetishmagan
kalit, mos kelmagan o'rinbosar va eskirgan TypeScript nusxasi —
uchalasi ham mijoz ekranida ko'rinadigan xato bo'lardi.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from chaqimchi_ai.event_models import EventType
from cloud import i18n
from tests.i18n_assert import assert_code, assert_text

ROOT = Path(__file__).resolve().parents[1]
CATALOGUE = {lang: json.loads((ROOT / "i18n" / f"{lang}.json").read_text(encoding="utf-8")) for lang in i18n.LANGS}

#: `{name}` ko'rinishidagi o'rinbosarlar.
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _placeholders(value) -> set:
    if isinstance(value, str):
        return set(PLACEHOLDER.findall(value))
    if isinstance(value, list):
        found = set()
        for item in value:
            found |= _placeholders(item)
        return found
    return set()


def test_every_language_has_the_same_keys() -> None:
    """Kalit uchala tilda ham bo'lsin.

    Yetishmagan kalit jimgina o'zbekchaga tushardi va ruscha panelda
    bitta o'zbekcha jumla paydo bo'lardi — mijoz buni "tarjima
    qilinmagan" emas, "buzuq" deb o'qiydi.
    """
    base = set(CATALOGUE[i18n.DEFAULT_LANG])
    for lang in i18n.LANGS:
        missing = base - set(CATALOGUE[lang])
        extra = set(CATALOGUE[lang]) - base
        assert not missing, f"{lang}: yetishmagan kalitlar — {sorted(missing)}"
        assert not extra, f"{lang}: ortiqcha kalitlar — {sorted(extra)}"


def test_placeholders_match_across_languages() -> None:
    """`{count}` har tilda bir xil bo'lsin.

    Tarjimon o'rinbosarni tushirib qoldirsa son umuman ko'rinmasdi;
    nomini o'zgartirsa `str.format` xato berardi.  Ikkalasi ham jonli
    xabar ichida bilinardi, shuning uchun qulf shu yerda.
    """
    for key, value in CATALOGUE[i18n.DEFAULT_LANG].items():
        expected = _placeholders(value)
        for lang in i18n.LANGS:
            actual = _placeholders(CATALOGUE[lang][key])
            assert actual == expected, f"{lang}/{key}: {actual} ≠ {expected}"


def test_value_shapes_match_across_languages() -> None:
    """Ro'yxat hamma tilda ro'yxat va bir xil uzunlikda bo'lsin.

    Oy nomlari 12 ta, hafta kunlari 7 ta.  Bittasi tushib qolsa
    `formatDate` sanani `undefined` bilan chizardi.
    """
    for key, value in CATALOGUE[i18n.DEFAULT_LANG].items():
        for lang in i18n.LANGS:
            other = CATALOGUE[lang][key]
            assert type(other) is type(value), f"{lang}/{key}: tur mos emas"
            if isinstance(value, list):
                assert len(other) == len(value), f"{lang}/{key}: uzunlik {len(other)} ≠ {len(value)}"


def test_every_event_type_has_a_label() -> None:
    """Har bir hodisa turi uchun nom bo'lsin — uchala tilda ham.

    Hodisa turlari yopiq ro'yxat (`chaqimchi_ai/event_models.py`).
    Yangi tur qo'shilib nomi unutilsa, mijoz panelda `zone_entered`
    kabi xom kod ko'rardi.  Shu test uni qo'shilgan kuniyoq ushlaydi.
    """
    for event_type in EventType.__args__:  # type: ignore[attr-defined]
        key = f"event.{event_type}"
        for lang in i18n.LANGS:
            assert key in CATALOGUE[lang], f"{lang}: {key} yo'q"
            assert CATALOGUE[lang][key], f"{lang}: {key} bo'sh"


def test_generated_typescript_is_up_to_date() -> None:
    """Panel nusxasi katalogdan orqada qolmasin.

    Nusxa commit qilinadi (Docker'ning birinchi bosqichida Python
    yo'q), ya'ni uni yangilashni unutish oson.  Buyruq xatoda to'g'ri
    yo'lni ham aytadi.
    """
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_i18n.py"), "--check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout


# ── Til zanjiri ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        ({"query": "ru"}, "ru"),
        ({"header": "en"}, "en"),
        ({"stored": "ru"}, "ru"),
        ({"telegram": "en-US"}, "en"),
        ({"accept": "ru-RU,ru;q=0.9,en;q=0.8"}, "ru"),
        # Aniq so'rov saqlangan tanlovni yengadi: ulashilgan havola
        # ("mana, ruscha ko'rinishi") ishlashi kerak.
        ({"query": "en", "stored": "ru"}, "en"),
        # Notanish til — zaxira zanjiri davom etadi.
        ({"query": "de", "stored": "ru"}, "ru"),
        ({"accept": "de-DE,fr;q=0.9"}, "uz"),
        ({}, "uz"),
    ],
)
def test_language_resolution_order(kwargs: dict, expected: str) -> None:
    assert i18n.resolve_lang(**kwargs) == expected


def test_missing_key_returns_the_key_itself() -> None:
    """Yo'q kalit — bo'sh joy emas, kalitning o'zi.

    Bo'sh satr qaytsa panelda jimgina bo'shliq qolardi va uni QA'da
    payqash qiyin; kalit esa darrov ko'zga tashlanadi.
    """
    assert i18n.tg("uz", "bunday.kalit.yoq") == "bunday.kalit.yoq"


def test_broken_placeholder_falls_back_instead_of_crashing() -> None:
    """Tarjimondagi xato butun javobni 500 qilmasin."""
    assert i18n.tg("uz", "money.mln", value="3.2") == "3.2 mln so'm"
    # Kutilmagan o'rinbosar berilsa ham matn qaytadi, istisno emas.
    assert i18n.tg("uz", "money.mln", value="3.2", extra="?") == "3.2 mln so'm"


# ── Marshrutlar tilni ko'radimi ─────────────────────────────────────────


@pytest.fixture
def cloud_client(tmp_path, monkeypatch):
    """`tests/test_cloud_api.py` dagi bilan bir xil izolyatsiya:
    har test o'z bazasi bilan ishlaydi."""
    monkeypatch.setenv("CHAQIMCHI_CLOUD_ADMIN_KEY", "test-admin")
    monkeypatch.setattr("cloud.main.DB_PATH", tmp_path / "c.db")
    monkeypatch.setattr("cloud.main._store", None)
    from cloud.main import app

    return TestClient(app)



def test_api_error_translates_and_carries_a_code(cloud_client: TestClient) -> None:
    """Xato matni so'rov tilida, yoniga esa mashina o'qiydigan kod.

    `detail` ATAYLAB satrligicha qoladi: panel (`api.ts`) uni
    to'g'ridan-to'g'ri ko'rsatadi va lug'at bo'lsa `[object Object]`
    chiqardi.
    """
    headers = {"X-Cloud-Admin-Key": "test-admin"}
    missing = "00000000-0000-0000-0000-000000000000"

    uz = cloud_client.post(f"/api/v1/admin/sites/{missing}/login", headers=headers)
    assert uz.status_code == 404
    assert_text(uz.json()["detail"], "error.site_not_found")
    assert_code(uz, "error.site_not_found")

    ru = cloud_client.post(
        f"/api/v1/admin/sites/{missing}/login", headers={**headers, "X-Lang": "ru"}
    )
    assert_text(ru.json()["detail"], "error.site_not_found", "ru")
    assert_code(ru, "error.site_not_found")

    en = cloud_client.post(f"/api/v1/admin/sites/{missing}/login?lang=en", headers=headers)
    assert_text(en.json()["detail"], "error.site_not_found", "en")


def test_language_does_not_leak_between_requests(cloud_client: TestClient) -> None:
    """Bitta so'rovdagi til keyingisiga o'tib ketmasin.

    `ContextVar` `finally` da qaytarilmasa, ruscha so'rovdan keyingi
    o'zbekcha so'rov ham ruscha javob olardi.
    """
    headers = {"X-Cloud-Admin-Key": "test-admin"}
    missing = "00000000-0000-0000-0000-000000000000"

    cloud_client.post(f"/api/v1/admin/sites/{missing}/login", headers={**headers, "X-Lang": "ru"})
    after = cloud_client.post(f"/api/v1/admin/sites/{missing}/login", headers=headers)
    assert_text(after.json()["detail"], "error.site_not_found")
