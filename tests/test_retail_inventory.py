"""Kamera ro'yxati: cloud inventari va lokal sozlama birlashishi.

Bu bo'shliq jimgina zarar keltiradigan turdan edi: o'rnatuvchi kamerani
cloud panelida qo'shadi, analitika esa lokal YAML dan o'qiydi.  Mos
kelmasa hech qanday xato chiqmaydi — kamera oddiygina tahlil qilinmaydi.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from chaqimchi_ai.retail.inventory import (
    InventoryCamera,
    describe,
    merge_cameras,
    read_sotqin_cache,
)
from chaqimchi_ai.retail.service import build_runner, plan_cameras
from chaqimchi_ai.settings import AppSettings


def cache_file(tmp_path: Path, cameras: List[Dict[str, Any]], revision: int = 4) -> Path:
    path = tmp_path / "sotqin-config.json"
    path.write_text(
        json.dumps({"revision": revision, "cameras": cameras}, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def settings_for(tmp_path: Path, **retail: Any) -> AppSettings:
    payload: Dict[str, Any] = {
        "scene": {"enabled": True, "model_path": "models/person.onnx"},
        "retail": {"enabled": True, **retail},
    }
    return AppSettings.model_validate(payload)


# ── Keshni o'qish ────────────────────────────────────────────────────────


def test_cameras_are_read_from_the_cloud_cache(tmp_path: Path) -> None:
    path = cache_file(
        tmp_path,
        [{"camera_id": "kassa-01", "source": "rtsp://nvr/sub1", "label": "Kassa"}],
    )

    cache = read_sotqin_cache(path)

    assert cache["revision"] == 4
    assert cache["cameras"][0].camera_id == "kassa-01"
    assert cache["cameras"][0].source == "rtsp://nvr/sub1"


def test_a_missing_cache_is_normal(tmp_path: Path) -> None:
    """Qurilma hali juftlanmagan yoki analitika cloud'siz ishlatilyapti."""
    cache = read_sotqin_cache(tmp_path / "yo-q.json")

    assert cache == {
        "revision": None,
        "config": {},
        "attendance": {},
        "cloud_features": [],
        "cameras": [],
    }


def test_a_broken_cache_is_an_error(tmp_path: Path) -> None:
    """Jimgina bo'sh ro'yxat bilan davom etish "kamera yo'qolgan" holatining
    aynan o'zi bo'lardi."""
    path = tmp_path / "sotqin-config.json"
    path.write_text("{buzuq", encoding="utf-8")

    with pytest.raises(ValueError):
        read_sotqin_cache(path)


# ── Birlashtirish ────────────────────────────────────────────────────────


class LocalCamera:
    """`RetailCameraSettings` o'rnida — faqat kerakli maydonlar."""

    def __init__(self, id: str, **kwargs: Any) -> None:  # noqa: A002 — konfig nomi
        self.id = id
        self.stream_url = kwargs.get("stream_url", "")
        self.record_url = kwargs.get("record_url")
        self.priority = kwargs.get("priority", "retail")
        self.sample_fps = kwargs.get("sample_fps", 5.0)
        self.floor_fps = kwargs.get("floor_fps")


def test_local_settings_are_applied_to_the_cloud_camera() -> None:
    """RTSP manzili cloud'dan, prioritet va klip manbasi obyekt sozlamasidan."""
    inventory = [InventoryCamera("kassa-01", "rtsp://nvr/sub1", label="Kassa")]
    local = [
        LocalCamera("kassa-01", record_url="rtsp://nvr/main1", priority="security", sample_fps=8.0)
    ]

    plans = merge_cameras(inventory, local)

    assert len(plans) == 1
    assert plans[0].stream_url == "rtsp://nvr/sub1"  # cloud
    assert plans[0].record_url == "rtsp://nvr/main1"  # lokal
    assert plans[0].priority == "security"
    assert plans[0].sample_fps == 8.0
    assert plans[0].origin == "cloud"


def test_a_cloud_camera_without_local_settings_gets_defaults() -> None:
    plans = merge_cameras([InventoryCamera("zal-01", "rtsp://nvr/sub2")], [])

    assert plans[0].priority == "retail"
    assert plans[0].record_url == "rtsp://nvr/sub2"  # xavfsizlik klipi yo'qolmaydi
    assert plans[0].sample_fps == 5.0


