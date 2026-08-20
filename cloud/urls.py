"""chaqimchi.uz subdomen manzillari — havola qaysi bo'limga tegishli.

Nega kerak.  Ilgari hamma havola bitta `CHAQIMCHI_PUBLIC_URL` dan
qurilardi.  Endi platforma subdomenlarga bo'linadi:

    chaqimchi.uz          landing (marketing)
    app.chaqimchi.uz      mijoz paneli — bot tugmalari, kirish havolalari
    api.chaqimchi.uz      qurilma/to'lov/webhook — ENG BARQAROR shartnoma
    dl.chaqimchi.uz       installer va relizlar — keyin CDN'ga ko'chsa
                          DNS o'zgaradi, kod emas
    partner.chaqimchi.uz  montajchi portali

Har funksiya o'z env o'zgaruvchisini o'qiydi; berilmagan bo'lsa apex
(`CHAQIMCHI_PUBLIC_URL`) ga tushadi — ya'ni subdomenlarsiz eski
bitta-domen rejimi ham to'liq ishlayveradi (testlar shu holatda o'tadi).
"""

from __future__ import annotations

import os

from cloud.payments.config import public_url

__all__ = ["public_url", "app_url", "api_url", "dl_url", "partner_url"]


def _url(env_key: str) -> str:
    value = os.environ.get(env_key, "").strip().rstrip("/")
    return value or public_url()


def app_url() -> str:
    """Mijoz paneli bazasi (bot tugmalari, login havolalari)."""
    return _url("CHAQIMCHI_APP_URL")


def api_url() -> str:
    """Qurilma va webhook bazasi (pairing `--cloud`, heartbeat)."""
    return _url("CHAQIMCHI_API_URL")


def dl_url() -> str:
    """Yuklab olish bazasi (installer, relizlar, OTA fayllari)."""
    return _url("CHAQIMCHI_DL_URL")


def partner_url() -> str:
    """Montajchi portali bazasi."""
    return _url("CHAQIMCHI_PARTNER_URL")
