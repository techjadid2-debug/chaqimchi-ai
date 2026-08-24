"""Qurilma tomoni: bulutdan kelgan topshiriqlar va ulanish oqimi.

Bu yerdagi eng muhim kafolat — **skanerlash heartbeat'ni bloklamasligi**.
Tarmoq skaneri 90 soniyagacha cho'zilishi mumkin, heartbeat esa har 20
soniyada ketishi kerak.  Ular bitta oqimda bo'lsa bulut qurilmani
"oflayn" deb belgilardi va egasi jonli ko'rishni yo'qotardi — aynan
skanerlash paytida, ya'ni u panelga eng ko'p qaraydigan daqiqada.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from chaqimchi_ai.local import cloud_jobs, cloud_link


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    """Har test o'z papkasida ishlaydi — `connect.json` sizib ketmasin."""
    monkeypatch.setenv("CHAQIMCHI_LOCAL_DIR", str(tmp_path))
    cloud_link._hello_attempt["at"] = -cloud_link.HELLO_RETRY_SEC
    # Navbat modul darajasida — oldingi testdan qolgan topshiriq
    # keyingisini chalg'itmasin.
    while not cloud_jobs._QUEUE.empty():
        cloud_jobs._QUEUE.get_nowait()
    yield


# ── Navbat ───────────────────────────────────────────────────────────


def test_only_one_job_runs_at_a_time() -> None:
    """Ikkinchi topshiriq navbatga sig'maydi.

    Bulut ham bittasiga ruxsat beradi; bu yerdagi chegara — ikkinchi
    himoya.  Ikki skaner bir vaqtda ishlasa ular bir xil multicast
    portini talashib, ikkalasi ham hech nima topmasdi.
    """
    assert cloud_jobs.enqueue({"job_id": "a", "kind": "lan_scan"}) is True
    assert cloud_jobs.enqueue({"job_id": "b", "kind": "lan_scan"}) is False


def test_heartbeat_answer_hands_the_job_over_without_running_it() -> None:
    """Heartbeat halqasi topshiriqni FAQAT navbatga qo'yadi.

    Agar u shu yerda bajarilsa, keyingi heartbeat 90 soniya kechikardi.
    """
    started = time.monotonic()
    cloud_jobs.apply_job_requests({"job_requested": [{"job_id": "x", "kind": "lan_scan"}]})
    assert time.monotonic() - started < 0.5
    assert cloud_jobs._QUEUE.qsize() == 1


def test_an_unknown_job_kind_is_reported_not_swallowed(monkeypatch) -> None:
    """Bulut javobsiz qolmasin — aks holda job muddati bilan o'chib,
    egasi «qurilma javob bermadi» degan noaniq xatoni ko'rardi."""
    sent: list = []
    monkeypatch.setattr(cloud_jobs, "_post", lambda path, payload, **kw: sent.append((path, payload)))

    cloud_jobs.run_one({"job_id": "z", "kind": "teleport"})

    assert len(sent) == 1
    path, payload = sent[0]
    assert path.endswith("/z/result")
    assert payload["ok"] is False
    assert "teleport" in payload["error"]


def test_a_crashing_job_still_answers_the_cloud(monkeypatch) -> None:
    sent: list = []
    monkeypatch.setattr(cloud_jobs, "_post", lambda path, payload, **kw: sent.append(payload))

    def _boom(*_args, **_kwargs):
        raise OSError("tarmoq yo'q")

    monkeypatch.setattr(cloud_jobs, "_run_lan_scan", _boom)
    cloud_jobs.run_one({"job_id": "z", "kind": "lan_scan"})

    assert sent and sent[-1]["ok"] is False
    assert "tarmoq yo'q" in sent[-1]["error"]


def test_the_runner_thread_survives_a_failing_job(monkeypatch) -> None:
    """Bitta xato topshiriq oqimni o'ldirsa, qolgan hamma topshiriq
    jimgina yo'qolardi va buni faqat mijoz shikoyat qilganda bilardik."""
    done = threading.Event()
    calls: list = []

    def _fake_run(job):
        calls.append(job["job_id"])
        if job["job_id"] == "first":
            raise RuntimeError("yiqildi")
        done.set()

    monkeypatch.setattr(cloud_jobs, "run_one", _fake_run)
    thread = cloud_jobs.start()
    try:
        cloud_jobs.enqueue({"job_id": "first", "kind": "lan_scan"})
        # Birinchisi olinguncha kutamiz, keyin ikkinchisini qo'yamiz.
        for _ in range(100):
            if calls:
                break
            time.sleep(0.02)
        cloud_jobs.enqueue({"job_id": "second", "kind": "lan_scan"})
        assert done.wait(3.0), "oqim birinchi xatodan keyin to'xtab qoldi"
    finally:
        assert thread.daemon


