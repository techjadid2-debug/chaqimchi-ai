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
    # `base_url` ataylab haqiqiy manzil: panel endi begona `Host` bilan
    # kelgan so'rovni rad etadi (DNS rebinding himoyasi), TestClient esa
    # sukut bo'yicha `testserver` yuboradi.
    return TestClient(app_module.app, base_url="http://127.0.0.1:8760")


def _config(tmp_path: Path) -> Dict[str, Any]:
    return yaml.safe_load((tmp_path / "config.yaml").read_text(encoding="utf-8"))


# ── Xavfsizlik: DNS rebinding ────────────────────────────────────────────


def test_foreign_host_header_is_refused(client: TestClient) -> None:
    """Zararli sahifa o'z domenini 127.0.0.1 ga qayta hal qilib panelga kira olmasin.

    `127.0.0.1` ga bog'lanish o'zi yetmaydi: DNS rebinding'dan keyin brauzer
    uchun hujumchi sahifasi panel bilan bir xil manba bo'lib qoladi.  O'shanda
    yagona farq — `Host` sarlavhasi, uni JavaScript o'zgartira olmaydi.
    """
    for host in ("evil.example", "evil.example:8760", "192.168.1.50:8760"):
        response = client.get("/api/setup/summary", headers={"Host": host})
        assert response.status_code == 403, host


def test_loopback_hosts_still_work(client: TestClient) -> None:
    """Halol yo'l yopilib qolmasin — mijoz `localhost` deb ham yozishi mumkin."""
    for host in ("127.0.0.1:8760", "localhost:8760"):
        response = client.get("/api/setup/summary", headers={"Host": host})
        assert response.status_code == 200, host


def test_panel_cannot_be_framed(client: TestClient) -> None:
    """Clickjacking: `Host` to'g'ri bo'lgani uchun yuqoridagi tekshiruv to'smaydi."""
    response = client.get("/")
    assert response.headers.get("X-Frame-Options") == "DENY"


# ── Sozlash oqimi ────────────────────────────────────────────────────────


def test_first_run_opens_the_status_page(client: TestClient) -> None:
    """Sozlash endi bulut panelida bo'ladi.

    Bu sahifa bitta savolga javob beradi — "boshqaruv panelim
    qayerda?".  Sehrgarni ochish esa mijozni shu kompyuter oldiga
    bog'lab qo'yardi, holbuki u kamerani telefonidan ham ulay oladi.
    """
    response = client.get("/")
    assert response.status_code == 200
    assert "Bugungi holat" in response.text
    assert "Kamerangizni ulaymiz" not in response.text


def test_the_local_pages_use_the_same_palette_as_the_cloud(client: TestClient) -> None:
    """Mijoz saytda ko'k sahifani ko'radi, dasturni o'rnatadi va shu
    yerda ham AYNAN o'sha rangni ko'rishi kerak.

    Eski krem/to'q-yashil palitra qaytib kelmasin: u bitta faylda
    yashaydi va bitta `git revert` bilan tiklanib qolishi mumkin edi.
    """
    css = (Path(__file__).resolve().parents[1] / "chaqimchi_ai/local/static/local.css").read_text(
        encoding="utf-8"
    )

    for old in ("#f3f0e8", "#173d2d", "#d9f55f", "#f26a3d", "#13231d", "#e7e4da"):
        assert old not in css, f"eski rang qaytib kelgan: {old}"
    # Nomlar bulut paneli bilan bir xil — ko'chirilgan qoida noto'g'ri
    # rangga tushib qolmasin.
    for token in ("--blue:", "--blue-dark:", "--text:", "--border:", "--paper-2:"):
        assert token in css, token


def test_the_status_page_answers_where_my_panel_is(client: TestClient) -> None:
    """Mijoz bu sahifaga bitta savol bilan keladi.  Javob — ulanish
    kartasi, va u aylantirmasdan ko'rinishi kerak."""
    body = client.get("/").text

    assert 'id="connectCard"' in body
    assert 'id="verifyCode"' in body
    # Sehrgar havolasi YO'QOLMAYDI — usta va internetsiz do'kon uchun.
    assert 'href="/setup"' in body
    # Ulanish kartasi statistikadan OLDIN turishi kerak.
    assert body.index('id="connectCard"') < body.index("Bugungi holat")


