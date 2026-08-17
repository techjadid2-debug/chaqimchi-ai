"""Cloudda kiritilgan sozlamani qurilmaga olib tushish.

O'rnatuvchi do'konga borib sovuq kompyuter oldida turib kamera
manzillarini kiritishi shart emas — u buni oldindan cloud panelida
qiladi.

Bu yerdagi eng muhim tekshiruv **buzmaslik** haqida: mijoz sehrgarda
kamera qo'shgan bo'lishi mumkin, cloudda esa hali hech narsa yo'q.
Bo'sh cloud javobini "haqiqat" deb qabul qilsak, uning ishlab turgan
sozlamasini yo'q qilgan bo'lardik — va u buni faqat hisobot bo'sh
chiqqanda sezardi.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

CLOUD_SYNC = {
    "enabled": True,
    "url": "https://cloud.example.uz",
    "site_id": "site-1",
    "device_id": "dev-1",
    "device_token": "tok-1",
}


@pytest.fixture
def local(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CHAQIMCHI_LOCAL_DIR", str(tmp_path))
    from chaqimchi_ai.local import cloud_config, config_store, paths

    for module in (paths, config_store, cloud_config):
        importlib.reload(module)
    config_store.update("cloud_sync", CLOUD_SYNC)
    cloud_config._last_revision["value"] = None
    return cloud_config


def _config(tmp_path: Path) -> Dict[str, Any]:
    return yaml.safe_load((tmp_path / "config.yaml").read_text(encoding="utf-8"))


def _reply(local, payload: Dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(local, "fetch", lambda cloud: payload)


CAMERA = {"camera_id": "camera-01", "source": "rtsp://u:p@10.0.0.5/sub", "label": "Kirish"}
LINE = {
    "name": "Kirish",
    "camera_id": "camera-01",
    "start": [0.1, 0.6],
    "end": [0.9, 0.6],
    "swap_direction": False,
}


# ── Cloud sozlamasi tushadi ──────────────────────────────────────────────


def test_cloud_cameras_reach_the_pipeline(local, tmp_path: Path, monkeypatch) -> None:
    """Zanjir kameralarni keshdan o'qiydi — kesh yozilishi va rejim
    `auto` ga o'tishi shart, aks holda cloudda qo'shilgan kamera
    umuman tahlil qilinmasdi."""
    _reply(local, {"revision": 3, "cameras": [CAMERA], "config": {}}, monkeypatch)

    applied = local.sync_once()

    assert applied is not None and applied["cameras"] == 1
    retail = _config(tmp_path)["retail"]
    assert retail["cameras_source"] == "auto"
    assert retail["sotqin_config_path"] == str(local.cache_path())
    assert retail["restart_on_config_change"] is True

    cached = json.loads(local.cache_path().read_text(encoding="utf-8"))
    assert cached["cameras"][0]["camera_id"] == "camera-01"


def test_cache_is_readable_by_the_pipeline(local, monkeypatch) -> None:
    """Kesh formati zanjir kutgani bilan bir xil bo'lishi kerak —
    aks holda xizmat "config keshi buzuq" deb ishga tushmasdi."""
    from chaqimchi_ai.retail.inventory import read_sotqin_cache

    _reply(local, {"revision": 1, "cameras": [CAMERA], "config": {}}, monkeypatch)
    local.sync_once()

    parsed = read_sotqin_cache(local.cache_path())
    assert parsed["revision"] == 1
    assert parsed["cameras"][0].source == CAMERA["source"]


def test_cloud_lines_reach_the_local_config(local, tmp_path: Path, monkeypatch) -> None:
    _reply(
        local, {"revision": 2, "cameras": [], "config": {"lines": [LINE], "zones": []}}, monkeypatch
    )

    applied = local.sync_once()

    assert applied["lines"] == 1
    assert _config(tmp_path)["scene"]["lines"][0]["camera_id"] == "camera-01"


def test_cloud_limits_and_hours_are_applied(local, tmp_path: Path, monkeypatch) -> None:
    _reply(
        local,
        {
            "revision": 4,
            "cameras": [],
            "config": {
                "occupancy_limit": 55,
                "queue_limit": 7,
                "loitering_sec": 120,
                "open_from": "09:00",
                "open_to": "21:00",
            },
        },
        monkeypatch,
    )
    local.sync_once()

    saved = _config(tmp_path)
    assert saved["scene"]["occupancy_limit"] == 55
    assert saved["scene"]["queue_limit"] == 7
    assert saved["retail"]["open_from"] == "09:00"


# ── Buzmaslik: eng muhim qism ────────────────────────────────────────────


def test_empty_cloud_never_erases_local_cameras(local, tmp_path: Path, monkeypatch) -> None:
    """Mijoz sehrgarda kamera qo'shgan, cloudda esa hali hech narsa yo'q.
    Bo'sh javob uning sozlamasini yo'q qilmasligi kerak."""
    from chaqimchi_ai.local import config_store

    config_store.save_camera(camera_id="camera-01", stream_url="rtsp://lokal/1", label="Mahalliy")
    _reply(local, {"revision": 9, "cameras": [], "config": {}}, monkeypatch)

    local.sync_once()

    cameras = _config(tmp_path)["retail"]["cameras"]
    assert len(cameras) == 1 and cameras[0]["stream_url"] == "rtsp://lokal/1"
    # Rejim ham o'zgarmasligi kerak: `auto` ga o'tsa bo'sh keshdan
    # o'qib, kamerasiz qolardi.
    assert _config(tmp_path)["retail"].get("cameras_source") == "config"


def test_empty_cloud_never_erases_local_lines(local, tmp_path: Path, monkeypatch) -> None:
    from chaqimchi_ai.local import config_store

    config_store.save_geometry([LINE], [])
    _reply(local, {"revision": 9, "cameras": [], "config": {"lines": [], "zones": []}}, monkeypatch)

    local.sync_once()

    assert len(_config(tmp_path)["scene"]["lines"]) == 1


def test_half_filled_hours_are_ignored(local, tmp_path: Path, monkeypatch) -> None:
    """Faqat ochilish berilsa `AppSettings` validatsiyasi yiqiladi va
    config umuman o'qilmay qolardi."""
    _reply(
        local,
        {"revision": 5, "cameras": [], "config": {"open_from": "09:00", "open_to": None}},
        monkeypatch,
    )
    local.sync_once()

    from chaqimchi_ai.local import config_store

    config_store.load_settings()  # yiqilmasligi kerak
    assert _config(tmp_path)["retail"].get("open_from") is None


