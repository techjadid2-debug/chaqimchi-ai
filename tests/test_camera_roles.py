"""Kamera rollari — rol SAQLANADI, O'QILADI va xatti-harakatni boshqaradi.

Tarixiy fon: sayt-konfigdagi `camera_roles` 2026-08-22 da o'chirilgan —
uni hech kim o'qimasdi va UI'da bo'sh variant yo'qligidan hamma kamera
jimgina "Kirish" bo'lib qolardi.  Yangi rol per-kamera maydon:
sehrgar → config.yaml → bulut (`site_cameras.role`) → edge config →
`CameraPlan.role` → zanjir.  Bu testlar aynan o'sha eski xatolar
qaytmasligini qulflaydi:

* taklif dvigateli signal bo'lmaganda JIM turadi (taxmin qilmaydi);
* eski (rolni bilmaydigan) qurilma bulutdagi rolni O'CHIRMAYDI;
* «kirish» roli davomat kamerasiga faqat O'TISHDA aylanadi — ega
  keyin olib tashlasa qayta urilmaydi;
* rol berilgan-u geometriya chizilmagan kamera BALAND aytiladi.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest
import yaml
from fastapi.testclient import TestClient

from chaqimchi_ai.camera_roles import RoleCandidate, suggest_role, suggest_roles
from cloud.store import CloudStore

SUB = "rtsp://admin:maxfiy@192.168.1.64:554/Streaming/Channels/102"
MAIN = "rtsp://admin:maxfiy@192.168.1.64:554/Streaming/Channels/101"


# ── Taklif dvigateli (sof mantiq) ────────────────────────────────────────


def test_a_named_channel_gets_its_role() -> None:
    """NVR kanal nomi — eng kuchli halol signal (uz/ru/en)."""
    cases = {
        "Kirish eshigi": "entrance",
        "КАССА 1": "checkout",
        "Savdo zali": "sales",
        "sklad": "storage",
    }
    for name, expected in cases.items():
        suggestion = suggest_role(RoleCandidate(camera_id="c", name=name, height=720))
        assert suggestion.suggested_role == expected, name


def test_a_low_res_camera_is_never_suggested_as_entrance() -> None:
    """352x288 oqimda yuz o'qib bo'lmaydi (`face_min_bbox_ratio` 0.95).

    Bunday kamera "Kirish" deb nomlangan bo'lsa ham taklif BOSILADI:
    davomat unda printsipial ishlamaydi va mijoz "Face ID buzilgan"
    deb o'ylardi.  Sababi javobda aytiladi.
    """
    suggestion = suggest_role(
        RoleCandidate(camera_id="c2", name="Kirish eshigi", width=352, height=288)
    )
    assert suggestion.suggested_role != "entrance"
    assert suggestion.face_id_ok is False
    assert any("yetarli emas" in reason for reason in suggestion.reasons)


def test_no_signal_means_no_suggestion_and_never_uniform() -> None:
    """2026-08-22 saboqning qulfi: signal yo'q — taklif YO'Q.

    Eski xato aynan "hammasi jimgina bitta rol bo'lib qoldi" edi.
    """
    suggestions = suggest_roles(
        [RoleCandidate(camera_id=f"c{i}") for i in range(4)]
    )
    assert all(item.suggested_role is None for item in suggestions)
    assert any("o'zingiz tanlang" in " ".join(item.reasons) for item in suggestions)


def test_an_ambiguous_name_gets_no_suggestion() -> None:
    """Ikki rol teng ball olsa tanlovni ODAM qiladi."""
    suggestion = suggest_role(
        RoleCandidate(camera_id="c", name="kassa zal", height=720)
    )
    assert suggestion.suggested_role is None


def test_more_than_limit_marks_the_best_four() -> None:
    """8 kanaldan 4 tasi belgilanadi: kirish va kassa albatta ichida.

    Ishlamaydigan va past sifatli kameralar tanlovdan chetda qoladi —
    chetda qolganiga sabab yoziladi.
    """
    candidates = [
        RoleCandidate(camera_id="1", name="Kirish", height=720),
        RoleCandidate(camera_id="2", name="Kassa", height=480),
        RoleCandidate(camera_id="3", height=720),
        RoleCandidate(camera_id="4", height=480),
        RoleCandidate(camera_id="5", height=288),
        RoleCandidate(camera_id="6", height=1080, works=False),
        RoleCandidate(camera_id="7", height=360),
        RoleCandidate(camera_id="8", height=240),
    ]
    suggestions = {item.camera_id: item for item in suggest_roles(candidates, limit=4)}

    kept = [key for key, item in suggestions.items() if item.keep]
    assert len(kept) == 4
    assert "1" in kept, "ishonchli kirish tanlovdan tushib qoldi"
    assert "2" in kept, "ishonchli kassa tanlovdan tushib qoldi"
    assert "6" not in kept, "ishlamaydigan kamera ishlaydiganini siqib chiqardi"
    assert not suggestions["8"].keep
    assert any("tanlovdan tashqarida" in reason for reason in suggestions["8"].reasons)


def test_under_the_limit_everything_is_kept() -> None:
    suggestions = suggest_roles([RoleCandidate(camera_id="1"), RoleCandidate(camera_id="2")])
    assert all(item.keep for item in suggestions)


# ── Bulut ombori: rol saqlanadi, eski qurilma uni o'chirmaydi ────────────


@pytest.fixture
def store(tmp_path: Path) -> CloudStore:
    return CloudStore(tmp_path / "cloud.db")


def _site(store: CloudStore) -> str:
    return store.create_site("Do'kon", plan="biznes")["site_id"]


def test_the_device_role_is_stored_and_listed(store: CloudStore) -> None:
    site_id = _site(store)
    store.register_device_cameras(
        site_id,
        [{"camera_id": "camera-01", "label": "Kirish", "source": SUB, "role": "entrance"}],
    )
    assert store.list_cameras(site_id)[0]["role"] == "entrance"


def test_an_old_device_does_not_wipe_the_role(store: CloudStore) -> None:
    """Manzil uchun bor bo'lgan no-wipe qoida rolga ham tegishli.

    Eski (0.6.25 va undan oldingi) qurilma `role` yubormaydi — bo'sh
    satr "bilmayman" degani, "o'chir" degani emas.
    """
    site_id = _site(store)
    store.register_device_cameras(
        site_id, [{"camera_id": "camera-01", "source": SUB, "role": "entrance"}]
    )

    store.register_device_cameras(site_id, [{"camera_id": "camera-01", "label": "Kirish"}])

    assert store.list_cameras(site_id)[0]["role"] == "entrance"


def test_an_explicit_none_clears_the_role(store: CloudStore) -> None:
    """`none` — ochiq "tanlanmagan": sehrgarda rol olib tashlansa bulutga yetsin."""
    site_id = _site(store)
    store.register_device_cameras(
        site_id, [{"camera_id": "camera-01", "source": SUB, "role": "entrance"}]
    )

    store.register_device_cameras(
        site_id, [{"camera_id": "camera-01", "source": SUB, "role": "none"}]
    )

    assert store.list_cameras(site_id)[0]["role"] == "none"


def test_an_invalid_role_is_rejected_loudly(store: CloudStore) -> None:
    """Yaroqsiz qiymat JIM yutilmaydi (`CHAQIMCHI_AVAILABLE_FEATURES` saboqi)."""
    site_id = _site(store)
    with pytest.raises(ValueError):
        store.register_device_cameras(
            site_id, [{"camera_id": "camera-01", "source": SUB, "role": "vip-zona"}]
        )
    with pytest.raises(ValueError):
        store.upsert_camera(
            site_id, "camera-01", label="K", rtsp_url=SUB, role="vip-zona"
        )


def test_a_panel_save_without_a_role_keeps_the_stored_one(store: CloudStore) -> None:
    """Panel rol maydonisiz saqlasa (eski forma) rol yo'qolmasin."""
    site_id = _site(store)
    store.upsert_camera(site_id, "camera-01", label="Kirish", rtsp_url=SUB, role="entrance")

    store.upsert_camera(site_id, "camera-01", label="Kirish 2", rtsp_url=SUB)

    assert store.list_cameras(site_id)[0]["role"] == "entrance"


