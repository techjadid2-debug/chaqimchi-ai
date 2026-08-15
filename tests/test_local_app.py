"""Mijozning o'z kompyuteridagi sozlash ustasi va paneli.

Bu testlar aynan o'sha yo'lni bosib o'tadi: kamera qo'shish → chiziq chizish →
ishga tushirishga tayyor bo'lish.  Sabab tarixiy: oldingi "onboarding sehrgari"
chiroyli ko'rinardi-yu, hech narsani saqlamasdi — kamera tanlansa `alert()`
chiqardi, pairing kod HTML ichida qotirilgan edi, oxiri esa login deviga olib
borardi.  Shuning uchun bu yerda tekshiriladigan narsa "sahifa ochildimi" emas,
**config faylida haqiqatan nima paydo bo'ldi**.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

import pytest
import yaml
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("CHAQIMCHI_LOCAL_DIR", str(tmp_path))
    # Modulni har testda toza holatda yuklaymiz: `paths` yo'llarni
    # muhitdan o'qiydi va modul darajasida keshlamaydi, lekin `supervisor`
    # bitta global obyekt — u eski `tmp_path` ni ushlab qolmasligi kerak.
    import importlib

    from chaqimchi_ai.local import app as app_module
    from chaqimchi_ai.local import config_store, paths, supervisor

    importlib.reload(paths)
    importlib.reload(config_store)
    importlib.reload(supervisor)
    importlib.reload(app_module)
    return TestClient(app_module.app)


def _config(tmp_path: Path) -> Dict[str, Any]:
    return yaml.safe_load((tmp_path / "config.yaml").read_text(encoding="utf-8"))


# ── Sozlash oqimi ────────────────────────────────────────────────────────


def test_first_run_opens_the_wizard_not_the_panel(client: TestClient) -> None:
    """Sozlanmagan dastur panelni ko'rsatsa, mijoz bo'sh raqamlarni ko'radi."""
    response = client.get("/")
    assert response.status_code == 200
    assert "Kamerangizni ulaymiz" in response.text


def test_camera_is_actually_written_to_config(client: TestClient, tmp_path: Path) -> None:
    response = client.post(
        "/api/setup/cameras",
        json={"label": "Kirish eshigi", "rtsp_url": "rtsp://admin:pw@192.168.1.64:554/Streaming/channels/102"},
    )
    assert response.status_code == 200
    assert response.json()["camera_id"] == "camera-01"

    saved = _config(tmp_path)["retail"]
    assert saved["cameras_source"] == "config", "cloudsiz ishlash uchun majburiy"
    assert saved["cameras"][0]["id"] == "camera-01"
    assert saved["cameras"][0]["stream_url"].startswith("rtsp://")


def test_camera_password_never_reaches_the_browser(client: TestClient) -> None:
    """RTSP manzili NVR paroli bilan keladi — u kameraga to'liq kirish demak."""
    secret = "JudaMaxfiyParol"
    client.post(
        "/api/setup/cameras",
        json={"label": "Kassa", "rtsp_url": f"rtsp://admin:{secret}@192.168.1.64:554/x"},
    )
    for path in ("/api/setup/cameras", "/api/setup/summary", "/api/status"):
        assert secret not in client.get(path).text, path


def test_rtsp_template_escapes_special_characters(client: TestClient) -> None:
    """Parolda `@` bo'lsa xom qo'shish manzilni buzadi va kamera ochilmaydi."""
    response = client.post(
        "/api/setup/rtsp-template",
        json={"brand": "hikvision", "host": "192.168.1.64", "username": "admin", "password": "a@b/c", "channel": 2},
    )
    url = response.json()["rtsp_url"]
    assert url == "rtsp://admin:a%40b%2Fc@192.168.1.64:554/Streaming/channels/202"
    assert response.json()["safe_url"] == "rtsp://…@192.168.1.64:554/Streaming/channels/202"


def test_camera_limit_matches_the_accepted_profile(client: TestClient) -> None:
    """4 kamera — o'lchangan sig'im (`docs/DOKON_MVP.md`).  Ortig'i va'da emas."""
    for index in range(4):
        assert (
            client.post(
                "/api/setup/cameras",
                json={"label": f"Kamera {index}", "rtsp_url": f"rtsp://host/{index}"},
            ).status_code
            == 200
        )
    response = client.post("/api/setup/cameras", json={"rtsp_url": "rtsp://host/5"})
    assert response.status_code == 422


def test_geometry_is_validated_before_it_is_kept(client: TestClient) -> None:
    """Noto'g'ri chiziq saqlansa, zanjir keyingi startda yiqilardi."""
    client.post("/api/setup/cameras", json={"rtsp_url": "rtsp://host/1"})
    response = client.put(
        "/api/setup/geometry",
        json={"lines": [{"name": "Kirish", "camera_id": "camera-01", "start": [5.0, 5.0], "end": [9.0, 9.0]}], "zones": []},
    )
    assert response.status_code == 422, "0..1 dan tashqaridagi koordinata qabul qilinmasligi kerak"