def test_camera_without_a_source_is_ignored(local, tmp_path: Path, monkeypatch) -> None:
    """Cloudda kamera yaratilgan, lekin RTSP hali kiritilmagan bo'lishi
    mumkin — bunday yozuv zanjirni kamerasiz qoldirardi."""
    _reply(
        local,
        {"revision": 6, "cameras": [{"camera_id": "camera-01", "source": ""}], "config": {}},
        monkeypatch,
    )
    assert local.sync_once() is None
    assert not local.cache_path().exists()


# ── Sikl va aloqa ────────────────────────────────────────────────────────


def test_unchanged_revision_does_no_work(local, monkeypatch) -> None:
    """Har daqiqada keshni qayta yozish zanjirni qayta ishga tushirar va
    do'kon nazorati uzluksiz uzilib turardi."""
    _reply(local, {"revision": 7, "cameras": [CAMERA], "config": {}}, monkeypatch)
    assert local.sync_once() is not None
    assert local.sync_once() is None, "bir xil revizya ikkinchi marta qo'llanmasin"


def test_unpaired_device_does_not_call_the_cloud(local, monkeypatch) -> None:
    from chaqimchi_ai.local import config_store

    config_store.update("cloud_sync", {"enabled": False})

    def _fail(cloud):
        raise AssertionError("ulanmagan qurilma cloudga so'rov yubormasligi kerak")

    monkeypatch.setattr(local, "fetch", _fail)
    assert local.sync_once() is None


