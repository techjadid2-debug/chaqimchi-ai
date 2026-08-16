"""Sotqin R1 uchun yagona apparat va media cheklovlari.

Bu qiymatlar cloud, installer va lokal agentda bir xil bo'lishi kerak.  NVR
to'liq video arxivini saqlaydi; Sotqin esa faqat event/frame navbatini ushlab
turadi.  Shuning uchun 128 GB NVMe'ni uzluksiz videoga ishlatish mumkin emas.
"""

from __future__ import annotations

from chaqimchi_ai.limits import SHOP_MAX_CAMERAS

PRODUCT_NAME = "Sotqin"
HARDWARE_PROFILE = "SOTQIN-N100-8-128-R1"
HARDWARE_MODEL = "Intel N100"
HARDWARE_REVISION = "R1"

# Sotilgan R1 profili: 4 kamera SLA (yagona manba: chaqimchi_ai/limits.py),
# 8 kamera esa apparat imkoniyati — faqat obyekt qabul testidan keyin.
GUARANTEED_CAMERAS = SHOP_MAX_CAMERAS
MAX_CAMERAS = 8

# 128 GB NVMe'da OS, update rollback va loglar uchun joy qoldiriladi.
BUFFER_MAX_BYTES = 40 * 1024**3
BUFFER_RETENTION_DAYS = 3
MIN_FREE_BYTES = 20 * 1024**3


def product_payload() -> dict[str, int | str]:
    """Cloud konfiguratsiyasi va health endpoint uchun mahsulot pasporti."""
    return {
        "name": PRODUCT_NAME,
        "hardware_profile": HARDWARE_PROFILE,
        "hardware_model": HARDWARE_MODEL,
        "hardware_revision": HARDWARE_REVISION,
        "guaranteed_cameras": GUARANTEED_CAMERAS,
        "max_cameras": MAX_CAMERAS,
    }