# ── Qurilmaga qaytish: CameraPlan va prioritet hosilasi ──────────────────


def test_the_role_reaches_the_camera_plan_with_its_priority() -> None:
    """Qayta o'rnatilgan kompyuter (lokal sozlama bo'sh): rol bulutdan
    keladi va prioritetni O'ZI beradi — «kirish» haqiqiy `security`
    navbatiga aylanadi."""
    from chaqimchi_ai.retail.inventory import InventoryCamera, merge_cameras

    plans = merge_cameras(
        [InventoryCamera(camera_id="camera-01", source=SUB, role="entrance")], []
    )

    assert plans[0].role == "entrance"
    assert plans[0].priority == "security"


def test_the_local_priority_still_wins_over_the_role_default() -> None:
    """Usta/support lokal kiritgan prioritet roldan ustun."""
    from chaqimchi_ai.retail.inventory import InventoryCamera, merge_cameras

    class LocalCamera:
        id = "camera-01"
        stream_url = SUB
        record_url = None
        priority = "background"
        sample_fps = 5.0
        floor_fps = None
        role = None

    plans = merge_cameras(
        [InventoryCamera(camera_id="camera-01", source=SUB, role="entrance")],
        [LocalCamera()],
    )

    assert plans[0].priority == "background"
    assert plans[0].role == "entrance"