def test_network_failure_is_not_fatal(local, monkeypatch) -> None:
    """Do'konda internet uzilishi odatiy hol — dastur ishlashda davom
    etishi va eski sozlamada qolishi kerak."""
    monkeypatch.setattr(local, "fetch", lambda cloud: None)
    assert local.sync_once() is None


# ── Heartbeat ────────────────────────────────────────────────────────────
#
# `retail.service` dagi `CloudEventSync` `health_provider`siz yaratilgan,
# ya'ni heartbeat **umuman yuborilmasdi**.  Natijada admin panelda
# versiya `v?` bo'lib turardi va kamera holati ko'rinmasdi.


def test_heartbeat_reports_the_running_version(local, monkeypatch) -> None:
    """Versiyasiz cloud yangilanish qaysi do'konga yetganini bilolmaydi."""
    from chaqimchi_ai import __version__

    sent = {}

    class _Response:
        def raise_for_status(self) -> None:
            return None

        @staticmethod
        def json() -> Dict[str, Any]:
            return {"ok": True}

    def _post(url, headers=None, json=None, timeout=None):
        sent["url"] = url
        sent["headers"] = headers
        sent["body"] = json
        return _Response()

    monkeypatch.setattr(local.httpx, "post", _post)
    assert local.send_heartbeat({"cameras_active": 2}) is True

    assert sent["url"].endswith("/api/v1/edge/heartbeat")
    assert sent["body"]["app_version"] == __version__
    assert sent["body"]["cameras_active"] == 2
    assert sent["body"]["product_name"] == "Chaqimchi Windows"
    assert sent["headers"]["X-Device-Token"] == "tok-1"


def test_heartbeat_is_skipped_when_not_paired(local, monkeypatch) -> None:
    from chaqimchi_ai.local import config_store

    config_store.update("cloud_sync", {"enabled": False})

    def _fail(*args, **kwargs):
        raise AssertionError("ulanmagan qurilma heartbeat yubormasligi kerak")

    monkeypatch.setattr(local.httpx, "post", _fail)
    assert local.send_heartbeat({}) is False


def test_heartbeat_failure_is_not_fatal(local, monkeypatch) -> None:
    """Internet uzilishi odatiy hol — dastur ishlashda davom etsin."""
    import httpx as real_httpx

    def _boom(*args, **kwargs):
        raise real_httpx.ConnectError("tarmoq yo'q")

    monkeypatch.setattr(local.httpx, "post", _boom)
    assert local.send_heartbeat({"cameras_active": 0}) is False


# ── Jonli ko'rish va preview so'rovlari (0.6.6) ──────────────────────────
#
# Muhim kontekst: heartbeat javobi ilgari umuman o'qilmasdi — shu sabab
# `preview_requested` Windows qurilmada ishlamasdi (botdagi /kamera yangi
# kadr olomasdi).  Endi javobdan `live-request.json` yoziladi.


def _future(seconds: int = 60) -> str:
    from datetime import datetime, timedelta, timezone

    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def test_heartbeat_response_creates_the_live_request_file(local) -> None:
    local.apply_media_requests(
        {
            "live_requested": [{"camera_id": "camera-01", "until": _future()}],
            "preview_requested": ["camera-02"],
        }
    )

    raw = json.loads(local.live_request_path().read_text(encoding="utf-8"))
    assert raw["camera-01"]["preview"] is False
    assert raw["camera-02"]["preview"] is True, "bir martalik preview ham shu mexanizmda"


def test_empty_response_clears_the_request_file(local) -> None:
    local.apply_media_requests({"live_requested": [{"camera_id": "camera-01", "until": _future()}]})
    assert local.live_request_path().is_file()

    local.apply_media_requests({"live_requested": [], "preview_requested": []})

    assert not local.live_request_path().is_file()


