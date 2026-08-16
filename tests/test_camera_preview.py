"""Kamera rasmi: o'rnatuvchi kamerani ko'radimi?

Bungacha o'rnatuvchi kamerani ko'rmasdi. `ffprobe` unga "h264 640x360 15fps"
derdi — lekin kamera to'g'ri joyga qaratilganini, linza toza ekanini yoki
umuman qaysi kamera ekanini bu aytmaydi. Natijada obyekt topshirilgandan
keyingina noto'g'ri qaratilgan kamera ma'lum bo'lardi.

Bu rasm ayni paytda chiziq va zona chizish uchun ham asos.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cloud import ratelimit
from cloud.snapshots import LocalSnapshotStore
from cloud.store import CloudStore

JPEG = b"\xff\xd8\xff\xe0" + b"soxta-rasm" * 40


@pytest.fixture
def store(tmp_path: Path) -> CloudStore:
    return CloudStore(tmp_path / "cloud.db")


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    import cloud.main as main

    monkeypatch.setenv("CHAQIMCHI_CLOUD_ADMIN_KEY", "test-admin")
    monkeypatch.setenv("CHAQIMCHI_OWNER_JWT_SECRET", "owner-secret-with-more-than-32-characters")
    monkeypatch.setenv("CHAQIMCHI_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("CHAQIMCHI_S3_ENDPOINT", raising=False)
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "cloud.db")
    monkeypatch.setattr(main, "_store", None)
    monkeypatch.setattr(main, "_event_store", None)
    monkeypatch.setattr(main, "_event_store_key", None)
    monkeypatch.setattr(main, "_snapshots", LocalSnapshotStore(tmp_path / "snapshots"))
    # Chegaralagich jarayon ichida global (`cloud/ratelimit.py`) — tozalanmasa
    # bir faylda ketma-ket ishlaydigan testlar bir-birining kvotasini yeydi.
    ratelimit.limiter().reset()
    with TestClient(main.app) as test_client:
        yield test_client
    ratelimit.limiter().reset()


ADMIN = {"X-Cloud-Admin-Key": "test-admin"}


def _site_with_camera(client: TestClient) -> tuple[dict, dict]:
    """Obyekt + pairing qilingan qurilma + bitta kamera."""
    site = client.post("/api/v1/admin/sites", headers=ADMIN, json={"name": "Do'kon"}).json()
    site_id = site["site_id"]
    client.put(
        f"/api/v1/admin/sites/{site_id}/camera-inventory/camera-01",
        headers=ADMIN,
        json={"label": "Kirish", "rtsp_url": "rtsp://user:secret@nvr/sub", "enabled": True},
    ).raise_for_status()
    device = client.post(
        "/api/v1/devices/claim", json={"pairing_code": site["pairing_code"]}
    ).json()
    return site, {
        "X-Site-Id": device["site_id"],
        "X-Device-Id": device["device_id"],
        "X-Device-Token": device["device_token"],
    }


def _installer(client: TestClient, site_id: str) -> dict:
    """Tasdiqlangan, obyektga biriktirilgan o'rnatuvchi."""
    registered = client.post(
        "/api/v1/auth/installer/register",
        json={
            "full_name": "Ali Valiyev",
            "phone": "+998901112233",
            "username": "usta.ali",
            "password": "ParolUzunVaKuchli1",
            "consent": True,
        },
    ).json()
    account_id = registered["account"]["id"]
    client.put(
        f"/api/v1/admin/accounts/{account_id}",
        headers=ADMIN,
        json={"status": "active"},
    ).raise_for_status()
    client.post(
        "/api/v1/admin/installer-assignments",
        headers=ADMIN,
        json={"installer_id": account_id, "site_id": site_id},
    ).raise_for_status()
    # Status o'zgargani pending tokenni bekor qiladi — qaytadan kiramiz.
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "usta.ali", "password": "ParolUzunVaKuchli1"},
    ).json()
    return {"Authorization": f"Bearer {login['access_token']}"}


# ── Store qatlami ────────────────────────────────────────────────────────


def test_request_is_pending_until_the_image_arrives(store: CloudStore) -> None:
    site = store.create_site("Do'kon", "lite")
    store.upsert_camera(site["site_id"], "camera-01", label="Kirish", rtsp_url="rtsp://nvr/sub")

    assert store.pending_preview_cameras(site["site_id"]) == []

    store.request_camera_preview(site["site_id"], "camera-01")
    assert store.pending_preview_cameras(site["site_id"]) == ["camera-01"]

    store.set_camera_preview(site["site_id"], "camera-01", "s/preview/camera-01.jpg")
    # So'rov bajarildi — qurilma har heartbeat'da qayta yubormasin.
    assert store.pending_preview_cameras(site["site_id"]) == []
    assert store.camera_preview_key(site["site_id"], "camera-01") == "s/preview/camera-01.jpg"


