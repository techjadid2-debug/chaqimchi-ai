"""Kamera manzili bulutda saqlanadi — do'kon kompyuteri o'lsa yo'qolmasin.

Nega bu o'zgarish qilindi.  Ilgari qurilma bulutga faqat kamera ID va
nomini yuborardi: RTSP ichidagi NVR paroli do'konda qolsin degan qaror
bor edi.  Amalda uning narxi ko'rindi:

* 2026-08-28 da sinov do'konida camera-02 ga `record_url` berilmagani
  aniqlandi — ya'ni o'sha kameradagi hodisalar uchun klip printsipial
  yozilmasdi.  Tuzatish uchun manzil kerak edi va u faqat do'kon
  kompyuterida turardi;
* oqim sifatini (720p ga o'tsa bo'ladimi) bulutdan bilib bo'lmasdi;
* do'kon kompyuteri o'lsa yoki qayta o'rnatilsa sozlama butunlay
  yo'qolardi.

Manzil `CHAQIMCHI_CAMERA_SECRET_KEY` bilan shifrlanadi va panelga
qaytarilmaydi.  Bu testlar aynan shu ikkisini va eng xavfli holatni —
eski qurilma bulutdagi yagona nusxani o'chirib yuborishini — qulflaydi.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cloud.store import CloudStore

SUB = "rtsp://admin:maxfiy@192.168.1.64:554/Streaming/Channels/102"
MAIN = "rtsp://admin:maxfiy@192.168.1.64:554/Streaming/Channels/101"


@pytest.fixture
def store(tmp_path: Path) -> CloudStore:
    return CloudStore(tmp_path / "cloud.db")


def _site(store: CloudStore) -> str:
    return store.create_site("Do'kon", plan="biznes")["site_id"]


def test_the_device_camera_address_is_stored_and_readable(store: CloudStore) -> None:
    site_id = _site(store)

    store.register_device_cameras(
        site_id,
        [{"camera_id": "camera-01", "label": "Kirish", "source": SUB, "record_url": MAIN}],
    )

    camera = store.list_cameras(site_id, include_source=True)[0]
    assert camera["source"] == SUB
    assert camera["record_url"] == MAIN
    assert camera["origin"] == "device"


def test_the_address_never_comes_back_in_the_panel_listing(store: CloudStore) -> None:
    """Panel ro'yxatida parol KO'RINMASIN — u faqat qurilmaga boradi."""
    site_id = _site(store)
    store.register_device_cameras(
        site_id, [{"camera_id": "camera-01", "source": SUB, "record_url": MAIN}]
    )

    camera = store.list_cameras(site_id)[0]

    assert "source" not in camera
    assert "record_url" not in camera
    assert "rtsp_ciphertext" not in camera, "shifrlangan matn ham chiqmasin"
    assert "record_ciphertext" not in camera


def test_it_is_actually_encrypted_at_rest(store: CloudStore, tmp_path: Path) -> None:
    """Parol bazada OCHIQ yotmasin — zaxira nusxasi ham shu faylni oladi."""
    import sqlite3

    site_id = _site(store)
    store.register_device_cameras(
        site_id, [{"camera_id": "camera-01", "source": SUB, "record_url": MAIN}]
    )

    raw = sqlite3.connect(str(store.db_path)).execute(
        "SELECT rtsp_ciphertext, record_ciphertext FROM site_cameras"
    ).fetchone()

    assert "maxfiy" not in str(raw), "parol ochiq saqlangan"
    assert "192.168.1.64" not in str(raw), "IP ham ochiq qolmasin"


def test_an_old_device_does_not_wipe_the_only_copy(store: CloudStore) -> None:
    """ENG XAVFLI HOLAT: 0.6.23 va undan oldingi qurilma manzil yubormaydi.

    Agar bo'sh qiymat mavjudining ustidan yozilsa, bulutdagi yagona
    nusxa yo'qolardi — ya'ni yangilanish paytida bir necha daqiqa eski
    versiya ishlagani do'konning kamera sozlamasini o'chirib yuborardi.
    """
    site_id = _site(store)
    store.register_device_cameras(
        site_id, [{"camera_id": "camera-01", "source": SUB, "record_url": MAIN}]
    )

    # Eski qurilma: faqat ID va nom.
    store.register_device_cameras(site_id, [{"camera_id": "camera-01", "label": "Kirish"}])

    camera = store.list_cameras(site_id, include_source=True)[0]
    assert camera["source"] == SUB, "eski qurilma manzilni o'chirib yubordi"
    assert camera["record_url"] == MAIN


def test_a_changed_address_replaces_the_old_one(store: CloudStore) -> None:
    """Mijoz kamerani almashtirsa yangi manzil yozilsin."""
    site_id = _site(store)
    store.register_device_cameras(site_id, [{"camera_id": "camera-01", "source": SUB}])

    yangi = "rtsp://admin:boshqa@192.168.1.90:554/Streaming/Channels/102"
    store.register_device_cameras(site_id, [{"camera_id": "camera-01", "source": yangi}])

    assert store.list_cameras(site_id, include_source=True)[0]["source"] == yangi


def test_a_panel_camera_is_never_overwritten_by_the_device(store: CloudStore) -> None:
    """Admin kiritgan manzil qurilma ro'yxati bilan almashmasin.

    Bu qoida o'zgarishdan OLDIN ham bor edi va saqlanishi shart:
    admin manzilni ataylab qo'yadi (masalan mijoz noto'g'ri kiritganda).
    """
    site_id = _site(store)
    store.upsert_camera(site_id, "camera-01", label="Admin qo'ygan", rtsp_url=MAIN)

    store.register_device_cameras(
        site_id, [{"camera_id": "camera-01", "label": "Qurilma", "source": SUB}]
    )

    camera = store.list_cameras(site_id, include_source=True)[0]
    assert camera["origin"] == "panel"
    assert camera["source"] == MAIN, "admin manzili qurilma bilan almashdi"
    assert camera["label"] == "Admin qo'ygan"


def test_a_camera_without_a_record_url_is_visible_as_such(store: CloudStore) -> None:
    """Klip manzili yo'qligi bulutda KO'RINSIN.

    Sinov do'konidagi camera-02 aynan shu holatda edi va uni faqat
    heartbeat'dagi `record_url_set: false` bilan sezish mumkin edi.
    """
    site_id = _site(store)
    store.register_device_cameras(
        site_id,
        [
            {"camera_id": "camera-01", "source": SUB, "record_url": MAIN},
            {"camera_id": "camera-02", "source": SUB},
        ],
    )

    cameras = {item["camera_id"]: item for item in store.list_cameras(site_id, include_source=True)}

    assert cameras["camera-01"].get("record_url") == MAIN
    assert not cameras["camera-02"].get("record_url")


def test_the_device_publishes_both_streams() -> None:
    """Qurilma ikkala manzilni ham yuborsin — kalit nomlari to'g'ri bo'lsin.

    Sozlamada maydon `stream_url`, bulut modelida esa `source`.  Nom
    farqi jimgina bo'sh manzil yuborishga olib kelishi mumkin edi.
    """
    from chaqimchi_ai.local import cloud_config

    source = (
        Path(__file__).resolve().parents[1] / "chaqimchi_ai" / "local" / "cloud_config.py"
    ).read_text(encoding="utf-8")
    block = source[source.index("def publish_cameras") : source.index("def _outbox_stats")]

    assert '"source": str(item.get("stream_url")' in block
    assert '"record_url": str(item.get("record_url")' in block
    assert cloud_config is not None


# ── Tiklash: bulutdagi zaxira ROSTDAN ishlatiladimi ──────────────────────


def test_a_reinstalled_computer_gets_its_clip_url_back_from_the_cloud() -> None:
    """Zaxira nusxaning butun ma'nosi shu testda.

    Do'kon kompyuteri qayta o'rnatilsa lokal sozlama BO'SH bo'ladi.
    Bulutdagi manzil ishlatilmasa, zaxira "bor, lekin foydasiz" bo'lardi:
    kamera yana ishlaydi, klip esa substreamdan yozilib past sifatli
    chiqardi va buni hech kim sezmasdi.
    """
    from chaqimchi_ai.retail.inventory import InventoryCamera, merge_cameras

    inventory = [
        InventoryCamera(
            camera_id="camera-01", source=SUB, label="Kirish", record_url=MAIN
        )
    ]

    plans = merge_cameras(inventory, [])  # lokal sozlama bo'sh — qayta o'rnatilgan

    assert plans[0].stream_url == SUB
    assert plans[0].record_url == MAIN, "bulutdagi klip manzili ishlatilmadi"


def test_the_local_setting_still_wins_over_the_cloud_copy() -> None:
    """Lokal sozlama ustun: usta shu kompyuterda ataylab kiritgan."""
    from chaqimchi_ai.retail.inventory import InventoryCamera, merge_cameras

    class LocalCamera:
        id = "camera-01"
        record_url = "rtsp://admin:maxfiy@192.168.1.64:554/lokal"
        priority = "retail"
        sample_fps = 5.0
        floor_fps = None
        stream_url = SUB

    plans = merge_cameras(
        [InventoryCamera(camera_id="camera-01", source=SUB, record_url=MAIN)],
        [LocalCamera()],
    )

    assert plans[0].record_url == LocalCamera.record_url


def test_without_any_record_url_the_substream_is_still_used() -> None:
    """Klipsiz qolgandan ko'ra past sifatli klip yaxshiroq — eski xulq."""
    from chaqimchi_ai.retail.inventory import InventoryCamera, merge_cameras

    plans = merge_cameras([InventoryCamera(camera_id="camera-01", source=SUB)], [])

    assert plans[0].record_url == SUB