def test_progress_is_throttled_but_the_last_one_always_goes(monkeypatch) -> None:
    """Har qadamda so'rov yuborilsa bulutdagi cheklovga urilardi;
    yakuniy 100% esa hech qachon tashlanmasligi kerak — panel aynan
    shuni kutib turadi."""
    sent: list = []
    monkeypatch.setattr(cloud_jobs, "_post", lambda path, payload, **kw: sent.append(payload["percent"]))

    report = cloud_jobs._reporter("j1")
    report(10, "")
    report(20, "")
    report(30, "")
    report(100, "")

    assert sent[0] == 10
    assert 100 in sent
    assert 20 not in sent and 30 not in sent


# ── Ulanish oqimi ────────────────────────────────────────────────────


def _write_connect(tmp_path, *, minutes_left: int) -> None:
    expires = datetime.now(timezone.utc) + timedelta(minutes=minutes_left)
    (tmp_path / cloud_link.CONNECT_STATE).write_text(
        json.dumps(
            {
                "cloud_url": "https://api.example.uz",
                "connect_token": "t" * 40,
                "connect_url": "https://app.example.uz/owner?connect=tttt",
                "verify_code": "AB12CD",
                "expires_at": expires.isoformat(),
                "fingerprint": "f" * 64,
            }
        ),
        encoding="utf-8",
    )


def test_an_expired_link_is_never_shown_to_the_owner(tmp_path) -> None:
    """Muddati o'tgan havolani ko'rsatish eng yomon variant: mijoz uni
    bosadi, 404 oladi va dastur buzuq deb o'ylaydi."""
    _write_connect(tmp_path, minutes_left=-5)

    assert cloud_link._connect_is_live(cloud_link._read_connect_state()) is False


def test_a_live_link_is_reused_instead_of_asking_for_a_new_one(tmp_path, monkeypatch) -> None:
    """Har 20 soniyada yangi havola so'ralsa, ekrandagi tekshiruv kodi
    egasi uni terguncha o'zgarib ketardi."""
    _write_connect(tmp_path, minutes_left=30)
    monkeypatch.setattr(cloud_link, "hello", lambda url: pytest.fail("keraksiz hello"))

    state = cloud_link.ensure_connect_state()

    assert state["verify_code"] == "AB12CD"
    assert state["connect_url"].endswith("connect=tttt")


def test_a_connected_device_never_asks_to_be_connected_again(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cloud_link, "is_connected", lambda: True)
    monkeypatch.setattr(cloud_link, "hello", lambda url: pytest.fail("keraksiz hello"))
    monkeypatch.setattr(cloud_link, "handover", lambda: pytest.fail("keraksiz handover"))

    assert cloud_link.poll_connection() is None
    assert cloud_link.ensure_connect_state() == {}


def test_the_device_stops_asking_when_the_cloud_says_no(tmp_path, monkeypatch) -> None:
    """`CHAQIMCHI_DEVICE_HELLO=0` yoqilgan (yoki bulut eski) bo'lsa
    har 20 soniyada 404 olishning ma'nosi yo'q — dastur sehrgar bilan
    ishlayveradi."""
    tries: list = []
    monkeypatch.setattr(cloud_link, "is_connected", lambda: False)
    monkeypatch.setattr(cloud_link, "hello", lambda url: tries.append(url))

    for _ in range(5):
        cloud_link.poll_connection()

    assert len(tries) == 1


def test_a_pending_approval_keeps_the_link_alive(tmp_path, monkeypatch) -> None:
    _write_connect(tmp_path, minutes_left=30)
    monkeypatch.setattr(cloud_link, "is_connected", lambda: False)
    monkeypatch.setattr(cloud_link, "hello", lambda url: pytest.fail("keraksiz hello"))
    monkeypatch.setattr(cloud_link, "handover", lambda: None)

    assert cloud_link.poll_connection() is None
    assert (tmp_path / cloud_link.CONNECT_STATE).exists()


