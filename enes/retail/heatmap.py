"""Kamera ko'rinishi bo'yicha odam-borligi issiqlik to'ri.

Do'kon egasining savoli: "mijozlar qayerda yuradi, qayerga qadam
bosmaydi?" — javob shu to'rda.  Har tahlil kadrida odamning oyoq nuqtasi
(bbox pastki markazi) tegishli katakka +1 qilinadi.  Bu **deyarli bepul**:
deteksiya allaqachon bor, qo'shimchasi bitta indeks hisobi.

To'r 48×27 (16:9 kadr nisbati) — panelda kamera rasmi ustiga qatlam
bo'lib tushadi.  Har 10 daqiqada to'r bo'shatilib JSON faylga yoziladi;
lokal ilova uni cloudga jo'natadi.  Rasm emas, faqat sonlar ketadi.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, Tuple

#: To'r o'lchami (ustunlar × qatorlar) — 16:9 kadrga mos.
GRID_COLS = 48
GRID_ROWS = 27


class HeatmapGrid:
    """Bitta kameraning yig'ma to'ri (ip-xavfsiz)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cells = [[0] * GRID_COLS for _ in range(GRID_ROWS)]
        self._frames = 0
        self._points = 0

    def add(self, x_norm: float, y_norm: float) -> None:
        """Normallashgan (0..1) oyoq nuqtasini katakka qo'shadi."""
        column = min(GRID_COLS - 1, max(0, int(x_norm * GRID_COLS)))
        row = min(GRID_ROWS - 1, max(0, int(y_norm * GRID_ROWS)))
        with self._lock:
            self._cells[row][column] += 1
            self._points += 1

    def frame_done(self) -> None:
        with self._lock:
            self._frames += 1

    def drain(self) -> Tuple[Any, int, int]:
        """To'rni qaytarib bo'shatadi: (kataklar, kadrlar, nuqtalar)."""
        with self._lock:
            cells, frames, points = self._cells, self._frames, self._points
            self._cells = [[0] * GRID_COLS for _ in range(GRID_ROWS)]
            self._frames = 0
            self._points = 0
        return cells, frames, points


def write_heatmap_file(
    directory: Path, camera_id: str, hour_bucket: str, cells: Any, frames: int
) -> Path:
    """Bo'shatilgan to'rni atomik JSON qilib yozadi.

    Fayl nomi kamera+soat bo'yicha: bir soat ichida bir necha marta
    yozilsa qiymatlar faylda JAMLANADI (cloud yetib olmagan bo'lsa
    yo'qolmasin).
    """
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{camera_id}-{hour_bucket.replace(':', '')}.json"
    if target.is_file():
        try:
            previous = json.loads(target.read_text(encoding="utf-8"))
            old_cells = previous.get("grid") or []
            for row_index, row in enumerate(old_cells[:GRID_ROWS]):
                for col_index, value in enumerate(row[:GRID_COLS]):
                    cells[row_index][col_index] += int(value)
            frames += int(previous.get("frames") or 0)
        except (ValueError, OSError, TypeError):
            pass
    payload: Dict[str, Any] = {
        "camera_id": camera_id,
        "hour": hour_bucket,
        "grid": cells,
        "frames": frames,
    }
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    os.replace(temporary, target)
    return target
