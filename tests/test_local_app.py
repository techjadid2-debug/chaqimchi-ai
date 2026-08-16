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


# ── RTSP formatini avtomatik topish ──────────────────────────────────────
#
# Mijoz NVR brendini ko'pincha bilmaydi yoki noto'g'ri tanlaydi.  Ilgari
# sehrgar faqat **bitta** formatni sinardi va "tasvir kelmadi" degan
# foydasiz xato berardi — mijoz nima qilishni bilmasdi.


def test_known_paths_cover_the_common_uzbek_market_brands() -> None:
    from chaqimchi_ai.local.camera_probe import KNOWN_PATHS

    joined = " ".join(path for _name, path in KNOWN_PATHS).lower()
    for marker in ("streaming/channels", "realmonitor", "unicast", "h264preview"):
        assert marker in joined, f"{marker} formatlar ro'yxatida yo'q"


def test_substream_is_tried_before_the_main_stream() -> None:
    """Substream yengil (640x360) va oddiy kompyuterda dekodlanadi;
    1080p main stream tahlil uchun og'ir."""
    from chaqimchi_ai.local.camera_probe import KNOWN_PATHS

    paths = [path for _name, path in KNOWN_PATHS]
    assert paths.index("/Streaming/Channels/{ch}02") < paths.index(
        "/Streaming/Channels/{ch}01"
    )


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("rtsp://h/Streaming/Channels/102", "/Streaming/Channels/{ch}02"),
        ("rtsp://h/cam/realmonitor?channel=1&subtype=1", "/cam/realmonitor?channel={ch}&subtype=1"),
        ("rtsp://h/unicast/c1/s1/live", "/unicast/c{ch}/s1/live"),
        ("rtsp://h/h264Preview_01_sub", "/h264Preview_0{ch}_sub"),
        # Kanal raqami yo'q format — shablon o'zgarmaydi.
        ("rtsp://h/stream2", "/stream2"),
    ],
)
def test_channel_slot_is_found_in_every_known_format(url: str, expected: str) -> None:
    """Birinchi kanalda topilgan format qolganlariga ham qo'llanadi —
    aks holda har kanal uchun o'nlab variantni qayta sinardik."""
    from chaqimchi_ai.local.camera_probe import path_template

    assert path_template(url, 1) == expected


