"""Hech qachon hodisa bermaydigan chiziq va zonalar topilsin.

Bu testlarning asosi — TAXMIN emas, jonli sozlama.  2026-08-28 da sinov
do'konining `site_configs` revision 11 yozuvida ikkita yaroqsiz chizma
topildi va ikkalasi ham jimgina hech narsa qilmasdi.  Shu yozuvning
o'zi quyida kirish ma'lumoti sifatida turibdi.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cloud.config_health import feature_problems, geometry_problems
from cloud.snapshots import LocalSnapshotStore

#: Sinov do'konining HAQIQIY sozlamasi (revision 11, 2026-08-28).
#: O'zgartirilmagan — aynan shu yozuv ikki kun davomida nol
#: `zone_entered` bergan.
LIVE_CONFIG = {
    "lines": [
        {
            "name": "Kirish",
            "camera_id": "camera-01",
            "start": [0.15, 0.65],
            "end": [0.339, 0.511],
            "swap_direction": False,
        },
        {
            "name": "Kirish",
            "camera_id": "camera-02",
            "start": [0.101, 0.679],
            "end": [0.164, 0.94],
            "swap_direction": False,
        },
        {
            # 0.007 uzunlik — 640 px kadrda ~4 piksel.
            "name": "kirish",
            "camera_id": "camera-02",
            "start": [0.094, 0.834],
            "end": [0.094, 0.827],
            "swap_direction": False,
        },
    ],
    "zones": [
        {
            "name": "Kassa navbati",
            "camera_id": "camera-02",
            "polygon": [[0.371, 0.184], [0.506, 0.294], [0.411, 0.371], [0.308, 0.235]],
            "queue": True,
            "restricted": False,
            "dwell_sec": 180,
        },
        {
            # 29x20 piksel — do'konning YAGONA critical signali.
            "name": "Taqiqlangan zona",
            "camera_id": "camera-02",
            "polygon": [[0.343, 0.048], [0.379, 0.046], [0.385, 0.102], [0.34, 0.102]],
            "queue": False,
            "restricted": True,
            "dwell_sec": None,
        },
    ],
}


def test_the_live_config_that_stayed_silent_is_flagged() -> None:
    """Ikki kunlik jimlikning sababi ro'yxatda ko'rinsin."""
    problems = geometry_problems(LIVE_CONFIG)
    named = {(item["kind"], item["name"]) for item in problems}

    assert ("line", "kirish") in named, "4 pikselli chiziq topilmadi"
    assert ("zone", "Taqiqlangan zona") in named, "29x20 pikselli zona topilmadi"
    assert len(problems) == 2, f"ortiqcha ogohlantirish: {problems}"


def test_working_geometry_is_not_flagged() -> None:
    """Ishlayotgan chizma ro'yxatga TUSHMASIN.

    "Kassa navbati" zonasi va ikkita normal "Kirish" chizig'i o'sha
    do'konda hodisa berayapti (uch kunda 68 ta navbat, 615 ta kirish) —
    ularni ogohlantirishga qo'shish ro'yxatni o'qilmas qilardi.
    """
    problems = geometry_problems(LIVE_CONFIG)
    flagged = {(item["kind"], item["camera_id"], item["name"]) for item in problems}

    assert ("zone", "camera-02", "Kassa navbati") not in flagged
    assert ("line", "camera-01", "Kirish") not in flagged
    assert ("line", "camera-02", "Kirish") not in flagged


def test_the_problem_text_names_pixels_not_fractions() -> None:
    """Admin 0.007 ni tushunmaydi, 4 pikselni tushunadi."""
    problems = geometry_problems(LIVE_CONFIG)
    line = next(item for item in problems if item["kind"] == "line")
    zone = next(item for item in problems if item["kind"] == "zone")

    assert "4 piksel" in line["problem"], line["problem"]
    assert "29x20 piksel" in zone["problem"], zone["problem"]


def test_a_narrow_strip_with_enough_area_is_still_flagged() -> None:
    """Yuzasi yetarli, lekin ensiz — markaz uni kesib o'tadi."""
    config = {
        "zones": [
            {
                "name": "Tasma",
                "camera_id": "camera-01",
                # 0.9 x 0.03 = 0.027 yuza (chegaradan katta), lekin
                # balandligi 0.03 — bir kadrdagi qadamdan ikki barobar.
                "polygon": [[0.05, 0.50], [0.95, 0.50], [0.95, 0.53], [0.05, 0.53]],
            }
        ]
    }

    problems = geometry_problems(config)

    assert len(problems) == 1
    assert "ensiz" in problems[0]["problem"]