def test_a_disabled_camera_is_skipped() -> None:
    """O'chirilgan kamerani tahlil qilish byudjetni bekorga yeydi."""
    inventory = [
        InventoryCamera("bor", "rtsp://nvr/1"),
        InventoryCamera("o-chiq", "rtsp://nvr/2", enabled=False),
    ]

    assert [plan.camera_id for plan in merge_cameras(inventory, [])] == ["bor"]


def test_a_local_only_camera_is_not_dropped() -> None:
    """Aynan shu jimgina yo'qolish tuzatilmoqda — teskari tomonga ham."""
    plans = merge_cameras(
        [InventoryCamera("kassa-01", "rtsp://nvr/1")],
        [LocalCamera("ombor-01", stream_url="rtsp://lokal/9")],
    )

    assert [(plan.camera_id, plan.origin) for plan in plans] == [
        ("kassa-01", "cloud"),
        ("ombor-01", "config"),
    ]


def test_a_local_entry_without_a_stream_is_only_settings() -> None:
    """Lokal yozuv faqat sozlama bersa, o'zi kamera yaratmaydi."""
    plans = merge_cameras([], [LocalCamera("kassa-01", priority="security")])

    assert plans == []


def test_an_inventory_camera_without_an_address_is_ignored() -> None:
    plans = merge_cameras([InventoryCamera("buzuq", "")], [])

    assert plans == []


def test_the_summary_says_where_cameras_came_from() -> None:
    plans = merge_cameras(
        [InventoryCamera("a", "rtsp://1"), InventoryCamera("b", "rtsp://2")],
        [LocalCamera("c", stream_url="rtsp://3")],
    )

    assert describe(plans) == "3 kamera: 2 tasi cloud inventaridan, 1 tasi lokal konfigdan"


# ── Xizmat bilan ─────────────────────────────────────────────────────────


def test_the_service_prefers_the_cloud_inventory(tmp_path: Path) -> None:
    path = cache_file(tmp_path, [{"camera_id": "kassa-01", "source": "rtsp://cloud/sub"}])
    settings = settings_for(
        tmp_path,
        sotqin_config_path=str(path),
        cameras=[{"id": "kassa-01", "stream_url": "rtsp://eski/sub", "priority": "security"}],
    )

    cameras, revision = plan_cameras(settings, tmp_path)

    assert revision == 4
    assert cameras[0].stream_url == "rtsp://cloud/sub"  # eski lokal manzil emas
    assert cameras[0].priority == "security"  # lokal sozlama saqlandi


def test_config_source_ignores_the_cloud_cache(tmp_path: Path) -> None:
    """Cloud'siz o'rnatish uchun: faqat lokal ro'yxat."""
    path = cache_file(tmp_path, [{"camera_id": "cloud-01", "source": "rtsp://cloud/sub"}])
    settings = settings_for(
        tmp_path,
        cameras_source="config",
        sotqin_config_path=str(path),
        cameras=[{"id": "lokal-01", "stream_url": "rtsp://lokal/sub"}],
    )

    cameras, revision = plan_cameras(settings, tmp_path)

    assert [camera.camera_id for camera in cameras] == ["lokal-01"]
    assert revision is None


def test_the_service_refuses_to_start_with_no_cameras_anywhere(tmp_path: Path) -> None:
    settings = settings_for(tmp_path, sotqin_config_path=str(tmp_path / "yo-q.json"))

    with pytest.raises(RuntimeError, match="Kamera topilmadi"):
        build_runner(settings, tmp_path, detector=object())


def test_cloud_cameras_reach_the_broker(tmp_path: Path) -> None:
    from chaqimchi_ai.outbox import EventOutbox

    path = cache_file(
        tmp_path,
        [
            {"camera_id": "kassa-01", "source": "rtsp://cloud/1"},
            {"camera_id": "zal-01", "source": "rtsp://cloud/2"},
        ],
    )
    settings = settings_for(
        tmp_path,
        sotqin_config_path=str(path),
        cameras=[{"id": "kassa-01", "stream_url": "", "priority": "security"}],
    )

    runner = build_runner(
        settings,
        tmp_path,
        detector=object(),
        outbox=EventOutbox(tmp_path / "outbox.db", max_bytes=10 * 1024**2),
    )

    cameras = runner.stats()["broker"]["cameras"]
    assert sorted(cameras) == ["kassa-01", "zal-01"]
    assert cameras["kassa-01"]["priority"] == "SECURITY"
