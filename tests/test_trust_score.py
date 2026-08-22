"""«Ishonch balli» — raqam qachon ko'rsatiladi va qachon YO'Q.

Ballning butun qiymati ishonchda: bir marta "hammasi joyida" deb yolg'on
aytsa, mijoz uni boshqa hech qachon o'qimaydi.  Shuning uchun testlarning
yarmi ballni EMAS, ballning **yo'qligini** tekshiradi.
"""

from __future__ import annotations

from typing import Any, Dict

from cloud.trust_score import label, score

GOOD_REPORT: Dict[str, Any] = {
    "traffic": {"entered": 150, "entered_yesterday": 140},
    "queue": {"alerts": 0, "longest": 0},
    "security": {"camera_tampered": 0, "after_hours_presence": 0, "loitering": 0},
}
GOOD_SHIFTS: Dict[str, Any] = {
    "employees": 2,
    "jami": {"kechikish_daq": 0, "kelmagan_kunlar": 0},
    # `ish_kunlari` SHART: usiz davomat o'lchanmagan deb qaraladi.
    "rows": [{"ish_kunlari": 1}, {"ish_kunlari": 1}],
}


def _score(**overrides: Any) -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {
        "report": GOOD_REPORT,
        "shifts": GOOD_SHIFTS,
        "minutes_since_seen": 2,
        "cameras_active": 4,
        "cameras_expected": 4,
        "queue_configured": True,
    }
    kwargs.update(overrides)
    return score(**kwargs)


# ── Ball KO'RSATILMAYDIGAN holatlar (eng muhim testlar) ──────────────────


def test_a_silent_shop_gets_no_score_at_all() -> None:
    """O'chib qolgan do'kon har kuni "94" ko'rsatib tursa — eng yomon nosozlik.

    Mijoz mahsulot ishlayapti deb o'ylab yuradi, holbuki kompyuter o'chiq.
    Aynan shu 2026-08-22 da bo'lgan: qurilma 19 soat jim turgan.
    """
    result = _score(minutes_since_seen=19 * 60)
    assert result["available"] is False
    assert result["total"] is None
    assert "jim" in result["reason"]


def test_an_unpaired_shop_gets_no_score() -> None:
    result = _score(minutes_since_seen=None)
    assert result["available"] is False
    assert result["total"] is None


def test_no_score_when_every_camera_is_down() -> None:
    """Kamera yo'q — ko'z yo'q.  Bunday kunga ball qo'yish ma'nosiz."""
    result = _score(cameras_active=0, cameras_expected=4)
    assert result["available"] is False
    assert "kamera" in result["reason"].lower()


def test_a_brief_gap_still_scores() -> None:
    """Bir soatlik jimlik normal — internet uzilib turadi, ball qolsin."""
    result = _score(minutes_since_seen=60)
    assert result["available"] is True


# ── O'lchanmagan narsa ballga kirmaydi ──────────────────────────────────


def test_queue_without_a_zone_is_excluded_not_scored_as_perfect() -> None:
    """Zona chizilmasa navbat hodisasi HECH QACHON chiqmaydi.

    Ya'ni "0 ta signal" mukammal navbat emas, "umuman o'lchamayapmiz".
    Uni 20 ball deb hisoblash — ballning eng jimgina yolg'oni bo'lardi.
    """
    result = _score(queue_configured=False)
    queue = next(item for item in result["parts"] if item["code"] == "queue")
    assert queue["measured"] is False
    assert queue["points"] is None
    assert "chizilmagan" in queue["note"]
    # Qolgan to'rt qism a'lo — demak ball baribir 100 bo'lishi kerak,
    # navbat "bepul 20 ball" sifatida qo'shilmagani uchun emas.
    assert result["total"] == 100


def test_a_shop_without_employees_is_not_punished() -> None:
    result = _score(shifts=None)
    staff = next(item for item in result["parts"] if item["code"] == "staff")
    assert staff["measured"] is False
    assert result["total"] == 100


# ── Ball haqiqatan tushishi kerak bo'lgan holatlar ───────────────────────


def test_a_perfect_day_scores_high() -> None:
    result = _score()
    assert result["total"] == 100
    assert label(result["total"]) == "A'lo kun"


def test_a_tampered_camera_pulls_the_score_down_hard() -> None:
    """Kamera buzilishi — o'g'rilikning birinchi qadami, ball buni ko'rsatsin."""
    report = {**GOOD_REPORT, "security": {"camera_tampered": 1}}
    result = _score(report=report)
    assert result["total"] < 90
    security = next(item for item in result["parts"] if item["code"] == "security")
    assert security["points"] == 4


