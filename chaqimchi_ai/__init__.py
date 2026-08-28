"""Chaqimchi AI paketi.

Lokal Face ID (davomat) to'plami arxivlangan — `archive/attendance-local`
git tegida turadi.  Yuz tanish keyinchalik **cloud** tomonda quriladi
(`docs/archive/README.md`).
"""

#: Versiya ikki joyda yozilgan: bu yerda va `pyproject.toml` da.
#:
#: `importlib.metadata` ishlatilmaydi — paket qurilmada hech qachon pip bilan
#: o'rnatilmaydi (venv faqat requirements'ni oladi), ya'ni u `PackageNotFound`
#: bilan import paytida ikkala xizmatni ham o'ldirardi.  `pyproject.toml` ni
#: o'qish ham mumkin emas: u reliz paketiga kirmaydi.
#:
#: Ikkalasining mosligini `tests/test_sotqin_release_contract.py` ushlab turadi.
__version__ = "0.6.22"
__all__ = ["__version__"]