def test_the_handover_writes_the_credentials_and_clears_the_link(tmp_path, monkeypatch) -> None:
    """Tasdiqdan keyingi yagona qadam.

    Bu test bir marta yiqilgan: `PairedSite` da `device_token` maydoni
    YO'Q (u ataylab faqat configga yoziladi), lekin `handover()` uni
    konstruktorga uzatardi.  Xato faqat egasi tasdiqlagan lahzada
    chiqardi — ya'ni birinchi haqiqiy mijozda.
    """
    _write_connect(tmp_path, minutes_left=30)

    class _Answer:
        status_code = 200

        @staticmethod
        def json():
            return {
                "status": "claimed",
                "site_id": "site-1",
                "device_id": "dev-1",
                "device_token": "secret-token",
                "cloud_url": "https://api.example.uz",
                "panel_url": "https://app.example.uz/owner",
            }

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def post(self, *_a, **_k):
            return _Answer()

    monkeypatch.setattr(cloud_link.httpx, "Client", lambda **_k: _Client())

    site = cloud_link.handover()

    assert site is not None
    assert site.site_id == "site-1"

    from chaqimchi_ai.local import config_store

    saved = config_store.read_raw().get("cloud_sync") or {}
    assert saved["device_token"] == "secret-token"
    assert saved["panel_url"] == "https://app.example.uz/owner"
    # Havola ishlatildi — u endi diskda qolmasligi kerak.
    assert not (tmp_path / cloud_link.CONNECT_STATE).exists()


def test_the_fingerprint_is_stable_across_calls() -> None:
    """Bulut shu iz bo'yicha qatorni qayta ishlatadi.  Iz har safar
    o'zgarsa, bitta kompyuter o'nlab "kutayotgan qurilma" yaratardi."""
    first = cloud_link.fingerprint()

    assert len(first) == 64
    assert first == cloud_link.fingerprint()


# ── Brauzer manzili ──────────────────────────────────────────────────


def test_the_first_run_opens_the_cloud_panel_when_connected(monkeypatch) -> None:
    from chaqimchi_ai.local import app as local_app

    monkeypatch.setattr(cloud_link, "is_connected", lambda: True)
    monkeypatch.setattr(cloud_link, "panel_url", lambda: "https://app.example.uz/owner")

    assert local_app._first_run_url("http://127.0.0.1:8760") == "https://app.example.uz/owner"


def test_the_first_run_opens_the_connect_page_when_not_connected(monkeypatch) -> None:
    from chaqimchi_ai.local import app as local_app

    monkeypatch.setattr(cloud_link, "is_connected", lambda: False)
    monkeypatch.setattr(
        cloud_link,
        "ensure_connect_state",
        lambda *_a, **_k: {"connect_url": "https://app.example.uz/owner?connect=zz"},
    )

    assert local_app._first_run_url("http://127.0.0.1:8760").endswith("connect=zz")


def test_without_internet_the_wizard_is_still_offered(monkeypatch) -> None:
    """Internetsiz o'rnatilgan do'konda mijoz baribir kamerani ulay
    olishi kerak — shuning uchun lokal sehrgar oxirgi pog'ona."""
    from chaqimchi_ai.local import app as local_app

    monkeypatch.setattr(cloud_link, "is_connected", lambda: False)
    monkeypatch.setattr(cloud_link, "ensure_connect_state", lambda *_a, **_k: {})

    assert local_app._first_run_url("http://127.0.0.1:8760") == "http://127.0.0.1:8760"


def test_the_panel_lives_on_a_different_host_than_the_api(monkeypatch) -> None:
    """`api.` xosti faqat `/api/*` ni o'tkazadi va `/owner` uchun 404
    beradi (`deploy/Caddyfile.chaqimchi`).

    Bu holat haqiqiy: pairing kod bilan o'rnatilgan qurilma birinchi
    `/edge/config` gacha ulangan, lekin panel manzilini bilmaydi —
    almashuvsiz mijozga o'lik havola ko'rsatilardi.
    """
    assert cloud_link._panel_host("https://api.chaqimchi.uz") == "https://app.chaqimchi.uz"
    assert cloud_link._panel_host("https://api.chaqimchi.uz/") == "https://app.chaqimchi.uz"
    # Ishlab chiqish manzili o'zgarmaydi — u yerda panel ham shu xostda.
    assert cloud_link._panel_host("http://127.0.0.1:8750") == "http://127.0.0.1:8750"
    assert cloud_link._panel_host("https://chaqimchi.uz") == "https://chaqimchi.uz"


def test_the_cloud_wins_over_the_guessed_panel_address(tmp_path, monkeypatch) -> None:
    from chaqimchi_ai.local import config_store

    config_store.update(
        "cloud_sync",
        {
            "enabled": True,
            "url": "https://api.chaqimchi.uz",
            "device_token": "t",
            "panel_url": "https://panel.example.uz/owner",
        },
    )

    assert cloud_link.panel_url() == "https://panel.example.uz/owner"


def test_a_broken_cloud_never_blocks_the_first_run(monkeypatch) -> None:
    from chaqimchi_ai.local import app as local_app

    def _boom(*_a, **_k):
        raise RuntimeError("bulut javob bermadi")

    monkeypatch.setattr(cloud_link, "is_connected", _boom)

    assert local_app._first_run_url("http://127.0.0.1:8760") == "http://127.0.0.1:8760"
