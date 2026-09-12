"""Kamera joylashuvi yo'riqnomasidagi sonlar koddan ajralib ketmasin.

Nega bu test bor.  `docs/DOKON_MVP.md` «yuz kadri 14 kun yashaydi» deb
yozib turardi, kod esa allaqachon 48 soatga o'tgan edi — hujjat o'z
mahsulotining kontrakti bo'la turib **yolg'on** gapirardi va buni hech
narsa aytmasdi.

`docs/KAMERA_JOYLASHUVI.md` dan ustaning obyektda qabul qiladigan
qarori chiqadi (kamerani qayerga qo'yish, substreamni nechaga qo'yish).
Undagi son eskirsa, xato do'konda qotib qoladi va faqat oylar o'tib,
`face_crops.too_small` dan ko'rinadi.  Shuning uchun hujjat kod bilan
qulflanadi.
"""

from __future__ import annotations

from pathlib import Path

from cloud import config_health
from enes import camera_roles, limits
from enes.retail import nightmode

DOC = Path(__file__).resolve().parents[1] / "docs" / "KAMERA_JOYLASHUVI.md"


def _text() -> str:
    return DOC.read_text(encoding="utf-8")


def test_the_face_crop_numbers_match_the_code() -> None:
    text = _text()

    assert f"FACE_MIN_CROP_PX  = {limits.FACE_MIN_CROP_PX}" in text
    assert f"FACE_CROP_RATIO   = {limits.FACE_CROP_RATIO}" in text
    assert f"**{limits.face_min_bbox_px()} piksel**" in text, (
        "eng kam odam ramkasi — yo'riqnomadagi asosiy son"
    )


def test_the_stream_table_matches_face_id_check() -> None:
    """Jadvaldagi har foiz `face_min_bbox_ratio` dan chiqsin."""
    # Jadvalda ba'zi katak qalin yozilgan (`**38%**`) — belgilar olib tashlanadi.
    text = _text().replace("*", "")

    for height, expected in ((288, 95), (360, 76), (480, 57), (720, 38), (1080, 25)):
        percent = round(limits.face_min_bbox_ratio(height) * 100)
        assert percent == expected, f"{height}p uchun formula {percent}% beradi, jadvalda {expected}%"
        assert f"| {percent}% |" in text, f"{height}p qatori yo'riqnomada yo'q"


def test_the_guide_recommends_the_lowest_stream_that_actually_works() -> None:
    """«720p kerak» — bu taxmin emas, `face_id_check` ning javobi."""
    assert camera_roles.face_id_check(720)[0] is True
    assert camera_roles.face_id_check(480)[0] is False
    assert camera_roles.face_id_check(360)[0] is False

    assert "**720p**" in _text()


def test_the_visible_field_derivation_is_arithmetic() -> None:
    """4,5 metr — 1,70 m bo'yni chegaraga bo'lish natijasi, tanlangan son emas."""
    text = _text()
    ratio = limits.face_min_bbox_ratio(720)

    assert round(1.70 / ratio, 1) == 4.5, "hisob o'zgargan — matnni ham yangilang"
    assert "4,5 metrdan katta" in text
    keng = round(1.70 / limits.face_min_bbox_ratio(1080), 1)
    assert keng == 6.7, "hisob o'zgargan — matnni ham yangilang"
    assert f"{keng} m".replace(".", ",") in text


def test_the_geometry_limits_match_config_health() -> None:
    text = _text()

    assert f"≥ {round(config_health.MIN_LINE_LENGTH * 100)}%" in text
    assert f"≥ {round(config_health.MIN_ZONE_AREA * 100)}%" in text
    assert f"≥ {round(config_health.MIN_ZONE_SIDE * 100)}%" in text
    # 720p dagi piksel qiymatlari — usta aynan shularni ko'radi.
    assert f"≥ {round(config_health.MIN_LINE_LENGTH * 1280)} px" in text
    assert f"≥ {round(config_health.MIN_ZONE_AREA * 1280 * 720):,} px²".replace(",", " ") in text


def test_the_night_thresholds_match_the_code() -> None:
    text = _text()

    assert f"| {nightmode.CHROMA_MAX_IR} |" in text
    assert f"| {nightmode.DARK_BRIGHTNESS} |" in text


def test_the_band_and_camera_count_match_the_code() -> None:
    # Hujjatda son o'zbekcha yoziladi (vergul bilan), koddagisi nuqta bilan.
    text = _text().replace(",", ".")

    assert f"{limits.SEEN_LINE_BAND} masofadagi tasma" in text
    assert f"ko'pi bilan {limits.SHOP_MAX_CAMERAS} kamera" in text
    assert f"{limits.NVR_SCAN_CHANNELS} kanalgacha" in text


def test_every_role_is_documented() -> None:
    """Yangi rol qo'shilsa yo'riqnoma ham yangilansin."""
    text = _text()

    for role in camera_roles.CAMERA_ROLES:
        assert f"`{role}`" in text, f"'{role}' roli yo'riqnomada tushuntirilmagan"
        assert camera_roles.ROLE_LABELS_UZ[role] in text


def test_the_uncalibrated_values_are_admitted() -> None:
    """Sinalmagan chegara «sozlama» bo'lib ko'rinmasin.

    Kalibrlanmagan sonni halol belgilamaslik — mahsulotning eng qattiq
    taqig'i: usta uni «to'g'ri qiymat» deb qabul qiladi.
    """
    text = _text()
    bolim = text.split("Kalibrlanmagan qiymatlar")[-1]

    for name in ("CHROMA_MAX_IR", "DARK_BRIGHTNESS", "NIGHT_MOTION_RATIO", "SEEN_LINE_BAND"):
        assert name in bolim, f"'{name}' kalibrlanmagan ro'yxatida yo'q"


def test_the_guide_does_not_promise_a_resolution_the_code_refuses() -> None:
    """Yo'riqnoma 480p ni «ishlaydi» deb aytmasin."""
    text = _text()
    qator = next(line for line in text.splitlines() if line.startswith("| 480p"))

    assert "imkonsiz" not in qator, "480p imkonsiz emas, chegarada"
    assert "chegarada" in qator
    assert "**ishlaydi**" not in qator


def test_the_substream_rule_is_stated() -> None:
    """Eng ko'p uchraydigan xato — asosiy oqim 4K, substream CIF."""
    text = _text()

    assert "substream" in text.lower()
    assert "1280×720" in text
