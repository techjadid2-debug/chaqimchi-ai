"""Chaqimchi AI paketi; og'ir vision importlari lazy yuklanadi."""

from typing import Any

#: Versiya ikki joyda yozilgan: bu yerda va `pyproject.toml` da.
#:
#: `importlib.metadata` ishlatilmaydi — paket qurilmada hech qachon pip bilan
#: o'rnatilmaydi (venv faqat requirements'ni oladi), ya'ni u `PackageNotFound`
#: bilan import paytida ikkala xizmatni ham o'ldirardi.  `pyproject.toml` ni
#: o'qish ham mumkin emas: u reliz paketiga kirmaydi.
#:
#: Ikkalasining mosligini `tests/test_sotqin_release_contract.py` ushlab turadi.
__version__ = "0.6.1"
__all__ = ["FaceEngine", "FaceCompareResult", "VideoFrameResult", "__version__"]


def __getattr__(name: str) -> Any:
    if name in {"FaceEngine", "FaceCompareResult", "VideoFrameResult"}:
        from chaqimchi_ai.face_engine import FaceCompareResult, FaceEngine, VideoFrameResult

        return {
            "FaceEngine": FaceEngine,
            "FaceCompareResult": FaceCompareResult,
            "VideoFrameResult": VideoFrameResult,
        }[name]
    raise AttributeError(name)