def test_the_cache_reader_parses_the_role(tmp_path: Path) -> None:
    import json

    from chaqimchi_ai.retail.inventory import read_sotqin_cache

    path = tmp_path / "sotqin-config.json"
    path.write_text(
        json.dumps(
            {"cameras": [{"camera_id": "camera-01", "source": SUB, "role": "checkout"}]}
        ),
        encoding="utf-8",
    )

    assert read_sotqin_cache(path)["cameras"][0].role == "checkout"


# ── Davomat avto-yozuvi (bulut API orqali) ───────────────────────────────


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("CHAQIMCHI_CLOUD_ADMIN_KEY", "test-admin")
    monkeypatch.setenv("CHAQIMCHI_OWNER_JWT_SECRET", "o" * 64)
    monkeypatch.setenv("CHAQIMCHI_PORTAL_JWT_SECRET", "p" * 64)
    monkeypatch.setenv("CHAQIMCHI_PUBLIC_URL", "https://chaqimchi.test")
    monkeypatch.setattr("cloud.main.DB_PATH", tmp_path / "cloud.db")
    monkeypatch.setattr("cloud.main._store", None)
    monkeypatch.setattr("cloud.main._event_store", None)
    monkeypatch.setattr("cloud.main._event_store_key", None)
    from cloud.main import app

    return TestClient(app)


@pytest.fixture
def shop(client: TestClient) -> Dict[str, Any]:
    trial = client.post(
        "/api/v1/public/quick-trial",
        json={
            "phone": "+998 90 123 45 67",
            "full_name": "Ega Egayev",
            "company": "Namuna do'kon",
            "username": "dokonchi",
            "password": "parol12345",
            "consent": True,
            "plan": "biznes",
        },
    ).json()
    login = client.post(
        "/api/v1/auth/login", json={"username": "dokonchi", "password": "parol12345"}
    ).json()
    claimed = client.post(
        "/api/v1/devices/claim",
        json={"pairing_code": trial["pairing_code"], "label": "KASSA-PC"},
    ).json()
    return {
        "site_id": trial["site_id"],
        "owner": {"Authorization": f"Bearer {login['access_token']}"},
        "device": {
            "X-Site-Id": claimed["site_id"],
            "X-Device-Id": claimed["device_id"],
            "X-Device-Token": claimed["device_token"],
        },
    }


def _attendance_ids(client: TestClient, shop: Dict[str, Any]) -> list:
    config = client.get("/api/v1/owner/config", headers=shop["owner"]).json()["config"]
    return list(config.get("attendance_camera_ids") or [])


def test_an_entrance_role_enrolls_the_camera_for_attendance(
    client: TestClient, shop: Dict[str, Any]
) -> None:
    """Ega qarori (2026-08-30): «kirish» tasdiqlandi — davomat kamerasi ham shu."""
    response = client.post(
        "/api/v1/edge/cameras",
        headers=shop["device"],
        json={
            "cameras": [
                {"camera_id": "camera-01", "label": "Kirish", "source": SUB, "role": "entrance"}
            ]
        },
    )
    assert response.status_code == 200

    assert _attendance_ids(client, shop) == ["camera-01"]


def test_the_owner_removal_is_not_fought_by_a_republish(
    client: TestClient, shop: Dict[str, Any]
) -> None:
    """Avto-yozuv faqat O'TISHDA: qurilma o'sha rolni qayta e'lon qilsa
    ega olib tashlagan kamera qaytib qo'shilmaydi."""
    payload = {
        "cameras": [
            {"camera_id": "camera-01", "label": "Kirish", "source": SUB, "role": "entrance"}
        ]
    }
    client.post("/api/v1/edge/cameras", headers=shop["device"], json=payload)
    assert _attendance_ids(client, shop) == ["camera-01"]

    # Ega davomatdan olib tashladi (panel shu store yo'lini ishlatadi).
    from cloud import main

    config = dict(main.get_event_store().get_site_config(shop["site_id"])["config"])
    config["attendance_camera_ids"] = []
    main.get_event_store().update_site_config(shop["site_id"], config)

    # Qurilma har 20 soniyada ro'yxatini qayta e'lon qiladi — rol o'sha-o'sha.
    client.post("/api/v1/edge/cameras", headers=shop["device"], json=payload)

    assert _attendance_ids(client, shop) == [], "ega qarori avto-yozuv bilan urishdi"


