"""Uch tilli matn — yagona kirish nuqtasi.

Qoida: **har satr faqat bitta joyda yashaydi — uni KIM chizsa,
o'shanda.**  Server chizadigan matn (hodisa nomi, xato izohi, Telegram
xabari, CSV sarlavhasi) shu yerdan, panelning o'z matni esa
`frontend/src/i18n/` dan keladi.  Ikkalasi ham BITTA manbadan —
`i18n/{uz,ru,en}.json` — o'qiydi, ya'ni ajralib ketmaydi.

## Nega ikkita funksiya bor

`tg(lang, key)` — tilni MAJBURIY so'raydi.  Telegram, digest va CSV
faqat shuni ishlatadi.  Sabab jiddiy: `asyncio.create_task` va FastAPI
`BackgroundTasks` so'rov kontekstini **meros oladi**, ya'ni fon rejimida
ketgan xabar qabul qiluvchining emas, so'rov yuborgan odamning tilida
ketardi.  Til argument bo'lsa bu xato yozilishi mumkin emas.

`t(key)` — joriy so'rov tilini `ContextVar` dan oladi va faqat HTTP
javob yo'lida ishlatiladi.  Usiz 238 ta marshrut imzosiga `lang`
parametri qo'shilishi kerak bo'lardi.

## Nega gettext (.po) emas

Gettext kaliti — matnning O'ZI.  Rebrending paytida matn ko'p
o'zgaradi va har tahrir barcha tarjimani bekor qilardi.  Nuqtali
kalit (`event.camera_tampered`) matn o'zgarganda ham joyida qoladi.
"""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal, Optional, Tuple

logger = logging.getLogger("enes.i18n")

Lang = Literal["uz", "ru", "en"]

#: Qo'llab-quvvatlanadigan tillar.  Tartib muhim: birinchisi — standart.
LANGS: Tuple[Lang, ...] = ("uz", "ru", "en")
DEFAULT_LANG: Lang = "uz"

#: Katalog repo ildizida turadi (`cloud/` ichida emas): undan Python ham,
#: `scripts/build_i18n.py` orqali TypeScript ham o'qiydi.
CATALOGUE_DIR = Path(__file__).resolve().parents[1] / "i18n"

_CATALOGUE: Dict[str, Dict[str, Any]] = {}

#: Joriy so'rov tili.  Standart qiymat bor: fon vazifasi yoki test
#: to'g'ridan-to'g'ri `t()` ni chaqirsa ham hech narsa yiqilmaydi.
_current: ContextVar[Lang] = ContextVar("enes_lang", default=DEFAULT_LANG)


def _load() -> Dict[str, Dict[str, Any]]:
    """Katalogni birinchi murojaatda o'qiydi va xotirada saqlaydi."""
    if not _CATALOGUE:
        for lang in LANGS:
            path = CATALOGUE_DIR / f"{lang}.json"
            _CATALOGUE[lang] = json.loads(path.read_text(encoding="utf-8"))
    return _CATALOGUE


def reload_catalogue() -> None:
    """Testlar uchun: fayl o'zgarganda keshni tashlash."""
    _CATALOGUE.clear()


def normalize(value: Optional[str]) -> Optional[Lang]:
    """`ru-RU`, `RU`, ` ru ` → `ru`.  Notanish qiymat → `None`.

    `None` va bo'sh satr farqlanmaydi: ikkalasi ham "til aytilmagan"
    degani va zanjirdagi keyingi manbaga o'tiladi.
    """
    if not value:
        return None
    code = value.strip().lower().replace("_", "-").split("-")[0]
    return code if code in LANGS else None  # type: ignore[return-value]


def _from_accept_language(header: Optional[str]) -> Optional[Lang]:
    """`Accept-Language` dagi eng ma'qul tilni tanlaydi.

    `q` og'irliklari ATAYLAB e'tiborga olinmaydi: brauzerlar ro'yxatni
    allaqachon afzallik tartibida yuboradi va bizda uchtagina til bor —
    to'liq RFC tahlili shu yerda foyda bermaydi.
    """
    if not header:
        return None
    for chunk in header.split(","):
        lang = normalize(chunk.split(";")[0])
        if lang:
            return lang
    return None


def resolve_lang(
    *,
    query: Optional[str] = None,
    header: Optional[str] = None,
    stored: Optional[str] = None,
    telegram: Optional[str] = None,
    accept: Optional[str] = None,
) -> Lang:
    """Til zanjiri — bitta joyda.

    Tartib: aniq so'rov (`?lang=`) → panel sarlavhasi (`X-Lang`) →
    saqlangan tanlov → Telegram profili → brauzer → `uz`.

    Nega aniq so'rov birinchi: havolani ulashganda ("mana, ruscha
    ko'rinishi") u saqlangan tanlovni yenga olishi kerak.
    """
    for candidate in (query, header, stored, telegram):
        lang = normalize(candidate)
        if lang:
            return lang
    return _from_accept_language(accept) or DEFAULT_LANG


def current_lang() -> Lang:
    return _current.get()


def set_current(lang: Lang):
    """Joriy tilni o'rnatadi va `reset` uchun tokenni qaytaradi."""
    return _current.set(lang)


def reset_current(token) -> None:
    _current.reset(token)


def tg(lang: str, key: str, /, **params: Any) -> str:
    """Aniq tildagi matn.  Telegram, digest va CSV faqat shuni ishlatadi.

    Kalit topilmasa KALITNING O'ZI qaytadi (bo'sh satr emas): shunda
    yetishmayotgan tarjima ekranda darrov ko'zga tashlanadi, jimgina
    bo'sh joy qoldirib ketmaydi.
    """
    catalogue = _load()
    code = normalize(lang) or DEFAULT_LANG
    template = catalogue.get(code, {}).get(key)
    if template is None:
        template = catalogue[DEFAULT_LANG].get(key)
    if template is None:
        logger.warning("i18n: kalit yo'q — %s", key)
        return key
    if not isinstance(template, str):
        # Ro'yxat (oy nomlari) — `t_list` orqali olinadi.
        return key
    if not params:
        return template
    try:
        return template.format(**params)
    except (KeyError, IndexError, ValueError):
        # Tarjimondagi bitta xato butun javobni 500 qilmasin: o'zbekcha
        # matn har doim ishlaydi, chunki uni biz yozganmiz.
        logger.warning("i18n: o'rinbosar xatosi — %s/%s", code, key)
        fallback = catalogue[DEFAULT_LANG].get(key, key)
        try:
            return fallback.format(**params) if isinstance(fallback, str) else key
        except (KeyError, IndexError, ValueError):
            return key


def t(key: str, /, **params: Any) -> str:
    """Joriy so'rov tilidagi matn.  Faqat HTTP javob yo'lida."""
    return tg(_current.get(), key, **params)


def t_list(lang: str, key: str) -> List[str]:
    """Ro'yxatli qiymat (oy va hafta kunlari nomlari)."""
    catalogue = _load()
    code = normalize(lang) or DEFAULT_LANG
    value = catalogue.get(code, {}).get(key)
    if not isinstance(value, list):
        value = catalogue[DEFAULT_LANG].get(key)
    return list(value) if isinstance(value, list) else []


def keys(lang: Lang = DEFAULT_LANG) -> Iterable[str]:
    """Katalogdagi kalitlar — testlar va kodgeneratsiya uchun."""
    return _load()[lang].keys()
