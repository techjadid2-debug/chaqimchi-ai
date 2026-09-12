"""Kamera kadrining o'lchami qurilmadan cloudgacha yetsin.

Nega bu test bor.  "Bu kamera yuz tanish uchun yaraydimi" degan savolga
javob beradigan yagona son — oqimning kadr BALANDLIGI
(`limits.face_min_bbox_ratio`: 360p da odam kadrning 76% ini egallashi
kerak, ya'ni amalda imkonsiz; 720p da 38%).  Mantiq
(`camera_roles.face_id_check`) ancha oldin yozilgan, lekin **Windows
yo'lida bu son cloudga hech qachon yubormasdi**: `report_camera_probes()`
faqat Box agentida (`enes/sotqin_agent.py`) va do'kon kompyuterida
chaqiruvchisi yo'q.  Natijada `site_cameras.width/height` pilotda oylab
NULL turdi, panel esa "o'lcham noma'lum" dan boshqa javob bera olmadi —
ya'ni usta kamerani noto'g'ri qo'yganini faqat oylar o'tib,
`face_crops.too_small` hisoblagichidan bilib qolardi.

Zanjir uch qo'ldan o'tadi va har biri alohida tekshiriladi:

    runner (dekodlangan kadr) → holat fayli → heartbeat → site_cameras
"""

from __future__ import annotations

import importlib
import json
import time
from pathlib import Path
from typing import Any, Dict

import pytest

from cloud.store import CloudStore

# ── 1) Qurilma: kadrdan holat fayligacha ────────────────────────────────


def test_the_runner_remembers_the_real_frame_size() -> None:
    """`CAP_PROP` emas, KADRNING O'ZI.

    RTSP da `CAP_PROP_FRAME_WIDTH` drayver taxminini qaytaradi va 720p ga
    o'tilgan-o'tilmaganini yolg'on aytadi — `benchmark` ham shu sababdan
    `native_size` ni kadrdan oladi.
    """
    from enes.retail import runner

    stream = runner._Stream(source=None)  # type: ignore[arg-type]

    assert stream.width == 0 and stream.height == 0, "kadr kelmaguncha — noma'lum"


def test_the_status_file_carries_the_frame_size(tmp_path: Path) -> None:
    from enes.retail import service

    path = tmp_path / "status.json"
    service.write_status(
        path,
        {
            "streams": {
                "camera-01": {"connected": True, "offline": False, "width": 1280, "height": 720},
                "camera-02": {"connected": True, "offline": False},
            }
        },
        now=time.time(),
    )

    cameras = json.loads(path.read_text(encoding="utf-8"))["cameras"]
    assert cameras["camera-01"]["width"] == 1280
    assert cameras["camera-01"]["height"] == 720
    assert cameras["camera-02"]["height"] == 0, "kadr kelmagan kamera — nol, yolg'on son emas"