def test_half_the_cameras_down_halves_that_part() -> None:
    result = _score(cameras_active=2, cameras_expected=4)
    cameras = next(item for item in result["parts"] if item["code"] == "cameras")
    assert cameras["points"] == 10
    assert "2 tasi o'chiq" in cameras["note"]


def test_a_collapse_in_traffic_is_a_warning_not_a_good_day() -> None:
    """Mijoz oqimi yarmiga tushsa — eshik yopiq yoki kamera burilgan."""
    report = {**GOOD_REPORT, "traffic": {"entered": 40, "entered_yesterday": 140}}
    result = _score(report=report)
    traffic = next(item for item in result["parts"] if item["code"] == "traffic")
    assert traffic["points"] == 3
    assert result["total"] < 75


def test_growth_is_never_punished() -> None:
    report = {**GOOD_REPORT, "traffic": {"entered": 300, "entered_yesterday": 140}}
    traffic = next(
        item for item in _score(report=report)["parts"] if item["code"] == "traffic"
    )
    assert traffic["points"] == 20


def test_a_day_with_no_customers_at_all_is_not_a_perfect_day() -> None:
    """Bugun 0, kecha 140 — bu "tinch kun" emas, bu nosozlik."""
    report = {**GOOD_REPORT, "traffic": {"entered": 0, "entered_yesterday": 140}}
    traffic = next(
        item for item in _score(report=report)["parts"] if item["code"] == "traffic"
    )
    assert traffic["points"] == 0


def test_absent_staff_shows_up_in_the_score() -> None:
    shifts = {
        "employees": 2,
        "jami": {"kechikish_daq": 0, "kelmagan_kunlar": 1},
        "rows": [{"ish_kunlari": 1}, {"ish_kunlari": 1}],
    }
    staff = next(item for item in _score(shifts=shifts)["parts"] if item["code"] == "staff")
    assert staff["points"] == 4
    assert "kelmadi" in staff["note"]


def test_label_never_calls_a_bad_day_good() -> None:
    assert label(None) == "Ma'lumot yo'q"
    assert label(40) == "Muammo bor"
    assert label(60) == "E'tibor talab qiladi"
    assert label(80) == "Yaxshi kun"


def test_one_serious_problem_is_not_averaged_away() -> None:
    """To'rt qism a'lo bo'lsa ham, bitta jiddiy muammo kunni "yaxshi" qilmaydi.

    Bu chegara testda topilgan: oqim 140 dan 40 ga tushgan kun o'rtacha
    hisobda 83 — "yaxshi kun" chiqardi, holbuki do'kon egasi uchun kunning
    eng muhim xabari aynan o'sha tushish edi.
    """
    report = {**GOOD_REPORT, "traffic": {"entered": 40, "entered_yesterday": 140}}
    result = _score(report=report)
    assert result["total"] == 70
    assert label(result["total"]) == "E'tibor talab qiladi"

    tampered = {**GOOD_REPORT, "security": {"camera_tampered": 1}}
    assert _score(report=tampered)["total"] == 70


def test_the_cap_does_not_punish_an_ordinary_dip() -> None:
    """Odatdagi 20% tushish jiddiy muammo emas — cheklov ishlamasin."""
    report = {**GOOD_REPORT, "traffic": {"entered": 112, "entered_yesterday": 140}}
    result = _score(report=report)
    assert result["total"] > 70


def test_staff_without_a_schedule_is_not_scored_as_punctual() -> None:
    """Ish kuni belgilanmagan bo'lsa nol kechikish nol O'LCHOVdan keladi.

    Jonli pilotda aynan shu holat topildi: bitta xodim bor, rasmi yo'q,
    `ish_kunlari: 0` — ball esa "Hammasi vaqtida keldi, 20/20" derdi.
    """
    shifts = {
        "employees": 1,
        "jami": {"kechikish_daq": 0, "kelmagan_kunlar": 0},
        "rows": [{"employee_name": "Abduvohid", "ish_kunlari": 0}],
    }
    staff = next(item for item in _score(shifts=shifts)["parts"] if item["code"] == "staff")
    assert staff["measured"] is False
    assert "jadval" in staff["note"]


def test_staff_with_a_schedule_is_scored() -> None:
    shifts = {
        "employees": 1,
        "jami": {"kechikish_daq": 0, "kelmagan_kunlar": 0},
        "rows": [{"employee_name": "Aziz", "ish_kunlari": 1}],
    }
    staff = next(item for item in _score(shifts=shifts)["parts"] if item["code"] == "staff")
    assert staff["measured"] is True
    assert staff["points"] == 20