def test_disabled_camera_is_never_asked_for_a_frame(store: CloudStore) -> None:
    site = store.create_site("Do'kon", "lite")
    store.upsert_camera(
        site["site_id"], "camera-01", label="Kirish", rtsp_url="rtsp://nvr/sub", enabled=False
    )
    store.request_camera_preview(site["site_id"], "camera-01")

    assert store.pending_preview_cameras(site["site_id"]) == []


def test_unknown_camera_cannot_be_requested(store: CloudStore) -> None:
    site = store.create_site("Do'kon", "lite")
    with pytest.raises(ValueError, match="Kamera topilmadi"):
        store.request_camera_preview(site["site_id"], "camera-04")


def test_camera_listing_reports_preview_state(store: CloudStore) -> None:
    site = store.create_site("Do'kon", "lite")
    store.upsert_camera(site["site_id"], "camera-01", label="Kirish", rtsp_url="rtsp://nvr/sub")

    camera = store.list_cameras(site["site_id"])[0]
    assert camera["preview_requested"] is False and camera["has_preview"] is False

    store.request_camera_preview(site["site_id"], "camera-01")
    assert store.list_cameras(site["site_id"])[0]["preview_requested"] is True

    store.set_camera_preview(site["site_id"], "camera-01", "k.jpg")
    camera = store.list_cameras(site["site_id"])[0]
    assert camera["preview_requested"] is False and camera["has_preview"] is True
    # RTSP manzili hech qachon ro'yxatda chiqmaydi.
    assert "secret" not in str(camera)


# ── To'liq oqim ──────────────────────────────────────────────────────────


def test_installer_asks_device_delivers_installer_sees_the_frame(client: TestClient) -> None:
    site, device_headers = _site_with_camera(client)
    site_id = site["site_id"]
    installer = _installer(client, site_id)

    # 1. Hali rasm yo'q.
    assert (
        client.get(
            f"/api/v1/installer/sites/{site_id}/cameras/camera-01/preview", headers=installer
        ).status_code
        == 404
    )

    # 2. O'rnatuvchi "rasmni ko'rsat" bosadi.
    asked = client.post(
        f"/api/v1/installer/sites/{site_id}/cameras/camera-01/preview", headers=installer
    )
    assert asked.status_code == 200
    assert asked.json()["wait_sec"] > 0

    # 3. Qurilma heartbeat'da so'rovni ko'radi.
    beat = client.post(
        "/api/v1/sotqin/heartbeat", headers=device_headers, json={"config_revision": 0}
    ).json()
    assert beat["preview_requested"] == ["camera-01"]

    # 4. Qurilma kadrni yuboradi.
    uploaded = client.put(
        "/api/v1/sotqin/cameras/camera-01/preview",
        headers={**device_headers, "Content-Type": "image/jpeg"},
        content=JPEG,
    )
    assert uploaded.status_code == 200

    # 5. So'rov yopildi — qurilma har daqiqada qayta yubormaydi.
    beat = client.post(
        "/api/v1/sotqin/heartbeat", headers=device_headers, json={"config_revision": 0}
    ).json()
    assert beat["preview_requested"] == []

    # 6. O'rnatuvchi rasmni ko'radi.
    shown = client.get(
        f"/api/v1/installer/sites/{site_id}/cameras/camera-01/preview", headers=installer
    )
    assert shown.status_code == 200
    assert shown.content == JPEG
    assert shown.headers["content-type"] == "image/jpeg"
    # Kamera qayta qaratilsa eski rasm keshdan ko'rinib qolmasin.
    assert shown.headers["cache-control"] == "no-store"


def test_preview_does_not_bump_the_config_revision(client: TestClient) -> None:
    """Aks holda har "rasmni ko'rsat" bosilganda retail xizmati qayta ishga
    tushardi (`restart_on_config_change`) va do'kon analitikasi uzilardi."""
    site, device_headers = _site_with_camera(client)
    site_id = site["site_id"]
    installer = _installer(client, site_id)
    before = client.post(
        "/api/v1/sotqin/heartbeat", headers=device_headers, json={"config_revision": 0}
    ).json()["config_revision"]

    client.post(f"/api/v1/installer/sites/{site_id}/cameras/camera-01/preview", headers=installer)
    client.put(
        "/api/v1/sotqin/cameras/camera-01/preview",
        headers={**device_headers, "Content-Type": "image/jpeg"},
        content=JPEG,
    )

    after = client.post(
        "/api/v1/sotqin/heartbeat", headers=device_headers, json={"config_revision": before}
    ).json()
    assert after["config_revision"] == before
    assert after["config_changed"] is False


