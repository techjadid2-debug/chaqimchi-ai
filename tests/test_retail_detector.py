"""OpenVINO SSD chiqishini dekodlash.

Dekodlash sof mantiq — OpenVINO o'rnatilmagan mashinada ham tekshiriladi.
Modelning o'zi qurilmada, lekin format xatosi bu yerda tutiladi.
"""

from __future__ import annotations

import numpy as np
import pytest

from chaqimchi_ai.retail.detector_ov import INPUT_HEIGHT, INPUT_WIDTH, decode_ssd_output


def ssd(*rows) -> np.ndarray:
    """`(1, 1, N, 7)` shaklidagi model chiqishini yasaydi."""
    return np.array([[list(rows)]], dtype=np.float32)


def row(conf: float, box, image_id: float = 0.0, label: float = 1.0):
    return [image_id, label, conf, *box]


def test_normalized_boxes_become_pixels() -> None:
    raw = ssd(row(0.9, [0.25, 0.5, 0.5, 1.0]))

    detections = decode_ssd_output(raw, width=640, height=360, confidence=0.5)

    assert len(detections) == 1
    assert detections[0]["bbox"] == pytest.approx([160.0, 180.0, 320.0, 360.0])
    assert detections[0]["score"] == pytest.approx(0.9)


def test_low_confidence_rows_are_dropped() -> None:
    raw = ssd(row(0.9, [0.1, 0.1, 0.2, 0.4]), row(0.3, [0.5, 0.1, 0.6, 0.4]))
    assert len(decode_ssd_output(raw, width=640, height=360, confidence=0.5)) == 1


def test_padding_rows_are_ignored() -> None:
    """Model bo'sh qatorlarni `image_id = -1` bilan to'ldiradi."""
    raw = ssd(
        row(0.9, [0.1, 0.1, 0.2, 0.4]),
        row(0.0, [0.0, 0.0, 0.0, 0.0], image_id=-1.0, label=0.0),
        row(0.99, [0.0, 0.0, 1.0, 1.0], image_id=-1.0, label=0.0),
    )
    detections = decode_ssd_output(raw, width=640, height=360, confidence=0.5)
    assert len(detections) == 1


def test_boxes_are_clipped_to_the_frame() -> None:
    """Model kadrdan chiqib ketgan ramka qaytarishi mumkin."""
    raw = ssd(row(0.9, [-0.2, -0.1, 1.3, 1.2]))

    bbox = decode_ssd_output(raw, width=640, height=360, confidence=0.5)[0]["bbox"]

    assert bbox == pytest.approx([0.0, 0.0, 640.0, 360.0])


def test_degenerate_boxes_are_dropped() -> None:
    raw = ssd(
        row(0.9, [0.5, 0.5, 0.5, 0.8]),   # nol kenglik
        row(0.9, [0.2, 0.9, 0.4, 0.2]),   # teskari koordinata
        row(0.9, [1.2, 0.1, 1.4, 0.4]),   # kadrdan tashqarida
    )
    assert decode_ssd_output(raw, width=640, height=360, confidence=0.5) == []


def test_empty_and_malformed_output_is_safe() -> None:
    assert decode_ssd_output(np.zeros((1, 1, 0, 7), dtype=np.float32),
                             width=640, height=360, confidence=0.5) == []
    # 7 ga bo'linmaydigan shakl — model almashib ketgan bo'lsa jim
    # ishlamasdan bo'sh qaytaradi (crash emas, noto'g'ri natija ham emas).
    assert decode_ssd_output(np.zeros((5,), dtype=np.float32),
                             width=640, height=360, confidence=0.5) == []


def test_flat_output_shape_is_accepted() -> None:
    """Ba'zi runtime versiyalari `(N, 7)` qaytaradi."""
    raw = np.array([[0.0, 1.0, 0.9, 0.1, 0.1, 0.2, 0.4]], dtype=np.float32)
    assert len(decode_ssd_output(raw, width=640, height=360, confidence=0.5)) == 1


def test_preprocess_produces_the_documented_tensor_shape() -> None:
    from chaqimchi_ai.retail.detector_ov import OpenVINOPersonDetector

    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    tensor = OpenVINOPersonDetector.preprocess(frame)

    assert tensor.shape == (1, 3, INPUT_HEIGHT, INPUT_WIDTH)
    assert tensor.dtype == np.float32


def test_missing_model_file_fails_before_importing_openvino(tmp_path) -> None:
    """Yo'q fayl uchun xato aniq bo'lsin, OpenVINO importi haqida emas."""
    from chaqimchi_ai.retail.detector_ov import OpenVINOPersonDetector

    with pytest.raises(FileNotFoundError, match="topilmadi"):
        OpenVINOPersonDetector(tmp_path / "yoq.xml")
