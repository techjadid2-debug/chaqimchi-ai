#!/usr/bin/env python3
"""Imzolangan Sotqin paketini atomik o'rnatadi va xatoda rollback qiladi.

Ikki rejim:

    # cloud'dan (odatiy)
    apply_signed_update.py --fetch-version 0.6.1 --cloud https://ai.example.uz

    # qo'lda ko'chirilgan fayllardan (zaxira yo'l)
    apply_signed_update.py paket.tar.gz paket.json

**Tartib qoidasi:** yiqilishi mumkin bo'lgan hamma narsa `current`
almashtirilishidan **oldin** bajariladi:

    tekshirish → yoyish → model → requirements → unitlar → chown
      → `current` almashtirish → daemon-reload → restart → health → (rollback)

Uchta narsa ataylab shunday:

1. **`models/` symlink qilinmaydi.**  Ilgari u bo'sh `shared/models` ga
   ulanardi va birinchi yangilanish detektor modelini yo'q qilardi.  Model
   runtime'da faqat o'qiladi, ya'ni relizning o'z papkasida turishi kerak.
   `data/` esa symlink bo'lib **qoladi**: xizmatlar `ProtectSystem=strict`
   ostida ishlaydi va faqat `shared/data` ga yoza oladi.
2. **Health darvozasi qurilmani oldingidan sog'lomroq bo'lishini talab
   qilmaydi.**  Kamerasiz stendda `chaqimchi-retail` umuman ishga tushmaydi
   (`retail/service.py` kamera topilmasa xato beradi), shuning uchun faqat
   yangilanishdan **oldin ishlab turgan** xizmatlardan keyin ham ishlashi
   so'raladi.  Agent uchun esa 503 ham yetarli — u pairing yo'qligini
   bildiradi, lekin butun zanjir import bo'lganini isbotlaydi.
3. **Yangi Python bog'liqligi standart holatda rad etiladi.**  venv reliz
   tashqarisida va umumiy, ya'ni `pip install` orqaga qaytmaydi —
   `current` ni qaytarish rollback'ni yolg'onga aylantirardi.

Barcha tashqi chaqiruvlar injektsiya qilinadi, shuning uchun modul
qurilmasiz, root'siz va systemd'siz test qilinadi.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from chaqimchi_ai.signed_update import (
    UpdateVerificationError,
    sha256_file,
    verify_release_manifest,
)

#: Chiqish kodlari — avtomatlashtirish shularga qarab qaror qiladi.
EXIT_OK = 0
EXIT_PRECONDITION = 1  # tekshiruv yiqildi, qurilmada hech nima o'zgarmadi
EXIT_ROLLED_BACK = 2  # health yiqildi, oldingi versiya qaytarildi
EXIT_BROKEN = 3  # rollback ham yiqildi — odam kerak

SOTQIN = "chaqimchi-sotqin.service"
RETAIL = "chaqimchi-retail.service"
ATTENDANCE = "chaqimchi-attendance.service"

#: Cloud'dan yuklab olinadigan eng katta paket.
MAX_ARCHIVE_BYTES = 200 * 1024 * 1024


def _normalized_arch(value: str) -> str:
    aliases = {"arm64": "aarch64", "amd64": "x86_64"}
    key = value.strip().lower()
    return aliases.get(key, key)


def validate_release_target(manifest: dict, machine: Optional[str] = None) -> None:
    """V2 Sotqin paketining shu qurilmaga mo'ljallanganini tekshiradi."""
    if int(manifest.get("schema_version", 1)) < 2:
        return
    if manifest.get("product") not in {"chaqimchi-sotqin", "chaqimchi-lite"}:
        raise UpdateVerificationError("Release boshqa mahsulot uchun")
    expected = _normalized_arch(str(manifest.get("target_arch", "")))
    actual = _normalized_arch(machine or platform.machine())
    if expected not in {"any", actual}:
        raise UpdateVerificationError(
            f"Release arxitekturasi mos emas: paket={expected}, qurilma={actual}"
        )


