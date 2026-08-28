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

from chaqimchi_ai.local import chain_processes, config_store, counters, paths

logger = logging.getLogger(__name__)

#: Zanjir shuncha soniyadan tez yiqilsa — bu "tugab qolish" emas, **xato**.
#: Cheksiz qayta urinish diskni log bilan to'ldirardi va mijoz muammoni
#: ko'rmasdan qolardi.
CRASH_WINDOW_SEC = 20

#: Ketma-ket shuncha marta tez yiqilgandan keyin darhol qayta urinishni
#: to'xtatamiz va sababni panelda ko'rsatamiz — lekin BUTUNLAY taslim
#: bo'lmaymiz (pastdagi `COOLDOWN_STEPS_SEC` ga qarang).
MAX_RAPID_CRASHES = 3

#: Ketma-ket tez yiqilishdan keyin shuncha kutib yana urinamiz: 1, 5,
#: keyin har 15 daqiqada.
#:
#: Ilgari bu holatda `_auto_restart` ABADIY `False` bo'lardi va zanjirni
#: faqat odam qo'lda ko'tarardi — do'kon egasi uchun bu aynan "svet
#: o'chib yongandan keyin dasturni o'chirib yoqish kerak" edi.  Sabab
#: odatda vaqtinchalik: tok kelganda kompyuter NVR va routerdan oldin
#: yonadi, kamera esa hali javob bermaydi.  Bir necha daqiqadan keyin
#: hammasi joyida bo'ladi — dastur buni o'zi kutib olishi kerak.
COOLDOWN_STEPS_SEC = (60, 300, 900)

#: Panelga ko'rsatiladigan log qatorlari soni.
LOG_TAIL_LINES = 200

#: Holat fayli shuncha soniyadan eski bo'lsa "eskirgan" deb hisoblanadi:
#: zanjir har ~30 soniyada yozadi.
STATUS_STALE_SEC = 180

#: `retail.log` shu hajmdan oshsa keyingi startda chetga suriladi
#: (`retail.log.1`).  Log — bola jarayonning stdout'i, shuning uchun
#: `RotatingFileHandler` ishlamaydi: rotatsiya faqat ochishdan oldin
#: mumkin.  Qulab qayta ishga tushish aynan shu nuqtadan o'tadi, ya'ni
#: eng shovqinli stsenariy (crash-loop) baribir chegaralangan.
LOG_MAX_BYTES = 20 * 1024 * 1024


