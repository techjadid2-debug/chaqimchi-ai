"""Yangi ko'rinish SHARTNOMASI: lenta, kadr holati, soatlik xarita.

Brauzer ishga tushmaydi — manba matni o'qiladi (`test_connect_ui.py`
naqshi).  Maqsad bitta: server tomonda endpoint yoki maydon o'zgarganda
panel jimgina sinib qolmasin, va bir marta tuzatilgan qarorlar qaytib
kelmasin.
"""

from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "frontend" / "src"


def read(name: str) -> str:
    path = SRC / name
    assert path.is_file(), f"{name} topilmadi"
    return path.read_text(encoding="utf-8")


# ── Lenta ────────────────────────────────────────────────────────────────


def test_the_timeline_asks_the_server_to_do_the_counting() -> None:
    """Lenta hodisalarni O'ZI sanamasin.

    Brauzerda sanash `limit=500` bilan olingan kesimdan hisoblash
    degani — ya'ni gavjum kunda ertalabki soatlar bo'sh ko'rinardi.
    """
    source = read("EventTimeline.tsx")

    assert "/api/v1/owner/events/timeline" in source
    assert "limit=500" not in source
    assert "limit=500" not in read("EventEvidence.tsx")


def test_the_timeline_colours_four_meanings_not_fifteen_types() -> None:
    """24 ustunda 15 rang hech narsa aytmaydi."""
    source = read("EventTimeline.tsx")

    assert "TONE_BY_TYPE" in source
    assert 'TONE_ORDER = ["red", "yellow", "grey", "green", "blue"]' in source


def test_an_unknown_event_type_still_reaches_the_timeline() -> None:
    """Ranglar ro'yxatiga yozish esdan chiqsa ham hodisa ko'rinsin —
    faqat rangi betaraf bo'ladi."""
    source = read("EventTimeline.tsx")

    assert '|| "grey"' in source


def test_the_hour_click_actually_changes_the_list() -> None:
    """«Tugma qo'yish yetarli emas — natijani ko'rsatish ham kerak.»

    Soatga bosilganda kartochkalar o'sha soatdan kelishi shart, aks
    holda bosildi-yu hech narsa bo'lmadi degan holat qoladi.
    """
    source = read("EventEvidence.tsx")

    assert "onSelectHour" in source
    assert 'query.set("hour"' in source


# ── Kadr holati ──────────────────────────────────────────────────────────


def test_a_card_without_a_photo_says_why() -> None:
    """To'rt holat — va ular chalkashtirilmasin."""
    source = read("EventEvidence.tsx")

    assert "saqlanmaydi" in source and "maxfiylik qoidasi" in source
    assert "Kadr hali yuklanmagan" in source
    assert "muddati o‘tdi" in source
    assert "Hodisaning o‘zi joyida" in source


def test_the_media_deadline_is_not_hard_coded() -> None:
    """«48» ni panelga yozish — ikki fayldagi ikki son bir-birini inkor
    qilishi tuzog'i.  Muddat serverdan keladi."""
    source = read("EventEvidence.tsx")

    assert "media_retention_hours" in source
    assert "media_retention_hours" in read("types.ts")


def test_the_hour_is_read_from_the_date_not_sliced_from_text() -> None:
    """`formatTimeUz(x).slice(0,2)` — format o'zgarsa raqam jimgina
    buziladi.  Bu yuqorida tuzatilgan xatoning aynan takrori bo'lardi."""
    api = read("api.ts")

    assert "export function tashkentHour" in api
    assert "export function tashkentDay" in api
    for name in ("EventEvidence.tsx", "VisionAgent.tsx", "EventTimeline.tsx"):
        assert "formatTimeUz(" not in read(name) or ".slice(0, 2)" not in read(name)