def test_broken_coordinates_do_not_crash_the_card() -> None:
    """Sozlama buzuq bo'lsa ham sayt kartochkasi ochilishi kerak."""
    config = {
        "lines": [{"name": "x", "camera_id": "camera-01", "start": None, "end": [1, 1]}],
        "zones": [{"name": "y", "camera_id": "camera-01", "polygon": [[0.1, 0.1]]}],
    }

    problems = geometry_problems(config)

    assert len(problems) == 2
    assert all(item["measure"] is None for item in problems)


def test_an_empty_config_has_no_problems() -> None:
    assert geometry_problems({}) == []
    assert geometry_problems({"lines": [], "zones": []}) == []


# ── Admin paneliga yetib borishi ─────────────────────────────────────────


ADMIN = {"X-Cloud-Admin-Key": "test-admin"}


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    import cloud.main as main

    monkeypatch.setenv("CHAQIMCHI_CLOUD_ADMIN_KEY", "test-admin")
    monkeypatch.setenv("CHAQIMCHI_OWNER_JWT_SECRET", "owner-secret-with-more-than-32-characters")
    monkeypatch.setenv("CHAQIMCHI_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("CHAQIMCHI_S3_ENDPOINT", raising=False)
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "cloud.db")
    monkeypatch.setattr(main, "_store", None)
    monkeypatch.setattr(main, "_event_store", None)
    monkeypatch.setattr(main, "_event_store_key", None)
    monkeypatch.setattr(main, "_snapshots", LocalSnapshotStore(tmp_path / "snapshots"))
    with TestClient(main.app) as test_client:
        yield test_client


def test_admin_site_detail_carries_the_problem_list(client: TestClient) -> None:
    """Ro'yxat sayt kartochkasi bilan BIRGA kelsin.

    Alohida so'rov bo'lsa panel uni chaqirishni unutishi mumkin —
    moliya paneli aynan shundan ochilmagan edi.
    """
    site = client.post("/api/v1/admin/sites", headers=ADMIN, json={"name": "Do'kon"}).json()
    site_id = site["site_id"]
    client.post(
        f"/api/v1/admin/sites/{site_id}/cameras",
        headers=ADMIN,
        json={"cameras": 2},
    )
    saved = client.put(
        f"/api/v1/admin/sites/{site_id}/config",
        headers=ADMIN,
        json={"lines": LIVE_CONFIG["lines"], "zones": LIVE_CONFIG["zones"]},
    )
    assert saved.status_code == 200, saved.text

    detail = client.get(f"/api/v1/admin/sites/{site_id}", headers=ADMIN)

    assert detail.status_code == 200, detail.text
    problems = detail.json()["geometry_problems"]
    assert {item["name"] for item in problems} == {"kirish", "Taqiqlangan zona"}


def test_a_clean_site_reports_an_empty_list(client: TestClient) -> None:
    site = client.post("/api/v1/admin/sites", headers=ADMIN, json={"name": "Toza"}).json()

    detail = client.get(f"/api/v1/admin/sites/{site['site_id']}", headers=ADMIN)

    assert detail.json()["geometry_problems"] == []


