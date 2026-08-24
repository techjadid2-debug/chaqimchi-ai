"""Bulutdagi RTSP redaksiyasi qurilmadagisidan ajralib ketmasin.

`cloud/rtsp.py` — `chaqimchi_ai/local/camera_probe.redact()` ning
nusxasi.  Nusxa ataylab: qurilmadagi modul `cv2` ni import qiladi va
uni bulut image'iga tortib kirish mumkin emas.

Ikki nusxa bir kun jimgina ajralib ketsa, panelda parol ko'rinib
qolishi mumkin — bu test aynan shuni to'sadi.
"""

import pytest

from chaqimchi_ai.local.camera_probe import redact as device_redact
from cloud.rtsp import redact as cloud_redact
from cloud.rtsp import safe_streams

CASES = [
    "rtsp://admin:Parol123@192.168.1.64:554/Streaming/Channels/102",
    "rtsp://admin:p%40ss@10.0.0.5/cam/realmonitor?channel=1&subtype=1",
    "rtsp://192.168.1.64:554/live",
    "rtsp://user@host/path",
    "rtsp://host/path",
    "",
    "bu manzil emas",
    "rtsp://[2001:db8::1]:554/live",
]


@pytest.mark.parametrize("url", CASES, ids=lambda value: value[:40] or "bo'sh")
def test_both_copies_agree(url: str) -> None:
    assert cloud_redact(url) == device_redact(url)


@pytest.mark.parametrize("url", [case for case in CASES if "Parol123" in case or "p%40ss" in case])
def test_the_password_never_survives(url: str) -> None:
    cleaned = cloud_redact(url)

    assert "Parol123" not in cleaned
    assert "p%40ss" not in cleaned
    # Xost qoladi: egasi qaysi kamera ekanini tanishi kerak.
    assert "192.168.1.64" in cleaned or "10.0.0.5" in cleaned


def test_streams_are_handed_to_the_browser_by_reference() -> None:
    """Panelga manzil emas, INDEKS ketadi.

    Kamerani saqlashda panel o'sha indeksni qaytaradi va server
    manzilni shifrlangan natijadan o'zi oladi — ya'ni parol brauzerga
    umuman tushmaydi."""
    streams = safe_streams(
        [
            {"name": "Sub", "uri": "rtsp://admin:Parol123@192.168.1.64/sub", "works": True},
            {"name": "Main", "rtsp_url": "rtsp://admin:Parol123@192.168.1.64/main"},
        ]
    )

    assert [item["stream_ref"] for item in streams] == [0, 1]
    assert all("uri" not in item and "rtsp_url" not in item for item in streams)
    assert all("Parol123" not in str(item) for item in streams)
    # Ko'rsatish uchun kerakli maydonlar saqlanadi.
    assert streams[0]["name"] == "Sub"
    assert streams[0]["works"] is True
