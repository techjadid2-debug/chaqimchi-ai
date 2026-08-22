"""Yangilanish qurilmaga yetib bormayotganini FAQAT bulut ko'ra oladi.

Qurilmadagi yangilovchida kamchilik bor: oldingi yangilanish taqdiri
aniqlanmasa u MUDDATSIZ "kutish" holatida qoladi va yangi versiyani
umuman tekshirmaydi (`chaqimchi_ai/local/updater.py`).  Ya'ni tuzatishni
qurilmaga yubora olmaymiz — u aynan yangilanmayapti.

Tashqaridan qaraganda esa manzara aniq: reliz chiqqan, kanal avto,
do'kon onlayn, lekin versiya kunlab o'zgarmayapti.  Jonli holat
(2026-08-22): do'kon 0.6.8 da, bulut 0.6.12 taklif qilyapti — uch reliz
o'tib ketgan va buni hech kim sezmagan.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from cloud.alerts import UPDATE_STUCK_DAYS, plan_update_stuck_alerts


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _stamp(days_ago: float) -> str:
    return (_now() - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")


def _site(
    *,
    connection: str = "online",
    license_status: str = "active",
    update_channel: str = "auto",
    minutes_since_seen: int = 5,
) -> dict:
    return {
        "id": "s1",
        "name": "Do'kon",
        "plan": "biznes",
        "license_status": license_status,
        "connection": connection,
        "minutes_since_seen": minutes_since_seen,
        "update_channel": update_channel,
        "contact_phone": "+998901112233",
    }


def _versions(version: str = "0.6.8", days_ago: float = 5) -> dict:
    return {"s1": {"version": version, "since": _stamp(days_ago)}}


def test_eski_versiyada_qotib_qolgan_dokon_haqida_xabar_beriladi() -> None:
    alerts, _ = plan_update_stuck_alerts([_site()], _versions(), "0.6.12", {})
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.kind == "update" and alert.remember == "stuck"
    assert "0.6.8" in alert.text and "0.6.12" in alert.text
    assert "Do'kon" in alert.text or "Do‘kon" in alert.text


def test_yangi_chiqqan_reliz_darhol_xabar_bermaydi() -> None:
    """Yangilanish yo'lda bo'lishi mumkin — bir necha soat kutiladi."""
    versions = _versions(days_ago=UPDATE_STUCK_DAYS - 1)
    assert plan_update_stuck_alerts([_site()], versions, "0.6.12", {})[0] == []


def test_ayni_versiyadagi_dokon_jim() -> None:
    assert plan_update_stuck_alerts([_site()], _versions("0.6.12"), "0.6.12", {})[0] == []


def test_qotib_qolgan_dokon_haqida_ikki_marta_yozilmaydi() -> None:
    assert plan_update_stuck_alerts([_site()], _versions(), "0.6.12", {"s1": "stuck"})[0] == []


def test_yangilangach_tiklandi_xabari_ketadi() -> None:
    alerts, _ = plan_update_stuck_alerts(
        [_site()], _versions("0.6.12", days_ago=0), "0.6.12", {"s1": "stuck"}
    )
    assert len(alerts) == 1
    assert "yangilandi" in alerts[0].text
    assert alerts[0].remember is None


def test_yangi_reliz_chiqqanda_ikkinchi_xabar_ketmaydi() -> None:
    """Holat sonsiz: 0.6.13 chiqqani o'sha do'kon uchun yangi xabar emas."""
    assert plan_update_stuck_alerts([_site()], _versions(), "0.6.13", {"s1": "stuck"})[0] == []


def test_hold_va_pin_kanallari_kuzatilmaydi() -> None:
    """Do'konni joriy versiyada ushlab turish — bizning qarorimiz."""
    for channel in ("hold", "pin"):
        alerts, _ = plan_update_stuck_alerts(
            [_site(update_channel=channel)], _versions(), "0.6.12", {}
        )
        assert alerts == [], channel


def test_jim_qurilma_haqida_ikkinchi_xabar_ketmaydi() -> None:
    """O'chgan kompyuter yangilana olmaydi; aloqa xabari allaqachon ketgan."""
    site = _site(connection="stale", minutes_since_seen=10 * 60)
    assert plan_update_stuck_alerts([site], _versions(), "0.6.12", {})[0] == []


def test_offline_dokon_kuzatilmaydi() -> None:
    site = _site(connection="offline", minutes_since_seen=30 * 60)
    alerts, forget = plan_update_stuck_alerts([site], _versions(), "0.6.12", {"s1": "stuck"})
    assert alerts == [] and forget == ["s1"]


def test_versiya_vaqti_nomalum_bolsa_jim() -> None:
    """Ustun yangi qo'shilgan — birinchi heartbeat'gacha sana yo'q.

    Shusiz deploy kuni hamma do'kon haqida bir vaqtda xabar ketardi.
    """
    versions = {"s1": {"version": "0.6.8", "since": None}}
    assert plan_update_stuck_alerts([_site()], versions, "0.6.12", {})[0] == []


def test_reliz_yoq_bolsa_jim() -> None:
    assert plan_update_stuck_alerts([_site()], _versions(), None, {})[0] == []


def test_tolovi_toxtagan_dokon_kuzatilmaydi() -> None:
    site = _site(license_status="expired")
    alerts, forget = plan_update_stuck_alerts([site], _versions(), "0.6.12", {"s1": "stuck"})
    assert alerts == [] and forget == ["s1"]