def _http_get(url: str, timeout: float) -> Tuple[int, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            return int(response.status), response.read(MAX_ARCHIVE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read(MAX_ARCHIVE_BYTES + 1)


def _chown_tree(path: Path, user: str, group: str) -> None:
    if os.geteuid() != 0:
        return
    try:
        shutil.chown(path, user, group)
    except (LookupError, PermissionError, OSError):
        return
    for child in path.rglob("*"):
        try:
            shutil.chown(child, user, group)
        except (LookupError, PermissionError, OSError):
            continue


@dataclass
class Updater:
    root: Path = Path("/opt/chaqimchi")
    public_key: Path = Path("/etc/chaqimchi/update-public.pem")
    venv_python: Path = Path("/opt/chaqimchi/venv/bin/python")
    systemd_dir: Path = Path("/etc/systemd/system")
    health_url: str = "http://127.0.0.1:8742/health"
    health_timeout: float = 120.0
    allow_pip: bool = False
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run
    http_get: Callable[[str, float], Tuple[int, bytes]] = _http_get
    chown: Callable[[Path, str, str], None] = _chown_tree
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    machine: Callable[[], str] = platform.machine
    log: List[str] = field(default_factory=list)

    # ── Yordamchilar ─────────────────────────────────────────────────────

    def _run(self, command: Sequence[str]) -> subprocess.CompletedProcess:
        return self.runner(list(command), capture_output=True, text=True, check=False)

    def _unit_state(self, unit: str) -> str:
        result = self._run(["systemctl", "is-active", unit])
        return (result.stdout or "").strip() or "unknown"

    def _installed_units(self) -> List[str]:
        """Diskda mavjud unitlar.  Yangi unit o'z-o'zidan yoqilmaydi."""
        return [
            unit for unit in (SOTQIN, RETAIL, ATTENDANCE) if (self.systemd_dir / unit).is_file()
        ]

    def note(self, message: str) -> None:
        self.log.append(message)
        print(message)

    # ── Yuklab olish ─────────────────────────────────────────────────────

    def fetch(self, cloud: str, version: str, target: Path) -> Tuple[Path, Path]:
        base = cloud.rstrip("/")
        if not base.startswith("https://") and "127.0.0.1" not in base and "localhost" not in base:
            raise UpdateVerificationError("Cloud manzili HTTPS bo'lishi kerak")
        name = f"chaqimchi-sotqin-{version}"
        pairs = ((f"{base}/releases/{name}.json", target / f"{name}.json"),
                 (f"{base}/releases/{name}.tar.gz", target / f"{name}.tar.gz"))
        for url, path in pairs:
            status, payload = self.http_get(url, 120.0)
            if status != 200:
                raise UpdateVerificationError(f"Yuklab bo'lmadi ({status}): {url}")
            if len(payload) > MAX_ARCHIVE_BYTES:
                raise UpdateVerificationError(f"Paket juda katta: {url}")
            path.write_bytes(payload)
        return pairs[1][1], pairs[0][1]

    # ── Bosqichlar ───────────────────────────────────────────────────────

    def provision_models(self, previous: Optional[Path], destination: Path) -> None:
        """Detektor modelini yangi relizga keltiradi.

        Ilgari bu yerda `models/` bo'sh `shared/models` ga symlink qilinardi
        va birinchi yangilanish modelni yo'q qilardi.  Retail esa qayta ishga
        tushirilmagani uchun buni hech kim sezmasdi — mijoz obyektida,
        birinchi qayta yuklashdan keyin bilinardi.
        """
        manifest_path = destination / "models" / "retail_manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            files: Dict[str, Any] = manifest.get("files") or {}
        except (OSError, json.JSONDecodeError) as exc:
            raise UpdateVerificationError("Paketda model manifesti yo'q") from exc

        target = destination / "models" / "retail"
        target.mkdir(parents=True, exist_ok=True)
        missing = []
        for name, entry in files.items():
            expected = str(entry.get("sha256", "")).lower()
            source = (previous / "models" / "retail" / name) if previous else None
            if source is not None and source.is_file() and sha256_file(source) == expected:
                shutil.copy2(source, target / name)
                continue
            missing.append(name)

        if not missing:
            self.note(f"Model oldingi relizdan ko'chirildi ({len(files)} fayl)")
            return

        self.note(f"Model yuklab olinmoqda: {', '.join(missing)}")
        result = self._run([str(self.venv_python), str(destination / "scripts" / "fetch_retail_model.py")])
        if result.returncode != 0:
            raise UpdateVerificationError(
                "Model yuklab olinmadi — yangilanish to'xtatildi (eski versiya joyida qoldi)"
            )

    def check_requirements(self, previous: Optional[Path], destination: Path) -> None:
        """Bog'liqliklar o'zgargan bo'lsa ogohlantiradi yoki o'rnatadi."""
        if previous is None:
            return
        names = ["requirements-sotqin.txt"]
        if (self.systemd_dir / ATTENDANCE).is_file():
            names.append("requirements-attendance.txt")
        changed = []
        for name in names:
            old, new = previous / name, destination / name
            if not new.is_file():
                continue
            if not old.is_file() or sha256_file(old) != sha256_file(new):
                changed.append(name)
        if not changed:
            return
        if not self.allow_pip:
            raise UpdateVerificationError(
                f"Bu relizda yangi Python paketlari bor ({', '.join(changed)}). "
                "`--pip` bilan qayta ishga tushiring."
            )
        for name in changed:
            self.note(f"Paketlar o'rnatilmoqda: {name}")
            result = self._run(
                [str(self.venv_python), "-m", "pip", "install", "-r", str(destination / name)]
            )
            if result.returncode != 0:
                raise UpdateVerificationError(f"pip yiqildi: {name}")

    def sync_units(self, destination: Path) -> Dict[str, bytes]:
        """Faqat allaqachon o'rnatilgan unitlarni yangilaydi.

        Yangi unit o'z-o'zidan yoqilmaydi — bu operatorning qaroriga
        qoldiriladi.  Rollback uchun eski baytlar qaytariladi.
        """
        restore: Dict[str, bytes] = {}
        for unit in self._installed_units():
            new_file = destination / "deploy" / unit
            if not new_file.is_file():
                continue
            live = self.systemd_dir / unit
            old = live.read_bytes()
            new = new_file.read_bytes()
            if old == new:
                continue
            restore[unit] = old
            live.write_bytes(new)
            live.chmod(0o644)
            self.note(f"Systemd unit yangilandi: {unit}")
        return restore

    def healthy(self, baseline: Dict[str, str]) -> bool:
        """Yangilanishdan keyin qurilma oldingidan yomon emasmi.

        Agent javob berishi shart (503 ham bo'ladi — u pairing yo'qligini
        bildiradi, lekin uvicorn ilovani import qilganini isbotlaydi).
        Boshqa xizmatlardan esa faqat **oldin ishlab turganlari** so'raladi:
        kamerasiz stendda retail baribir ishga tushmaydi va bu yangilanishni
        rad etish uchun sabab emas.
        """
        deadline = self.clock() + self.health_timeout
        agent_ok = False
        while self.clock() < deadline:
            status, payload = self.http_get(self.health_url, 3.0)
            if status and b'"product"' in payload and b"Sotqin" in payload:
                agent_ok = True
                break
            self.sleep(2.0)
        if not agent_ok:
            self.note("Agent javob bermadi")
            return False

        for unit, was in baseline.items():
            if was != "active":
                continue
            if self._unit_state(unit) != "active":
                self.note(f"{unit} yangilanishdan keyin ishga tushmadi")
                return False
        for unit, was in baseline.items():
            if was != "active":
                self.note(f"{unit} yangilanishdan oldin ham ishlamayotgan edi — o'tkazib yuborildi")
        return True

    # ── Asosiy oqim ──────────────────────────────────────────────────────

    def run(self, archive: Path, manifest_path: Path) -> int:
        manifest = verify_release_manifest(archive, manifest_path, self.public_key)
        validate_release_target(manifest, self.machine())
        version = str(manifest["version"])

        root = self.root.resolve()
        if str(root) in {"/", str(Path.home())}:
            raise UpdateVerificationError("Xavfsiz install root talab qilinadi")
        releases = root / "releases"
        releases.mkdir(parents=True, exist_ok=True)
        destination = releases / version
        if destination.exists():
            raise UpdateVerificationError(f"Bu versiya allaqachon o'rnatilgan: {version}")
        current = root / "current"
        previous = current.resolve() if current.exists() else None

        with tempfile.TemporaryDirectory(dir=releases, prefix=".update-") as temp_name:
            stage = Path(temp_name)
            with tarfile.open(archive, "r:gz") as package:
                package.extractall(stage, filter="data")
            children = list(stage.iterdir())
            source = children[0] if len(children) == 1 and children[0].is_dir() else stage
            product = manifest.get("product", "chaqimchi-lite")
            required = (
                source / "chaqimchi_ai" / "sotqin_agent.py"
                if product == "chaqimchi-sotqin"
                else source / "webapp" / "main.py"
            )
            if not required.is_file():
                raise UpdateVerificationError(f"Paketda {required.name} yo'q")
            if source == stage:
                destination.mkdir()
                for child in children:
                    shutil.move(str(child), destination / child.name)
            else:
                shutil.move(str(source), destination)

        # `data` symlink **majburiy**: xizmatlar `ProtectSystem=strict` ostida
        # ishlaydi va faqat `shared/data` ga yoza oladi.  `models` esa yo'q —
        # u faqat o'qiladi va relizning o'z papkasida turishi kerak.
        shared_data = root / "shared" / "data"
        shared_data.mkdir(parents=True, exist_ok=True)
        link = destination / "data"
        if link.exists() and not link.is_symlink():
            shutil.move(str(link), str(destination / "data.release"))
        link.symlink_to(shared_data, target_is_directory=True)

        self.provision_models(previous, destination)
        self.check_requirements(previous, destination)
        restore_units = self.sync_units(destination)
        self.chown(destination, "chaqimchi", "chaqimchi")

        baseline = {unit: self._unit_state(unit) for unit in self._installed_units()}

        # ── Shu qatordan boshlab qurilma o'zgaradi ──────────────────────
        current_tmp = root / ".current-next"
        current_tmp.unlink(missing_ok=True)
        current_tmp.symlink_to(destination, target_is_directory=True)
        os.replace(current_tmp, current)
        if restore_units:
            self._run(["systemctl", "daemon-reload"])
        self._run(["systemctl", "restart", *self._installed_units()])

        if self.healthy(baseline):
            self.note(f"Update muvaffaqiyatli: {version}")
            return EXIT_OK

        if previous is None:
            self.note("Oldingi versiya yo'q — qaytarib bo'lmaydi")
            return EXIT_BROKEN
        try:
            rollback_tmp = root / ".current-rollback"
            rollback_tmp.unlink(missing_ok=True)
            rollback_tmp.symlink_to(previous, target_is_directory=True)
            os.replace(rollback_tmp, current)
            for unit, payload in restore_units.items():
                (self.systemd_dir / unit).write_bytes(payload)
            if restore_units:
                self._run(["systemctl", "daemon-reload"])
            self._run(["systemctl", "restart", *self._installed_units()])
        except OSError:
            self.note("Rollback yiqildi — qurilma holati noaniq")
            return EXIT_BROKEN
        self.note(f"Health o'tmadi, {previous.name} ga qaytarildi")
        return EXIT_ROLLED_BACK

    def write_log(self, line: str) -> None:
        path = self.root / "shared" / "logs" / "update.log"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(f"{datetime.now(timezone.utc).isoformat()} {line}\n")
        except OSError:
            pass


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, nargs="?")
    parser.add_argument("manifest", type=Path, nargs="?")
    parser.add_argument("--fetch-version", default=None, help="cloud'dan shu versiyani oladi")
    parser.add_argument("--cloud", default=None, help="cloud manzili (--fetch-version bilan)")
    parser.add_argument("--public-key", type=Path, default=Path("/etc/chaqimchi/update-public.pem"))
    parser.add_argument("--root", type=Path, default=Path("/opt/chaqimchi"))
    parser.add_argument("--pip", action="store_true", help="yangi bog'liqliklarni o'rnatishga ruxsat")
    args = parser.parse_args(argv)

    if args.fetch_version and not args.cloud:
        parser.error("--fetch-version bilan --cloud ham kerak")
    if not args.fetch_version and not (args.archive and args.manifest):
        parser.error("archive va manifest, yoki --fetch-version --cloud bering")

    updater = Updater(
        root=args.root,
        public_key=args.public_key,
        allow_pip=args.pip,
    )

    lock_path = args.root / ".update.lock"
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock = lock_path.open("w")
    except OSError as exc:
        print(f"XATO: {exc}", file=sys.stderr)
        return EXIT_PRECONDITION
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("XATO: boshqa yangilanish ketmoqda", file=sys.stderr)
        return EXIT_PRECONDITION

    try:
        with tempfile.TemporaryDirectory(prefix="chaqimchi-update-") as download_dir:
            if args.fetch_version:
                archive, manifest = updater.fetch(
                    args.cloud, args.fetch_version, Path(download_dir)
                )
            else:
                archive, manifest = args.archive, args.manifest
            code = updater.run(archive, manifest)
    except UpdateVerificationError as exc:
        print(f"XATO: {exc}", file=sys.stderr)
        updater.write_log(f"FAILED {exc}")
        return EXIT_PRECONDITION
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()

    updater.write_log(f"exit={code} " + " | ".join(updater.log))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
