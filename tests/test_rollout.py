"""Yangi versiya do'kondagi qurilmaga qanday yetadi.

Zanjir uzun va uning oxirgi ikki bo'g'ini qo'lda edi:

    quriladi → imzolanadi → SERVERGA QO'YILADI → qurilma 15 daqiqada oladi
                            ^^^^^^^^^^^^^^^^^^
                            `scp` — unutilsa "reliz chiqdi, lekin hech
                            kimga yetmadi" degan jim holat

va tarqatish tartibi (`docs/RELIZ_VA_OTA.md`) — "hammasini `hold` ga,
24 soat kut, keyin qaytar" — yigirma do'konda yigirma marta bosish edi.

Bu testlar shu ikki bo'g'inni qo'riqlaydi.  Cloud API'ning o'zi bilan
ishlaydi: `rollout.py` `httpx.Client` qabul qiladi, `TestClient` esa
aynan shuning vorisi.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
PUBLISH = ROOT / "scripts" / "publish_windows_release.sh"


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
    monkeypatch.setattr(main, "BASE_DIR", tmp_path)
    (tmp_path / "releases").mkdir()
    with TestClient(main.app, headers={"X-Cloud-Admin-Key": "test-admin"}) as test_client:
        yield test_client


def _create(client: TestClient, name: str) -> dict:
    response = client.post("/api/v1/admin/sites", json={"name": name, "plan": "lite"})
    assert response.status_code < 400, response.text
    return response.json()


def _site(client: TestClient, name: str) -> str:
    # Yaratish javobida kalit `site_id`, ro'yxatda esa `id` — ikkalasi
    # bir xil qiymat.
    return str(_create(client, name)["site_id"])


def _device(client: TestClient, created: dict) -> dict:
    """Haqiqiy qurilma: pairing kodni tokenga almashtiradi."""
    response = client.post(
        "/api/v1/devices/claim",
        json={
            "pairing_code": created["pairing_code"],
            "label": "Sinov kompyuteri",
            "hardware_id": "sinov-" + created["site_id"],
            "product_name": "Chaqimchi Windows",
        },
    )
    assert response.status_code < 400, response.text
    device = response.json()
    return {
        "X-Site-Id": str(device["site_id"]),
        "X-Device-Id": str(device["device_id"]),
        "X-Device-Token": str(device["device_token"]),
    }


def _publish_fake_release(tmp_path: Path, version: str = "9.9.9") -> None:
    """Cloud manifestsiz `.exe` ni e'tiborsiz qoldiradi — juftini yozamiz."""
    releases = tmp_path / "releases"
    (releases / f"chaqimchi-windows-{version}.exe").write_bytes(b"soxta")
    (releases / f"chaqimchi-windows-{version}.json").write_text(
        '{"version": "' + version + '"}', encoding="utf-8"
    )


# ── Bosqichli tarqatish ─────────────────────────────────────────────────


def test_canary_holds_every_other_shop(client: TestClient) -> None:
    """Yangi versiya avval BITTA do'konda sinaladi.

    Qurilmalar har 15 daqiqada so'raydi — buzuq reliz chorak soatda
    hammaga yetadi.  Shuning uchun sinov do'koni `auto`, qolganlari
    `hold` bo'lishi kerak.
    """
    import scripts.rollout as rollout

    sinov = _site(client, "Sinov do'koni")
    boshqa = [_site(client, f"Mijoz {i}") for i in range(3)]

    assert rollout.canary(client, sinov) == 0

    sites = {str(s["id"]): s for s in client.get("/api/v1/admin/sites").json()}
    assert sites[sinov]["update_channel"] == "auto"
    for site_id in boshqa:
        assert sites[site_id]["update_channel"] == "hold", "mijoz do'koni kutishi kerak"


def test_the_held_device_is_told_to_wait(client: TestClient, tmp_path: Path) -> None:
    """Eng muhim tekshiruv: `hold` haqiqatan QURILMAGA yetadimi.

    Siyosat bazada to'g'ri yozilib, `/api/v1/edge/update` uni e'tiborga
    olmasa — himoya qog'ozda qolardi va buzuq reliz baribir tarqalardi.
    Shuning uchun bu yerda haqiqiy qurilma tokeni bilan so'raymiz.
    """
    import scripts.rollout as rollout

    _publish_fake_release(tmp_path)
    sinov = _create(client, "Sinov")
    mijoz = _create(client, "Mijoz")
    sinov_device = _device(client, sinov)
    mijoz_device = _device(client, mijoz)

    rollout.canary(client, sinov["site_id"])

    kutayotgan = client.get("/api/v1/edge/update", headers=mijoz_device).json()
    assert kutayotgan["available"] is False
    assert "to'xtatilgan" in kutayotgan["reason"]

    sinovda = client.get("/api/v1/edge/update", headers=sinov_device).json()
    assert sinovda["available"] is True, "sinov do'koni yangilanishi kerak"
    assert sinovda["version"] == "9.9.9"