def test_expert_mode_still_serves_the_wizard(client: TestClient) -> None:
    """Internetsiz o'rnatilgan do'konda va usta uchun sehrgar yagona
    kafolatlangan yo'l — u O'CHIRILMAYDI, faqat brauzer uni o'zi
    ochmaydi."""
    response = client.get("/setup")
    assert response.status_code == 200
    assert "Kamerangizni ulaymiz" in response.text


def test_camera_is_actually_written_to_config(client: TestClient, tmp_path: Path) -> None:
    response = client.post(
        "/api/setup/cameras",
        json={
            "label": "Kirish eshigi",
            "rtsp_url": "rtsp://admin:pw@192.168.1.64:554/Streaming/channels/102",
        },
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
        json={
            "brand": "hikvision",
            "host": "192.168.1.64",
            "username": "admin",
            "password": "a@b/c",
            "channel": 2,
        },
    )
    url = response.json()["rtsp_url"]
    assert url == "rtsp://admin:a%40b%2Fc@192.168.1.64:554/Streaming/Channels/202"
    assert response.json()["safe_url"] == "rtsp://…@192.168.1.64:554/Streaming/Channels/202"


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
        json={
            "lines": [
                {"name": "Kirish", "camera_id": "camera-01", "start": [5.0, 5.0], "end": [9.0, 9.0]}
            ],
            "zones": [],
        },
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


def _seed_outbox(
    tmp_path: Path, events: list[Dict[str, Any]], *, sent: bool = False
) -> None:
    """Zanjir yozadigan navbatni taqlid qiladi (panel faqat o'qiydi).

    `sent=True` — hodisalar cloudga yuborilib bo'lingan holat.  Do'kon
    internetda bo'lsa navbat bir necha soniyada shu holatga o'tadi, ya'ni
    bu **oddiy** holat, istisno emas.
    """
    db = tmp_path / "data" / "outbox.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS outbox ("
        "event_id TEXT PRIMARY KEY, payload TEXT, created_at TEXT, "
        "priority INTEGER DEFAULT 0, sent_at TEXT)"
    )
    for index, event in enumerate(events):
        # `created_at` HAR DOIM UTC bo'lishi shart: navbatga yozadigan
        # `OutboxQueue.enqueue` aynan shunday yozadi va panel hisoboti
        # ustunni SATR sifatida solishtiradi.  Mahalliy siljish bilan
        # yozilsa (`+05:00`) test faqat UTC kompyuterda o'tardi —
        # Toshkentdagi ishlab chiqish mashinasida esa qizil bo'lardi.
        stored = datetime.fromisoformat(event["occurred_at"]).astimezone(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO outbox (event_id, payload, created_at, sent_at) VALUES (?,?,?,?)",
            (
                f"e{index}",
                json.dumps(event),
                stored,
                stored if sent else None,
            ),
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
            {
                "event_type": "line_crossed",
                "direction": "in",
                "camera_id": "camera-01",
                "occurred_at": now.isoformat(),
            },
            {
                "event_type": "line_crossed",
                "direction": "in",
                "camera_id": "camera-01",
                "occurred_at": now.isoformat(),
            },
            {
                "event_type": "line_crossed",
                "direction": "out",
                "camera_id": "camera-01",
                "occurred_at": now.isoformat(),
            },
            {
                "event_type": "line_crossed",
                "direction": "in",
                "camera_id": "camera-01",
                "occurred_at": yesterday.isoformat(),
            },
        ],
    )
    report = client.get("/api/report").json()
    assert report["date"] == now.date().isoformat()
    assert report["entered"] == 2
    assert report["exited"] == 1
    assert report["inside_estimate"] == 1