# ── Himoya ───────────────────────────────────────────────────────────────


def test_upload_rejects_wrong_type_empty_and_oversized(client: TestClient) -> None:
    _site, device_headers = _site_with_camera(client)

    png = client.put(
        "/api/v1/sotqin/cameras/camera-01/preview",
        headers={**device_headers, "Content-Type": "image/png"},
        content=JPEG,
    )
    assert png.status_code == 415

    empty = client.put(
        "/api/v1/sotqin/cameras/camera-01/preview",
        headers={**device_headers, "Content-Type": "image/jpeg"},
        content=b"",
    )
    assert empty.status_code == 400

    huge = client.put(
        "/api/v1/sotqin/cameras/camera-01/preview",
        headers={**device_headers, "Content-Type": "image/jpeg"},
        content=b"\xff\xd8" + b"x" * (2 * 1024 * 1024),
    )
    assert huge.status_code == 413


def test_upload_needs_a_paired_device(client: TestClient) -> None:
    _site_with_camera(client)

    anonymous = client.put(
        "/api/v1/sotqin/cameras/camera-01/preview",
        headers={"Content-Type": "image/jpeg"},
        content=JPEG,
    )
    assert anonymous.status_code in {401, 403, 422}


def test_upload_to_an_unknown_camera_is_rejected(client: TestClient) -> None:
    _site, device_headers = _site_with_camera(client)

    response = client.put(
        "/api/v1/sotqin/cameras/camera-04/preview",
        headers={**device_headers, "Content-Type": "image/jpeg"},
        content=JPEG,
    )
    assert response.status_code == 404


def test_an_installer_cannot_read_another_sites_camera(client: TestClient) -> None:
    first, first_device = _site_with_camera(client)
    installer = _installer(client, first["site_id"])
    other = client.post("/api/v1/admin/sites", headers=ADMIN, json={"name": "Boshqa do'kon"}).json()

    client.put(
        "/api/v1/sotqin/cameras/camera-01/preview",
        headers={**first_device, "Content-Type": "image/jpeg"},
        content=JPEG,
    )

    denied = client.get(
        f"/api/v1/installer/sites/{other['site_id']}/cameras/camera-01/preview", headers=installer
    )
    assert denied.status_code == 403


# ── Chizilgan chiziq qurilmagacha yetadimi ───────────────────────────────


def test_a_line_drawn_by_the_installer_reaches_the_device(
    client: TestClient, tmp_path: Path
) -> None:
    """Butun zanjirning ma'nosi shu.

    O'rnatuvchi kadr ustida chiziq chizadi -> cloud saqlaydi -> qurilma
    config'da oladi -> `apply_remote_site_settings` uni `scene.lines` ga
    qo'yadi -> `SceneAnalyzer` kirganlarni sanay boshlaydi.

    Shu zanjirning oxirgi bo'g'ini uzilgan bo'lsa, chizish vositasi
    chiroyli ishlab turadi-yu, hisob hech qachon o'smaydi.
    """
    import json

    from chaqimchi_ai.retail.service import apply_remote_site_settings
    from chaqimchi_ai.settings import AppSettings

    site, device_headers = _site_with_camera(client)
    site_id = site["site_id"]
    installer = _installer(client, site_id)

    current = client.get(f"/api/v1/installer/sites/{site_id}/config", headers=installer).json()[
        "config"
    ]
    saved = client.put(
        f"/api/v1/installer/sites/{site_id}/config",
        headers=installer,
        json={
            **current,
            "lines": [
                {
                    "name": "kirish",
                    "camera_id": "camera-01",
                    "start": [0.1, 0.6],
                    "end": [0.9, 0.6],
                    "swap_direction": True,
                }
            ],
            "zones": [
                {
                    "name": "kassa",
                    "camera_id": "camera-01",
                    "polygon": [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]],
                    "queue": True,
                    "dwell_sec": 120,
                }
            ],
        },
    )
    assert saved.status_code == 200

    # Qurilma config'ni oladi.
    payload = client.get("/api/v1/sotqin/config", headers=device_headers).json()
    assert payload["config"]["lines"][0]["name"] == "kirish"

    # Qurilma uni keshga yozadi (`sotqin_agent.persist_config` shuni qiladi).
    cache = tmp_path / "sotqin-config.json"
    cache.write_text(json.dumps(payload), encoding="utf-8")

    settings = AppSettings.model_validate(
        {
            "retail": {"enabled": True, "cameras_source": "auto", "sotqin_config_path": str(cache)},
            "scene": {"enabled": True},
        }
    )
    apply_remote_site_settings(settings, tmp_path)

    # Chiziq analizatorga yetdi.
    assert len(settings.scene.lines) == 1
    line = settings.scene.lines[0]
    assert line.name == "kirish" and line.camera_id == "camera-01"
    assert line.start == (0.1, 0.6) and line.swap_direction is True
    zone = settings.scene.zones[0]
    assert zone.queue is True and zone.dwell_sec == 120


