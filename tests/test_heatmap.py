"""Issiqlik xaritasi: to'r yig'ish (edge) va soatlik jamlash (cloud).

Butun oqim: SceneAnalyzer oyoq nuqtalarini katakka yig'adi → 10 daqiqada
JSON fayl → lokal ilova POST qiladi → cloud soat bo'yicha JAMLAB yozadi →
panel Toshkent kuni/soati bo'yicha o'qiydi.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from chaqimchi_ai.retail.heatmap import (
    GRID_COLS,
    GRID_ROWS,
    HeatmapGrid,
    write_heatmap_file,
)
from cloud import ratelimit
from cloud.snapshots import LocalSnapshotStore

ADMIN = {"X-Cloud-Admin-Key": "test-admin"}


# ── Edge: to'r yig'ish ───────────────────────────────────────────────────


def test_points_land_in_the_right_cells() -> None:
    grid = HeatmapGrid()
    grid.add(0.0, 0.0)  # chap-yuqori
    grid.add(0.999, 0.999)  # o'ng-past
    grid.add(0.5, 0.5)
    grid.frame_done()

    cells, frames, points = grid.drain()

    assert cells[0][0] == 1
    assert cells[GRID_ROWS - 1][GRID_COLS - 1] == 1
    assert cells[GRID_ROWS // 2][GRID_COLS // 2] == 1
    assert (frames, points) == (1, 3)


def test_drain_resets_the_grid() -> None:
    grid = HeatmapGrid()
    grid.add(0.5, 0.5)
    grid.drain()

    cells, frames, points = grid.drain()

    assert points == 0 and frames == 0
    assert sum(sum(row) for row in cells) == 0


def test_out_of_range_points_are_clamped() -> None:
    grid = HeatmapGrid()
    grid.add(-0.5, 1.7)

    cells, _frames, points = grid.drain()

    assert points == 1
    assert cells[GRID_ROWS - 1][0] == 1


def test_hourly_file_accumulates_between_flushes(tmp_path: Path) -> None:
    """Cloud yetib olmagan bo'lsa bir soat fayli JAMLANIB boradi."""
    cells = [[0] * GRID_COLS for _ in range(GRID_ROWS)]
    cells[3][7] = 2
    write_heatmap_file(tmp_path, "camera-01", "2026-08-18T09", cells, 10)

    again = [[0] * GRID_COLS for _ in range(GRID_ROWS)]
    again[3][7] = 5
    target = write_heatmap_file(tmp_path, "camera-01", "2026-08-18T09", again, 4)

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["grid"][3][7] == 7
    assert payload["frames"] == 14


# ── SceneAnalyzer bilan integratsiya ─────────────────────────────────────


