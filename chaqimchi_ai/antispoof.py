"""Anti-spoofing: tirik yuzni ekran/bosma hujumidan ajratish.

Ikki backend:

* ``heuristic`` — model talab qilmaydi. Uchta signalni birlashtiradi: ekran
  piksel panjarasi (moiré), rang to‘yinganligi va ko‘zgu yorqinligi. Bundan
  tashqari o‘tkirlik **qattiq pastki chegara** sifatida ishlatiladi (musbat
  ovoz sifatida emas — sababi `HeuristicBackend.WEIGHTS` izohida).
* ``onnx`` — o‘qitilgan model (kirish ``[1, 3, N, N]`` BGR ``[0, 1]``,
  chiqish ``[1, C]`` logitlar). Model topilmasa heuristikaga qaytadi.

Bu **filtr**, to‘liq himoya emas: oson hujumlarni to‘xtatadi, qasddan
tayyorlangan hujumni yo‘q. Kirish nazorati uchun ikkinchi omil qo‘shing.
Sifatni o‘z suratlaringizda o‘lchash: `scripts/validate_antispoof.py`.

Sozlash: `config.yaml` → `antispoof`. Batafsil: `docs/ANTISPOOF.md`.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

#: Yuz kesimi shundan kichik bo‘lsa, hech bir signal ishonchli emas.
MIN_FACE_SIZE = 40


@dataclass
class LivenessResult:
    """Bitta yuz uchun tiriklik xulosasi."""

    live: bool
    score: float
    method: str
    signals: Dict[str, float] = field(default_factory=dict)
    reason: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "live": self.live,
            "score": round(self.score, 4),
            "method": self.method,
            "signals": {k: round(v, 4) for k, v in self.signals.items()},
            "reason": self.reason,
        }


# ── Alohida signallar ────────────────────────────────────────────────────
#
# Har biri [0, 1] oralig‘ida "tiriklik foydasiga" ball qaytaradi:
# 1.0 = tirik yuzga xos, 0.0 = soxtaga xos.


def _sharpness_score(gray: np.ndarray, min_blur_variance: float) -> tuple[float, float]:
    """Laplacian dispersiyasi — xira (uzoqdagi ekran, fokusdan chiqqan) kadrlar.

    Qaytaradi: (ball, xom dispersiya).
    """
    variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    return float(np.clip(variance / (min_blur_variance * 2.0), 0.0, 1.0)), variance


def _moire_peakiness(gray: np.ndarray) -> float:
    """Furye spektridagi eng baland cho‘qqi medianadan necha sigma yuqorida.

    Ekranni suratga olganda piksel panjarasi spektrda tor, kuchli cho‘qqi
    beradi; tirik yuzning spektri silliq. O‘lchangan qiymatlar: toza yuz
    ~2.5–3, ekran panjarasi ~9–11.
    """
    h, w = gray.shape[:2]
    # Hann oynasi: kesim chetlaridagi keskin uzilish soxta cho'qqi bermasin.
    window = np.outer(np.hanning(h), np.hanning(w))
    spectrum = np.log1p(np.abs(np.fft.fftshift(np.fft.fft2(gray.astype(np.float64) * window))))

    cy, cx = h // 2, w // 2
    yy, xx = np.ogrid[:h, :w]
    radius = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
    max_r = min(cy, cx)

    # Past chastota (yuz shakli) va eng chekka shovqin hisobga olinmaydi.
    values = spectrum[(radius > max_r * 0.15) & (radius < max_r * 0.98)]
    if values.size < 32:
        return 0.0

    std = float(values.std())
    if std <= 1e-6:
        return 0.0
    return (float(values.max()) - float(np.median(values))) / std


def _moire_score(gray: np.ndarray) -> float:
    """Panjara qanchalik kam bo‘lsa, ball shunchalik yuqori."""
    h, w = gray.shape[:2]
    if h < 32 or w < 32:
        return 0.5  # juda kichik — bu signal ishlamaydi, neytral
    # 4 sigma dan past → toza; 7 dan yuqori → aniq panjara.
    return float(np.clip((7.0 - _moire_peakiness(gray)) / 3.0, 0.0, 1.0))


def _specular_score(gray: np.ndarray) -> float:
    """Ko‘zgu yorqinligi — ekran va yaltiroq qog‘ozdagi "porlash" dog‘lari.

    To‘yingan (>=250) piksellar ulushi katta bo‘lsa, ehtimol yorug‘lik
    tekis sirtdan qaytgan. Tirik terida bunday keng dog‘lar kam bo‘ladi.
    """
    saturated = float((gray >= 250).mean())
    # 0% → 1.0 ball; 3% va undan yuqori → 0.0 ball.
    return float(np.clip(1.0 - saturated / 0.03, 0.0, 1.0))


def _chroma_score(bgr: np.ndarray) -> float:
    """Rang xilma-xilligi — ekran va bosma rang gammasini siqadi.

    Tirik terida to‘yinganlik sezilarli tarqoq bo‘ladi; qayta suratga
    olingan tasvirda esa tekislashadi.
    """
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    sat_std = float(hsv[:, :, 1].std())
    # 12 dan past → shubhali; 30 va undan yuqori → normal.
    return float(np.clip((sat_std - 12.0) / 18.0, 0.0, 1.0))


# ── Backendlar ───────────────────────────────────────────────────────────


class HeuristicBackend:
    """Modelsiz tekshiruv — signallarning vaznli o‘rtachasi."""

    method = "heuristic_multi"

    #: Signal vaznlari. Moiré eng ishonchli belgi, shuning uchun og‘irroq.
    #:
    #: O'tkirlik ballari ataylab yo'q: ekran panjarasi Laplacian dispersiyasini
    #: **oshiradi** (o'lchangan: tirik yuz ~130, ekrandagi surat ~2500), ya'ni
    #: musbat ovoz sifatida u soxta tomonni qo'llab-quvvatlar edi. O'tkirlik
    #: faqat pastki chegara (juda xira kadrni rad etish) sifatida ishlatiladi.
    WEIGHTS = {"moire": 0.50, "chroma": 0.30, "specular": 0.20}

    def __init__(self, *, min_blur_variance: float = 80.0, min_score: float = 0.5) -> None:
        self.min_blur_variance = min_blur_variance
        self.min_score = min_score

    def check(self, face_crop_bgr: np.ndarray) -> LivenessResult:
        gray = cv2.cvtColor(face_crop_bgr, cv2.COLOR_BGR2GRAY)

        _, blur_variance = _sharpness_score(gray, self.min_blur_variance)
        signals = {
            "moire": _moire_score(gray),
            "chroma": _chroma_score(face_crop_bgr),
            "specular": _specular_score(gray),
            "blur_variance": blur_variance,
            "moire_peakiness": _moire_peakiness(gray) if min(gray.shape[:2]) >= 32 else 0.0,
        }

        score = sum(signals[k] * w for k, w in self.WEIGHTS.items())

        # Qattiq shart: o'ta xira kadr boshqa signallardan qat'i nazar rad etiladi.
        if blur_variance < self.min_blur_variance:
            return LivenessResult(
                live=False,
                score=score,
                method=self.method,
                signals=signals,
                reason=f"Juda xira (Laplacian {blur_variance:.0f} < {self.min_blur_variance:.0f})",
            )

        live = score >= self.min_score
        weakest = min(self.WEIGHTS, key=lambda k: signals[k])
        return LivenessResult(
            live=live,
            score=score,
            method=self.method,
            signals=signals,
            reason="" if live else f"Ball past ({score:.2f}), eng zaif signal: {weakest}",
        )


class OnnxBackend:
    """O‘qitilgan ONNX model (MiniFASNet uslubi: 80x80 BGR, 3 sinf).

    Modelning **sifati** bu yerda tekshirilmaydi — u faqat real suratlarda
    o‘lchanadi: `scripts/validate_antispoof.py`.
    """

    method = "onnx"

    def __init__(
        self,
        model_path: Path,
        *,
        min_score: float = 0.5,
        live_index: int = 1,
        providers: Optional[list[str]] = None,
    ) -> None:
        import onnxruntime as ort  # og'ir import — faqat kerak bo'lganda

        if not model_path.is_file():
            raise FileNotFoundError(f"Anti-spoof modeli topilmadi: {model_path}")

        self.model_path = model_path
        self.min_score = min_score
        self.live_index = live_index
        self.session = ort.InferenceSession(
            str(model_path), providers=providers or ["CPUExecutionProvider"]
        )

        spec = self.session.get_inputs()[0]
        self.input_name = spec.name
        # Shakl [N, C, H, W] — H/W dinamik bo'lsa, MiniFASNet standarti 80.
        self.input_size = int(spec.shape[2]) if isinstance(spec.shape[2], int) else 80
        n_out = self.session.get_outputs()[0].shape[-1]
        if isinstance(n_out, int) and not 0 <= live_index < n_out:
            raise ValueError(f"live_index={live_index} chiqish o‘lchamidan ({n_out}) tashqarida")

        # Diqqat: bu yerda "tasodifiy shovqin bilan model jonli-mi" testi ataylab
        # yo'q. Sinab ko'rildi — yuz kesimlariga o'qitilgan model shovqinga deyarli
        # o'zgarmas javob beradi, ya'ni bunday test yaxshi modelni ham rad etardi.
        # Modelning haqiqiy sifati faqat real suratlarda o'lchanadi:
        # `scripts/validate_antispoof.py`.

    def _infer(self, blob: np.ndarray) -> float:
        logits = self.session.run(None, {self.input_name: blob})[0][0]
        exp = np.exp(logits - np.max(logits))
        probs = exp / exp.sum()
        return float(probs[self.live_index])

    def check(self, face_crop_bgr: np.ndarray) -> LivenessResult:
        size = self.input_size
        resized = cv2.resize(face_crop_bgr, (size, size), interpolation=cv2.INTER_LINEAR)
        blob = (resized.astype(np.float32) / 255.0).transpose(2, 0, 1)[None]
        score = self._infer(blob)
        live = score >= self.min_score
        return LivenessResult(
            live=live,
            score=score,
            method=self.method,
            signals={"model_score": score},
            reason="" if live else f"Model ball past ({score:.2f} < {self.min_score:.2f})",
        )


# ── Tanlash va kesh ──────────────────────────────────────────────────────

_checker_lock = threading.Lock()
_checker_cache: Dict[tuple, Any] = {}


def build_checker(
    *,
    backend: str = "heuristic",
    model_path: Optional[Path] = None,
    min_score: float = 0.5,
    min_blur_variance: float = 80.0,
    live_index: int = 1,
) -> Any:
    """Backend obyektini quradi. ONNX yuklanmasa — heuristikaga qaytadi."""
    heuristic = HeuristicBackend(min_blur_variance=min_blur_variance, min_score=min_score)

    if backend != "onnx":
        return heuristic

    if model_path is None:
        logger.warning("antispoof.backend=onnx, lekin model_path berilmagan — heuristika.")
        return heuristic

    try:
        checker = OnnxBackend(Path(model_path), min_score=min_score, live_index=live_index)
        logger.info("Anti-spoof ONNX modeli yuklandi: %s", model_path)
        return checker
    except Exception as e:
        logger.warning("Anti-spoof ONNX yuklanmadi (%s) — heuristikaga qaytildi.", e)
        return heuristic


def get_checker(**kwargs: Any) -> Any:
    """Bir xil sozlama uchun backendni keshlab qaytaradi (model qayta yuklanmasin)."""
    key = tuple(sorted((k, str(v)) for k, v in kwargs.items()))
    with _checker_lock:
        if key not in _checker_cache:
            _checker_cache[key] = build_checker(**kwargs)
        return _checker_cache[key]


def reset_checker_cache() -> None:
    """Testlar va sozlama o‘zgarganda keshni tozalash."""
    with _checker_lock:
        _checker_cache.clear()


def check_liveness(
    face_crop_bgr: Optional[np.ndarray],
    *,
    min_blur_variance: float = 80.0,
    min_size: int = MIN_FACE_SIZE,
    checker: Optional[Any] = None,
) -> Dict[str, Any]:
    """Yuz kesimini tekshiradi.

    Args:
        face_crop_bgr: BGR yuz kesimi.
        min_blur_variance: Heuristika uchun eng kam o‘tkirlik.
        min_size: Shundan kichik kesim baholanmaydi.
        checker: Tayyor backend. Berilmasa — heuristika.

    Returns:
        `live`, `score`, `method`, `signals`, `reason` kalitlari bo‘lgan dict.
    """
    if face_crop_bgr is None or face_crop_bgr.size == 0:
        return LivenessResult(False, 0.0, "empty", reason="Bo‘sh kesim").as_dict()

    h, w = face_crop_bgr.shape[:2]
    if h < min_size or w < min_size:
        return LivenessResult(
            False, 0.0, "too_small", reason=f"Yuz juda kichik ({w}x{h} < {min_size})"
        ).as_dict()

    backend = checker or HeuristicBackend(min_blur_variance=min_blur_variance)
    return backend.check(face_crop_bgr).as_dict()
