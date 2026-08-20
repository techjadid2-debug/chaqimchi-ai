"""Qurilma qanchalik bosim ostida — 0 (bo'sh) dan 1 (chegarada) gacha.

`InferenceBudget` o'zini o'lchangan latency bo'yicha sozlaydi, lekin latency
kech signal: harorat ko'tarilganda yoki boshqa jarayon CPU'ni yeganda
kechikish hali ko'rinmasligi mumkin, natijada byudjet kech tushadi va
navbat o'sib ketadi.  Shu sabab `budget.set_pressure()` mavjud edi — lekin
uni hech kim chaqirmasdi, ya'ni `budget.py` dagi `pressure >= 0.85` tarmog'i
yozilganidan beri o'lik kod bo'lib turgan.

**`psutil` yo'q.**  Uchala o'lchov ham stdlib bilan olinadi, va qo'shimcha
bog'liqlik 8 GB qurilmada bejiz emas: har paket o'rnatish vaqti, disk va
yangilanish yuki demak.  `sotqin_agent.py` allaqachon `/sys/class/thermal`
ni shu yo'l bilan o'qiydi.

Har manba **mustaqil** yiqiladi: macOS'da `/sys/class/thermal` yo'q,
konteynerda `/proc/meminfo` boshqacha bo'lishi mumkin.  O'qilmagan manba
0.0 beradi va qolganlari ishlashda davom etadi — o'lchov yo'qligi sababli
butun zanjirni to'xtatish noto'g'ri bo'lardi.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Dict, Optional

#: CPU shu ulushdan oshsa bosim 1.0 ga yetadi.  Talablar hujjatidagi
#: "o'rtacha CPU <= 80%" shundan keladi.
CPU_CEILING = 0.80

#: Xotira shu ulushdan oshsa bosim 1.0.  8 GB qurilmada 6.5 GB — 0.81.
MEMORY_CEILING = 0.81

#: Harorat shkalasi: 70 °C dan past bosim bermaydi, 85 °C da 1.0.
#: N100 throttling'i ~90 °C atrofida boshlanadi, ya'ni 85 — ogohlantirish
#: emas, allaqachon chegara.
TEMP_FLOOR_C = 70.0
TEMP_CEILING_C = 85.0

THERMAL_ZONES = "/sys/class/thermal"


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def read_load_ratio() -> float:
    """So'nggi bir daqiqalik yuk / yadro soni.

    `os.getloadavg()` tanlangani — u `/proc/stat` dagi kabi ikki o'lchov
    orasidagi farqni talab qilmaydi, ya'ni holatsiz va chaqirilish
    chastotasidan mustaqil.  Housekeeping halqasi 30 soniyada bir marta
    ishlaydi, bir daqiqalik o'rtacha esa aynan shunga mos.
    """
    try:
        one_minute = os.getloadavg()[0]
    except (OSError, AttributeError):  # pragma: no cover - Windows
        return 0.0
    cores = os.cpu_count() or 1
    return one_minute / cores


def read_memory_ratio() -> float:
    """Band xotira ulushi.

    `MemAvailable` ishlatiladi, `MemFree` emas: kesh va bufer texnik jihatdan
    band, lekin kerak bo'lganda bo'shatiladi.  `MemFree` bo'yicha o'lchash
    sog'lom Linux tizimini doim "xotira tugadi" deb ko'rsatardi.
    """
    try:
        text = Path("/proc/meminfo").read_text(encoding="utf-8")
    except OSError:
        return 0.0
    values: Dict[str, float] = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        if key in ("MemTotal", "MemAvailable"):
            try:
                values[key] = float(rest.strip().split()[0])
            except (IndexError, ValueError):
                return 0.0
    total = values.get("MemTotal", 0.0)
    available = values.get("MemAvailable")
    if total <= 0 or available is None:
        return 0.0
    return _clamp(1.0 - available / total)


def read_temperature_c() -> Optional[float]:
    """Eng issiq termal zona, °C.  O'qilmasa `None`."""
    hottest: Optional[float] = None
    try:
        zones = sorted(Path(THERMAL_ZONES).glob("thermal_zone*/temp"))
    except OSError:
        return None
    for zone in zones:
        try:
            milli = float(zone.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            continue
        celsius = milli / 1000.0
        # Ba'zi zonalar ma'nosiz qiymat beradi (0 yoki 1e6 dan katta).
        if not 0.0 < celsius < 150.0:
            continue
        if hottest is None or celsius > hottest:
            hottest = celsius
    return hottest


class SystemPressure:
    """Uch o'lchovdan eng yomonini qaytaradi.

    Eng yomoni olinadi, o'rtacha emas: CPU bo'sh bo'lsa-yu qurilma qizib
    ketgan bo'lsa, o'rtacha buni yashirib qo'yardi.  Byudjet esa aynan shu
    holatda tushishi kerak.
    """

    def __init__(
        self,
        *,
        cpu_ceiling: float = CPU_CEILING,
        memory_ceiling: float = MEMORY_CEILING,
        temp_floor_c: float = TEMP_FLOOR_C,
        temp_ceiling_c: float = TEMP_CEILING_C,
        load_reader: Callable[[], float] = read_load_ratio,
        memory_reader: Callable[[], float] = read_memory_ratio,
        temperature_reader: Callable[[], Optional[float]] = read_temperature_c,
    ) -> None:
        if cpu_ceiling <= 0 or memory_ceiling <= 0:
            raise ValueError("chegaralar musbat bo'lishi kerak")
        if temp_ceiling_c <= temp_floor_c:
            raise ValueError("temp_ceiling_c temp_floor_c dan katta bo'lsin")
        self.cpu_ceiling = float(cpu_ceiling)
        self.memory_ceiling = float(memory_ceiling)
        self.temp_floor_c = float(temp_floor_c)
        self.temp_ceiling_c = float(temp_ceiling_c)
        self._load_reader = load_reader
        self._memory_reader = memory_reader
        self._temperature_reader = temperature_reader
        self._last: Dict[str, float] = {"cpu": 0.0, "memory": 0.0, "temperature": 0.0}

    def _safe(self, reader: Callable[[], float]) -> float:
        try:
            return float(reader())
        except Exception:
            # O'lchov yo'qligi sababli zanjirni to'xtatmaymiz: bosimsiz
            # ishlagan byudjet hech bo'lmasa latency bo'yicha sozlanadi.
            return 0.0

    def read(self) -> float:
        cpu = _clamp(self._safe(self._load_reader) / self.cpu_ceiling)
        memory = _clamp(self._safe(self._memory_reader) / self.memory_ceiling)

        temperature = 0.0
        try:
            celsius = self._temperature_reader()
        except Exception:
            celsius = None
        if celsius is not None:
            span = self.temp_ceiling_c - self.temp_floor_c
            temperature = _clamp((celsius - self.temp_floor_c) / span)

        self._last = {"cpu": cpu, "memory": memory, "temperature": temperature}
        return max(cpu, memory, temperature)

    __call__ = read

    def stats(self) -> Dict[str, float]:
        return {key: round(value, 3) for key, value in self._last.items()}
