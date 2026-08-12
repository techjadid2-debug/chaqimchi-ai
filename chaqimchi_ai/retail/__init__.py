"""Chaqimchi Retail AI — do'kon analitikasining edge qismi.

Bu paket N100 (8 GB / 128 GB) qurilmasida 8 kamerani bitta cheklangan inferens
byudjeti ustida ishlatish uchun.  Asosiy g'oya: kameralar bir vaqtda emas,
**navbat bilan** ishlaydi va navbatni ehtiyoj belgilaydi.
"""

from chaqimchi_ai.retail.broker import FrameBroker
from chaqimchi_ai.retail.budget import InferenceBudget
from chaqimchi_ai.retail.claims import Claim, Priority

__all__ = ["Claim", "FrameBroker", "InferenceBudget", "Priority"]