class RetailSupervisor:
    """Bitta `retail.service` jarayonini kuzatadi."""

    def __init__(self) -> None:
        self._process: Optional[subprocess.Popen] = None
        #: Oxirgi tozalash natijasi — heartbeat shu yerdan oladi.
        #: `remaining` noldan katta bo'lsa yetimlar o'lmagan.
        self.last_orphan_cleanup: Dict[str, Any] = {}
        # `RLock`: `restart()` qulfni ushlab turib `start()` ni chaqiradi.
        # Oddiy `Lock` bilan qulfni oraliqda bo'shatishga to'g'ri kelardi
        # va aynan o'sha oynada kuzatuvchi ip "to'xtatilgan" deb chiqib
        # ketishi mumkin edi — zanjir nazoratsiz qolardi.
        self._lock = threading.RLock()
        self._log_path = paths.logs_dir() / "retail.log"
        self._log_handle: Optional[Any] = None
        self._crashes: Deque[float] = deque(maxlen=MAX_RAPID_CRASHES)
        self._last_error: str = ""
        self._started_at: Optional[float] = None
        self._auto_restart = True
        self._watch_thread: Optional[threading.Thread] = None
        #: Sovish oralig'i: shu vaqtdan keyin yana urinamiz (0 — darhol).
        self._retry_at: float = 0.0
        #: Nechanchi sovish qadamidamiz (`COOLDOWN_STEPS_SEC` indeksi).
        self._cooldown_step: int = 0

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
            self._retry_at = 0.0
            self._cooldown_step = 0
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
        # Hammasi BITTA qulf ichida (`RLock`): ilgari qulf `terminate` bilan
        # `start` orasida bo'shardi va kuzatuvchi ip o'sha oynada
        # "to'xtatilgan" deb chiqib ketishi mumkin edi — zanjir ishlab
        # turgani holda uni hech kim kuzatmasdi va keyingi yiqilish
        # abadiy bo'lardi.
        with self._lock:
            self._auto_restart = False
            self._terminate()
            return self.start()

    # ── Ichki ────────────────────────────────────────────────────────────

    def _alive(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _kill_orphan_chain(self) -> None:
        """Oldingi dastur nusxasidan qolgan zanjirlarni to'xtatadi.

        NEGA KERAK.  Supervisor faqat O'Z bolasini biladi
        (`self._process`).  Dastur yangilanganda eski nusxa o'ladi, uning
        bolasi esa **yetim qolib ishlashda davom etadi** — uni hech kim
        to'xtatmaydi.

        2026-08-26 da oqibati o'lchandi: do'kon kompyuterida BESHTA
        zanjir bir vaqtda ishlayotgan edi (`edge_version`: 0.6.13,
        0.6.16, 0.6.17, 0.6.18, 0.6.19 — beshtasi ham o'sha daqiqada
        hodisa yuborardi).  Har chegara jarayonlar soniga ko'payib
        ketardi: yuz kadri soatlik shifti, davomat ro'yxati, kamera
        byudjeti.  Shu sabab bir necha reliz "ishlamayotgandek"
        ko'rindi — aslida ular ishlayotgan, lekin eski jarayonlar ham
        yonma-yon ishlayotgan edi.

        Ilgari bu yerda **bitta** PID (holat faylidagisi) o'ldirilardi.
        Beshta yetim bo'lsa bu yetmaydi: har restartda bittadan
        kamayardi.  Endi ro'yxat buyruq qatori bo'yicha olinadi va
        hammasi bir yo'la to'xtatiladi.

        Natija saqlanadi (`last_orphan_cleanup`) va heartbeat orqali
        panelga chiqadi: `remaining` noldan katta bo'lsa o'ldirish
        ishlamagan va buni KO'RISH kerak.
        """
        own = {self._process.pid} if self._process is not None else set()
        try:
            result = chain_processes.kill_chains(exclude=own)
        except Exception:  # noqa: BLE001 — tozalash zanjirni ko'tarishga to'sqinlik qilmasin
            logger.exception("Eski zanjirlarni tozalashda kutilmagan xato")
            return
        if result["found"]:
            logger.warning(
                "Yetim zanjirlar: topildi %s, to'xtatildi %s, qoldi %s",
                result["found"],
                result["killed"],
                result["remaining"],
            )
        self.last_orphan_cleanup = result

    def _spawn(self) -> None:
        # Yangi zanjirni ko'tarishdan OLDIN eskisini to'xtatamiz — aks
        # holda ikkalasi bir vaqtda ishlaydi va hamma chegara ikkiga
        # ko'payadi.
        self._kill_orphan_chain()
        data_dir = paths.data_dir()
        (data_dir / "data").mkdir(parents=True, exist_ok=True)

        env = dict(os.environ)
        # Kamera sinovi qoldirgan OpenCV sozlamasi zanjirga o'tmasin: u
        # boshqa maqsad uchun (qisqa kutish) qo'yiladi va bir marta barcha
        # kamerani ochilmaydigan qilib qo'ygan edi.  Zanjir o'z qiymatini
        # o'zi belgilaydi (`retail/runner.py`).
        env.pop("OPENCV_FFMPEG_CAPTURE_OPTIONS", None)
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
        self._rotate_log_if_big()
        self._log_handle = self._log_path.open("a", encoding="utf-8", errors="replace")
        self._log_handle.write(
            f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} ishga tushmoqda =====\n"
        )
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
        counters.bump("chain_starts")
        logger.info("Retail zanjiri ishga tushdi (pid %s)", self._process.pid)

        if self._watch_thread is None or not self._watch_thread.is_alive():
            self._watch_thread = threading.Thread(
                target=self._watch, name="retail-supervisor", daemon=True
            )
            self._watch_thread.start()

    def _rotate_log_if_big(self) -> None:
        """Katta logni chetga suradi — `C:` disk log bilan to'lmasin."""
        try:
            if self._log_path.stat().st_size <= LOG_MAX_BYTES:
                return
            backup = self._log_path.with_name(self._log_path.name + ".1")
            backup.unlink(missing_ok=True)
            self._log_path.rename(backup)
        except OSError:
            # Rotatsiya bo'lmasa ham zanjir ishga tushishi muhimroq.
            logger.warning("retail.log rotatsiyasi bajarilmadi", exc_info=True)

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
        """Jarayon yiqilsa qayta ishga tushiradi — hech qachon taslim bo'lmay.

        Tez ketma-ket yiqilish odatda vaqtinchalik sabab: tok kelganda
        kompyuter NVR'dan oldin yonadi, kamera hali javob bermaydi.
        Shuning uchun urinish TO'XTAMAYDI, faqat sekinlashadi
        (`COOLDOWN_STEPS_SEC`).
        """
        while True:
            time.sleep(2)
            with self._lock:
                if not self._tick(time.time()):
                    return

    def _tick(self, now: float) -> bool:
        """Kuzatuvchi siklining bitta qadami.  `False` — ip yopilsin.

        Alohida usul, chunki tiklanish mantig'i aynan shu yerda va uni
        soatga bog'liq bo'lmagan holda sinash kerak: "svet o'chib
        yongandan keyin o'zi ko'tariladimi" degan savol shu qadamlar
        ketma-ketligi bilan hal bo'ladi.
        """
        if not self._auto_restart:
            if not self._alive():
                # Mijoz o'zi to'xtatgan.  Ip yopiladi; keyingi `_spawn()`
                # yangisini ochadi (shuning uchun havola shu yerda
                # tozalanadi — `is_alive()` hali `True` qaytarayotgan ip
                # yangisini to'sib qo'ymasin).
                self._watch_thread = None
                return False
            return True

        if self._alive():
            # Bir marta uzoq ishlab ketdi — sovish qadami nolga qaytadi,
            # keyingi nosozlikda yana tezda ko'tariladi.
            if self._cooldown_step and now - (self._started_at or 0) > CRASH_WINDOW_SEC:
                self._cooldown_step = 0
                self._last_error = ""
            return True

        if self._retry_at:
            if now < self._retry_at:
                return True
            # Kutish tugadi — hisob-kitobsiz, to'g'ridan-to'g'ri qayta
            # urinamiz.  Bu yerda `_note_exit` chaqirilsa KUTILGAN
            # vaqtning o'zi "zanjir uzoq ishladi" bo'lib hisoblanardi va
            # sovish qadami har safar nolga qaytardi: 1 → 5 → 15
            # daqiqalik o'sish hech qachon ishlamasdi.
            self._retry_at = 0.0
            counters.bump("chain_crashes")
            logger.warning("Sovish oralig'i tugadi — zanjir qayta urinilmoqda")
            self._spawn()
            return True

        ran_for = now - (self._started_at or now)
        self._terminate()
        if not self._note_exit(ran_for, now=now):
            return True

        # Bu — qabul mezonidagi "kutilmagan qayta ishga tushish".  Mijoz
        # o'zi bosgan `restart()` bu yerga tushmaydi: u `_auto_restart`
        # ni o'chirib, keyin `start()` chaqiradi.
        counters.bump("chain_crashes")
        logger.warning("Zanjir to'xtab qoldi — qayta ishga tushirilmoqda")
        self._spawn()
        return True

    def _note_exit(self, ran_for: float, *, now: Optional[float] = None) -> bool:
        """Zanjir to'xtadi — HOZIR qayta ko'tarilsinmi?

        `False` — hozir emas: ketma-ket tez yiqilish sabab sovish oralig'i
        qo'yildi (`_retry_at`).  Kutish tugagach kuzatuvchi o'zi qayta
        urinadi; taslim bo'lish YO'Q.
        """
        moment = time.time() if now is None else now
        if ran_for >= CRASH_WINDOW_SEC:
            # Uzoq ishlab, keyin to'xtadi — bu "xato" emas, oddiy yiqilish.
            self._crashes.clear()
            self._cooldown_step = 0
            self._retry_at = 0.0
            return True

        self._crashes.append(moment)
        if len(self._crashes) < MAX_RAPID_CRASHES:
            self._retry_at = 0.0
            return True

        wait = COOLDOWN_STEPS_SEC[min(self._cooldown_step, len(COOLDOWN_STEPS_SEC) - 1)]
        self._cooldown_step += 1
        self._crashes.clear()
        self._retry_at = moment + wait
        self._last_error = (
            "AI xizmati ketma-ket bir necha marta to'xtadi. "
            f"{wait // 60} daqiqadan keyin o'zi yana urinadi — "
            "kamera yoki NVR o'chgan bo'lishi mumkin."
        )
        logger.error(
            "Zanjir %s marta tez yiqildi — %s soniyadan keyin qayta urinamiz",
            MAX_RAPID_CRASHES,
            wait,
        )
        return False

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
            # Sovish oralig'i: panel "necha daqiqadan keyin o'zi urinadi"
            # deb aniq yozsin — mijoz kutsinmi yoki NVR'ni tekshirsinmi,
            # bilib tursin.
            "retry_in_sec": (
                max(0, int(self._retry_at - time.time())) if self._retry_at else 0
            ),
            "started_at": self._started_at,
            "uptime_sec": (time.time() - self._started_at) if (running and self._started_at) else 0,
            "error": self._last_error,
            "cameras_configured": status_file.get("cameras_configured", 0),
            "cameras_active": status_file.get("cameras_active", 0),
            "cameras": status_file.get("cameras", {}),
            # Klip hisoblagichlari: "hodisa bor, klip yo'q" holatini panel
            # ham, cloud ham ko'rsin.
            "clips": status_file.get("clips") or {},
            # Rasm yozildimi — klip bilan bir xil sabab.
            "snapshots": status_file.get("snapshots") or {},
            # Davomat va mijoz portreti sifati.  Holat faylida bor
            # (`retail/service.py: write_status`) va heartbeat ularni
            # kutadi (`local/cloud_config.py`) — o'rtada shu qator
            # yo'q edi va cloudga doim nol borardi.  Yuqoridagi
            # `analyzed`/`errors` izohi bilan bir xil sabab.
            "face_crops": status_file.get("face_crops") or {},
            "demography": status_file.get("demography") or {},
            # Tarif faollashtirilmagani sabab tashlangan hodisalar — panel
            # "hisobot cloudga bormayapti" ogohlantirishini shundan chiqaradi.
            "plan_filtered": status_file.get("plan_filtered", 0),
            # Bu uchtasi holat faylida allaqachon bor edi, lekin shu yerdan
            # o'tmasdi — natijada `cloud_config.send_heartbeat()` ularni
            # `status` dan o'qiy olmay, cloudga DOIM `0, 0, 0` yuborardi va
            # cloudning "qurilma jimgina ishlamay qoldi" detektori
            # (`cloud/main.py`) Windows yo'lida umuman ishlamasdi.
            "analyzed": int(status_file.get("analyzed") or 0),
            "errors": int(status_file.get("errors") or 0),
            "action_errors": int(status_file.get("action_errors") or 0),
            "events": int(status_file.get("events") or 0),
            # 72 soatlik sinovning asosiy mezoni: zanjir o'zi necha marta
            # yiqilib, qayta ko'tarilgan.  Xotiradagi hisoblagich restart
            # paytida yo'qolardi, shuning uchun diskdan o'qiladi.
            "restart_count": int(counters.read().get("chain_crashes") or 0),
            # Zanjir ishlayapti-yu holat fayli eskirgan bo'lsa — u qotib
            # qolgan.  Mijoz uchun bu "ishlamayapti" bilan bir xil, shuning
            # uchun panel buni alohida ko'rsatishi kerak.
            "status_stale": bool(status_file.get("stale", True)) if running else False,
            # Zanjir o'lchagan ish ko'rsatkichlari.  Bular ham holat
            # faylida bor edi-yu shu yerdan o'tmasdi: `send_heartbeat`
            # ularni `status` dan o'qishga urinardi va doim bo'sh
            # topardi, ya'ni admin paneldagi FPS va kechikish ustunlari
            # Windows yo'lida HECH QACHON to'lmagan.
            "fps": status_file.get("fps"),
            "inference_latency_ms": status_file.get("inference_latency_ms"),
            "pressure": status_file.get("pressure") or {},
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