def test_the_attendance_cap_of_two_is_respected(
    client: TestClient, shop: Dict[str, Any]
) -> None:
    """Uchinchi «kirish» kamerasi chegarani buzmaydi (DOKON_MVP: 2 ta)."""
    client.post(
        "/api/v1/edge/cameras",
        headers=shop["device"],
        json={
            "cameras": [
                {"camera_id": "camera-01", "source": SUB, "role": "entrance"},
                {"camera_id": "camera-02", "source": SUB, "role": "entrance"},
                {"camera_id": "camera-03", "source": SUB, "role": "entrance"},
            ]
        },
    )

    ids = _attendance_ids(client, shop)
    assert len(ids) == 2
    assert ids == ["camera-01", "camera-02"], "tartib deterministik bo'lsin"


def test_the_scan_view_carries_role_suggestions(
    client: TestClient, shop: Dict[str, Any]
) -> None:
    """Bulut paneli skan natijasida tayyor taklifni ko'radi —
    qo'shimcha qurilma so'rovisiz."""
    client.post("/api/v1/owner/scan", headers=shop["owner"], json={"kind": "onvif"})
    beat = client.post("/api/v1/edge/heartbeat", headers=shop["device"], json={}).json()
    job_id = beat["job_requested"][0]["job_id"]
    client.put(
        f"/api/v1/edge/jobs/{job_id}/result",
        headers=shop["device"],
        json={
            "ok": True,
            "result": {
                "streams": [
                    {"uri": SUB, "name": "Kassa", "width": 1280, "height": 720},
                    {"uri": SUB, "name": "", "width": 0, "height": 0},
                ]
            },
        },
    )

    job = client.get(f"/api/v1/owner/scan/{job_id}", headers=shop["owner"]).json()["job"]
    streams = job["result"]["streams"]

    assert streams[0]["suggested_role"] == "checkout"
    assert streams[0]["face_id_ok"] is True
    assert streams[1]["suggested_role"] == "", "signalsiz taklif bo'lmasin"
    assert "uri" not in streams[0], "to'liq manzil panelga chiqib ketdi"


# ── Rol-geometriya nomuvofiqligi baland aytiladi ─────────────────────────


def test_role_problems_flag_missing_geometry() -> None:
    from cloud.config_health import role_problems

    problems = role_problems(
        [
            {"camera_id": "camera-01", "label": "Kirish", "role": "entrance"},
            {"camera_id": "camera-02", "label": "Kassa", "role": "checkout"},
            {"camera_id": "camera-03", "label": "Zal", "role": "sales"},
        ],
        {"lines": [], "zones": []},
    )

    by_camera = {item["camera_id"]: item for item in problems}
    assert "camera-01" in by_camera, "chiziqsiz kirish roli jim qoldi"
    assert "camera-02" in by_camera, "navbat zonasisiz kassa roli jim qoldi"
    assert "camera-03" not in by_camera, "savdo zali roliga geometriya majburiy emas"


def test_role_problems_stay_silent_when_geometry_exists() -> None:
    from cloud.config_health import role_problems

    problems = role_problems(
        [{"camera_id": "camera-01", "label": "Kirish", "role": "entrance", "height": 720}],
        {
            "lines": [{"camera_id": "camera-01", "start": [0.2, 0.5], "end": [0.8, 0.5]}],
            "zones": [],
        },
    )
    assert problems == []


def test_role_problems_report_a_low_res_entrance() -> None:
    """352x288 oqimli «kirish» — davomat printsipial ishlamaydi, aytilsin."""
    from cloud.config_health import role_problems

    problems = role_problems(
        [{"camera_id": "camera-02", "label": "Kirish", "role": "entrance", "height": 288}],
        {"lines": [{"camera_id": "camera-02", "start": [0.2, 0.5], "end": [0.8, 0.5]}]},
    )
    assert len(problems) == 1
    assert "yetarli emas" in problems[0]["problem"]


# ── Lokal sehrgar: rol yozildi, backfill uni o'chirmaydi ─────────────────


@pytest.fixture
def local_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("CHAQIMCHI_LOCAL_DIR", str(tmp_path))
    import importlib

    from chaqimchi_ai.local import app as app_module
    from chaqimchi_ai.local import config_store, paths, supervisor

    importlib.reload(paths)
    importlib.reload(config_store)
    importlib.reload(supervisor)
    importlib.reload(app_module)
    return TestClient(app_module.app, base_url="http://127.0.0.1:8760")


