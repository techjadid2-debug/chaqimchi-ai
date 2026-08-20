#!/usr/bin/env python3
"""Windows do'kon kompyuterida 72 soatlik barqarorlik sinovini yig'adi.

Nega `soak_n100.py` yaramaydi: u Linux uchun yozilgan va uchta manbaga
tayanadi — `systemctl show ... NRestarts`, `127.0.0.1:8742/health` va
`/sys/class/thermal`.  Windows'da uchalasi ham yo'q, skript esa xatoni
yutib **jimgina 0** qaytaradi.  Ya'ni hisobotda "kutilmagan restart 0"
yozilardi — o'lchangani uchun emas, o'lchanmagani uchun.

Bu skript faqat standart kutubxonaga tayanadi (paket import qilmaydi),
shuning uchun uni do'kon kompyuteriga shunchaki nusxalab, istalgan
Python bilan ishga tushirish mumkin:

    python soak_windows.py --hours 72 --output soak-windows.json

Manbalari:
    http://127.0.0.1:8760/api/status   panel (kamera, xato, restart soni)
    %PROGRAMDATA%\\Chaqimchi\\counters.json   doimiy hisoblagichlar
    %PROGRAMDATA%\\Chaqimchi\\data\\outbox.db  navbat va tashlangan hodisalar

Natija `accept_n100_pilot.py` kutgan shaklda chiqadi.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

#: Qurilma paneli (`chaqimchi_ai/local/app.py`).
DEFAULT_STATUS_URL = "http://127.0.0.1:8760/api/status"

#: `outbox.priority`: critical=30 (`chaqimchi_ai/outbox.py`).
CRITICAL_PRIORITY = 30


def default_data_dir() -> Path:
    """Sozlama va navbat qayerda (`chaqimchi_ai/local/paths.py` bilan bir xil)."""
    override = os.environ.get("CHAQIMCHI_LOCAL_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        root = os.environ.get("PROGRAMDATA") or os.environ.get("LOCALAPPDATA") or r"C:\ProgramData"
        return Path(root) / "Chaqimchi"
    return Path.home() / ".chaqimchi"


def read_status(url: str) -> Dict[str, Any]:
    with urllib.request.urlopen(url, timeout=15) as response:  # noqa: S310 - localhost
        return dict(json.load(response))


def read_counters(data_dir: Path) -> Dict[str, int]:
    """Jarayondan omon qoladigan hisoblagichlar (`local/counters.py`)."""
    try:
        data = json.loads((data_dir / "counters.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {
        key: int(value)
        for key, value in data.items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }


def read_outbox(data_dir: Path) -> Dict[str, Optional[int]]:
    """Navbat holati — baza **faqat o'qish** rejimida ochiladi.

    `dead_letter` = butunlay yo'qolgan hodisalar.  Bu jadval hech qachon
    kichraymaydi, ya'ni uning oxirgi qiymati butun sinov davomida
    yo'qolganlar sonini beradi.
    """
    db = data_dir / "data" / "outbox.db"
    if not db.is_file():
        return {"pending": 0, "critical": 0, "poisoned": 0}
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5.0)
        try:
            pending, critical = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(priority >= ?), 0) "
                "FROM outbox WHERE sent_at IS NULL",
                (CRITICAL_PRIORITY,),
            ).fetchone()
            try:
                poisoned = int(conn.execute("SELECT COUNT(*) FROM dead_letter").fetchone()[0])
            except sqlite3.Error:
                poisoned = 0
            return {
                "pending": int(pending or 0),
                "critical": int(critical or 0),
                "poisoned": poisoned,
            }
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return {"pending": None, "critical": None, "poisoned": None, "error": str(exc)[:200]}


def take_sample(status_url: str, data_dir: Path) -> Dict[str, Any]:
    """Bitta o'lchov.  Panel javob bermasa ham yozuv qoladi — uzilishning
    o'zi sinov natijasining bir qismi."""
    sample: Dict[str, Any] = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    try:
        status = read_status(status_url)
        sample.update(
            {
                "running": bool(status.get("running")),
                "cameras_active": int(status.get("cameras_active") or 0),
                "cameras_configured": int(status.get("cameras_configured") or 0),
                "analyzed": int(status.get("analyzed") or 0),
                "errors": int(status.get("errors") or 0),
                "action_errors": int(status.get("action_errors") or 0),
                "status_stale": bool(status.get("status_stale")),
                "uptime_sec": float(status.get("uptime_sec") or 0),
            }
        )
    except Exception as exc:  # noqa: BLE001 - panel o'chgani ham natija
        sample.update({"running": False, "cameras_active": 0, "error": str(exc)[:300]})
    sample["counters"] = read_counters(data_dir)
    sample["outbox"] = read_outbox(data_dir)
    return sample