def test_empty_cloud_geometry_keeps_the_wizard_drawn_line(tmp_path: Path) -> None:
    """Ulanish sehrgarda chizilgan chiziqni o'chirmasligi KERAK.

    Haqiqiy bag: cloud `get_site_config()` har doim bo'sh `"lines": []`
    qaytaradi, `apply_remote_site_settings` esa `key in remote` sharti
    bilan uni yangi qiymat deb olib, lokal chizilgan chiziqni runtime'da
    o'chirardi.  Kirish-chiqish sanash jimgina to'xtar, config.yaml va
    panel esa "chiziq bor" deb ko'rsatib turardi — jonli qurilmada aynan
    shu kuzatilgan (kuniga 2 ta line_crossed).
    """
    import json

    from chaqimchi_ai.retail.service import apply_remote_site_settings
    from chaqimchi_ai.settings import AppSettings

    cache = tmp_path / "sotqin-config.json"
    cache.write_text(
        json.dumps(
            {
                "revision": 3,
                "cameras": [],
                "config": {"lines": [], "zones": [], "queue_limit": 5},
            }
        ),
        encoding="utf-8",
    )
    settings = AppSettings.model_validate(
        {
            "retail": {"enabled": True, "cameras_source": "auto", "sotqin_config_path": str(cache)},
            "scene": {
                "enabled": True,
                "lines": [
                    {
                        "name": "kirish",
                        "camera_id": "camera-01",
                        "start": [0.1, 0.6],
                        "end": [0.9, 0.6],
                    }
                ],
                "zones": [
                    {
                        "name": "kassa",
                        "camera_id": "camera-01",
                        "polygon": [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]],
                        "queue": True,
                    }
                ],
            },
        }
    )

    apply_remote_site_settings(settings, tmp_path)

    assert len(settings.scene.lines) == 1, "bo'sh cloud lokal chiziqni o'chirmasin"
    assert settings.scene.lines[0].name == "kirish"
    assert len(settings.scene.zones) == 1, "bo'sh cloud lokal zonani o'chirmasin"
    # Skalyar limitlar esa cloud'dan olinaveradi.
    assert settings.scene.queue_limit == 5


def test_a_line_on_an_unknown_camera_is_rejected(client: TestClient) -> None:
    site, _device = _site_with_camera(client)
    site_id = site["site_id"]
    installer = _installer(client, site_id)
    current = client.get(f"/api/v1/installer/sites/{site_id}/config", headers=installer).json()[
        "config"
    ]

    rejected = client.put(
        f"/api/v1/installer/sites/{site_id}/config",
        headers=installer,
        json={
            **current,
            "lines": [
                {
                    "name": "kirish",
                    "camera_id": "camera-99",
                    "start": [0.1, 0.6],
                    "end": [0.9, 0.6],
                }
            ],
        },
    )
    assert rejected.status_code == 422


def test_onboarding_cannot_reach_100_percent_without_a_drawn_line(client: TestClient) -> None:
    """O'rnatuvchi ishni chiziqsiz "yakunlandi" deb belgilay olmasin.

    Chiziqsiz `line_crossed` chiqmaydi — mijoz to'lovni boshlaydi-yu,
    panelda "Bugun kirdi: 0" turaveradi.
    """
    site, device_headers = _site_with_camera(client)
    site_id = site["site_id"]
    installer = _installer(client, site_id)

    def steps() -> dict:
        payload = client.get(
            f"/api/v1/installer/sites/{site_id}/onboarding", headers=installer
        ).json()
        return {step["key"]: step["done"] for step in payload["steps"]}

    assert steps()["geometry"] is False
    assert steps()["preview"] is False

    client.put(
        "/api/v1/sotqin/cameras/camera-01/preview",
        headers={**device_headers, "Content-Type": "image/jpeg"},
        content=JPEG,
    )
    assert steps()["preview"] is True

    current = client.get(f"/api/v1/installer/sites/{site_id}/config", headers=installer).json()[
        "config"
    ]
    client.put(
        f"/api/v1/installer/sites/{site_id}/config",
        headers=installer,
        json={
            **current,
            "lines": [
                {
                    "name": "kirish",
                    "camera_id": "camera-01",
                    "start": [0.1, 0.6],
                    "end": [0.9, 0.6],
                }
            ],
        },
    )
    assert steps()["geometry"] is True
