#!/usr/bin/env python3
"""Sotqin qurilmasidagi tekshiruv ro'yxati — "ishladimi?" degan savolga javob.

`scripts/production_preflight.py` cloud `.env` faylini tekshiradi; qurilma
uchun ekvivalenti yo'q edi. O'rnatuvchi obyektda turib ishning tugaganini
bilishning yagona yo'li — xizmat loglarini o'qish bo'lgan, bu esa undan
kutilmaydi.

Har tekshiruv ikkita narsa beradi: **holat** va **nima qilish kerak**.
"FAIL: iGPU" foydasiz; "iGPU drayveri yo'q, inferens CPU'da ketadi —
`apt-get install intel-opencl-icd`" foydali.

Barcha tashqi chaqiruvlar (`subprocess`, HTTP, fayl tizimi) injektsiya
qilinadi, shuning uchun modul qurilmasiz, ffmpeg'siz va kamerasiz test
qilinadi.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

#: Diskda kamida shuncha bo'sh joy bo'lmasa klip yozib bo'lmaydi.
MIN_FREE_BYTES = 20 * 1024**3

#: Muhit faylida qolib ketmasligi kerak bo'lgan belgilar.
PLACEHOLDERS = ("GENERATE", "FROM_PAIRING", "FROM_DEVICE", "CHANGE_ME", "example.uz")

#: Bularsiz qurilma umuman ishlamaydi.
REQUIRED_ENV = (
    "CHAQIMCHI_CLOUD_URL",
    "CHAQIMCHI_SITE_ID",
    "CHAQIMCHI_DEVICE_ID",
    "CHAQIMCHI_DEVICE_TOKEN",
)

SERVICES = ("chaqimchi-sotqin", "chaqimchi-retail")

OK = "OK"
WARN = "OGOHLANTIRISH"
FAIL = "XATO"


@dataclass
class Check:
    name: str
    status: str
    detail: str = ""
    #: Nima qilish kerak. `OK` bo'lganda bo'sh.
    fix: str = ""

    @property
    def failed(self) -> bool:
        return self.status == FAIL

    def payload(self) -> Dict[str, str]:
        return {"name": self.name, "status": self.status, "detail": self.detail, "fix": self.fix}


@dataclass
class Preflight:
    """Tekshiruvlar to'plami.

    Har bir bog'liqlik alohida beriladi — testda soxta qiymat qo'yiladi.
    """

    env_path: Path = Path("/etc/chaqimchi/sotqin.env")
    model_dir: Path = Path("/opt/chaqimchi/current/models/retail")
    manifest_path: Path = Path("/opt/chaqimchi/current/models/retail_manifest.json")
    data_dir: Path = Path("/opt/chaqimchi/shared/data")
    config_cache: Path = Path("/opt/chaqimchi/shared/data/sotqin-config.json")
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run
    which: Callable[[str], Optional[str]] = shutil.which
    disk_usage: Callable[[Any], Any] = shutil.disk_usage
    checks: List[Check] = field(default_factory=list)

    # ── Yordamchilar ─────────────────────────────────────────────────────

    def _run(self, command: Sequence[str], *, timeout: int = 15) -> Optional[str]:
        """Buyruqni ishga tushiradi; muvaffaqiyatsiz bo'lsa `None`."""
        try:
            completed = self.runner(
                list(command), capture_output=True, text=True, timeout=timeout, check=False
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if completed.returncode != 0:
            return None
        return completed.stdout or ""

    def add(self, name: str, status: str, detail: str = "", fix: str = "") -> Check:
        check = Check(name=name, status=status, detail=detail, fix=fix)
        self.checks.append(check)
        return check

    # ── Tekshiruvlar ─────────────────────────────────────────────────────

    def check_binaries(self) -> None:
        missing = [name for name in ("ffmpeg", "ffprobe") if not self.which(name)]
        if missing:
            self.add(
                "ffmpeg",
                FAIL,
                f"topilmadi: {', '.join(missing)}",
                "sudo apt-get install -y ffmpeg",
            )
        else:
            self.add("ffmpeg", OK, "ffmpeg va ffprobe topildi")

    def check_igpu(self) -> None:
        """Eng muhim tekshiruv.

        iGPU ko'rinmasa OpenVINO jimgina CPU'ga tushadi: tizim ishlayotgandek
        ko'rinadi, lekin 4-8 barobar sekin bo'ladi va 4 kamera sig'maydi.
        """
        output = self._run(["clinfo", "-l"])
        if output is None or "intel" not in output.lower():
            self.add(
                "iGPU (OpenCL)",
                FAIL,
                "Intel grafikasi ko'rinmadi — inferens CPU'da ketadi (~4-8 barobar sekin)",
                "sudo apt-get install -y intel-opencl-icd && "
                "sudo usermod -aG render,video chaqimchi && sudo reboot",
            )
        else:
            self.add("iGPU (OpenCL)", OK, "Intel grafikasi topildi")

    def check_vaapi(self) -> None:
        output = self._run(["vainfo", "--display", "drm"])
        if output is None:
            self.add(
                "VAAPI (video dekod)",
                WARN,
                "apparatli dekod tekshirilmadi — dekod CPU'da ketadi",
                "sudo apt-get install -y intel-media-va-driver-non-free vainfo",
            )
        elif "H264" not in output.upper():
            self.add(
                "VAAPI (video dekod)",
                WARN,
                "H.264 dekod profili topilmadi",
                "Drayver versiyasini tekshiring: vainfo --display drm",
            )
        else:
            self.add("VAAPI (video dekod)", OK, "H.264 apparatli dekod mavjud")

    def check_env(self) -> None:
        if not self.env_path.is_file():
            self.add(
                "Sozlama fayli",
                FAIL,
                f"{self.env_path} topilmadi",
                "O'rnatuvchini qayta ishga tushiring: install_sotqin.sh",
            )
            return
        mode = self.env_path.stat().st_mode & 0o777
        if mode != 0o600:
            self.add(
                "Sozlama fayli huquqi",
                FAIL,
                f"rejim {oct(mode)} — parollar boshqalarga ko'rinadi",
                f"sudo chmod 0600 {self.env_path}",
            )
        else:
            self.add("Sozlama fayli huquqi", OK, "0600")

        values = self._read_env()
        missing = [key for key in REQUIRED_ENV if not values.get(key)]
        placeholders = [
            key
            for key, value in values.items()
            if key in REQUIRED_ENV and any(mark in value for mark in PLACEHOLDERS)
        ]
        if missing or placeholders:
            problem = []
            if missing:
                problem.append(f"to'ldirilmagan: {', '.join(missing)}")
            if placeholders:
                problem.append(f"namuna qiymat qolgan: {', '.join(placeholders)}")
            self.add(
                "Pairing",
                FAIL,
                "; ".join(problem),
                "Panel bergan kod bilan: pair_sotqin.py --cloud <manzil> --code <kod>",
            )
        else:
            self.add("Pairing", OK, f"obyekt {values['CHAQIMCHI_SITE_ID']}")

    def _read_env(self) -> Dict[str, str]:
        values: Dict[str, str] = {}
        try:
            lines = self.env_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return values
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
        return values

    def check_model(self) -> None:
        try:
            manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.add(
                "AI modeli",
                FAIL,
                "manifest o'qilmadi",
                "python scripts/fetch_retail_model.py",
            )
            return
        names = list(manifest.get("files") or {})
        missing = [name for name in names if not (self.model_dir / name).is_file()]
        if missing or not names:
            reason = f"fayl yetishmaydi: {', '.join(missing)}" if missing else "manifest bo'sh"
            self.add(
                "AI modeli",
                FAIL,
                reason,
                "python scripts/fetch_retail_model.py",
            )
        else:
            self.add("AI modeli", OK, f"{len(names)} fayl joyida")

    def check_disk(self) -> None:
        try:
            usage = self.disk_usage(self.data_dir)
        except OSError:
            self.add("Disk", FAIL, f"{self.data_dir} o'qilmadi", "Diskni tekshiring")
            return
        free_gb = usage.free / 1024**3
        if usage.free < MIN_FREE_BYTES:
            self.add(
                "Disk",
                FAIL,
                f"bo'sh joy {free_gb:.1f} GB — klip yozilmaydi",
                "Eski kliplarni tozalang yoki buffer_max_bytes ni kamaytiring",
            )
        else:
            self.add("Disk", OK, f"bo'sh joy {free_gb:.1f} GB")

    def check_services(self) -> None:
        for service in SERVICES:
            output = self._run(["systemctl", "is-active", service])
            if output is None or output.strip() != "active":
                self.add(
                    f"Xizmat {service}",
                    FAIL,
                    "ishlamayapti",
                    f"sudo systemctl restart {service} && journalctl -u {service} -n 50 --no-pager",
                )
            else:
                self.add(f"Xizmat {service}", OK, "ishlayapti")

    def check_geometry(self) -> None:
        """Chiziq va zona chizilganmi.

        Chizilmagan bo'lsa qurilma ishlab turadi, lekin kirganlar sanalmaydi
        va navbat o'lchanmaydi — do'kon egasi to'lovni boshlab, panelda
        "Bugun kirdi: 0" ni ko'radi.
        """
        try:
            payload = json.loads(self.config_cache.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.add(
                "Chiziq va zona",
                WARN,
                "cloud sozlamasi hali olinmagan",
                "Bir daqiqa kuting va qayta tekshiring",
            )
            return
        config = payload.get("config") or {}
        lines = config.get("lines") or []
        zones = config.get("zones") or []
        if not lines and not zones:
            self.add(
                "Chiziq va zona",
                FAIL,
                "chizilmagan — kirganlar soni, navbat va uzoq turish hisoblanmaydi",
                "O'rnatuvchi panelida kadr ustida chiziq va zonani chizing",
            )
        elif not lines:
            self.add(
                "Chiziq va zona",
                WARN,
                f"{len(zones)} zona bor, lekin hisoblash chizig'i yo'q — kirganlar sanalmaydi",
                "Kirish kamerasida kamida bitta chiziq chizing",
            )
        else:
            self.add("Chiziq va zona", OK, f"{len(lines)} chiziq, {len(zones)} zona")

    def check_cameras(self) -> None:
        try:
            payload = json.loads(self.config_cache.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.add(
                "Kameralar",
                WARN,
                "cloud sozlamasi hali olinmagan",
                "Bir daqiqa kuting va qayta tekshiring",
            )
            return
        cameras = [c for c in (payload.get("cameras") or []) if c.get("enabled", True)]
        if not cameras:
            self.add(
                "Kameralar",
                FAIL,
                "kamera kiritilmagan",
                "Panelda RTSP substream manzillarini kiriting",
            )
            return
        # ffprobe bilan har birini tekshiramiz — bu yerda RTSP manzili
        # chiqishga tushmasligi uchun faqat kamera ID yoziladi.
        from chaqimchi_ai.sotqin_media import SotqinMediaRuntime

        media = SotqinMediaRuntime(runner=self.runner)
        media.apply_config(payload)
        offline = [probe["camera_id"] for probe in media.probe_all() if probe["status"] != "online"]
        if offline:
            self.add(
                "Kameralar",
                FAIL,
                f"javob bermadi: {', '.join(offline)}",
                "RTSP manzili, login/parol va kabelni tekshiring",
            )
        else:
            self.add("Kameralar", OK, f"{len(cameras)} kamera javob berdi")

    # ── Ishga tushirish ──────────────────────────────────────────────────

    def run(self) -> List[Check]:
        self.checks = []
        self.check_binaries()
        self.check_igpu()
        self.check_vaapi()
        self.check_env()
        self.check_model()
        self.check_disk()
        self.check_services()
        self.check_cameras()
        self.check_geometry()
        return self.checks

    def payload(self) -> Dict[str, Any]:
        checks = self.checks or self.run()
        failed = [check for check in checks if check.failed]
        return {
            "ready": not failed,
            "failed": len(failed),
            "checks": [check.payload() for check in checks],
        }


def render(checks: Sequence[Check]) -> str:
    marks = {OK: "✓", WARN: "!", FAIL: "✗"}
    lines = []
    for check in checks:
        lines.append(f"{marks.get(check.status, '?')} {check.name}: {check.detail}")
        if check.fix:
            lines.append(f"    → {check.fix}")
    failed = sum(1 for check in checks if check.failed)
    lines.append("")
    lines.append(
        "Hammasi joyida — obyektni topshirish mumkin."
        if not failed
        else f"{failed} ta muammo bor. Yuqoridagi → belgili qatorlarni bajaring."
    )
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Natijani JSON ko'rinishida chiqarish")
    parser.add_argument(
        "--env",
        type=Path,
        default=Path(os.environ.get("CHAQIMCHI_ENV_FILE", "/etc/chaqimchi/sotqin.env")),
    )
    args = parser.parse_args(argv)

    preflight = Preflight(env_path=args.env)
    checks = preflight.run()
    if args.json:
        print(json.dumps(preflight.payload(), ensure_ascii=False, indent=2))
    else:
        print(render(checks))
    return 1 if any(check.failed for check in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