def _local_config(tmp_path: Path) -> Dict[str, Any]:
    return yaml.safe_load((tmp_path / "config.yaml").read_text(encoding="utf-8"))


def test_the_wizard_role_is_actually_written_to_config(
    local_client: TestClient, tmp_path: Path
) -> None:
    """Eski sehrgar rolni nom+prioritetga aylantirib TASHLAB yuborardi."""
    response = local_client.post(
        "/api/setup/cameras",
        json={
            "label": "Kirish",
            "rtsp_url": SUB,
            "record_url": MAIN,
            "priority": "security",
            "role": "entrance",
        },
    )
    assert response.status_code == 200

    cameras = _local_config(tmp_path)["retail"]["cameras"]
    assert cameras[0]["role"] == "entrance"
    listed = local_client.get("/api/setup/cameras").json()["cameras"]
    assert listed[0]["role"] == "entrance"


def test_an_unknown_role_is_rejected_by_the_wizard(local_client: TestClient) -> None:
    response = local_client.post(
        "/api/setup/cameras",
        json={"label": "K", "rtsp_url": SUB, "record_url": MAIN, "role": "vip"},
    )
    assert response.status_code == 422


def test_the_record_url_backfill_preserves_the_role(
    local_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`save_camera` yozuvni NOLDAN quradi — backfill rolni uzatmasa u
    jimgina o'chib ketardi.  Bu regressiya testi o'sha tuzoqni qulflaydi."""
    from chaqimchi_ai.local import app as app_module
    from chaqimchi_ai.local import config_store

    config_store.save_camera(
        camera_id="camera-01",
        stream_url=SUB,
        label="Kirish",
        record_url=None,  # backfill ishga tushishi uchun bo'sh
        priority="security",
        role="entrance",
    )
    monkeypatch.setattr(app_module, "_verified_record_url", lambda stream: MAIN)

    # Ro'yxat so'rovi backfill'ni yurgizadi.
    local_client.get("/api/setup/cameras")

    camera = _local_config(tmp_path)["retail"]["cameras"][0]
    assert camera["record_url"] == MAIN, "backfill ishlamadi — test sharti buzilgan"
    assert camera.get("role") == "entrance", "backfill rolni o'chirib yubordi"


def test_the_local_suggestion_endpoint_contract(local_client: TestClient) -> None:
    response = local_client.post(
        "/api/setup/role-suggestions",
        json={
            "items": [
                {"ref": "1", "name": "Kirish", "width": 1280, "height": 720},
                {"ref": "2", "name": "", "width": 0, "height": 0},
            ]
        },
    )
    assert response.status_code == 200
    payload = response.json()
    by_ref = {item["ref"]: item for item in payload["suggestions"]}

    assert by_ref["1"]["role"] == "entrance"
    assert by_ref["1"]["label"] == "Kirish eshigi"
    assert by_ref["2"]["role"] == "", "signalsiz taklif bo'lmasin"
    assert payload["max_cameras"] >= 1


# ── feature_status: rol berilgan-u geometriya yo'q ───────────────────────


def test_feature_status_warns_about_a_role_without_geometry(
    local_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from chaqimchi_ai.local import config_store

    config_store.save_camera(
        camera_id="camera-01",
        stream_url=SUB,
        label="Kirish",
        record_url=MAIN,
        priority="security",
        role="entrance",
    )
    config_store.save_camera(
        camera_id="camera-02",
        stream_url=SUB,
        label="Kassa",
        record_url=MAIN,
        priority="retail",
        role="checkout",
    )

    codes = {item["code"]: item for item in config_store.feature_status()}

    assert codes["role_entrance_camera-01"]["active"] is False
    assert "Face ID" in codes["role_entrance_camera-01"]["reason"]
    assert codes["role_checkout_camera-02"]["active"] is False


def test_feature_status_is_quiet_when_the_geometry_matches(
    local_client: TestClient,
) -> None:
    from chaqimchi_ai.local import config_store

    config_store.save_camera(
        camera_id="camera-01",
        stream_url=SUB,
        label="Kirish",
        record_url=MAIN,
        priority="security",
        role="entrance",
    )
    config_store.save_geometry(
        lines=[
            {
                "name": "kirish",
                "camera_id": "camera-01",
                "start": [0.2, 0.5],
                "end": [0.8, 0.5],
            }
        ],
        zones=[],
    )

    codes = {item["code"] for item in config_store.feature_status()}
    assert "role_entrance_camera-01" not in codes
