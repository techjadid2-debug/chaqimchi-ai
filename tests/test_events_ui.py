"""Yangi ko'rinish SHARTNOMASI: lenta, kadr holati, soatlik xarita.

Brauzer ishga tushmaydi — manba matni o'qiladi (`test_connect_ui.py`
naqshi).  Maqsad bitta: server tomonda endpoint yoki maydon o'zgarganda
panel jimgina sinib qolmasin, va bir marta tuzatilgan qarorlar qaytib
kelmasin.
"""

from pathlib import Path

import pytest

from cloud.i18n import tg

SRC = Path(__file__).resolve().parents[1] / "frontend" / "src"


def key_text(source: str, key: str) -> str:
    """Manba KALITGA bog'langanini tekshiradi va o'zbekcha matnini qaytaradi.

    Matn katalogga ko'chdi (F4c): testlar endi "shu jumla manbada bormi"
    emas, "manba shu kalitni ishlatadimi va kalit shu ma'noni beradimi"
    deb so'raydi — tarjima tahriri testga tegmaydi, kalit yo'qolsa
    yiqiladi.
    """
    assert f'"{key}"' in source, f"{key} manbada ishlatilmagan"
    text = tg("uz", key)
    assert text != key, f"katalogda {key} yo'q"
    return text


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

    not_kept = key_text(source, "panel.evidence.media_not_kept")
    assert "saqlanmaydi" in not_kept and "maxfiylik qoidasi" in not_kept
    assert "Kadr hali yuklanmagan" in key_text(source, "panel.evidence.media_pending")
    assert "muddati o‘tdi" in key_text(source, "panel.evidence.media_expired")
    assert "Hodisaning o‘zi joyida" in key_text(source, "panel.evidence.media_expired_kept")


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
    yo'qotmaydi: server tomonda `/owner/events` ga MARSHRUT darajasida
    403 qo'yilmagan.  2026-09-10 da unga biometrik darvoza qo'shildi,
    lekin ataylab turga: menejer yuz hodisalarini ko'rmaydi, qolgan
    ro'yxat esa unga o'zgarishsiz keladi
    (`tests/test_cloud_faces.py: test_a_manager_keeps_the_evidence_page_...`).
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
    assert "eng gavjum katagiga nisbatan" in key_text(source, "panel.heat.scale_note")


def test_the_owner_can_stop_the_animation() -> None:
    source = read("Heatmap.tsx")

    assert "To‘xtatish" in key_text(source, "panel.heat.pause")
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
    assert "harakat qayd etilmagan" in key_text(source, "panel.heat.hour_empty")


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


# ── Raqamlar kartasi (chek, konversiya, eshik) ───────────────────────────


def test_the_panel_does_not_compute_the_conversion_itself() -> None:
    """«Kichik namunadan foiz chiqarmang» qoidasi BITTA joyda tursin.

    Panel foizni o'zi hisoblasa, u serverdagi chegaradan (20 tashrif)
    bexabar qoladi va o'sha kun haqida Telegram xabari bilan ikki xil
    gapiradi.  Shuning uchun `percent` faqat serverdan olinadi.
    """
    source = read("Numbers.tsx")

    assert "conversion.percent" in source
    # Foizni chiqarishning ikkala tabiiy yo'li ham yopiladi.  (Eshik
    # ustunining `* 100` i — CSS kengligi, foiz emas.)
    assert "/ conversion.entered" not in source
    assert "receipts /" not in source


def test_a_day_without_receipts_is_shown_as_empty_not_zero() -> None:
    """Nol «hech kim sotib olmadi» degani; kiritilmagan kun «ma'lumot yo'q»."""
    source = read("Numbers.tsx")

    assert "Chek soni kiritilmagan" in key_text(source, "panel.numbers.no_receipts")


def test_a_small_day_shows_numbers_instead_of_a_percentage() -> None:
    source = read("Numbers.tsx")

    assert "foiz uchun kam" in key_text(source, "panel.numbers.without_percent")


def test_an_old_day_says_the_door_split_was_not_stored() -> None:
    """Deploydan oldingi kunlarda kalit YO'Q — nol ko'rsatish yolg'on."""
    source = read("Numbers.tsx")

    assert "doors === undefined" in source
    assert "eshik taqsimoti saqlanmagan" in key_text(source, "panel.numbers.doors_missing")


def test_the_door_bars_share_one_scale() -> None:
    """Har qatorni o'zicha to'ldirish yon eshikni asosiy eshik bilan
    teng ko'rsatardi — issiqlik xaritasidagi bilan bir xil tuzoq."""
    source = read("Numbers.tsx")

    assert "Math.max(...doors.map" in source


def test_the_receipt_count_can_be_entered_from_telegram_too() -> None:
    """Ega kechqurun hisobotni Telegramda o'qiydi — panelga kirish shart
    emasligi o'sha yerda aytilsin."""
    source = read("Numbers.tsx")

    assert "/chek 100" in source


def test_the_numbers_card_lives_in_its_own_file() -> None:
    assert (SRC / "Numbers.tsx").is_file()
    assert "function ReceiptsBlock" not in read("owner.tsx")
    assert "<Numbers " in read("owner.tsx")