def test_analyzer_accumulates_foot_points() -> None:
    import numpy as np

    from chaqimchi_ai.scene_analytics import SceneAnalyzer
    from chaqimchi_ai.settings import SceneSettings

    class OnePerson:
        def detect(self, frame):
            return [{"bbox": [40.0, 20.0, 60.0, 80.0], "score": 0.9}]

    analyzer = SceneAnalyzer("cam-1", OnePerson(), SceneSettings(event_debounce_sec=1))
    analyzer.motion.has_motion = lambda _frame: True
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    analyzer.analyze(frame, now=1.0)
    analyzer.analyze(frame, now=2.0)

    cells, frames, points = analyzer.heatmap.drain()
    assert frames == 2 and points == 2
    # Oyoq nuqtasi: markaz-x 0.5, past-y 0.8.
    assert cells[int(0.8 * GRID_ROWS)][GRID_COLS // 2] == 2


# ── Cloud: qabul, jamlash, o'qish ────────────────────────────────────────


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    import cloud.main as main

    monkeypatch.setenv("CHAQIMCHI_CLOUD_ADMIN_KEY", "test-admin")
    monkeypatch.setenv("CHAQIMCHI_OWNER_JWT_SECRET", "owner-secret-with-more-than-32-characters")
    monkeypatch.setenv("CHAQIMCHI_OTP_TEST_CODE", "123456")
    monkeypatch.setenv("CHAQIMCHI_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("CHAQIMCHI_S3_ENDPOINT", raising=False)
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "cloud.db")
    monkeypatch.setattr(main, "_store", None)
    monkeypatch.setattr(main, "_event_store", None)
    monkeypatch.setattr(main, "_event_store_key", None)
    monkeypatch.setattr(main, "_snapshots", LocalSnapshotStore(tmp_path / "snapshots"))
    ratelimit.limiter().reset()
    with TestClient(main.app) as test_client:
        yield test_client
    ratelimit.limiter().reset()


def _device(client: TestClient):
    site = client.post("/api/v1/admin/sites", headers=ADMIN, json={"name": "Xarita"}).json()
    device = client.post(
        "/api/v1/devices/claim", json={"pairing_code": site["pairing_code"]}
    ).json()
    return site, {
        "X-Site-Id": device["site_id"],
        "X-Device-Id": device["device_id"],
        "X-Device-Token": device["device_token"],
    }


def _owner(client: TestClient, site_id: str) -> dict:
    client.post(
        f"/api/v1/admin/sites/{site_id}/members",
        headers=ADMIN,
        json={"telegram_id": "808", "role": "owner"},
    )
    client.post("/api/v1/owner/auth/request", json={"telegram_id": "808"})
    verified = client.post(
        "/api/v1/owner/auth/verify",
        json={"telegram_id": "808", "site_id": site_id, "code": "123456"},
    )
    return {"Authorization": f"Bearer {verified.json()['access_token']}"}


def _grid(value_at=None) -> list:
    cells = [[0] * GRID_COLS for _ in range(GRID_ROWS)]
    if value_at:
        row, col, value = value_at
        cells[row][col] = value
    return cells


def test_uploads_accumulate_and_the_owner_reads_them_back(client: TestClient) -> None:
    site, headers = _device(client)
    owner = _owner(client, site["site_id"])
    bucket = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")

    for value in (3, 4):
        response = client.post(
            "/api/v1/edge/heatmap",
            headers=headers,
            json={
                "items": [
                    {
                        "camera_id": "camera-01",
                        "hour": bucket,
                        "grid": _grid((5, 10, value)),
                        "frames": 100,
                    }
                ]
            },
        )
        assert response.status_code == 200

    data = client.get("/api/v1/owner/heatmap?camera_id=camera-01", headers=owner).json()
    assert data["grid"][5][10] == 7, "ikki yuborish jamlansin"
    assert data["frames"] == 200
    assert data["points"] == 7


def test_wrong_grid_shape_is_rejected(client: TestClient) -> None:
    _site, headers = _device(client)
    response = client.post(
        "/api/v1/edge/heatmap",
        headers=headers,
        json={
            "items": [{"camera_id": "c", "hour": "2026-08-18T09", "grid": [[1, 2]], "frames": 1}]
        },
    )
    assert response.status_code == 422


def test_heatmap_is_tenant_scoped(client: TestClient) -> None:
    site, headers = _device(client)
    bucket = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
    client.post(
        "/api/v1/edge/heatmap",
        headers=headers,
        json={
            "items": [
                {"camera_id": "camera-01", "hour": bucket, "grid": _grid((1, 1, 9)), "frames": 5}
            ]
        },
    )
    other = client.post("/api/v1/admin/sites", headers=ADMIN, json={"name": "Boshqa"}).json()
    stranger = _owner(client, other["site_id"])

    data = client.get("/api/v1/owner/heatmap?camera_id=camera-01", headers=stranger).json()

    assert data["points"] == 0, "boshqa saytning to'ri ko'rinmasin"


def test_old_heatmaps_are_purged(client: TestClient) -> None:
    import cloud.main as main

    site, headers = _device(client)
    client.post(
        "/api/v1/edge/heatmap",
        headers=headers,
        json={
            "items": [
                {
                    "camera_id": "camera-01",
                    "hour": "2020-01-01T09",
                    "grid": _grid((1, 1, 3)),
                    "frames": 5,
                }
            ]
        },
    )

    removed = main.get_event_store().purge_heatmaps(site["site_id"], retention_days=90)

    assert removed == 1
