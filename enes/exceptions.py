"""Loyiha istisnolari — API va CLI uchun bir xil xato turlari."""


class ChaqimchiError(Exception):
    """Asosiy bazaviy istisno."""


class FaceEngineError(ChaqimchiError):
    """Yuz yadrosi bilan bog‘liq xatolar."""


class ModelLoadError(FaceEngineError):
    """ONNX / InsightFace modellari yuklanmagan."""


class ConfigurationError(ChaqimchiError):
    """Noto‘g‘ri yoki yetarli bo‘lmagan konfiguratsiya."""