def test_the_diagnostics_endpoint_carries_the_benchmark_result(client: TestClient) -> None:
    """Admin o'lchov natijasini paneldan KO'RA olsin.

    Tugma o'lchovni boshlardi, natija esa `device_jobs` da qolib ketardi
    va unga panelda yo'l yo'q edi.  Endi u diagnostika javobida keladi —
    admin uchun bitta joy.
    """
    import cloud.main as main

    site = client.post("/api/v1/admin/sites", headers=ADMIN, json={"name": "O'lchov"}).json()
    site_id = site["site_id"]

    empty = client.get(f"/api/v1/admin/sites/{site_id}/diagnostics", headers=ADMIN)
    assert empty.status_code == 200
    assert empty.json()["benchmark"] is None, "o'lchov qilinmagan do'konda bo'sh"

    store = main.get_store()
    job = store.create_job(site_id, kind="benchmark", params={}, requested_by="admin")
    store.job_result(
        site_id, job["job_id"], ok=True, result={"verdict": {"cameras": 4, "ok": True}}
    )

    answer = client.get(f"/api/v1/admin/sites/{site_id}/diagnostics", headers=ADMIN)

    assert answer.status_code == 200, answer.text
    benchmark = answer.json()["benchmark"]
    assert benchmark["status"] == "done"
    assert benchmark["result"]["verdict"]["cameras"] == 4


# ── To'lovchi mijoz hodisa olmayotgan holat ──────────────────────────────
#
# 2026-08-29 dan 08-30 gacha "Do'kon (5070)" ning hamma biznes hodisasi
# qurilmada tashlandi.  Quyidagi raqamlar HAQIQIY heartbeat'dan olingan
# (30-avgust 07:45): 806 hodisa yaratildi, 806 tasi tashlandi.


def test_a_paying_site_without_features_is_flagged() -> None:
    problems = feature_problems({"status": "active"}, [])

    assert len(problems) == 1
    assert problems[0]["kind"] == "feature"
    assert "birorta funksiya ketmayapti" in problems[0]["problem"]


def test_grace_counts_as_serving() -> None:
    """Sayt "obuna tugagach yana 14 kun ishlaydi" deb va'da qiladi."""
    assert feature_problems({"status": "grace"}, [])


def test_an_expired_site_is_not_a_problem() -> None:
    """Obunasi tugagan saytda bo'sh ro'yxat — nosozlik emas, qoida."""
    assert feature_problems({"status": "expired"}, []) == []
    assert feature_problems({"status": "suspended"}, []) == []


def test_a_site_with_features_is_quiet() -> None:
    assert feature_problems({"status": "active"}, [{"code": "person_count"}]) == []


def test_the_device_dropping_everything_is_flagged() -> None:
    """Natija bo'yicha tekshiruv — sabab noma'lum bo'lsa ham ishlaydi."""
    problems = feature_problems(
        {"status": "active"},
        [{"code": "person_count"}],  # ro'yxat BOR, lekin qurilma baribir tashlayapti
        {"events": 806, "plan_filtered": 806},
    )

    assert len(problems) == 1
    assert problems[0]["measure"] == "806 ta hodisadan 806 tasi tashlangan"


def test_partial_filtering_is_normal() -> None:
    """Bir qism tashlanishi normal: tarifga kirmagan hodisa turlari bor."""
    assert (
        feature_problems(
            {"status": "active"},
            [{"code": "person_count"}],
            {"events": 806, "plan_filtered": 40},
        )
        == []
    )


def test_a_broken_heartbeat_does_not_crash_the_check() -> None:
    """Maydon yo'q yoki buzuq bo'lsa sayt kartochkasi baribir ochilsin."""
    assert feature_problems({"status": "active"}, [{"code": "x"}], {}) == []
    assert (
        feature_problems(
            {"status": "active"}, [{"code": "x"}], {"events": "yo'q", "plan_filtered": None}
        )
        == []
    )


def test_the_site_card_carries_the_feature_check(client) -> None:
    """Tekshiruv admin kartochkasiga ULANGAN bo'lsin.

    Mantiq yuqorida sinaladi; bu test faqat simni qulflaydi — 2026-08-29
    dagi nosozlik aynan "hech kim ko'rmadi" degan joyda yashiringan edi.
    """
    site = client.post(
        "/api/v1/admin/sites", headers=ADMIN, json={"name": "Sim tekshiruvi"}
    ).json()

    detail = client.get(f"/api/v1/admin/sites/{site['site_id']}", headers=ADMIN)

    assert detail.status_code == 200, detail.text
    assert "feature_problems" in detail.json()