def test_the_heartbeat_carries_the_frame_size(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Zanjirning oxirgi qo'li — aynan shu yerda uzilgan edi."""
    monkeypatch.setenv("ENES_LOCAL_DIR", str(tmp_path))
    from enes.local import cloud_config, cloud_link, config_store, counters, paths

    for module in (paths, config_store, counters, cloud_link, cloud_config):
        importlib.reload(module)
    config_store.update(
        "cloud_sync",
        {
            "enabled": True,
            "url": "https://cloud.example.uz",
            "site_id": "site-1",
            "device_id": "dev-1",
            "device_token": "tok-1",
        },
    )

    sent: Dict[str, Any] = {}

    class _Response:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        @staticmethod
        def json() -> Dict[str, Any]:
            return {"ok": True}

    monkeypatch.setattr(
        cloud_config.httpx,
        "post",
        lambda url, headers=None, json=None, timeout=None: (sent.update(json or {}), _Response())[1],
    )

    cloud_config.send_heartbeat(
        {
            "cameras_active": 1,
            "cameras": {
                "camera-01": {"connected": True, "offline": False, "width": 1280, "height": 720}
            },
        }
    )

    camera = next(item for item in sent["cameras"] if item["camera_id"] == "camera-01")
    assert camera["width"] == 1280
    assert camera["height"] == 720


# ── 2) Cloud: o'lcham saqlansin, lekin jimlik uni o'chirmasin ───────────


@pytest.fixture
def store(tmp_path: Path) -> CloudStore:
    return CloudStore(tmp_path / "cloud.db")


def _camera(store: CloudStore) -> str:
    site = store.create_site("Do'kon", "business")
    store.upsert_camera(
        site["site_id"], "camera-01", label="Kirish", rtsp_url="rtsp://x/1", enabled=True
    )
    return str(site["site_id"])


def test_the_frame_size_is_stored(store: CloudStore) -> None:
    site_id = _camera(store)

    store.record_camera_frame_size(site_id, "camera-01", width=1280, height=720)

    camera = store.list_cameras(site_id)[0]
    assert camera["width"] == 1280 and camera["height"] == 720


def test_the_frame_size_does_not_clobber_what_the_probe_found(store: CloudStore) -> None:
    """`record_camera_probe()` ni qayta ishlatib bo'lmasligining sababi.

    U `codec`, `fps`, `probe_status` va `probe_error` ni ham qayta
    yozadi — heartbeatdan har daqiqada chaqirilsa probe topgan hamma
    narsani `NULL` ga aylantirardi.
    """
    site_id = _camera(store)
    store.record_camera_probe(
        site_id, "camera-01", status="online", codec="h264", width=640, height=360, fps=12.0
    )

    store.record_camera_frame_size(site_id, "camera-01", width=1280, height=720)

    camera = store.list_cameras(site_id)[0]
    assert camera["height"] == 720, "yangi o'lcham yozilsin"
    assert camera["codec"] == "h264", "kodek yo'qolmasin"
    assert camera["fps"] == 12.0, "fps yo'qolmasin"
    assert camera["probe_status"] == "online", "probe holati yolg'onga aylanmasin"


def test_an_unknown_size_is_refused(store: CloudStore) -> None:
    """Nol "bilmayman" degani — u bazadagi bilganimizni o'chirmasin."""
    site_id = _camera(store)
    store.record_camera_frame_size(site_id, "camera-01", width=1280, height=720)

    with pytest.raises(ValueError):
        store.record_camera_frame_size(site_id, "camera-01", width=0, height=0)

    assert store.list_cameras(site_id)[0]["height"] == 720


def test_face_id_check_finally_has_an_answer(store: CloudStore) -> None:
    """Zanjirning MA'NOSI: o'lcham kelgach tekshiruv rost javob beradi."""
    from enes.camera_roles import face_id_check

    site_id = _camera(store)
    assert face_id_check(store.list_cameras(site_id)[0]["height"] or 0)[0] is None

    store.record_camera_frame_size(site_id, "camera-01", width=1280, height=720)

    ok, reason = face_id_check(store.list_cameras(site_id)[0]["height"])
    assert ok is True and "720" in reason


# ── 3) Uchidan-uchiga: heartbeat rostdan bazaga yozadimi ───────────────


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("ENES_CLOUD_ADMIN_KEY", "test-admin")
    monkeypatch.setenv("ENES_OWNER_JWT_SECRET", "o" * 64)
    monkeypatch.setenv("ENES_PORTAL_JWT_SECRET", "p" * 64)
    monkeypatch.setenv("ENES_PUBLIC_URL", "https://enes.test")
    monkeypatch.setattr("cloud.main.DB_PATH", tmp_path / "cloud.db")
    monkeypatch.setattr("cloud.main._store", None)
    monkeypatch.setattr("cloud.main._event_store", None)
    monkeypatch.setattr("cloud.main._event_store_key", None)
    from cloud.main import app

    return TestClient(app)


@pytest.fixture
def shop(client) -> Dict[str, Any]:
    trial = client.post(
        "/api/v1/public/quick-trial",
        json={
            "phone": "+998 90 123 45 67",
            "full_name": "Ega Egayev",
            "company": "Namuna do'kon",
            "username": "dokonchi",
            "password": "parol12345",
            "consent": True,
        },
    ).json()
    claimed = client.post(
        "/api/v1/devices/claim",
        json={"pairing_code": trial["pairing_code"], "label": "KASSA-PC"},
    ).json()
    from cloud.main import get_store

    get_store().upsert_camera(
        trial["site_id"], "camera-01", label="Kirish", rtsp_url="rtsp://x/1", enabled=True
    )
    return {
        "site_id": trial["site_id"],
        "device": {
            "X-Site-Id": claimed["site_id"],
            "X-Device-Id": claimed["device_id"],
            "X-Device-Token": claimed["device_token"],
        },
    }


def _beat(client, shop: Dict[str, Any], cameras: list) -> None:
    response = client.post(
        "/api/v1/edge/heartbeat", headers=shop["device"], json={"cameras": cameras}
    )
    assert response.status_code == 200, response.text


def test_the_heartbeat_fills_the_camera_size(client, shop: Dict[str, Any]) -> None:
    from cloud.main import get_store

    _beat(client, shop, [{"camera_id": "camera-01", "width": 1280, "height": 720}])

    assert get_store().list_cameras(shop["site_id"])[0]["height"] == 720


def test_an_old_device_does_not_wipe_the_known_size(client, shop: Dict[str, Any]) -> None:
    """Jimlik "noma'lum" degani, "yo'q" degani emas.

    Eski qurilma bu maydonni umuman yubormaydi.  Uning har daqiqadagi
    heartbeat'i bilganimizni o'chirsa, panel yuz tanish tekshiruvini
    abadiy "o'lcham noma'lum" da ushlab turardi.
    """
    from cloud.main import get_store

    _beat(client, shop, [{"camera_id": "camera-01", "width": 1280, "height": 720}])
    _beat(client, shop, [{"camera_id": "camera-01"}])

    assert get_store().list_cameras(shop["site_id"])[0]["height"] == 720


def test_an_unknown_camera_does_not_break_the_heartbeat(client, shop: Dict[str, Any]) -> None:
    """Telemetriya kamera ro'yxatga olinmagani uchun yo'qolmasin."""
    _beat(client, shop, [{"camera_id": "camera-04", "width": 640, "height": 360}])


# ── 4) Panel uchun QAROR: matn emas, holat ─────────────────────────────


def test_the_camera_list_carries_the_face_id_decision(store: CloudStore) -> None:
    """Panel uch tilda — server matni esa o'zbekcha.

    Shuning uchun QAROR (`face_id_state`) va MATN (`face_id_reason`)
    ajratilgan: qaror `enes/camera_roles.py` da bir marta chiqadi,
    matnni har sahifa o'z tilida chizadi.  Ega paneli, usta paneli va
    admin kartasi uchtasi ham shu bitta javobni o'qiydi — chegara uch
    joyda qayta hisoblanmaydi.
    """
    site_id = _camera(store)

    assert store.list_cameras(site_id)[0]["face_id_state"] == "unknown"

    for width, height, expected in (
        (352, 288, "low"),
        (854, 480, "edge"),
        (1280, 720, "ok"),
        (1920, 1080, "ok"),
    ):
        store.record_camera_frame_size(site_id, "camera-01", width=width, height=height)
        camera = store.list_cameras(site_id)[0]
        assert camera["face_id_state"] == expected, f"{height}p → {expected} kutilgan"
        assert camera["face_id_reason"], "sabab matni ham berilsin (usta va admin uchun)"


def test_the_two_false_cases_are_told_apart() -> None:
    """«Chegarada» va «720p kerak» ikkalasi ham `False` — lekin BOSHQA ish.

    Birinchisida kamerani yaqinlashtirish yetadi, ikkinchisida NVR
    sozlamasi o'zgaradi.  `bool` bu farqni yo'qotardi.
    """
    from enes.camera_roles import face_id_check, face_id_state

    assert face_id_check(480)[0] is False and face_id_state(480) == "edge"
    assert face_id_check(288)[0] is False and face_id_state(288) == "low"


# ── 5) Darvozalar: yoqilmagan funksiya sotilgan bo'lib ko'rinmasin ─────


def test_the_dashboard_says_whether_the_ai_assistant_is_connected(
    client, shop: Dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Gemini kaliti yo'q do'konda «AI yordamchi» tabi ochilar, har savol
    xato bilan tugar va ega «buzuq» deb o'ylardi — jonli bazada
    `vision_observations` = 0.  Panel darvozani shu javobdan oladi;
    qaror `vision_agent.configured()` da bir marta chiqadi."""
    trial = client.post(
        "/api/v1/auth/login", json={"username": "dokonchi", "password": "parol12345"}
    ).json()
    headers = {"Authorization": f"Bearer {trial['access_token']}"}

    payload = client.get("/api/v1/owner/dashboard", headers=headers).json()
    assert payload["capabilities"]["agent"]["ready"] is False
    assert payload["capabilities"]["agent"]["reason"], "sabab matni bo'lsin"

    monkeypatch.setenv("ENES_GEMINI_API_KEY", "kalit")
    monkeypatch.setenv("ENES_GEMINI_VISION_MODEL", "gemini-2.5-flash")
    payload = client.get("/api/v1/owner/dashboard", headers=headers).json()
    assert payload["capabilities"]["agent"]["ready"] is True
    assert payload["capabilities"]["agent"]["reason"] is None


def test_the_dashboard_says_whether_attendance_is_open(
    client, shop: Dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Davomat — yopiq pilot.  Yoqilmagan serverda «Xodimlar» bo'limi
    menyuda turar, ochilsa har so'rov 403 berardi.

    `_attendance_enabled()` dev/test muhitida ATAYLAB ochiq (aks holda
    har test env qo'yishi kerak bo'lardi) — shuning uchun yopiq holat
    `ENES_ENV=production` bilan sinaladi, ya'ni aynan mijoz ko'radigan
    sozlamada.
    """
    login = client.post(
        "/api/v1/auth/login", json={"username": "dokonchi", "password": "parol12345"}
    ).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}

    payload = client.get("/api/v1/owner/dashboard", headers=headers).json()
    assert payload["capabilities"]["attendance"]["ready"] is True, "dev muhitida ochiq"

    monkeypatch.setenv("ENES_ENV", "production")
    payload = client.get("/api/v1/owner/dashboard", headers=headers).json()
    attendance = payload["capabilities"]["attendance"]
    assert attendance["ready"] is False, "production'da pilot ruxsatisiz yopiq"
    assert attendance["reason"], "sabab matni bo'lsin"