def test_the_events_page_is_locked_behind_the_business_plan() -> None:
    """Qulf «buzilibdi» emas, «ko'tarish mumkin» degani.

    Oddiy ro'yxat esa qulf ostida QOLMAYDI — hech kim funksiya
    yo'qotmaydi (server tomonda `/owner/events` ga 403 qo'shilmagan).
    """
    source = read("EventEvidence.tsx")

    assert 'hasFeature(dashboard, "xavfsizlik")' in source
    assert "PlanLock" in source
    assert 'onNavigate?.("billing")' in source


def test_the_list_is_paged_so_blobs_do_not_pile_up() -> None:
    """Kadr endi o'zi yuklanadi, ya'ni har kartochka bitta blob."""
    source = read("EventEvidence.tsx")

    assert "const PAGE = 20" in source
    assert "revokeObjectURL" in source


# ── AI yordamchi ─────────────────────────────────────────────────────────


def test_the_agent_marks_its_sources_on_the_same_timeline() -> None:
    source = read("VisionAgent.tsx")

    assert "EventTimeline" in source
    assert "markedHours" in source


def test_the_agent_timeline_is_shown_even_without_sources() -> None:
    """«Hech kim kirmadi» matnining eng qimmatli davomi — o'sha kuni
    NIMA bo'lgani."""
    source = read("VisionAgent.tsx")

    assert "tashkentToday()" in source


def test_the_agent_still_opens_the_evidence() -> None:
    """Tugma nomi va'da qilgan ishni bajarsin — bir marta tuzatilgan."""
    source = read("VisionAgent.tsx")

    assert 'onNavigate("alerts", source.event_id)' in source


def test_the_agent_source_carries_the_raw_event_type() -> None:
    """Rang turdan hisoblanadi; o'zbekcha matndan teskari xarita mo'rt."""
    assert '"event_type": event.get("event_type")' in (
        Path(__file__).resolve().parents[1] / "cloud" / "vision_agent.py"
    ).read_text(encoding="utf-8")


# ── Issiqlik xaritasi ────────────────────────────────────────────────────


def test_the_heat_hours_share_one_scale() -> None:
    """Har soatni o'z cho'qqisiga bo'yash — animatsiyani chiroyli va
    YOLG'ON qilardi: ertalabki uch kishi kechqurungi uch yuz kishi bilan
    bir xil qizil bo'lardi."""
    source = read("Heatmap.tsx")

    assert "hoursAnswer?.peak" in source
    assert "Math.max(1, ...heat.grid.flat())" not in source
    assert "eng gavjum katagiga nisbatan" in source


def test_the_owner_can_stop_the_animation() -> None:
    source = read("Heatmap.tsx")

    assert "To‘xtatish" in source
    assert "clearInterval" in source
    assert "document.hidden" in source


def test_the_slider_does_not_fire_a_request_per_step() -> None:
    """24 soat bitta so'rovda keladi va keshda qoladi."""
    source = read("Heatmap.tsx")

    assert "by=hour" in source
    assert "cache.current" in source


def test_an_empty_hour_is_drawn_empty() -> None:
    """Eski to'r ekranda qolib ketsa ega uni «yangilanmayapti» deb
    o'qiydi."""
    source = read("Heatmap.tsx")

    assert "if (!grid || !rows || !cols) return;" in source
    assert "harakat qayd etilmagan" in source


def test_the_camera_frame_is_loaded_once_not_per_hour() -> None:
    """Preview alohida effektda: aks holda soat o'zgarganda kadr ham
    qaytadan yuklanardi (24 barobar isrof)."""
    source = read("Heatmap.tsx")

    assert "}, [cameraId, siteId]);" in source


@pytest.mark.parametrize("name", ["Heatmap.tsx", "EventTimeline.tsx"])
def test_the_new_screens_live_in_their_own_files(name: str) -> None:
    """`owner.tsx` 742 qator edi — yangi ekranlar uni yana
    shishirmasin.  Naqsh: `Demography.tsx`, `VisionAgent.tsx`."""
    assert (SRC / name).is_file()
    assert "function HeatmapPage" not in read("owner.tsx")
