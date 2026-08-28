"""Support paketi cloudga O'ZI yetib borsin.

Nega bu test bor.  Diagnostika paketi uzoq vaqt "bor" edi: qurilmada
yig'uvchi funksiya (`cloud_config.diagnostics_report`), cloudda
endpoint (`POST /api/v1/edge/diagnostics`), jadval, 14 kunlik
retention va admin panelida ko'rinishi — hammasi yozilgan.

2026-08-28 da jonli bazadan o'qilganda `device_diagnostics` jadvalida
**0 qator** bo'lib chiqdi.  Sabab oddiy: paketni yuboradigan yagona yo'l
do'kon kompyuteridagi lokal paneldagi tugma edi va uni hech kim
bosmagan.  Ya'ni nosozlik "ishlamayapti" ko'rinishida emas — kod
to'g'ri, faqat hech qachon CHAQIRILMAGAN.

Shuning uchun test funksiyani emas, uning **o'zi ishga tushishini**
tekshiradi.
"""

from __future__ import annotations

from pathlib import Path

from chaqimchi_ai.local import cloud_config


def _reset() -> None:
    cloud_config._last_diagnostics_at = None


def test_the_first_heartbeat_sends_the_packet(monkeypatch) -> None:
    _reset()
    calls: list[int] = []
    monkeypatch.setattr(
        cloud_config, "upload_diagnostics", lambda: calls.append(1) or {"ok": True}
    )

    assert cloud_config.upload_diagnostics_if_due(now=0.0) is True
    assert calls == [1]


def test_it_does_not_repeat_within_a_day(monkeypatch) -> None:
    """Paket katta — har 20 soniyada yuborish tarmoqni bekorga yuklaydi."""
    _reset()
    calls: list[int] = []
    monkeypatch.setattr(
        cloud_config, "upload_diagnostics", lambda: calls.append(1) or {"ok": True}
    )

    cloud_config.upload_diagnostics_if_due(now=0.0)
    assert cloud_config.upload_diagnostics_if_due(now=3600.0) is False
    assert cloud_config.upload_diagnostics_if_due(now=cloud_config.DIAGNOSTICS_INTERVAL_SEC - 1) is False
    assert len(calls) == 1


def test_it_sends_again_after_a_day(monkeypatch) -> None:
    _reset()
    calls: list[int] = []
    monkeypatch.setattr(
        cloud_config, "upload_diagnostics", lambda: calls.append(1) or {"ok": True}
    )

    cloud_config.upload_diagnostics_if_due(now=0.0)
    assert cloud_config.upload_diagnostics_if_due(now=cloud_config.DIAGNOSTICS_INTERVAL_SEC) is True
    assert len(calls) == 2


def test_a_failed_upload_is_retried_not_postponed_for_a_day(monkeypatch) -> None:
    """Bitta tarmoq uzilishi paketni bir kunga kechiktirmasin.

    Soat faqat MUVAFFAQIYATDA suriladi.  Aks holda internet o'chgan
    daqiqaga to'g'ri kelgan urinish "yuborildi" deb hisoblanardi va
    support yana bo'sh jadval ko'rardi.
    """
    _reset()
    results = [{"ok": False, "error": "tarmoq yo'q"}, {"ok": True}]
    monkeypatch.setattr(cloud_config, "upload_diagnostics", lambda: results.pop(0))

    assert cloud_config.upload_diagnostics_if_due(now=0.0) is False
    assert cloud_config.upload_diagnostics_if_due(now=1.0) is True


def test_a_disconnected_device_does_not_crash_the_sync_loop() -> None:
    """Cloud ulanmagan bo'lsa ham halqa yiqilmasin."""
    _reset()

    assert cloud_config.upload_diagnostics_if_due(now=0.0) is False


def test_the_sync_loop_actually_calls_it() -> None:
    """Eng muhim tekshiruv: chaqiruv HALQADA bormi.

    Funksiya to'g'ri yozilgani yetarli emas edi — aynan shu sababdan
    jadval oylab bo'sh turdi.
    """
    source = (
        Path(__file__).resolve().parents[1] / "chaqimchi_ai" / "local" / "app.py"
    ).read_text(encoding="utf-8")

    assert "upload_diagnostics_if_due()" in source, (
        "diagnostika paketi fon halqasida chaqirilmayapti — "
        "`device_diagnostics` jadvali yana bo'sh qoladi"
    )
