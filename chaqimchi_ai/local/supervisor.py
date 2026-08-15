"""AI zanjirini boshqarish: ishga tushirish, to'xtatish, holatini bilish.

Nega alohida jarayon (thread emas): `chaqimchi_ai.retail.service` OpenVINO va
FFmpeg bilan ishlaydi, ya'ni C darajasida yiqilishi mumkin.  Sehrgar u bilan
bitta jarayonda bo'lsa, zanjir yiqilganda mijoz brauzerda **oq sahifa**
ko'rardi va nima bo'lganini bilmasdi.  Alohida jarayonda esa panel tirik
qoladi va aynan xato matnini ko'rsata oladi.

Linux'da bu ishni `systemd` qiladi (`Restart=always`).  Windows'da xizmat
hali yo'q, shuning uchun qayta ishga tushirish mas'uliyati shu modulda.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

from chaqimchi_ai.local import config_store, paths

logger = logging.getLogger(__name__)

#: Zanjir shuncha soniyadan tez yiqilsa — bu "tugab qolish" emas, **xato**.
#: Cheksiz qayta urinish diskni log bilan to'ldirardi va mijoz muammoni
#: ko'rmasdan qolardi.
CRASH_WINDOW_SEC = 20

#: Ketma-ket shuncha marta tez yiqilgandan keyin to'xtaymiz va sababni
#: panelda ko'rsatamiz.
MAX_RAPID_CRASHES = 3

#: Panelga ko'rsatiladigan log qatorlari soni.
LOG_TAIL_LINES = 200

#: Holat fayli shuncha soniyadan eski bo'lsa "eskirgan" deb hisoblanadi:
#: zanjir har ~30 soniyada yozadi.
STATUS_STALE_SEC = 180


class RetailSupervisor:
    """Bitta `retail.service` jarayonini kuzatadi."""

    def __init__(self) -> None:
        self._process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._log_path = paths.logs_dir() / "retail.log"
        self._log_handle: Optional[Any] = None
        self._crashes: Deque[float] = deque(maxlen=MAX_RAPID_CRASHES)
        self._last_error: str = ""
        self._started_at: Optional[float] = None
        self._auto_restart = True
        self._watch_thread: Optional[threading.Thread] = None

    # ── Boshqaruv ────────────────────────────────────────────────────────

    def start(self) -> Dict[str, Any]:
        """Zanjirni ishga tushiradi.  Allaqachon ishlayotgan bo'lsa — tegmaydi."""
        with self._lock:
            if self._alive():
                return self.status()

            if not config_store.model_available():
                self._last_error = (
                    "AI modeli topilmadi. Dasturni qayta o'rnating — "
                    "o'rnatuvchi modelni birga olib keladi."
                )
                return self.status()
            if not config_store.cameras():
                self._last_error = "Avval kamera qo'shing."
                return self.status()

            self._last_error = ""
            self._crashes.clear()
            self._auto_restart = True
            self._spawn()
            return self.status()

    def stop(self) -> Dict[str, Any]:
        """Zanjirni to'xtatadi.  Mijoz "to'xtatish" tugmasini bosganda."""
        with self._lock:
            self._auto_restart = False
            self._terminate()
            return self.status()

    def restart(self) -> Dict[str, Any]:
        """Sozlama o'zgargach chaqiriladi.

        Zanjir kamera ro'yxatini faqat ishga tushishda o'qiydi — brokerni,
        byudjetni va ring bufferni ishlab turganda qayta qurish ancha
        murakkab va xatoga moyil bo'lardi.  Qayta ishga tushish bir necha
        soniya oladi va natijasi aniq.
        """
        with self._lock:
            # Avval avtomatik qayta ishga tushirishni o'chiramiz: aks holda
            # kuzatuvchi ip biz `start()` ga yetgunimizcha bo'sh o'rinni
            # ko'rib, ikkinchi jarayonni ochib yuborardi.
            self._auto_restart = False
            self._terminate()
        return self.start()

    # ── Ichki ────────────────────────────────────────────────────────────

    def _alive(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _spawn(self) -> None:
        data_dir = paths.data_dir()
        (data_dir / "data").mkdir(parents=True, exist_ok=True)

        env = dict(os.environ)
        env["CHAQIMCHI_CONFIG"] = str(config_store.config_file())
        env["CHAQIMCHI_RETAIL_STATUS"] = str(paths.status_path())
        # Bolaning stdout'i buferlanmasin: yiqilganda oxirgi qatorlar
        # logda qolishi kerak, aks holda eng muhim xabar yo'qoladi.
        env["PYTHONUNBUFFERED"] = "1"

        command = [
            sys.executable,
            "-m",
            "chaqimchi_ai.retail.service",
            "--config",
            str(config_store.config_file()),
            "--base-dir",
            str(data_dir),
        ]
        self._log_handle = self._log_path.open("a", encoding="utf-8", errors="replace")
        self._log_handle.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} ishga tushmoqda =====\n")
        self._log_handle.flush()

        creationflags = 0
        if os.name == "nt":
            # Konsol oynasi ochilmasin: mijoz brauzerda ishlaydi, qora
            # oyna faqat qo'rqitadi.
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        self._process = subprocess.Popen(  # noqa: S603 — buyruq qat'iy, foydalanuvchi kiritmaydi
            command,
            stdout=self._log_handle,
            stderr=subprocess.STDOUT,
            env=env,
            cwd=str(paths.app_root()),
            creationflags=creationflags,
        )
        self._started_at = time.time()
        logger.info("Retail zanjiri ishga tushdi (pid %s)", self._process.pid)

        if self._watch_thread is None or not self._watch_thread.is_alive():
            self._watch_thread = threading.Thread(
                target=self._watch, name="retail-supervisor", daemon=True
            )
            self._watch_thread.start()

    def _terminate(self) -> None:
        process, self._process = self._process, None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning("Zanjir 10 soniyada to'xtamadi — majburan yopiladi")
                process.kill()
        if self._log_handle is not None:
            try:
                self._log_handle.close()
            finally:
                self._log_handle = None
        self._started_at = None

    def _watch(self) -> None:
        """Jarayon yiqilsa qayta ishga tushiradi (cheklangan urinish bilan)."""
        while True:
            time.sleep(2)
            with self._lock:
                if not self._auto_restart:
                    if not self._alive():
                        return
                    continue
                if self._alive():
                    continue

                ran_for = time.time() - (self._started_at or time.time())
                self._terminate()

                if ran_for < CRASH_WINDOW_SEC:
                    self._crashes.append(time.time())
                    if len(self._crashes) >= MAX_RAPID_CRASHES:
                        self._auto_restart = False
                        self._last_error = (
                            "AI xizmati ketma-ket bir necha marta to'xtadi. "
                            "Kamera manzilini tekshiring yoki jurnalni ko'ring."
                        )
                        logger.error("Zanjir %s marta tez yiqildi — to'xtatildi", MAX_RAPID_CRASHES)
                        return
                else:
                    self._crashes.clear()

                logger.warning("Zanjir to'xtab qoldi — qayta ishga tushirilmoqda")
                self._spawn()

    # ── Holat ────────────────────────────────────────────────────────────

    def _read_status_file(self) -> Dict[str, Any]:
        path = paths.status_path()
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        updated = float(data.get("updated_at") or 0)
        data["stale"] = (time.time() - updated) > STATUS_STALE_SEC if updated else True
        return data

    def status(self) -> Dict[str, Any]:
        running = self._alive()
        status_file = self._read_status_file()
        return {
            "running": running,
            "auto_restart": self._auto_restart,
            "started_at": self._started_at,
            "uptime_sec": (time.time() - self._started_at) if (running and self._started_at) else 0,
            "error": self._last_error,
            "cameras_configured": status_file.get("cameras_configured", 0),
            "cameras_active": status_file.get("cameras_active", 0),
            "cameras": status_file.get("cameras", {}),
            # Zanjir ishlayapti-yu holat fayli eskirgan bo'lsa — u qotib
            # qolgan.  Mijoz uchun bu "ishlamayapti" bilan bir xil, shuning
            # uchun panel buni alohida ko'rsatishi kerak.
            "status_stale": bool(status_file.get("stale", True)) if running else False,
            "log_path": str(self._log_path),
        }

    def log_tail(self, lines: int = LOG_TAIL_LINES) -> List[str]:
        """Jurnalning oxirgi qatorlari — panelda "Nima bo'ldi?" tugmasi uchun."""
        if not self._log_path.is_file():
            return []
        try:
            with self._log_path.open("r", encoding="utf-8", errors="replace") as handle:
                return [line.rstrip("\n") for line in deque(handle, maxlen=lines)]
        except OSError:
            return []


def log_file() -> Path:
    return paths.logs_dir() / "retail.log"