def test_frames_are_uploaded_and_preview_is_one_shot(local, monkeypatch) -> None:
    """O'zgargan kadr yuboriladi; preview bitta kadrdan keyin tugaydi."""
    local.apply_media_requests(
        {
            "live_requested": [{"camera_id": "camera-01", "until": _future()}],
            "preview_requested": ["camera-02"],
        }
    )
    frames = local.live_frames_dir()
    frames.mkdir(parents=True, exist_ok=True)
    (frames / "camera-01.jpg").write_bytes(b"live-kadr")
    (frames / "camera-02.jpg").write_bytes(b"preview-kadr")

    uploads = []

    class _Answer:
        content = b"{}"

        def raise_for_status(self):
            return None

        @staticmethod
        def json():
            return {"ok": True, "continue": True}

    def fake_put(url, headers=None, content=None, timeout=None):
        uploads.append((url, content))
        return _Answer()

    monkeypatch.setattr(local.httpx, "put", fake_put)
    local._uploaded_mtimes.clear()

    sent = local.upload_media_frames()

    assert sent == 2
    endpoints = {url.rsplit("/", 1)[-1] for url, _ in uploads}
    assert endpoints == {"live-frame", "preview"}, "preview eski endpointga borsin"
    # Preview bir martalik — ro'yxatdan chiqdi; jonli esa qoladi.
    remaining = json.loads(local.live_request_path().read_text(encoding="utf-8"))
    assert "camera-02" not in remaining and "camera-01" in remaining

    # Kadr o'zgarmagan — qayta yuborilmaydi.
    assert local.upload_media_frames() == 0


def test_continue_false_stops_the_live_stream(local, monkeypatch) -> None:
    local.apply_media_requests({"live_requested": [{"camera_id": "camera-01", "until": _future()}]})
    frames = local.live_frames_dir()
    frames.mkdir(parents=True, exist_ok=True)
    (frames / "camera-01.jpg").write_bytes(b"kadr")

    class _Stop:
        content = b"{}"

        def raise_for_status(self):
            return None

        @staticmethod
        def json():
            return {"ok": True, "continue": False}

    monkeypatch.setattr(local.httpx, "put", lambda *a, **k: _Stop())
    local._uploaded_mtimes.clear()

    local.upload_media_frames()

    assert not local.live_request_path().is_file(), "server to'xta dedi — so'rov o'chdi"


def test_heatmap_files_are_uploaded_then_deleted(local, monkeypatch) -> None:
    """Fayl faqat 200 dan keyin o'chadi — internet uzilganda kutib turadi."""
    directory = local.heatmap_dir()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "camera-01-2026-08-18T09.json").write_text(
        json.dumps({"camera_id": "camera-01", "hour": "2026-08-18T09", "grid": [[1]], "frames": 2}),
        encoding="utf-8",
    )
    sent = {}

    class _Ok:
        def raise_for_status(self):
            return None

    def fake_post(url, headers=None, json=None, timeout=None):
        sent["url"] = url
        sent["body"] = json
        return _Ok()

    monkeypatch.setattr(local.httpx, "post", fake_post)

    assert local.upload_heatmaps() == 1
    assert sent["url"].endswith("/api/v1/edge/heatmap")
    assert sent["body"]["items"][0]["camera_id"] == "camera-01"
    assert not list(directory.glob("*.json")), "muvaffaqiyatdan keyin fayl o'chadi"


def test_heatmap_files_survive_a_network_failure(local, monkeypatch) -> None:
    directory = local.heatmap_dir()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "camera-01-x.json").write_text(
        json.dumps({"camera_id": "camera-01", "hour": "2026-08-18T09", "grid": [[1]], "frames": 2}),
        encoding="utf-8",
    )

    def fail(*_args, **_kwargs):
        raise local.httpx.ConnectError("aloqa yo'q")

    monkeypatch.setattr(local.httpx, "post", fail)

    assert local.upload_heatmaps() == 0
    assert list(directory.glob("*.json")), "fayl saqlanib qoladi"
