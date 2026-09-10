"""Telegram uchun grafik rasmlar (`cloud/chartimg.py`).

Rasm — xabarning birinchi ekrani.  Testlar uch narsani qulflaydi: rasm
haqiqatan PNG/JPEG va o'lchami me'yorida; uch tilda ham chiziladi
(kirillcha yozuv uchun repo ichidagi shrift); bo'sh hisobot va buzuq
kadr xabarni yiqitmaydi.
"""

from __future__ import annotations

from io import BytesIO

import pytest

from cloud import chartimg

PNG = b"\x89PNG\r\n\x1a\n"
JPEG = b"\xff\xd8"


def _report(entered: int = 120) -> dict:
    hourly = [{"hour": hour, "entered": 0, "exited": 0} for hour in range(24)]
    hourly[10]["entered"] = entered
    hourly[18]["exited"] = 40
    return {
        "date": "2026-09-10",
        "traffic": {"entered": entered, "exited": 40, "hourly": hourly, "busiest_hour": {"hour": 10, "entered": entered}},
    }


def _trend() -> dict:
    return {
        "from": "2026-09-01",
        "to": "2026-09-07",
        "days": 7,
        "total": 700,
        "previous_total": 630,
        "change_percent": 11.1,
        "daily": [{"date": f"2026-09-0{day}", "weekday": "x", "entered": 100} for day in range(1, 8)],
    }


@pytest.mark.parametrize("lang", ["uz", "ru", "en"])
def test_daily_chart_is_a_png_in_every_language(lang: str) -> None:
    data = chartimg.daily_png(_report(), lang, site_name="Oq Saroy")
    assert data.startswith(PNG)
    assert len(data) < chartimg.MAX_BYTES


@pytest.mark.parametrize("lang", ["uz", "ru", "en"])
def test_weekly_chart_is_a_png_in_every_language(lang: str) -> None:
    data = chartimg.weekly_png(_trend(), lang, site_name="Oq Saroy")
    assert data.startswith(PNG)
    assert len(data) < chartimg.MAX_BYTES


def test_the_font_covers_cyrillic() -> None:
    """Rus tilidagi a'zo bo'sh to'rtburchaklar emas, harflar olsin.

    DejaVu Sans'da kirill bor; `.notdef` glifi bo'lsa matn kengligi
    boshqacha chiqadi — shuni tekshiramiz.
    """
    from PIL import ImageFont

    font = ImageFont.truetype(str(chartimg.FONT_BOLD), 20)
    assert font.getlength("Вошли") > 0
    assert font.getmask("Вошли").getbbox() is not None
    assert chartimg.FONT_REGULAR.exists() and chartimg.FONT_BOLD.exists()


def test_empty_report_still_renders() -> None:
    """Sokin kun — rasm baribir chiziladi, yiqilmaydi."""
    report = {"date": "2026-09-10", "traffic": {"entered": 0, "exited": 0, "hourly": [], "busiest_hour": None}}
    assert chartimg.daily_png(report, "uz").startswith(PNG)
    assert chartimg.weekly_png({"daily": [], "total": 0}, "uz").startswith(PNG)


def test_snapshot_annotation_keeps_a_jpeg_and_survives_garbage() -> None:
    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (640, 360), "#333333").save(buffer, format="JPEG")
    original = buffer.getvalue()

    annotated = chartimg.annotate_snapshot(original, "23:41", "Kassa")
    assert annotated.startswith(JPEG)
    assert annotated != original
    assert Image.open(BytesIO(annotated)).size == (640, 360)

    # Buzuq kadr — asl baytlar qaytadi, xabar yetib boradi.
    assert chartimg.annotate_snapshot(b"not-a-jpeg", "23:41") == b"not-a-jpeg"