def test_report_still_counts_after_the_queue_was_uploaded(
    client: TestClient, tmp_path: Path
) -> None:
    """Ish stolidagi panelning bosh raqami — «Bugun kirdi».

    U navbatdan o'qiladi, cloudga yuborilgan hodisalar esa navbatdan
    o'chirilardi.  Do'kon internetda bo'lsa navbat har besh soniyada
    bo'shaydi — ya'ni raqam faqat internet **yo'q** paytda to'g'ri edi.
    Aynan teskarisi: mijoz uni har kuni ko'radi.
    """
    now = datetime.now().astimezone()
    _seed_outbox(
        tmp_path,
        [
            {
                "event_type": "line_crossed",
                "direction": "in",
                "camera_id": "camera-01",
                "occurred_at": now.isoformat(),
            }
            for _ in range(6)
        ],
        sent=True,
    )

    report = client.get("/api/report").json()

    assert report["entered"] == 6, "yuborilgan hodisalar ham hisobotda qolsin"


def test_report_does_not_truncate_a_busy_day(client: TestClient, tmp_path: Path) -> None:
    """Ilgari eng yangi 500 ta olinib, **keyin** bugungi kunga filtrlanardi.

    Gavjum do'konda kuniga mingdan ortiq hodisa bo'ladi — ertalabki
    kirishlar ro'yxat oxiridan tushib qolardi va panel kam ko'rsatardi.
    """
    now = datetime.now().astimezone().replace(hour=12, minute=0, second=0, microsecond=0)
    _seed_outbox(
        tmp_path,
        [
            {
                "event_type": "line_crossed",
                "direction": "in",
                "camera_id": "camera-01",
                "occurred_at": (now - timedelta(seconds=index)).isoformat(),
            }
            for index in range(700)
        ],
        sent=True,
    )

    report = client.get("/api/report").json()

    assert report["entered"] == 700


def test_events_endpoint_returns_the_newest_first_and_honours_the_limit(
    client: TestClient, tmp_path: Path
) -> None:
    """`/api/events` hech qanday test bilan qoplanmagandi — shu sabab
    `_read_events` imzosi o'zgarganda buzilishi sezilmasdi."""
    now = datetime.now().astimezone()
    _seed_outbox(
        tmp_path,
        [
            {
                "event_type": "line_crossed",
                "direction": "in",
                "camera_id": f"camera-{index:02d}",
                "occurred_at": (now - timedelta(minutes=index)).isoformat(),
            }
            for index in range(5)
        ],
        sent=True,
    )

    body = client.get("/api/events", params={"limit": 2}).json()

    assert len(body["events"]) == 2
    assert body["events"][0]["camera_id"] == "camera-00", "eng yangisi birinchi"


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
    assert paths.index("/Streaming/Channels/{ch}02") < paths.index("/Streaming/Channels/{ch}01")


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
    code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
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


