import pytest
from fastapi.testclient import TestClient

import chaqimchi_ai.sotqin_agent as module


def test_control_health_is_fail_closed_before_pairing(monkeypatch) -> None:
    monkeypatch.setattr(module.control, "cloud_url", "")
    monkeypatch.setattr(module.control, "site_id", "")
    monkeypatch.setattr(module.control, "device_id", "")
    monkeypatch.setattr(module.control, "device_token", "")
    response = TestClient(module.app).get("/health")
    assert response.status_code == 503
    assert response.json()["ai_model"] == "cloud-only"
    assert response.json()["product"] == "Sotqin"


def test_control_health_reports_paired_without_loading_model(monkeypatch) -> None:
    monkeypatch.setattr(module.control, "cloud_url", "https://cloud.example.uz")
    monkeypatch.setattr(module.control, "site_id", "site")
    monkeypatch.setattr(module.control, "device_id", "device")
    monkeypatch.setattr(module.control, "device_token", "token")
    response = TestClient(module.app).get("/health")
    assert response.status_code == 200
    assert response.json()["mode"] == "control-only"


def test_sotqin_config_is_validated_and_saved_atomically(tmp_path, monkeypatch) -> None:
    payload = {
        "revision": 3,
        "product": {"name": "Sotqin", "max_cameras": 8},
        "buffer_policy": {"max_days": 3, "max_bytes": 40 * 1024**3},
        "cloud_features": [{"code": "person_count", "camera_count": 2, "queue_kind": "batch"}],
    }
    monkeypatch.setattr(module.control, "config_path", tmp_path / "config.json")
    module.control.validate_config(payload)
    module.control.persist_config(payload)
    assert module.control.config_path.stat().st_mode & 0o777 == 0o600
    assert '"revision":3' in module.control.config_path.read_text(encoding="utf-8")


def test_sotqin_rejects_wrong_product() -> None:
    try:
        module.control.validate_config(
            {"revision": 1, "product": {"name": "Boshqa", "max_cameras": 1}, "cloud_features": []}
        )
        assert False
    except ValueError as exc:
        assert "Sotqin" in str(exc)


def test_sotqin_rejects_profile_over_8_cameras_or_40gb_buffer() -> None:
    with pytest.raises(ValueError, match="8 kamera"):
        module.control.validate_config(
            {"revision": 1, "product": {"name": "Sotqin", "max_cameras": 9}, "cloud_features": []}
        )
    with pytest.raises(ValueError, match="40 GB"):
        module.control.validate_config(
            {
                "revision": 1,
                "product": {"name": "Sotqin", "max_cameras": 8},
                "buffer_policy": {"max_days": 3, "max_bytes": 41 * 1024**3},
                "cloud_features": [],
            }
        )


# ── Heartbeat orqali kelgan rasm so'rovi ─────────────────────────────────


class _Sent:
    """Yuborilgan PUT so'rovlarini yozadi."""

    def __init__(self, *, fails: bool = False) -> None:
        self.calls: list = []
        self.fails = fails

    async def put(self, url, *, headers=None, content=None):
        self.calls.append((url, headers or {}, content))
        if self.fails:
            raise RuntimeError("tarmoq yo'q")

        class _Response:
            @staticmethod
            def raise_for_status() -> None:
                return None

        return _Response()


def _agent_with_cameras(monkeypatch, media_frames: dict, *, fails: bool = False):
    control = module.SotqinAgent()
    control.cloud_url = "https://cloud.test"
    control.site_id, control.device_id, control.device_token = "s", "d", "t"
    control.media.apply_config(
        {
            "cameras": [
                {"camera_id": "camera-01", "source": "rtsp://nvr/1", "enabled": True},
                {"camera_id": "camera-02", "source": "rtsp://nvr/2", "enabled": True},
                {"camera_id": "camera-03", "source": "rtsp://nvr/3", "enabled": False},
            ]
        }
    )
    monkeypatch.setattr(
        control.media, "grab_preview", lambda camera: media_frames.get(camera["camera_id"])
    )
    sent = _Sent(fails=fails)
    control.client = sent
    return control, sent


def test_only_requested_cameras_send_a_frame(monkeypatch) -> None:
    import asyncio

    control, sent = _agent_with_cameras(monkeypatch, {"camera-01": b"a", "camera-02": b"b"})

    assert asyncio.run(control.upload_previews(["camera-01"])) == 1
    assert len(sent.calls) == 1
    assert sent.calls[0][0].endswith("/api/v1/sotqin/cameras/camera-01/preview")
    assert sent.calls[0][1]["Content-Type"] == "image/jpeg"
    assert sent.calls[0][2] == b"a"


def test_disabled_and_unknown_cameras_are_skipped(monkeypatch) -> None:
    import asyncio

    control, sent = _agent_with_cameras(monkeypatch, {"camera-03": b"c"})

    assert asyncio.run(control.upload_previews(["camera-03", "camera-09"])) == 0
    assert sent.calls == []


def test_one_broken_camera_does_not_stop_the_others(monkeypatch) -> None:
    """O'rnatuvchi to'rttadan uchtasini ko'rib, to'rtinchisi ishlamayotganini
    bilsin — bitta xato butun so'rovni yiqitmasin."""
    import asyncio

    control, sent = _agent_with_cameras(monkeypatch, {"camera-02": b"b"})  # camera-01 -> None

    assert asyncio.run(control.upload_previews(["camera-01", "camera-02"])) == 1
    assert len(sent.calls) == 1


