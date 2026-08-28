"""Yuz kadri chegaralari bir-birini INKOR QILMASIN.

Bu fayl bitta savolga javob beradi: `scene_analytics` yuz kadri olishga
ruxsat bergan eng kichik odam ramkasidan olingan kesma `pipeline` ning
chegarasidan **o'tadimi**?

Nega alohida fayl kerak bo'ldi.  Ikki chegara ikki modulda alohida
yozilgan edi va ular zid bo'lib qolgan:

    scene_analytics: ramka balandligi >= 0.28 * 360 = 101 px
    pipeline:        kesma = 0.35 * 101 = 35 px, talab >= 96 px

Ya'ni 640x360 oqimda chegara **hech qachon** o'tolmasdi.  1 835 test
o'tib turgan holda davomat oylab ishlamadi va sabab telemetriyada ham
ko'rinmadi — 2026-08-28 da jonli qurilmadan o'qilgan raqam buni
oshkor qildi: `face_crops: {written: 0, too_small: 93}`.

Xato modul ICHIDA emas, ikki modul ORASIDA edi.  Shuning uchun test
ham modulni emas, ularning kelishuvini tekshiradi.
"""

from __future__ import annotations

import numpy as np
import pytest

from chaqimchi_ai import limits
from chaqimchi_ai.retail import pipeline

#: Amalda uchraydigan tahlil oqimlari.  360p — sinov do'konining
#: bugungi holati; 720p — kelishilgan keyingi qadam.
FRAME_SIZES = [(640, 360), (1280, 720), (1920, 1080)]


def _crop_size(bbox: tuple[int, int, int, int], frame: tuple[int, int]) -> tuple[int, int]:
    """`pipeline._attach_face_crop` bilan bir xil hisob.

    Formulani ko'chirib yozish ataylab: agar kesish mantig'i o'zgarsa
    quyidagi testlar tushib qolsin va kimdir buni QAYTA o'ylab ko'rsin.
    """
    width, height = frame
    x1, y1, x2, y2 = bbox
    margin = int((x2 - x1) * 0.10)
    top = max(0, y1)
    bottom = min(height, y1 + max(1, int((y2 - y1) * limits.FACE_CROP_RATIO)))
    left = max(0, x1 - margin)
    right = min(width, x2 + margin)
    return (bottom - top, right - left)


@pytest.mark.parametrize("frame", FRAME_SIZES)
def test_the_smallest_allowed_person_still_yields_a_usable_crop(frame) -> None:
    """Ruxsat berilgan eng kichik ramka kesmasi chegaradan O'TSIN.

    Aynan shu tekshiruv bo'lganida davomat nosozligi bir kunda
    topilardi, oy o'tib jonli bazadan emas.
    """
    width, height = frame
    ratio = limits.face_min_bbox_ratio(height)
    if ratio > 1.0:
        pytest.skip(f"{height}p oqimda yuz kadri printsipial mumkin emas (ratio {ratio:.2f})")

    # Detektor butun piksel beradi; chegaradagi eng kichik ramka.
    bbox_height = limits.face_min_bbox_px()
    # Tik turgan odam: eni bo'yining ~40% i (`person-detection-retail-0013`
    # chiqishidagi odatiy nisbat).
    bbox_width = int(round(bbox_height * 0.40))
    x1 = (width - bbox_width) // 2
    y1 = (height - bbox_height) // 2
    crop_height, crop_width = _crop_size((x1, y1, x1 + bbox_width, y1 + bbox_height), frame)

    assert crop_height >= limits.FACE_MIN_CROP_PX, (
        f"{width}x{height}: ruxsat berilgan eng kichik ramkadan {crop_height} px "
        f"kesma chiqdi, {limits.FACE_MIN_CROP_PX} px kerak — chegaralar zid"
    )
    assert crop_width >= limits.FACE_MIN_CROP_PX, (
        f"{width}x{height}: kesma eni {crop_width} px, {limits.FACE_MIN_CROP_PX} px kerak"
    )


def test_a_360p_stream_demands_an_unrealistic_person() -> None:
    """360p da odam kadr balandligining ~76% ini egallashi kerak.

    Bu amalda "kameraga tegay deb turgan odam" degani.  Chegara
    yashirilmaydi: tizim endi 93 marta urinib 93 marta tashlamaydi,
    balki umuman urinmaydi — protsessor ham, cloud byudjeti ham
    bekorga sarflanmaydi.
    """
    assert limits.face_min_bbox_ratio(360) > 0.7


def test_720p_makes_attendance_reachable() -> None:
    """720p da chegara amalda erishiladigan darajaga tushadi.

    0.38 — odam kadr balandligining 38% ini egallashi, ya'ni kirish
    kamerasidan ~2-3 metr.  Bu do'kon eshigi uchun odatiy masofa.
    """
    ratio = limits.face_min_bbox_ratio(720)
    assert 0.3 < ratio < 0.45, ratio


def test_an_unknown_frame_size_never_takes_a_crop() -> None:
    """Kadr o'lchami noma'lum bo'lsa jim turiladi, taxmin qilinmaydi."""
    assert limits.face_min_bbox_ratio(0) == 1.0
    assert limits.face_min_bbox_ratio(-1) == 1.0


def test_pipeline_and_limits_share_one_number() -> None:
    """Ikki modul bitta manbadan o'qisin — ular ajralib ketgan edi."""
    assert pipeline.FACE_MIN_CROP_PX is limits.FACE_MIN_CROP_PX


def test_the_crop_helper_matches_the_real_pipeline(tmp_path) -> None:
    """Yuqoridagi hisob `_attach_face_crop` bilan mos ekanini tekshiradi.

    Test o'z formulasini tekshirib qolmasin: bu yerda haqiqiy metod
    chaqiriladi va yozilgan rasm o'lchami solishtiriladi.
    """
    width, height = 1280, 720
    bbox_height = limits.face_min_bbox_px()
    bbox_width = int(round(bbox_height * 0.40))
    x1 = (width - bbox_width) // 2
    y1 = (height - bbox_height) // 2
    bbox = (x1, y1, x1 + bbox_width, y1 + bbox_height)

    written: dict = {}

    def writer(path, frame) -> bool:
        written["shape"] = frame.shape[:2]
        return True

    engine = pipeline.RetailPipeline.__new__(pipeline.RetailPipeline)
    engine.snapshot_dir = tmp_path
    engine.snapshot_writer = writer
    engine._lock = __import__("threading").Lock()
    engine._totals = pipeline._Totals()
    camera = type("Camera", (), {"last_frame": np.zeros((height, width, 3), dtype=np.uint8)})()
    engine._cameras = {"camera-01": camera}

    from chaqimchi_ai.event_models import EdgeEvent

    event = EdgeEvent(
        event_type="face_captured",
        camera_id="camera-01",
        occurred_at="2026-08-28T10:00:00+00:00",
        metadata={"bbox": list(bbox)},
    )

    assert engine._attach_face_crop(event, camera_id="camera-01") is True
    assert written["shape"] == _crop_size(bbox, (width, height))