def summarize(
    samples: List[Dict[str, Any]],
    *,
    duration_hours: float,
    cameras_expected: int,
    planned_reboots: int,
) -> Dict[str, Any]:
    """`accept_n100_pilot.py` kutgan shakl + Windows uchun tafsilot."""
    total = len(samples)
    active = [int(item.get("cameras_active") or 0) for item in samples]
    online = sum(1 for count in active if count >= cameras_expected)

    first = samples[0].get("counters") or {} if samples else {}
    last = samples[-1].get("counters") or {} if samples else {}

    def _delta(name: str) -> int:
        return max(0, int(last.get(name) or 0) - int(first.get(name) or 0))

    chain_crashes = _delta("chain_crashes")
    panel_boots = max(0, _delta("panel_boots") - max(0, planned_reboots))

    last_outbox = (samples[-1].get("outbox") or {}) if samples else {}
    poisoned = int(last_outbox.get("poisoned") or 0)
    critical_stuck = int(last_outbox.get("critical") or 0)

    return {
        "duration_hours": round(max(0.0, duration_hours), 3),
        "cameras_min_active": min(active, default=0),
        # Qabul mezoni: zanjirning o'zi yiqilgani ham, panel jarayoni
        # kutilmaganda qayta ko'tarilgani ham hisobga olinadi.  Ataylab
        # qilingan qayta yoqishlar `--planned-reboots` bilan chiqariladi.
        "unexpected_restarts": chain_crashes + panel_boots,
        "camera_uptime_percent": round(online * 100 / total if total else 0.0, 3),
        # Windows'da harorat manbasi yo'q.  `null` — "o'lchanmadi", "sovuq"
        # emas; Windows qabul profili buni rad etish sababi qilmaydi.
        "max_temperature_c": None,
        # Butunlay yo'qolganlar (`dead_letter`) + hali navbatda qolib
        # ketgan kritiklar.  `soak_n100.py` faqat oxirgi namunadagi
        # navbatni olardi, ya'ni yo'lda tashlangan hodisa ko'rinmasdi.
        "undelivered_critical_events": poisoned + critical_stuck,
        "samples": total,
        "platform": "windows",
        "detail": {
            "chain_crashes": chain_crashes,
            "panel_boots": panel_boots,
            "planned_reboots": max(0, planned_reboots),
            "poisoned_events": poisoned,
            "critical_stuck_in_queue": critical_stuck,
            "cameras_expected": cameras_expected,
            "analyzed_total": int(samples[-1].get("analyzed") or 0) if samples else 0,
            "errors_total": int(samples[-1].get("errors") or 0) if samples else 0,
        },
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hours", type=float, default=72.0)
    parser.add_argument("--interval", type=float, default=60.0)
    parser.add_argument("--status-url", default=DEFAULT_STATUS_URL)
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--cameras", type=int, default=4, help="nechta kamera kutilyapti")
    parser.add_argument(
        "--planned-reboots",
        type=int,
        default=0,
        help="ataylab qilingan qayta yoqishlar (ular nosozlik deb sanalmaydi)",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--samples-file",
        type=Path,
        default=None,
        help="har bir o'lchov JSONL bo'lib yoziladi (sinovdan keyin tahlil uchun)",
    )
    args = parser.parse_args(argv)
    if args.hours <= 0 or args.interval < 1:
        parser.error("hours musbat, interval kamida 1 soniya bo'lishi kerak")
    if args.cameras < 1:
        parser.error("kamera soni kamida 1 bo'lishi kerak")

    data_dir = args.data_dir or default_data_dir()
    started_wall = datetime.now(timezone.utc)
    started = time.monotonic()
    deadline = started + args.hours * 3600
    samples: List[Dict[str, Any]] = []
    failures = 0

    print(f"Sinov boshlandi: {args.hours} soat, har {args.interval:.0f} soniyada")
    print(f"Panel: {args.status_url}")
    print(f"Ma'lumot: {data_dir}")
    print("To'xtatish: Ctrl+C (shu paytgacha yig'ilgani baribir saqlanadi)")

    try:
        while time.monotonic() < deadline:
            sample = take_sample(args.status_url, data_dir)
            samples.append(sample)
            if sample.get("error"):
                failures += 1
            if args.samples_file:
                try:
                    args.samples_file.parent.mkdir(parents=True, exist_ok=True)
                    with args.samples_file.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(sample, ensure_ascii=False) + "\n")
                except OSError:
                    pass
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(args.interval, remaining))
    except KeyboardInterrupt:
        print("\nTo'xtatildi — yig'ilgani saqlanmoqda")

    duration = (time.monotonic() - started) / 3600
    report = summarize(
        samples,
        duration_hours=duration,
        cameras_expected=args.cameras,
        planned_reboots=args.planned_reboots,
    )
    report.update(
        {
            "started_at": started_wall.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "poll_failures": failures,
            "complete": duration >= args.hours,
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print()
    print(f"Davomiylik:        {report['duration_hours']} soat")
    print(f"Kamera uptime:     {report['camera_uptime_percent']}%")
    print(f"Eng kam kamera:    {report['cameras_min_active']}")
    print(f"Kutilmagan restart {report['unexpected_restarts']}")
    print(f"Yo'qolgan kritik:  {report['undelivered_critical_events']}")
    print(f"Natija:            {args.output}")
    if not report["complete"]:
        print("DIQQAT: sinov to'liq tugamadi — qabul uchun yaramaydi")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
