import cv2
import numpy as np
import pytest

from chaqimchi_ai.antispoof import (
    HeuristicBackend,
    _moire_peakiness,
    build_checker,
    check_liveness,
    get_checker,
    reset_checker_cache,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    reset_checker_cache()
    yield
    reset_checker_cache()


def _texture(size: int = 200, seed: int = 0) -> np.ndarray:
    """Tirik yuzga o'xshash silliq, davriy bo'lmagan tekstura."""
    rng = np.random.default_rng(seed)
    base = rng.integers(60, 200, (size // 8, size // 8, 3), dtype=np.uint8)
    img = cv2.resize(base, (size, size), interpolation=cv2.INTER_CUBIC)
    noise = rng.normal(0, 14, img.shape)
    return np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)


def _add_screen_grid(img: np.ndarray, period: int = 3) -> np.ndarray:
    """Ekran piksel panjarasini qo'shish."""
    out = img.astype(np.float32).copy()
    out[::period, :, :] *= 0.72
    out[:, ::period, :] *= 0.85
    return np.clip(out, 0, 255).astype(np.uint8)


# ── Kirish tekshiruvi ────────────────────────────────────────────────────


def test_rejects_empty_and_none() -> None:
    assert check_liveness(None)["live"] is False
    assert check_liveness(np.zeros((0, 0, 3), dtype=np.uint8))["live"] is False


def test_rejects_too_small_face() -> None:
    r = check_liveness(_texture(20), min_size=40)
    assert r["live"] is False
    assert r["method"] == "too_small"
    assert "kichik" in r["reason"]


def test_rejects_blank_image() -> None:
    # Tekis qora — Laplacian dispersiyasi 0, qattiq chegaradan o'tmaydi.
    r = check_liveness(np.zeros((80, 80, 3), dtype=np.uint8), min_blur_variance=80.0)
    assert r["live"] is False


# ── Moiré signali ────────────────────────────────────────────────────────


def test_moire_peakiness_rises_with_screen_grid() -> None:
    """Panjara qo'shilganda spektr cho'qqisi sezilarli ko'tarilishi kerak."""
    img = _texture(200)
    clean = _moire_peakiness(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    grid = _moire_peakiness(cv2.cvtColor(_add_screen_grid(img), cv2.COLOR_BGR2GRAY))
    assert grid > clean + 2.0, f"toza={clean:.2f} panjara={grid:.2f}"


def test_screen_grid_lowers_liveness_score() -> None:
    backend = HeuristicBackend(min_blur_variance=10.0)
    img = _texture(200)
    clean = backend.check(img)
    spoofed = backend.check(_add_screen_grid(img))
    assert spoofed.score < clean.score
    assert spoofed.signals["moire"] < clean.signals["moire"]


def test_sharpness_is_not_a_positive_vote() -> None:
    """Panjara Laplacian dispersiyasini oshiradi — bu ballni ko'tarmasligi shart."""
    backend = HeuristicBackend(min_blur_variance=10.0)
    img = _texture(200)
    spoofed = _add_screen_grid(img)
    assert (
        backend.check(spoofed).signals["blur_variance"]
        > backend.check(img).signals["blur_variance"]
    )
    assert "sharpness" not in backend.WEIGHTS


# ── Boshqa signallar ─────────────────────────────────────────────────────


def test_specular_penalises_blown_highlights() -> None:
    backend = HeuristicBackend(min_blur_variance=10.0)
    img = _texture(200)
    glared = img.copy()
    glared[:60, :60] = 255  # keng to'yingan porlash dog'i
    assert backend.check(glared).signals["specular"] < backend.check(img).signals["specular"]


def test_chroma_penalises_flat_colour() -> None:
    backend = HeuristicBackend(min_blur_variance=10.0)
    img = _texture(200)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    hsv[:, :, 1] = 40  # to'yinganlik butunlay tekis
    flat = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    assert backend.check(flat).signals["chroma"] < backend.check(img).signals["chroma"]


def test_hard_blur_floor_overrides_other_signals() -> None:
    backend = HeuristicBackend(min_blur_variance=1e9)  # hech qachon o'tmaydigan chegara
    r = backend.check(_texture(200))
    assert r.live is False
    assert "xira" in r.reason


# ── Backend tanlash ──────────────────────────────────────────────────────


def test_build_checker_defaults_to_heuristic() -> None:
    assert build_checker().method == "heuristic_multi"


def test_onnx_backend_falls_back_when_model_missing(tmp_path) -> None:
    checker = build_checker(backend="onnx", model_path=tmp_path / "yo-q.onnx")
    assert checker.method == "heuristic_multi"


def test_onnx_backend_falls_back_when_path_not_given() -> None:
    assert build_checker(backend="onnx", model_path=None).method == "heuristic_multi"


def test_get_checker_is_cached() -> None:
    a = get_checker(backend="heuristic", min_score=0.5)
    b = get_checker(backend="heuristic", min_score=0.5)
    c = get_checker(backend="heuristic", min_score=0.7)
    assert a is b
    assert a is not c


def test_check_liveness_uses_supplied_checker() -> None:
    strict = HeuristicBackend(min_blur_variance=10.0, min_score=1.01)  # hech narsa o'tmaydi
    lenient = HeuristicBackend(min_blur_variance=10.0, min_score=0.0)
    img = _texture(200)
    assert check_liveness(img, checker=strict)["live"] is False
    assert check_liveness(img, checker=lenient)["live"] is True


# ── ONNX backend (sintetik model bilan) ──────────────────────────────────


def _write_toy_onnx(path, *, live_index_wins: bool, n_classes: int = 3):
    """Kirishning o‘rtachasiga qarab sinf tanlaydigan eng sodda ONNX model.

    Rasm yorug‘ bo‘lsa `live_index_wins` sinfi g‘olib chiqadi — shu orqali
    preprocess, softmax va chegara mantig‘ini tekshiramiz.
    """
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    # logits = W @ mean(input) ko'rinishida: global o'rtacha → Gemm.
    weights = np.zeros((n_classes, 1), dtype=np.float32)
    weights[1 if live_index_wins else 2, 0] = 10.0
    bias = np.zeros((n_classes,), dtype=np.float32)
    bias[2 if live_index_wins else 1] = 1.0

    nodes = [
        helper.make_node("ReduceMean", ["input"], ["pooled"], axes=[1, 2, 3], keepdims=1),
        helper.make_node("Reshape", ["pooled", "shape"], ["flat"]),
        helper.make_node("Gemm", ["flat", "W", "B"], ["output"], transB=1),
    ]
    graph = helper.make_graph(
        nodes,
        "toy_antispoof",
        [helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, 3, 80, 80])],
        [helper.make_tensor_value_info("output", TensorProto.FLOAT, [1, n_classes])],
        [
            numpy_helper.from_array(np.array([1, 1], dtype=np.int64), "shape"),
            numpy_helper.from_array(weights, "W"),
            numpy_helper.from_array(bias, "B"),
        ],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 9
    onnx.save(model, str(path))
    return path


def test_onnx_backend_loads_and_scores(tmp_path) -> None:
    path = _write_toy_onnx(tmp_path / "toy.onnx", live_index_wins=True)
    checker = build_checker(backend="onnx", model_path=path, min_score=0.5, live_index=1)
    assert checker.method == "onnx"

    bright = np.full((200, 200, 3), 240, dtype=np.uint8)
    result = checker.check(bright)
    assert result.live is True
    assert result.score > 0.5
    assert "model_score" in result.signals


def test_onnx_backend_rejects_when_below_threshold(tmp_path) -> None:
    path = _write_toy_onnx(tmp_path / "toy.onnx", live_index_wins=False)
    checker = build_checker(backend="onnx", model_path=path, min_score=0.5, live_index=1)
    dark = np.full((200, 200, 3), 240, dtype=np.uint8)
    result = checker.check(dark)
    assert result.live is False
    assert "past" in result.reason


def test_onnx_backend_rejects_out_of_range_live_index(tmp_path) -> None:
    path = _write_toy_onnx(tmp_path / "toy.onnx", live_index_wins=True)
    # live_index chiqish o'lchamidan tashqarida — heuristikaga qaytishi kerak.
    checker = build_checker(backend="onnx", model_path=path, live_index=99)
    assert checker.method == "heuristic_multi"


def test_result_dict_shape() -> None:
    r = check_liveness(_texture(200), min_blur_variance=10.0)
    assert set(r) == {"live", "score", "method", "signals", "reason"}
    assert 0.0 <= r["score"] <= 1.0
