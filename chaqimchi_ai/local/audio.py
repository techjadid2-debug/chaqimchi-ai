"""Do'kon karnayidan ibora aytish.

Telegramdagi tugma bosilganda do'kon kompyuteri gapiradi — egasi uydan
turib do'konda **hozir** bo'ladi.  Verisure'da bu "Intervene" bosqichi
va u uchun butun qo'riqchilar kompaniyasi kerak; bizda esa allaqachon
turgan kompyuter va arzon karnay buni qiladi.

## Uch bosqichli tanlov

1. **Do'konning o'z yozuvi** — `<data>/audio/<kod>.wav`.  Eng yaxshi
   variant: haqiqiy odam ovozi, do'kon egasining o'z tilida va
   lahjasida.  Fayl shu yerga qo'yilsa qolgan ikkisi ishlatilmaydi.
2. **Dastur bilan kelgan fayl** — `assets/audio/<kod>.wav`.
3. **Tizim ovozi (TTS)** — Windows'dagi SAPI.  Zaxira yo'l: o'zbek
   ovozi o'rnatilmagan bo'lsa talaffuz g'alati chiqadi, lekin
   "hech narsa" dan yaxshiroq.

## Nega `winsound`, `playsound` emas

`winsound` — Python standart kutubxonasi, ya'ni Windows payload'iga
qo'shimcha paket kerak emas (payload allaqachon 97 MB).  U faqat WAV
o'qiydi — shuning uchun MP3 emas, WAV ishlatiladi.

## Ovoz HECH QACHON asosiy oqimni bloklamaydi

Uzun fayl yoki javob bermayotgan audio qurilma heartbeat halqasini
to'xtatib qo'ymasligi kerak: ijro alohida oqimda ketadi.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Optional

from chaqimchi_ai import announcements
from chaqimchi_ai.local import paths

logger = logging.getLogger(__name__)

#: Bitta ibora shuncha soniyadan uzoq cho'zilmasin.
PLAY_TIMEOUT_SEC = 20

#: Ijro natijasi heartbeat'da bulutga boradi.
#:
#: Bu SHART: ovoz do'konda yangraydi, biz esa uni eshitmaymiz.  Hisoblagich
#: bo'lmasa "tugmani bosdim, hech narsa bo'lmadi" degan shikoyatning
#: sababini topib bo'lmasdi — karnay o'chiqmi, fayl yo'qmi, TTS
#: ishlamadimi.
_counters = {"played_file": 0, "played_tts": 0, "failed": 0}
#: Increment o'qish-yozish ikki qadam — parallel announce'lar hisobni
#: yo'qotmasin (hisoblagich diagnostikaning yagona manbai).
_counters_lock = threading.Lock()


def counters() -> dict:
    """Heartbeat uchun ijro hisoblagichlari (nusxa)."""
    with _counters_lock:
        return dict(_counters)


def _count(key: str) -> None:
    with _counters_lock:
        _counters[key] += 1


def custom_dir() -> Path:
    """Do'konning o'z yozuvlari shu yerga qo'yiladi."""
    return paths.data_dir() / "audio"


def bundled_dir() -> Path:
    return Path(__file__).resolve().parent / "assets" / "audio"


def resolve_file(code: str) -> Optional[Path]:
    """Iboraga mos WAV fayl.  Topilmasa `None`."""
    for folder in (custom_dir(), bundled_dir()):
        candidate = folder / f"{code}.wav"
        if candidate.is_file():
            return candidate
    return None


def _play_file(path: Path) -> bool:
    if os.name == "nt":
        try:
            import winsound

            # SND_FILENAME — fayldan; bloklovchi, lekin biz alohida
            # oqimdamiz.  `SND_NODEFAULT` — fayl buzuq bo'lsa Windows
            # o'zining "xato" ovozini chalmasin.
            winsound.PlaySound(
                str(path), winsound.SND_FILENAME | winsound.SND_NODEFAULT
            )
            return True
        except Exception:  # noqa: BLE001 — ovoz dasturni to'xtatmasin
            logger.warning("winsound ijro etolmadi: %s", path, exc_info=True)
            return False

    # Linux (Sotqin): tizimda bori ishlatiladi.
    for player in ("paplay", "aplay"):
        binary = shutil.which(player)
        if not binary:
            continue
        try:
            subprocess.run(
                [binary, str(path)],
                check=True,
                timeout=PLAY_TIMEOUT_SEC,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception:  # noqa: BLE001
            logger.warning("%s ijro etolmadi: %s", player, path, exc_info=True)
    return False


def _speak_with_tts(text: str) -> bool:
    """Zaxira yo'l — Windows'ning o'z ovozi."""
    if os.name != "nt" or not text:
        return False
    # PowerShell ataylab: `System.Speech` .NET'da va u har Windows 10/11
    # da bor.  Qo'shimcha paket ham, internet ham kerak emas.
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.Speak('{text.replace(chr(39), chr(39) * 2)}')"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            check=True,
            timeout=PLAY_TIMEOUT_SEC,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True
    except Exception:  # noqa: BLE001
        logger.warning("TTS ishlamadi", exc_info=True)
        return False


def announce(code: str) -> bool:
    """Iborani karnayga chiqaradi.  Chaqiruv BLOKLAMAYDI.

    `True` — ijro boshlandi (natijasi jurnalga yoziladi).
    `False` — ibora noma'lum, ya'ni umuman urinilmadi.
    """
    if not announcements.is_valid(code):
        logger.warning("Noma'lum ibora: %s", code)
        return False

    # Fon thread'i global funksiyalarni keyin o'qimasin. Testda yoki
    # xizmat restartida ular almashsa, avvalgi announce keyingi so'rovning
    # hisoblagichini buzib qo'yardi.
    path = resolve_file(code)
    play_file = _play_file
    speak = _speak_with_tts
    count = _count
    text = announcements.text_for(code)

    def _run() -> None:
        if path and play_file(path):
            count("played_file")
            logger.info("Ovoz berildi (fayl): %s", code)
            return
        if speak(text):
            count("played_tts")
            logger.info("Ovoz berildi (tizim ovozi): %s", code)
            return
        count("failed")
        logger.warning(
            "Ovoz berilmadi: %s — na WAV fayl topildi (%s), na tizim ovozi ishladi",
            code,
            custom_dir() / f"{code}.wav",
        )

    threading.Thread(target=_run, name=f"chaqimchi-audio-{code}", daemon=True).start()
    return True