def test_the_emergency_stop_reaches_the_device(client: TestClient, tmp_path: Path) -> None:
    """Global to'xtatuvchi ham qurilmaga yetsin — `hold` dan farqi shuki,
    u bitta bosishda HAMMA do'konni to'xtatadi."""
    import scripts.rollout as rollout

    _publish_fake_release(tmp_path)
    site = _create(client, "Mijoz")
    device = _device(client, site)

    assert client.get("/api/v1/edge/update", headers=device).json()["available"] is True

    rollout.pause(client, paused=True)
    javob = client.get("/api/v1/edge/update", headers=device).json()
    assert javob["available"] is False


def test_everyone_returns_the_shops_to_auto(client: TestClient) -> None:
    import scripts.rollout as rollout

    sinov = _site(client, "Sinov")
    mijoz = _site(client, "Mijoz")
    rollout.canary(client, sinov)

    assert rollout.everyone(client) == 0

    sites = {str(s["id"]): s for s in client.get("/api/v1/admin/sites").json()}
    assert sites[mijoz]["update_channel"] == "auto"


def test_an_unknown_shop_is_refused(client: TestClient) -> None:
    """Xato yozilgan site_id butun parkni `hold` ga o'tkazib qo'ymasin."""
    import scripts.rollout as rollout

    mijoz = _site(client, "Mijoz")

    with pytest.raises(rollout.RolloutError):
        rollout.canary(client, "yo-q-obyekt")

    sites = {str(s["id"]): s for s in client.get("/api/v1/admin/sites").json()}
    assert sites[mijoz]["update_channel"] == "auto", "hech narsa o'zgarmasligi kerak"


def test_the_emergency_stop_works_both_ways(client: TestClient) -> None:
    """Buzuq reliz chiqib ketsa har do'konni alohida to'xtatishga ulgurib
    bo'lmaydi — bitta bayroq hammasini to'xtatadi."""
    import scripts.rollout as rollout

    _site(client, "Mijoz")

    rollout.pause(client, paused=True)
    assert client.get("/api/v1/admin/updates-paused").json()["paused"] is True

    rollout.pause(client, paused=False)
    assert client.get("/api/v1/admin/updates-paused").json()["paused"] is False


def test_status_survives_a_shop_without_devices(client: TestClient) -> None:
    """Yangi ochilgan, hali qurilmasiz obyekt ro'yxatni yiqitmasin."""
    import scripts.rollout as rollout

    _site(client, "Qurilmasiz")
    assert rollout.show_status(client) == 0


# ── Serverga chiqarish skripti ──────────────────────────────────────────


def test_publish_uses_the_name_the_cloud_looks_for() -> None:
    """Cloud aynan `chaqimchi-windows-<versiya>.{exe,json}` juftini
    qidiradi (`latest_windows_release`).  Boshqa nom bilan qo'yilgan fayl
    e'tiborsiz qoladi va buni hech kim sezmaydi."""
    source = PUBLISH.read_text(encoding="utf-8")
    assert 'releases/chaqimchi-windows-$version.exe' in source
    assert 'releases/chaqimchi-windows-$version.json' in source


def test_publish_refuses_to_ship_an_unsigned_release() -> None:
    """Imzosiz paketni qurilma baribir rad etadi — uni chiqarish foydasiz."""
    source = PUBLISH.read_text(encoding="utf-8")
    assert "sign_release.py" in source
    assert "verify_release_manifest" in source, "chiqarishdan oldin imzo tekshirilsin"


def test_publish_verifies_from_the_outside() -> None:
    """"Yubordim" degani "qurilma ola oladi" degani emas: papka noto'g'ri
    bo'lishi yoki fayl yarim ko'chgan bo'lishi mumkin."""
    source = PUBLISH.read_text(encoding="utf-8")
    assert "curl" in source and "/releases/" in source
    assert "size_bytes" in source, "hajm mos kelishi tekshirilsin"


def test_publish_is_executable() -> None:
    assert PUBLISH.stat().st_mode & 0o111, "bajariladigan bo'lsin"
    assert re.match(r"^#!/usr/bin/env bash", PUBLISH.read_text(encoding="utf-8"))