def test_old_cameras_get_a_record_url_so_clips_start_working(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    """Yangilanishdan oldin saqlangan kameralar ham klip yoza olsin.

    `record_url` bo'lmasa kameraga halqa buferi berilmaydi
    (`retail/service.py`: `RingBuffer(...) if camera.record_url else None`),
    ya'ni `save_clip` qoidasi jimgina bajarilmaydi — hodisa ketadi,
    videosi esa yo'q.

    Yangi kamera qo'shilganda u 0.6.9 dan beri to'ldiriladi, lekin
    BUNGACHA saqlanganlar bo'sh qolardi.  Jonli do'konda aynan shu holat
    (2026-08-21): `camera_tampered` ikki marta chiqqan, klip NOL ta.
    """
    from chaqimchi_ai.local import app as app_module
    from chaqimchi_ai.local import config_store

    monkeypatch.setattr(
        app_module.camera_probe, "rtsp_describe", lambda url, timeout_sec=4.0: (200, "OK")
    )
    monkeypatch.setattr(app_module, "_record_url_backfilled", False)

    config_store.save_camera(
        camera_id="camera-01",
        stream_url="rtsp://u:p@10.0.0.5:554/Streaming/Channels/102",
        label="Kirish",
        record_url=None,
        priority="retail",
    )
    assert not config_store.cameras()[0].get("record_url")

    listed = client.get("/api/setup/cameras")
    assert listed.status_code == 200
    assert listed.json()["cameras"][0]["record_url_set"] is True

    stored = config_store.cameras()[0]["record_url"]
    assert "101" in stored, "substream asosiy oqimga o'girilsin"
    saved = yaml.safe_load((tmp_path / "config.yaml").read_text(encoding="utf-8"))
    assert saved["retail"]["cameras"][0].get("record_url"), (
        "to'ldirish faylga ham yozilsin — keyingi restartda ham tursin"
    )


def test_backfill_never_stores_an_unreachable_guess(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    """Tekshirilmagan taxmin yozilsa ffmpeg abadiy xato aylanardi.

    Bu qoida yangi kamera saqlashda allaqachon bor edi; to'ldirish ham
    unga bo'ysunishi shart.
    """
    from chaqimchi_ai.local import app as app_module
    from chaqimchi_ai.local import config_store

    monkeypatch.setattr(
        app_module.camera_probe, "rtsp_describe", lambda url, timeout_sec=4.0: (404, "Not Found")
    )
    monkeypatch.setattr(app_module, "_record_url_backfilled", False)

    config_store.save_camera(
        camera_id="camera-01",
        stream_url="rtsp://u:p@10.0.0.5:554/Streaming/Channels/102",
        label="Kirish",
        record_url=None,
        priority="retail",
    )
    client.get("/api/setup/cameras")
    assert config_store.cameras()[0].get("record_url") is None


def test_backfill_does_not_overwrite_a_url_the_customer_set(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    """Mijoz o'zi kiritgan manzil ustiga yozilmasin."""
    from chaqimchi_ai.local import app as app_module
    from chaqimchi_ai.local import config_store

    monkeypatch.setattr(app_module, "_record_url_backfilled", False)
    config_store.save_camera(
        camera_id="camera-01",
        stream_url="rtsp://u:p@10.0.0.5:554/Streaming/Channels/102",
        label="Kirish",
        record_url="rtsp://u:p@10.0.0.5:554/qolga/yozilgan",
        priority="retail",
    )
    client.get("/api/setup/cameras")
    assert config_store.cameras()[0]["record_url"].endswith("/qolga/yozilgan")


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


def test_explicit_record_url_wins_over_the_suggestion(client: TestClient, tmp_path: Path) -> None:
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
                {"name": "kirish", "camera_id": "camera-01", "start": [0.1, 0.6], "end": [0.9, 0.6]}
            ],
            "zones": [
                {
                    "name": "kassa",
                    "camera_id": "camera-01",
                    "queue": True,
                    "polygon": [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]],
                }
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


# ── NVR kanal skaneri: fon-ish + progress (0.6.6) ────────────────────────


def test_channel_scan_runs_in_the_background_with_progress(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Skaner endi sinxron emas: start → status polling.

    Ilgari yomon holatda so'rov o'nlab daqiqa osilib turardi va mijoz
    hech narsa ko'rmasdi.
    """
    import time as time_module

    from chaqimchi_ai.local import app as app_module

    channels = [
        {
            "channel": 1,
            "rtsp_url": "rtsp://admin:p@10.0.0.5:554/Streaming/Channels/102",
            "safe_url": "rtsp://…@10.0.0.5:554/Streaming/Channels/102",
            "width": 640,
            "height": 360,
        }
    ]
    monkeypatch.setattr(app_module, "_scan_via_onvif", lambda body, deadline: channels)
    monkeypatch.setattr(
        app_module,
        "_scan_via_templates",
        lambda body, deadline: (_ for _ in ()).throw(
            AssertionError("ONVIF topdi — zaxira kerak emas")
        ),
    )

    start = client.post(
        "/api/setup/scan-channels",
        json={"host": "10.0.0.5", "username": "admin", "password": "p"},
    )
    assert start.status_code == 200
    assert start.json()["started"] is True

    for _ in range(50):
        status = client.get("/api/setup/scan-channels/status").json()
        if not status["running"]:
            break
        time_module.sleep(0.1)
    assert status["running"] is False
    assert status["found"] == 1
    assert status["channels"][0]["channel"] == 1


def test_channel_scan_falls_back_to_templates_without_credentials(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Parolsiz ONVIF ishlamaydi — to'g'ri zaxira yo'lga o'tsin."""
    import time as time_module

    from chaqimchi_ai.local import app as app_module

    calls = {"onvif": 0}

    def fake_onvif(body, deadline):
        calls["onvif"] += 1
        return []

    monkeypatch.setattr(app_module, "_scan_via_onvif", fake_onvif)
    monkeypatch.setattr(app_module, "_scan_via_templates", lambda body, deadline: [])

    client.post("/api/setup/scan-channels", json={"host": "10.0.0.5"})
    for _ in range(50):
        status = client.get("/api/setup/scan-channels/status").json()
        if not status["running"]:
            break
        time_module.sleep(0.1)

    assert calls["onvif"] == 0, "parol yo'q — ONVIF sinalmasin"
    assert "tekshiring" in status["hint"]


def test_scan_response_carries_onvif_details(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Topilgan ONVIF port/xaddr UI'ga yetsin — so'rov doim 80 ga ketmasin."""
    from chaqimchi_ai import discovery

    async def fake_discover(timeout_sec=3.0):
        return [
            {
                "ip": "192.168.1.60",
                "vendor_hint": "NVR",
                "has_onvif": True,
                "onvif_port": 8899,
                "xaddrs": "http://192.168.1.60:8899/onvif/device_service",
                "suggested_urls": [],
            }
        ]

    monkeypatch.setattr(discovery, "discover_cameras_all", fake_discover)

    data = client.post("/api/setup/scan").json()

    assert data["devices"][0]["onvif_port"] == 8899
    assert "8899" in data["devices"][0]["xaddrs"]


# ── Ikkinchi nusxa ──────────────────────────────────────────────────────
#
# Nazorat endi kompyuter yonganda avtomatik vazifa orqali ishga tushadi
# (SYSTEM nomidan, ko'rinmas holda).  Mijoz keyin ish stolidagi yorliqni
# bosadi — bungacha ikkinchi nusxa "port band" xatosi bilan yiqilib,
# oynada Python traceback ko'rsatardi.


def test_the_port_is_reserved_before_anything_else_starts() -> None:
    import socket

    from chaqimchi_ai.local import app as app_module

    taken = socket.socket()
    taken.bind(("127.0.0.1", 0))
    taken.listen(1)
    port = taken.getsockname()[1]
    try:
        assert app_module._reserve_panel_port(port=port) is None, (
            "band port ikkinchi nusxaga berilmasin"
        )
    finally:
        taken.close()

    mine = app_module._reserve_panel_port(port=port)
    assert mine is not None, "bo'sh port egallanishi kerak"
    try:
        # Endi u haqiqatan band: ikkinchi urinish None qaytaradi.
        assert app_module._reserve_panel_port(port=port) is None
    finally:
        mine.close()


def test_second_copy_opens_the_panel_instead_of_crashing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from chaqimchi_ai.local import app as app_module

    # Log fayli haqiqiy uy katalogiga yozilmasin.
    monkeypatch.setenv("CHAQIMCHI_LOCAL_DIR", str(tmp_path))
    opened: list[str] = []
    started: list[str] = []
    monkeypatch.setattr(app_module, "_reserve_panel_port", lambda *a, **k: None)
    monkeypatch.setattr(
        app_module, "webbrowser", type("W", (), {"open": staticmethod(opened.append)})
    )
    monkeypatch.setattr(app_module, "_write_alive", lambda *a, **k: started.append("alive"))
    monkeypatch.delenv("CHAQIMCHI_LOCAL_NO_BROWSER", raising=False)

    app_module.main()

    assert opened, "ishlab turgan nusxaning paneli ochilishi kerak"
    assert not started, "ikkinchi nusxa holat belgisiga tegmasin"


def test_service_launcher_does_not_open_a_browser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Avtostart vazifasi SYSTEM nomidan ishlaydi — u yerdagi brauzerni
    hech kim ko'rmaydi, jarayon esa osilib qoladi."""
    from chaqimchi_ai.local import app as app_module

    monkeypatch.setenv("CHAQIMCHI_LOCAL_NO_BROWSER", "1")
    assert app_module._browser_enabled() is False
    monkeypatch.setenv("CHAQIMCHI_LOCAL_NO_BROWSER", "0")
    assert app_module._browser_enabled() is True


# ── O'tgan kun hisoboti ─────────────────────────────────────────────────
#
# 72 soatlik barqarorlik sinovida kunlik son qo'lda sanash bilan
# solishtiriladi.  Bungacha hisobot faqat "hozir" ni bilardi — uchinchi
# kuni birinchi kunning raqamini olishning iloji yo'q edi.


def test_report_can_look_back_at_an_earlier_day(client: TestClient, tmp_path: Path) -> None:
    now = datetime.now().astimezone()
    yesterday = now - timedelta(days=1)
    _seed_outbox(
        tmp_path,
        [
            {
                "event_type": "line_crossed",
                "direction": "in",
                "camera_id": "camera-01",
                "occurred_at": yesterday.isoformat(),
            },
            {
                "event_type": "line_crossed",
                "direction": "in",
                "camera_id": "camera-01",
                "occurred_at": yesterday.isoformat(),
            },
            {
                "event_type": "line_crossed",
                "direction": "in",
                "camera_id": "camera-01",
                "occurred_at": now.isoformat(),
            },
        ],
    )

    kecha = client.get(f"/api/report?date={yesterday.date().isoformat()}").json()

    assert kecha["date"] == yesterday.date().isoformat()
    assert kecha["entered"] == 2, "faqat o'sha kunning hodisalari sanalsin"

    bugun = client.get("/api/report").json()
    assert bugun["entered"] == 1, "bugungi hisobot o'zgarmasin"


def test_a_broken_date_is_refused_clearly(client: TestClient) -> None:
    assert client.get("/api/report?date=kecha").status_code == 422
    assert client.get("/api/report?date=2026-13-40").status_code == 422


def test_a_future_day_has_no_report(client: TestClient) -> None:
    tomorrow = (datetime.now().astimezone() + timedelta(days=1)).date()
    assert client.get(f"/api/report?date={tomorrow.isoformat()}").status_code == 422


# ── Tarifdagi kamera chegarasi ──────────────────────────────────────────


def test_the_wizard_honours_the_camera_limit_sent_by_the_cloud(
    client: TestClient, tmp_path: Path
) -> None:
    """Boshlang'ich tarifidagi mijozga uchinchi kamera taklif qilinmasin.

    Bungacha chegara modul darajasidagi doimiy edi va HAR DOIM 4 qaytardi:
    2 kameralik tarifni sotgan bo'lsak ham sehrgar to'rttasini qabul
    qilardi va mijoz farqni hech qachon sezmasdi.
    """
    from chaqimchi_ai.local import cloud_config

    cloud_config.apply({"product": {"max_cameras": 2}, "cameras": [], "config": {}})

    assert client.get("/api/setup/summary").json()["max_cameras"] == 2

    for index in (1, 2):
        response = client.post(
            "/api/setup/cameras",
            json={"camera_id": "", "rtsp_url": f"rtsp://10.0.0.{index}/1", "label": f"K{index}"},
        )
        assert response.status_code == 200, response.text

    third = client.post(
        "/api/setup/cameras",
        json={"camera_id": "", "rtsp_url": "rtsp://10.0.0.3/1", "label": "K3"},
    )
    assert third.status_code == 422
    assert "2 kamera" in third.json()["detail"]


def test_a_broken_cloud_limit_cannot_raise_the_hardware_cap(client: TestClient) -> None:
    """Cloud noto'g'ri qiymat yuborsa ham apparat chegarasi buzilmasin.

    Sig'im o'lchangan: i5-4590 da to'rt yadroning bittasi RTSP dekodlashga
    ketadi.  Cloud xatosi sabab 8 kamera ochilsa do'kon sekinlashadi va
    sababi hech qayerda ko'rinmaydi.
    """
    from chaqimchi_ai.limits import SHOP_MAX_CAMERAS
    from chaqimchi_ai.local import cloud_config

    cloud_config.apply({"product": {"max_cameras": 99}, "cameras": [], "config": {}})

    assert client.get("/api/setup/summary").json()["max_cameras"] == SHOP_MAX_CAMERAS


def test_an_offline_device_keeps_the_hardware_limit(client: TestClient) -> None:
    """Cloud hali gapirmagan qurilma ishlashda davom etsin."""
    from chaqimchi_ai.limits import SHOP_MAX_CAMERAS

    assert client.get("/api/setup/summary").json()["max_cameras"] == SHOP_MAX_CAMERAS


# ── Panel kamera holati ─────────────────────────────────────────────────


def test_status_keeps_camera_health_and_names_apart(
    client: TestClient, tmp_path: Path
) -> None:
    """Ikki xil "cameras" bir-birini yutmasin.

    `supervisor.status()` sog'liq LUG'ATINI beradi, `config_store.summary()`
    esa nom RO'YXATINI.  Ikkalasi bitta kalitda edi va ro'yxat sog'liqni
    ustidan yozardi — panel har kamerani qizil nuqta bilan "javob
    bermayapti" deb ko'rsatar, nom o'rniga `0`, `1` chiqarardi.
    """
    import json
    import time

    from chaqimchi_ai.local import paths

    client.post(
        "/api/setup/cameras",
        json={"camera_id": "camera-01", "label": "Kirish", "rtsp_url": "rtsp://10.0.0.5/1"},
    )
    client.post(
        "/api/setup/cameras",
        json={"camera_id": "camera-02", "label": "Kassa", "rtsp_url": "rtsp://10.0.0.6/1"},
    )
    paths.status_path().write_text(
        json.dumps(
            {
                "updated_at": time.time(),
                "cameras_configured": 2,
                "cameras_active": 1,
                "cameras": {
                    "camera-01": {"connected": True, "offline": False, "frames": 10},
                    "camera-02": {"connected": False, "offline": True, "frames": 0},
                },
            }
        ),
        encoding="utf-8",
    )

    data = client.get("/api/status").json()

    assert data["cameras"]["camera-01"]["connected"] is True
    assert data["cameras"]["camera-02"]["offline"] is True
    assert [item["label"] for item in data["cameras_list"]] == ["Kirish", "Kassa"]
    # "2 kameradan 1 tasi ulangan" — maxraj sozlamadagi kameralar soni.
    assert data["cameras_configured"] == 2
    assert data["cameras_active"] == 1


def test_status_counts_cameras_even_when_the_chain_is_down(client: TestClient) -> None:
    """Zanjir to'xtaganda ham "0/0" emas, "2 kameradan 0 tasi" ko'rinsin."""
    client.post(
        "/api/setup/cameras",
        json={"camera_id": "camera-01", "label": "Kirish", "rtsp_url": "rtsp://10.0.0.5/1"},
    )
    client.post(
        "/api/setup/cameras",
        json={"camera_id": "camera-02", "label": "Kassa", "rtsp_url": "rtsp://10.0.0.6/1"},
    )

    data = client.get("/api/status").json()

    assert data["cameras_configured"] == 2
    assert data["cameras_active"] == 0


def test_camera_codec_is_remembered(client: TestClient, tmp_path: Path) -> None:
    """ONVIF aniqlagan format saqlansin — diagnostika uchun."""
    client.post(
        "/api/setup/cameras",
        json={
            "camera_id": "camera-01",
            "label": "Kirish",
            "rtsp_url": "rtsp://10.0.0.5/1",
            "codec": "h265",
        },
    )

    saved = client.get("/api/setup/cameras").json()["cameras"][0]
    assert saved["codec"] == "H265"


def test_the_second_copy_is_refused_on_windows_too() -> None:
    """Ikkinchi nusxa portni TORTIB OLMASIN.

    `SO_REUSEADDR` Windows'da POSIX'dagidan boshqacha ishlaydi: u ikkinchi
    jarayonga band portni egallashga RUXSAT beradi.  Shu sabab "bitta
    nusxa" qo'riqchisi aynan asosiy platformada ishlamasdi va do'konda
    0.6.9 ga yangilangandan keyin ikkita dastur birga ishlab, bitta
    kamerani ikkalasi o'qidi.

    Test kodni o'qiydi: haqiqiy xatti-harakatni faqat Windows'da
    tekshirib bo'ladi, lekin bayroq tanlovini shu yerda qulflash mumkin.
    """
    from pathlib import Path as _Path

    source = (_Path(__file__).resolve().parents[1] / "chaqimchi_ai/local/app.py").read_text(
        encoding="utf-8"
    )
    guard = source.split("def _reserve_panel_port")[1].split("def ")[0]

    assert "SO_EXCLUSIVEADDRUSE" in guard, "Windows uchun eksklyuziv bayroq shart"
    assert 'if os.name == "nt"' in guard, "bayroq faqat Windows'da qo'yiladi"
    # POSIX'da `SO_REUSEADDR` KERAK: usiz qayta ishga tushirishda
    # `TIME_WAIT` sabab port bir necha daqiqa band bo'lib turardi.
    assert "SO_REUSEADDR" in guard


def test_only_one_panel_can_bind_the_port(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Bitta nusxa qoidasi: ikkinchi `bind` `None` qaytarsin."""
    import importlib

    monkeypatch.setenv("CHAQIMCHI_LOCAL_DIR", str(tmp_path))
    from chaqimchi_ai.local import app as app_module

    importlib.reload(app_module)

    first = app_module._reserve_panel_port(8791)
    assert first is not None
    try:
        assert app_module._reserve_panel_port(8791) is None
    finally:
        first.close()


# ── Ish vaqti o'zgarsa zanjir qayta ishga tushsin ────────────────────────
#
# Bag tarixi: `save_store_hours()` yangi soatni faylga yozardi, lekin
# `changed` lug'atida "hours" kaliti YO'Q edi.  Natijada `sync_once()`
# `None` qaytarardi va zanjir qayta ishga tushmasdi.  Zanjir esa ish
# vaqtini FAQAT startda o'qiydi (`retail/service.py`: `build_runner`).
#
# Oqibati jonli do'konda: panelda 08:30-22:00 turardi, qurilma esa uni
# hech qachon ko'rmadi va "ish vaqtidan tashqari harakat" bir marta ham
# chiqmadi — tunda 48 ta hodisa bo'lgan bo'lsa ham.


def test_ish_vaqti_ozgarishi_sezib_qolinadi(client: TestClient, tmp_path: Path) -> None:
    """Yangi ish vaqti kelsa `changed["hours"]` rost bo'lsin."""
    from chaqimchi_ai.local import cloud_config

    # Ish vaqti `config` kalitida keladi (`cloud_config.py`: `site =
    # payload.get("config")`), alohida `site` blokida emas.
    payload = {
        "product": {"max_cameras": 4},
        "cameras": [],
        "config": {"open_from": "08:30", "open_to": "22:00"},
    }
    first = cloud_config.apply(payload)
    assert first["hours"] is True, "birinchi marta kelgan soat o'zgarish hisoblanadi"

    # Ikkinchi marta o'sha soat — qayta ishga tushirishga hojat yo'q.
    again = cloud_config.apply(payload)
    assert again["hours"] is False, "o'zgarmagan soat zanjirni qayta yoqmasin"

    # Endi haqiqiy o'zgarish.
    payload["config"]["open_to"] = "23:00"
    third = cloud_config.apply(payload)
    assert third["hours"] is True, "yangi yopilish vaqti sezilishi shart"

    saved = yaml.safe_load((tmp_path / "config.yaml").read_text(encoding="utf-8"))
    assert saved["retail"]["open_to"] == "23:00"


def test_ish_vaqti_ozgarsa_zanjir_qayta_yoqiladi() -> None:
    """Sinxronizatsiya sikli soat o'zgarishini ham hisobga olsin.

    Bungacha shart faqat `applied.get("cameras")` edi.
    """
    source = (
        Path(__file__).resolve().parents[1] / "chaqimchi_ai" / "local" / "app.py"
    ).read_text(encoding="utf-8")
    assert 'applied.get("cameras") or applied.get("hours")' in source, (
        "ish vaqti o'zgarganda zanjir qayta ishga tushmaydi — "
        "paneldagi maydon jonli qurilmada ishlamay qoladi"
    )