def test_upload_failure_is_swallowed(monkeypatch) -> None:
    import asyncio

    control, _sent = _agent_with_cameras(monkeypatch, {"camera-01": b"a"}, fails=True)

    assert asyncio.run(control.upload_previews(["camera-01"])) == 0


def test_a_missing_request_list_is_ignored(monkeypatch) -> None:
    import asyncio

    control, sent = _agent_with_cameras(monkeypatch, {"camera-01": b"a"})

    assert asyncio.run(control.upload_previews(None)) == 0
    assert asyncio.run(control.upload_previews("camera-01")) == 0
    assert sent.calls == []


def test_health_reports_poisoned_events(tmp_path) -> None:
    """Tashlangan hodisalar soni cloudga yetsin.

    Nolga teng bo'lmasa cloud biror narsani doimiy rad etyapti — bu kod
    xatosi, tarmoq emas, va uni admin ko'rishi kerak.
    """
    from datetime import datetime, timedelta, timezone

    from chaqimchi_ai.event_models import EdgeEvent
    from chaqimchi_ai.outbox import MAX_ATTEMPTS, EventOutbox

    path = tmp_path / "outbox.db"
    outbox = EventOutbox(path, max_bytes=10**7)
    outbox.enqueue(EdgeEvent(event_id="umidsiz", event_type="line_crossed", camera_id="camera-01"))
    moment = datetime.now(timezone.utc)
    for _ in range(MAX_ATTEMPTS):
        # `permanent=True` — cloud hodisaning O'ZINI rad etdi.  Tarmoq
        # uzilishi hodisani o'ldirmaydi (`tests/test_outbox.py`).
        outbox.fail("umidsiz", "rad etildi", permanent=True, now=moment)
        moment += timedelta(seconds=600)

    control = module.SotqinAgent()
    control.outbox_paths = [path]

    assert control.health_payload()["outbox_poisoned"] == 1


def test_health_survives_an_old_database_without_the_dead_letter_table(tmp_path) -> None:
    """Yangilanmagan qurilmada jadval hali yo'q — heartbeat yiqilmasin."""
    import sqlite3

    path = tmp_path / "outbox.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE outbox (event_id TEXT PRIMARY KEY, payload TEXT NOT NULL,"
            "created_at TEXT NOT NULL)"
        )
        conn.execute("INSERT INTO outbox VALUES('a','{}','2026-01-01T00:00:00+00:00')")

    control = module.SotqinAgent()
    control.outbox_paths = [path]

    payload = control.health_payload()
    assert payload["outbox_pending"] == 1
    assert payload["outbox_poisoned"] == 0


# ── Kameralarning haqiqiy holati ─────────────────────────────────────────


def _status_file(tmp_path, payload: dict):
    import json

    path = tmp_path / "retail-status.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_camera_count_comes_from_the_chain_not_from_ffprobe(tmp_path) -> None:
    """Butun tuzatishning sababi.

    `ffprobe` "RTSP manzil javob beryaptimi" deydi; kamera javob berib
    turib, retail zanjiri bir soat backoff'da bo'lishi mumkin. 72 soatlik
    soak testi aynan shu farqni ko'rmasdan "4 kamera ishlayapti" deb
    sertifikatlab qo'yardi.
    """
    import time

    control = module.SotqinAgent()
    control.retail_status_path = _status_file(
        tmp_path, {"updated_at": time.time(), "cameras_active": 2, "cameras_configured": 4}
    )
    # ffprobe esa to'rttasi ham joyida deb turibdi.
    from chaqimchi_ai.sotqin_media import StreamProbe

    control.media.apply_config(
        {
            "cameras": [
                {"camera_id": f"camera-0{n}", "source": f"rtsp://nvr/{n}", "enabled": True}
                for n in range(1, 5)
            ]
        }
    )
    control.media.probes = {
        f"camera-0{n}": StreamProbe(f"camera-0{n}", "online") for n in range(1, 5)
    }
    assert control.media.health()["online"] == 4

    # Zanjir haqiqatni biladi.
    assert control.health_payload()["cameras_active"] == 2


def test_a_stale_status_file_is_not_trusted(tmp_path) -> None:
    """Retail xizmati o'lgan bo'lishi mumkin — eski raqamni "hozirgi holat"
    deb yuborish yolg'on bo'lardi."""
    import time

    control = module.SotqinAgent()
    control.retail_status_path = _status_file(
        tmp_path, {"updated_at": time.time() - 3600, "cameras_active": 4}
    )

    assert control.retail_status() is None
    # ffprobe zaxirasiga tushadi (kamera sozlanmagan → 0).
    assert control.health_payload()["cameras_active"] == 0


def test_a_missing_or_broken_status_file_falls_back(tmp_path) -> None:
    control = module.SotqinAgent()

    control.retail_status_path = tmp_path / "yo-q.json"
    assert control.retail_status() is None

    broken = tmp_path / "buzuq.json"
    broken.write_text("{ bu json emas", encoding="utf-8")
    control.retail_status_path = broken
    assert control.retail_status() is None

    without_timestamp = _status_file(tmp_path, {"cameras_active": 4})
    control.retail_status_path = without_timestamp
    assert control.retail_status() is None
