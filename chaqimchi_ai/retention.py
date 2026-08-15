"""Voqea arxivini saqlash muddati (retention) — eski yozuv va rasmlarni tozalash.

Nima uchun kerak:

1. **Tarif va’dasi.** Narx jadvalida har bir tarif uchun arxiv muddati yozilgan
   (Starter 30 kun, Business 90, Enterprise 365). Bungacha bu son faqat
   litsenziya javobida ko‘rinardi, hech narsani cheklamasdi.
2. **Disk.** Mini PC da har mos kelish uchun bitta JPEG saqlanadi. Kuniga 500
   voqea ≈ 15 MB; bir yilda ~5 GB va u hech qachon kamaymaydi.
3. **Ma’lumot minimallashtirish.** Biometrik kadrni kerakli muddatdan ortiq
   saqlamaslik — `docs/archive/REJA.md` dagi talab.

Muddat ikki manbadan keladi: litsenziya (tarif) va `config.yaml`. Ikkalasi ham
bo‘lsa **qisqarog‘i** ishlatiladi — mijoz o‘z xohishi bilan kamroq saqlashi
mumkin, lekin tarifdan ko‘p emas.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, List, Optional

from chaqimchi_ai.events import EventLog
from chaqimchi_ai.metrics import get_metrics

if TYPE_CHECKING:  # pragma: no cover
    from chaqimchi_ai.runtime.container import AppContainer

logger = logging.getLogger(__name__)

#: Snapshot papkasidan yetim fayllarni izlashda qaraladigan kengaytmalar.
SNAPSHOT_SUFFIXES = (".jpg", ".jpeg", ".png")


@dataclass
class PurgeResult:
    """Bitta tozalash natijasi."""

    retention_days: int
    events_deleted: int = 0
    files_deleted: int = 0
    bytes_freed: int = 0
    ran_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "retention_days": self.retention_days,
            "events_deleted": self.events_deleted,
            "files_deleted": self.files_deleted,
            "bytes_freed": self.bytes_freed,
            "ran_at": round(self.ran_at, 1),
        }


def effective_retention_days(config_days: int, license_days: Optional[int] = None) -> int:
    """Amaldagi muddat: ikkalasi berilgan bo‘lsa qisqarog‘i.

    `0` yoki manfiy — "cheklanmagan" degani, shuning uchun u minimumga
    qatnashmaydi. Ikkalasi ham bo‘sh bo‘lsa natija `0` — tozalash o‘chiq.
    """
    candidates = [d for d in (config_days, license_days) if d and d > 0]
    return min(candidates) if candidates else 0


def _delete_files(paths: Iterable[str], root: Path) -> tuple[int, int]:
    """Faqat `root` ichidagi fayllarni o‘chiradi. (soni, baytlar)"""
    deleted = 0
    freed = 0
    root = root.resolve()
    for raw in paths:
        try:
            path = Path(raw)
            if not path.is_absolute():
                path = root / path.name
            path = path.resolve()
        except (OSError, ValueError):
            continue

        # Yo'l bazadan keladi — papkadan tashqariga chiqib ketmasligini
        # tekshirmasdan o'chirish xavfli.
        if root not in path.parents or not path.is_file():
            continue
        try:
            size = path.stat().st_size
            path.unlink()
        except OSError:
            logger.debug("Snapshot o‘chirilmadi: %s", path, exc_info=True)
            continue
        deleted += 1
        freed += size
    return deleted, freed


def _sweep_orphans(root: Path, cutoff_ts: float) -> tuple[int, int]:
    """Bazada yozuvi qolmagan eski snapshotlarni o‘chiradi.

    Yetim fayllar paydo bo‘ladi: bazani qo‘lda tozalash, `image_path` yozilmay
    qolgan xato, eski versiyadan qolgan kadrlar. Ular bo‘lmasa disk hech qachon
    bo‘shamaydi, shuning uchun muddat o‘tgan fayllar ham supuriladi.
    """
    if not root.is_dir():
        return 0, 0

    deleted = 0
    freed = 0
    for path in root.iterdir():
        if not path.is_file() or path.suffix.lower() not in SNAPSHOT_SUFFIXES:
            continue
        try:
            stat = path.stat()
            if stat.st_mtime >= cutoff_ts:
                continue
            path.unlink()
        except OSError:
            logger.debug("Yetim snapshot o‘chirilmadi: %s", path, exc_info=True)
            continue
        deleted += 1
        freed += stat.st_size
    return deleted, freed


def purge_once(
    events: EventLog,
    snapshots_dir: Path,
    retention_days: int,
    *,
    now: Optional[float] = None,
) -> PurgeResult:
    """Muddati o‘tgan voqealarni va ularning rasmlarini o‘chiradi."""
    result = PurgeResult(retention_days=retention_days)
    if retention_days <= 0:
        return result

    deleted, paths = events.purge_older_than(retention_days)
    result.events_deleted = deleted

    files, freed = _delete_files(paths, snapshots_dir)

    cutoff_ts = (now if now is not None else time.time()) - retention_days * 86400
    orphan_files, orphan_freed = _sweep_orphans(snapshots_dir, cutoff_ts)

    result.files_deleted = files + orphan_files
    result.bytes_freed = freed + orphan_freed
    return result


def container_retention_days(container: "AppContainer") -> int:
    """Konteynerdagi konfig va litsenziya asosidagi amaldagi muddat."""
    license_days: Optional[int] = None
    state = container.license_state
    if state is not None:
        license_days = getattr(state, "retention_days", None)
    return effective_retention_days(container.settings.events.retention_days, license_days)


async def run_purge(container: "AppContainer") -> PurgeResult:
    """Bir marta tozalash — bloklovchi ish alohida threadda."""
    days = container_retention_days(container)
    snapshots_dir = container.base_dir / container.settings.paths.snapshots_dir
    result = await asyncio.to_thread(purge_once, container.events, snapshots_dir, days)

    container.last_purge = result
    if result.events_deleted or result.files_deleted:
        get_metrics().record_purge(result.events_deleted, result.files_deleted)
        logger.info(
            "Arxiv tozalandi (%d kun): %d voqea, %d fayl, %.1f MB",
            result.retention_days,
            result.events_deleted,
            result.files_deleted,
            result.bytes_freed / 1_048_576,
        )
    return result


async def retention_loop(container: "AppContainer") -> None:
    """Fon vazifasi: ishga tushganda va keyin belgilangan oraliqda tozalaydi.

    Server o‘chib turgan vaqtda ham arxiv eskirgani uchun birinchi tozalash
    darhol bajariladi, kutmasdan.
    """
    interval = container.settings.events.retention_interval_sec
    while True:
        try:
            if container_retention_days(container) <= 0:
                # Litsenziya keyinroq kelishi mumkin — chiqmay, kutib turamiz.
                await asyncio.sleep(interval)
                continue
            await run_purge(container)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.warning("Arxivni tozalashda xato", exc_info=True)
        await asyncio.sleep(interval)


def purge_summary(container: "AppContainer") -> dict:
    """`GET /api/retention` uchun holat."""
    days = container_retention_days(container)
    state = container.license_state
    last: Optional[PurgeResult] = getattr(container, "last_purge", None)
    events_total: Optional[int] = None
    oldest: Optional[str] = None
    try:
        events_total = container.events.count_all()
        oldest = container.events.oldest_timestamp()
    except Exception:
        logger.debug("Arxiv statistikasi olinmadi", exc_info=True)

    return {
        "ok": True,
        "enabled": days > 0,
        "retention_days": days,
        "config_days": container.settings.events.retention_days,
        "license_days": getattr(state, "retention_days", None) if state else None,
        "interval_sec": container.settings.events.retention_interval_sec,
        "events_total": events_total,
        "oldest_event": oldest,
        "last_purge": last.to_dict() if last else None,
    }


__all__: List[str] = [
    "PurgeResult",
    "container_retention_days",
    "effective_retention_days",
    "purge_once",
    "purge_summary",
    "retention_loop",
    "run_purge",
]