def test_full_setup_makes_the_system_ready(client: TestClient, tmp_path: Path) -> None:
    client.post("/api/setup/cameras", json={"label": "Kirish", "rtsp_url": "rtsp://host/1"})
    assert client.get("/api/setup/summary").json()["ready"] is False, "chiziqsiz tayyor emas"

    client.put(
        "/api/setup/geometry",
        json={
            "lines": [
                {
                    "name": "Kirish",
                    "camera_id": "camera-01",
                    "start": [0.1, 0.5],
                    "end": [0.9, 0.5],
                    "swap_direction": False,
                }
            ],
            "zones": [],
        },
    )
    assert client.get("/api/setup/summary").json()["ready"] is True
    # Sozlangandan keyin bosh sahifa panelga aylanadi.
    assert "Bugungi holat" in client.get("/").text

    scene = _config(tmp_path)["scene"]
    assert scene["lines"][0]["camera_id"] == "camera-01"


def test_deleting_a_camera_removes_its_lines(client: TestClient, tmp_path: Path) -> None:
    """Kamerasiz qolgan chiziq jimgina e'tiborsiz qolardi va mijoz
    "chizdim, lekin sanamayapti" holatiga tushardi."""
    client.post("/api/setup/cameras", json={"rtsp_url": "rtsp://host/1"})
    client.put(
        "/api/setup/geometry",
        json={
            "lines": [
                {"name": "Kirish", "camera_id": "camera-01", "start": [0.1, 0.5], "end": [0.9, 0.5]}
            ],
            "zones": [],
        },
    )
    client.delete("/api/setup/cameras/camera-01")
    assert _config(tmp_path)["scene"]["lines"] == []


def test_store_hours_must_be_given_as_a_pair(client: TestClient) -> None:
    """Faqat ochilish berilsa `after_hours_presence` yolg'on signal berardi."""
    response = client.put("/api/setup/settings", json={"open_from": "09:00"})
    assert response.status_code == 422


# ── Xizmat ───────────────────────────────────────────────────────────────


def test_service_refuses_to_start_without_a_camera(client: TestClient) -> None:
    """Kamerasiz zanjir darhol yiqilardi; sabab mijozga aytiladi."""
    response = client.post("/api/service/start")
    assert response.status_code == 200
    body = response.json()
    assert body["running"] is False
    assert body["error"]


def test_service_reports_a_missing_model_in_plain_language(client: TestClient) -> None:
    client.post("/api/setup/cameras", json={"rtsp_url": "rtsp://host/1"})
    body = client.post("/api/service/start").json()
    assert body["running"] is False
    assert "model" in body["error"].lower()


# ── Hisobot ──────────────────────────────────────────────────────────────


def _seed_outbox(tmp_path: Path, events: list[Dict[str, Any]]) -> None:
    """Zanjir yozadigan navbatni taqlid qiladi (panel faqat o'qiydi)."""
    db = tmp_path / "data" / "outbox.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS outbox ("
        "event_id TEXT PRIMARY KEY, payload TEXT, created_at TEXT, priority INTEGER DEFAULT 0)"
    )
    for index, event in enumerate(events):
        conn.execute(
            "INSERT INTO outbox (event_id, payload, created_at) VALUES (?,?,?)",
            (f"e{index}", json.dumps(event), event["occurred_at"]),
        )
    conn.commit()
    conn.close()


def test_report_counts_only_todays_local_day(client: TestClient, tmp_path: Path) -> None:
    """Toshkent UTC+5: UTC kuni bo'yicha hisoblansa ertalabki savdo
    kechagi kunga tushib qolardi va do'kon egasi nol ko'rardi."""
    now = datetime.now().astimezone()
    yesterday = now - timedelta(days=1)
    _seed_outbox(
        tmp_path,
        [
            {"event_type": "line_crossed", "direction": "in", "camera_id": "camera-01", "occurred_at": now.isoformat()},
            {"event_type": "line_crossed", "direction": "in", "camera_id": "camera-01", "occurred_at": now.isoformat()},
            {"event_type": "line_crossed", "direction": "out", "camera_id": "camera-01", "occurred_at": now.isoformat()},
            {"event_type": "line_crossed", "direction": "in", "camera_id": "camera-01", "occurred_at": yesterday.isoformat()},
        ],
    )
    report = client.get("/api/report").json()
    assert report["date"] == now.date().isoformat()
    assert report["entered"] == 2
    assert report["exited"] == 1
    assert report["inside_estimate"] == 1


def test_report_collects_alerts(client: TestClient, tmp_path: Path) -> None:
    now = datetime.now().astimezone()
    _seed_outbox(
        tmp_path,
        [
            {
                "event_type": "camera_tampered",
                "severity": "critical",
                "camera_id": "camera-01",
                "occurred_at": now.isoformat(),
            }
        ],
    )
    report = client.get("/api/report").json()
    assert report["alert_count"] == 1
    assert report["alerts"][0]["type"] == "camera_tampered"


def test_report_survives_a_missing_outbox(client: TestClient) -> None:
    """Birinchi kunda navbat fayli hali yo'q — panel yiqilmasligi kerak."""
    report = client.get("/api/report").json()
    assert report["entered"] == 0
    assert report["events_total"] == 0


def test_utc_timestamps_are_converted_to_local_time(client: TestClient, tmp_path: Path) -> None:
    """Zanjir vaqtni UTC da yozadi; hisobot mahalliy kunga tushishi kerak."""
    now_utc = datetime.now(timezone.utc)
    _seed_outbox(
        tmp_path,
        [
            {
                "event_type": "line_crossed",
                "direction": "in",
                "camera_id": "camera-01",
                "occurred_at": now_utc.isoformat().replace("+00:00", "Z"),
            }
        ],
    )
    report = client.get("/api/report").json()
    assert report["entered"] == 1
    assert report["date"] == now_utc.astimezone().date().isoformat()
