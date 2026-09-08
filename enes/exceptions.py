"""Loyiha istisnolari — API va CLI uchun bir xil xato turlari."""


class EnesError(Exception):
    """Asosiy bazaviy istisno."""


class FaceEngineError(EnesError):
    """Yuz yadrosi bilan bog‘liq xatolar."""


class ModelLoadError(FaceEngineError):
    """ONNX / InsightFace modellari yuklanmagan."""


class ConfigurationError(EnesError):
    """Noto‘g‘ri yoki yetarli bo‘lmagan konfiguratsiya."""
