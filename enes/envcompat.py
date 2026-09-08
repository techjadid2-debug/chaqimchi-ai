"""Eski `CHAQIMCHI_*` muhit nomlari → `ENES_*` ko'priki.

Nega: 2026-09 rebrendida 134 ta muhit o'zgaruvchisi nomi almashdi.
Kod yangi nomni o'qiydi, lekin jonli serverdagi `/etc/*/backup.env`,
compose `.env`, pilot kompyuteridagi `sotqin.env` va systemd
`EnvironmentFile` lar eski nom bilan turadi va ular kod bilan bir
commitda o'zgarmaydi.  Ko'priksiz deploy kuni har bir unutilgan nom
alohida 500 bo'lardi.

Qoida: yangi nom bor bo'lsa u g'olib; eski nom faqat yangisi YO'Q
bo'lganda ko'chiriladi.  Shunda cutoverdan keyin eski nomlarni bittalab
olib tashlash mumkin, hech narsa sinmaydi.

Compose fayllaridagi `${ENES_*}` almashtirishlar Python'dan o'tmaydi —
ular uchun serverdagi env faylini cutover kuni qo'lda qayta nomlash
shart (`docs/ISH_DAFTARI.md`, F7 ro'yxati).
"""

from __future__ import annotations

import os
from typing import List, MutableMapping

LEGACY_PREFIX = "CHAQIMCHI_"
PREFIX = "ENES_"


def adopt_legacy_env(environ: MutableMapping[str, str] = os.environ) -> List[str]:
    """`CHAQIMCHI_X` → `ENES_X` (faqat `ENES_X` bo'lmasa).  Ko'chirilganlar ro'yxati."""
    adopted: List[str] = []
    for key in list(environ):
        if not key.startswith(LEGACY_PREFIX):
            continue
        new_key = PREFIX + key[len(LEGACY_PREFIX):]
        if new_key in environ:
            continue
        environ[new_key] = environ[key]
        adopted.append(new_key)
    return adopted


adopt_legacy_env()
