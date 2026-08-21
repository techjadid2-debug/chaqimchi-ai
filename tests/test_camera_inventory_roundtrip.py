"""Qurilma → cloud → panel: kamera ro'yxati butun yo'lni bosib o'tsin.

Nega alohida test.  Ikkala tomon alohida sinalgan edi-yu, ular
**bir-biriga ulanmagan** edi: haqiqiy do'konda qurilma 4 kamerani tahlil
qilib turardi, cloudda esa `site_cameras` bo'm-bo'sh edi.  Natijada mijoz
panelida kamera ro'yxati bo'sh bo'lib, jonli ko'rish, do'kon xaritasi,
davomat kamerasini tanlash va kamera rollari — to'rtta bo'lim ham
jimgina ishlamasdi.

Shuning uchun bu yerda qurilmaning HAQIQIY yuborish kodi
(`cloud_config.publish_cameras`) haqiqiy cloud ilovasiga ulanadi.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def cloud(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CHAQIMCHI_CLOUD_DB", str(tmp_path / "cloud.db"))
    monkeypatch.setenv("CHAQIMCHI_EVENT_DB", str(tmp_path / "events.db"))
    monkeypatch.setenv("CHAQIMCHI_CLOUD_ADMIN_KEY", "test-admin")
    monkeypatch.setenv("CHAQIMCHI_OWNER_JWT_SECRET", "x" * 32)
    monkeypatch.setenv("CHAQIMCHI_SNAPSHOT_DIR", str(tmp_path / "snapshots"))

    from cloud import main

    importlib.reload(main)
    with TestClient(main.app) as client:
        yield client


def test_wizard_camera_shows_up_in_the_owner_panel(
    cloud: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    site = cloud.post(
        "/api/v1/admin/sites",
        headers={"X-Cloud-Admin-Key": "test-admin"},
        json={"name": "Do'kon", "plan": "biznes"},
    ).json()
    device = cloud.post(
        "/api/v1/devices/claim", json={"pairing_code": site["pairing_code"]}
    ).json()

    # ── Qurilma tomoni: sehrgarda kamera qo'shilgan ────────────────────
    monkeypatch.setenv("CHAQIMCHI_LOCAL_DIR", str(tmp_path / "device"))
    from chaqimchi_ai.local import cloud_config, cloud_link, config_store, paths

    for module in (paths, config_store, cloud_link, cloud_config):
        importlib.reload(module)
    config_store.update(
        "cloud_sync",
        {
            "enabled": True,
            "url": "https://cloud.test",
            "site_id": device["site_id"],
            "device_id": device["device_id"],
            "device_token": device["device_token"],
        },
    )
    config_store.save_camera(
        camera_id="camera-01", stream_url="rtsp://admin:parol@10.0.0.5/1", label="Kirish eshigi"
    )

    def _post(url, headers=None, json=None, timeout=None):
        path = str(url).replace("https://cloud.test", "")
        return cloud.post(path, headers=headers, json=json)

    monkeypatch.setattr(cloud_config.httpx, "post", _post)

    assert cloud_config.publish_cameras() is True

    # ── Cloud tomoni: mijoz panelida ko'rinadimi ───────────────────────
    cameras = cloud.get(
        f"/api/v1/admin/sites/{device['site_id']}/camera-inventory",
        headers={"X-Cloud-Admin-Key": "test-admin"},
    ).json()["cameras"]

    assert [item["camera_id"] for item in cameras] == ["camera-01"]
    assert cameras[0]["label"] == "Kirish eshigi"
    # NVR paroli do'konda qoladi: cloudga manzil umuman yuborilmaydi.
    assert cameras[0]["origin"] == "device"
