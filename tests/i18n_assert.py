"""Testlar matnga emas, KALITGA bog'lansin.

## Nega kerak

To'plamda ~70 ta joyda aniq o'zbekcha satr yozilgan
(`assert body["label"] == "Kamera yopildi yoki burildi"`).  Matn
katalogga ko'chgach uni bir harfga tuzatish ham testni qulatadi —
holbuki xulq o'zgarmagan.  Bu yordamchi bilan test "shu KALIT chiqdimi"
degan savolga javob beradi va tarjima tahriri testga tegmaydi.

## Nega matnni umuman tekshirmaymiz emas

Tekshirish kerak: kalit to'g'ri, lekin `params` noto'g'ri uzatilsa
xabar buzuq chiqadi.  Shuning uchun yordamchi katalogdan MATN yasab
solishtiradi — ya'ni o'rinbosarlar ham tekshiriladi.
"""

from __future__ import annotations

from typing import Any

from cloud import i18n


def assert_text(actual: str, key: str, lang: str = i18n.DEFAULT_LANG, **params: Any) -> None:
    """Matn shu kalitdan chiqqanini tekshiradi."""
    expected = i18n.tg(lang, key, **params)
    assert expected != key, f"katalogda `{key}` yo'q — test bekorga o'tayapti"
    assert actual == expected, f"{key}: kutilgan {expected!r}, kelgani {actual!r}"


def assert_code(response: Any, code: str) -> None:
    """HTTP xatosi — matn emas, KOD bo'yicha.

    Kod tarjima qilinmaydi, ya'ni ruscha va inglizcha javob ham shu
    testdan o'tadi.
    """
    body = response.json()
    assert body.get("code") == code, f"kutilgan kod {code}, javob: {body}"
