"""Telegram menyusi va yordam matni bir-biriga mos tursin.

Nega bu test bor.  `/chek` buyrug'i 2026-08-31 da qo'shilgan, yordam
matniga (`bot.help`) yozilgan va ishlov beruvchisi ham bor edi — lekin
`BOT_COMMANDS` ro'yxatiga tushmagan.  Ya'ni Telegramda "/" bosgan ega uni
ko'rmasdi va konversiyani kiritishning YAGONA yo'lini faqat yordamni
o'qigan odam topardi.  Buyruq ikki joyda qo'lda yoziladi, shuning uchun
mosligini test qulflaydi.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Set

ROOT = Path(__file__).resolve().parents[1]

#: Yordam matnida ko'rsatiladi, lekin menyuda ATAYLAB yo'q.  Ro'yxat
#: qisqa tursin: har yozuv "nega menyuda emas" degan javobni talab qiladi.
HELP_ONLY: dict = {}

#: Menyuda bor, lekin yordam matnida ATAYLAB yo'q.
MENU_ONLY: dict = {}


def _menu_commands() -> Set[str]:
    text = (ROOT / "cloud" / "main.py").read_text(encoding="utf-8")
    block = re.search(r"BOT_COMMANDS = \[(.*?)\n\]", text, re.S)
    assert block is not None, "BOT_COMMANDS ro'yxati topilmadi"
    return set(re.findall(r'"command":\s*"([a-z_]+)"', block.group(1)))


def _help_commands(lang: str) -> Set[str]:
    catalogue = json.loads((ROOT / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
    return set(re.findall(r"(?m)^/([a-z_]+)", catalogue["bot.help"]))


def test_every_menu_command_is_explained_in_the_help() -> None:
    missing = _menu_commands() - _help_commands("uz") - set(MENU_ONLY)
    assert missing == set(), (
        f"menyuda bor, yordamda yo'q: {sorted(missing)} — "
        "`bot.help` ga yozing yoki MENU_ONLY ga sabab bilan qo'shing"
    )


def test_every_documented_command_is_in_the_menu() -> None:
    """Aynan shu yo'nalish `/chek` ni oylab yashirib turgan edi."""
    missing = _help_commands("uz") - _menu_commands() - set(HELP_ONLY)
    assert missing == set(), (
        f"yordamda bor, menyuda yo'q: {sorted(missing)} — "
        "`BOT_COMMANDS` ga qo'shing yoki HELP_ONLY ga sabab bilan qo'shing"
    )


def test_the_help_lists_the_same_commands_in_every_language() -> None:
    """Ruscha yordam matni o'zbekchadan orqada qolmasin."""
    uz = _help_commands("uz")
    for lang in ("ru", "en"):
        assert _help_commands(lang) == uz, (
            f"`bot.help` {lang} da boshqa buyruqlarni sanaydi: "
            f"{sorted(_help_commands(lang) ^ uz)}"
        )