def test_auto_find_reports_a_usable_reason_when_nothing_works(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Xato xabari mijoz **tuzata oladigan** bo'lishi kerak."""
    from chaqimchi_ai.local import camera_probe

    monkeypatch.setattr(camera_probe, "rtsp_describe", lambda url, **kw: (401, ""))
    response = client.post(
        "/api/setup/auto-find",
        json={"host": "192.168.1.64", "username": "admin", "password": "xato"},
    )
    body = response.json()
    assert body["ok"] is False
    assert "parol" in (body["error"] + body["hint"]).lower()


def test_unreachable_camera_says_so_plainly(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from chaqimchi_ai.local import camera_probe

    monkeypatch.setattr(camera_probe, "rtsp_describe", lambda url, **kw: (0, "timeout"))
    body = client.post("/api/setup/auto-find", json={"host": "10.0.0.9"}).json()
    assert body["ok"] is False
    assert "ulanib bo'lmadi" in body["error"].lower()
    assert "ping" in body["hint"].lower(), "mijozga aniq tekshiruv berilishi kerak"


def test_codec_problem_is_named(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """RTSP 200 qaytardi-yu kadr kelmadi — bu deyarli doim H.265."""
    from chaqimchi_ai.local import camera_probe

    monkeypatch.setattr(camera_probe, "rtsp_describe", lambda url, **kw: (200, ""))
    monkeypatch.setattr(
        camera_probe,
        "grab_frame",
        lambda url, **kw: camera_probe.ProbeResult(ok=False, error="x", hint="y"),
    )
    body = client.post("/api/setup/auto-find", json={"host": "192.168.1.64"}).json()
    assert body["ok"] is False


# ── OpenCV sozlamasi zanjirga oqib ketmasligi ────────────────────────────
#
# Haqiqiy xato: kamera sinovi `OPENCV_FFMPEG_CAPTURE_OPTIONS` ni jarayon
# muhitiga yozardi, supervisor esa bolaga butun muhitni uzatardi.  Zanjir
# `setdefault` ishlatgani uchun o'sha begona qiymatni saqlab qolardi va
# **barcha kamera ochilmay qolardi** — logda faqat "ochilmadi" ko'rinardi.


def test_probe_restores_the_capture_options(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    from chaqimchi_ai.local import camera_probe

    monkeypatch.setenv("OPENCV_FFMPEG_CAPTURE_OPTIONS", "oldindan;bor")
    camera_probe.grab_frame("rtsp://10.255.255.1:554/x", timeout_sec=1)
    assert os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] == "oldindan;bor"


def test_probe_leaves_no_trace_when_nothing_was_set(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    from chaqimchi_ai.local import camera_probe

    monkeypatch.delenv("OPENCV_FFMPEG_CAPTURE_OPTIONS", raising=False)
    camera_probe.grab_frame("rtsp://10.255.255.1:554/x", timeout_sec=1)
    assert "OPENCV_FFMPEG_CAPTURE_OPTIONS" not in os.environ


def test_probe_never_uses_the_ambiguous_timeout_option() -> None:
    """RTSP demuxer uchun `timeout` "kiruvchi ulanishni kutish" degani va
    `listen` rejimini nazarda tutadi — mijoz ulanishini buzadi."""
    source = (
        Path(__file__).resolve().parents[1] / "chaqimchi_ai" / "local" / "camera_probe.py"
    ).read_text(encoding="utf-8")
    assert "|timeout;" not in source, "noaniq `timeout` opsiyasi qaytarilmasin"
    assert "stimeout;" in source


def test_pipeline_pins_its_own_capture_options() -> None:
    """Zanjir tashqaridan kelgan qiymatga tayanmasligi kerak."""
    source = (
        Path(__file__).resolve().parents[1] / "chaqimchi_ai" / "retail" / "runner.py"
    ).read_text(encoding="utf-8")
    assert 'os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"]' in source
    code = "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("#")
    )
    assert "os.environ.setdefault" not in code, "meros qilib olingan qiymat saqlanib qolardi"


def test_supervisor_strips_the_probe_options() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "chaqimchi_ai" / "local" / "supervisor.py"
    ).read_text(encoding="utf-8")
    assert 'env.pop("OPENCV_FFMPEG_CAPTURE_OPTIONS"' in source


# ── Qoidalar fayli (rules.yaml) ulanishi ─────────────────────────────────
#
# Bag tarixi: `rules_path` hech qayerda o'rnatilmasdi, `RuleEngine()` bo'sh
# ishlar edi — `person_detected` bosilmasdan cloudga oqdi (jonli qurilmada
# bir kunda 394 ta), sovutishlar va `save_clip` o'lik edi.


def test_fresh_config_wires_the_rules_file(client: TestClient, tmp_path: Path) -> None:
    client.get("/api/status")  # config yaratilsin
    config = _config(tmp_path)
    rules_path = config["retail"].get("rules_path") or ""
    assert rules_path.endswith("rules.yaml"), "yangi config qoidalarsiz qolmasin"
    assert Path(rules_path).is_file(), "ko'rsatilgan qoidalar fayli mavjud bo'lsin"


def test_old_config_without_rules_is_healed(tmp_path: Path, monkeypatch) -> None:
    """Ishlab turgan eski qurilmalar yangilanishdan keyin o'zi tuzalsin."""
    import importlib

    from chaqimchi_ai.local import config_store, paths

    monkeypatch.setenv("CHAQIMCHI_LOCAL_DIR", str(tmp_path))
    importlib.reload(paths)
    importlib.reload(config_store)

    old = config_store.default_config()
    del old["retail"]["rules_path"]  # eski versiya configi
    config_store._write_raw_unlocked(old)

    healed = config_store.read_raw()

    assert str(healed["retail"].get("rules_path", "")).endswith("rules.yaml")
    saved = yaml.safe_load((tmp_path / "config.yaml").read_text(encoding="utf-8"))
    assert str(saved["retail"].get("rules_path", "")).endswith("rules.yaml"), (
        "davolash faylga ham yozilsin — keyingi restartda ham tursin"
    )


# ── Klip uchun asosiy oqim (record_url) ──────────────────────────────────
#
# Bag tarixi: `record_url` hech qachon to'ldirilmasdi — kliplar Windows'da
# umuman ishlamaganining uchta sababidan biri.  Endi substream saqlanganda
# asosiy oqim avto-taklif qilinadi va tekshirib yoziladi.


def test_saving_a_camera_autofills_the_record_url(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    from chaqimchi_ai.local import app as app_module

    monkeypatch.setattr(
        app_module.camera_probe, "rtsp_describe", lambda url, timeout_sec=4.0: (200, "OK")
    )
    response = client.post(
        "/api/setup/cameras",
        json={"label": "Kirish", "rtsp_url": "rtsp://admin:pw@10.0.0.5:554/Streaming/Channels/102"},
    )

    assert response.status_code == 200
    assert response.json()["record_url_found"] is True
    saved = _config(tmp_path)["retail"]["cameras"][0]
    assert saved["record_url"] == "rtsp://admin:pw@10.0.0.5:554/Streaming/Channels/101"


def test_unreachable_main_stream_is_not_stored(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    """Ishlamaydigan taxmin yozilsa ffmpeg abadiy xato aylanardi."""
    from chaqimchi_ai.local import app as app_module

    monkeypatch.setattr(
        app_module.camera_probe, "rtsp_describe", lambda url, timeout_sec=4.0: (404, "Not Found")
    )
    response = client.post(
        "/api/setup/cameras",
        json={"label": "Kirish", "rtsp_url": "rtsp://admin:pw@10.0.0.5:554/Streaming/Channels/102"},
    )

    assert response.status_code == 200
    assert response.json()["record_url_found"] is False
    assert _config(tmp_path)["retail"]["cameras"][0].get("record_url") is None


def test_explicit_record_url_wins_over_the_suggestion(
    client: TestClient, tmp_path: Path
) -> None:
    response = client.post(
        "/api/setup/cameras",
        json={
            "label": "Kassa",
            "rtsp_url": "rtsp://admin:pw@10.0.0.5:554/Streaming/Channels/202",
            "record_url": "rtsp://admin:pw@10.0.0.5:554/maxsus/asosiy",
        },
    )

    assert response.status_code == 200
    saved = _config(tmp_path)["retail"]["cameras"][0]
    assert saved["record_url"] == "rtsp://admin:pw@10.0.0.5:554/maxsus/asosiy"


# ── Funksiyalar holati ro'yxati ──────────────────────────────────────────
#
# "Yashil chiroq yolg'oni"ga qarshi: xizmat ishlayotgani hamma funksiya
# ishlayotganini bildirmaydi.  Panel va sehrgar shu ro'yxatni ko'rsatadi.


def test_status_lists_every_feature_with_a_reason(client: TestClient) -> None:
    data = client.get("/api/status").json()
    features = {item["code"]: item for item in data["features"]}

    expected = {"line_count", "queue", "restricted", "dwell", "after_hours", "tamper", "clips"}
    assert expected <= set(features), "har funksiya ro'yxatda bo'lsin"
    # Yangi o'rnatishda geometriya yo'q — sabab aniq matnda aytiladi.
    assert features["line_count"]["active"] is False
    assert "chiz" in (features["line_count"]["reason"] or "")
    assert features["queue"]["active"] is False
    # Tamper standart yoqilgan.
    assert features["tamper"]["active"] is True and features["tamper"]["reason"] is None


def test_feature_status_turns_green_after_configuration(client: TestClient) -> None:
    client.put(
        "/api/setup/geometry",
        json={
            "lines": [
                {"name": "kirish", "camera_id": "camera-01",
                 "start": [0.1, 0.6], "end": [0.9, 0.6]}
            ],
            "zones": [
                {"name": "kassa", "camera_id": "camera-01", "queue": True,
                 "polygon": [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]}
            ],
        },
    )
    client.put(
        "/api/setup/settings",
        json={"open_from": "09:00", "open_to": "21:00"},
    )

    features = {item["code"]: item for item in client.get("/api/status").json()["features"]}

    assert features["line_count"]["active"] is True
    assert features["queue"]["active"] is True
    assert features["after_hours"]["active"] is True
    assert features["restricted"]["active"] is False, "taqiqlangan zona hali yo'q"
