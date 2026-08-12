#!/usr/bin/env python3
"""Sotqin'ni pairing kodi bilan Chaqimchi Cloud'ga ulaydi.

Fayl nomi eski installerlar uchun saqlangan; yangi buyruq `pair_sotqin.py`.
"""

from __future__ import annotations

import argparse
import os
import platform
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx

MANAGED_KEYS = (
    "CHAQIMCHI_CONFIG",
    "CHAQIMCHI_CLOUD_URL",
    "CHAQIMCHI_SITE_ID",
    "CHAQIMCHI_DEVICE_ID",
    "CHAQIMCHI_DEVICE_TOKEN",
    "CHAQIMCHI_SOTQIN_MODEL",
    "CHAQIMCHI_SOTQIN_REVISION",
    "CHAQIMCHI_SOTQIN_SERIAL",
)


def hardware_id() -> str:
    machine_id = Path("/etc/machine-id")
    if machine_id.is_file():
        value = machine_id.read_text(encoding="utf-8").strip()
        if value:
            return value
    return platform.node() or "sotqin"


def hardware_model() -> str:
    configured = os.environ.get("CHAQIMCHI_SOTQIN_MODEL", "").strip()
    if configured:
        return configured
    cpuinfo = Path("/proc/cpuinfo")
    try:
        for line in cpuinfo.read_text(encoding="utf-8").splitlines():
            if line.lower().startswith("model name"):
                return line.split(":", 1)[1].strip()[:120]
    except OSError:
        pass
    return platform.processor() or "Intel N100"


def serial_number() -> str:
    configured = os.environ.get("CHAQIMCHI_SOTQIN_SERIAL", "").strip()
    if configured:
        return configured
    for path in (
        Path("/sys/class/dmi/id/product_serial"),
        Path("/sys/class/dmi/id/board_serial"),
        Path("/etc/machine-id"),
    ):
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if value and value.lower() not in {"none", "unknown", "default string"}:
            return value[:120]
    return hardware_id()[:120]


def validate_cloud_url(value: str, *, allow_http: bool = False) -> str:
    url = value.strip().rstrip("/")
    parsed = urlparse(url)
    local = parsed.hostname in {"127.0.0.1", "localhost"}
    if parsed.scheme != "https" and not (allow_http or local):
        raise ValueError("Production cloud URL HTTPS bo'lishi shart")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Cloud URL noto'g'ri")
    return url


def render_env(existing: str, updates: dict[str, str]) -> str:
    """Boshqa secret va kamera sozlamalarini saqlab, pairing maydonlarini yangilaydi."""
    remaining = dict(updates)
    rendered: list[str] = []
    for line in existing.splitlines():
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else ""
        if key in remaining:
            rendered.append(f"{key}={remaining.pop(key)}")
        else:
            rendered.append(line)
    if rendered and rendered[-1]:
        rendered.append("")
    rendered.extend(f"{key}={remaining[key]}" for key in MANAGED_KEYS if key in remaining)
    return "\n".join(rendered).rstrip() + "\n"


def atomic_write_env(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Chaqimchi Sotqin pairing")
    parser.add_argument("--cloud", required=True, help="https://cloud.example.uz")
    parser.add_argument("--code", required=True, help="Admin paneldagi 6 xonali pairing kod")
    parser.add_argument("--label", default=platform.node() or "sotqin-1")
    parser.add_argument("--model", default=hardware_model())
    parser.add_argument("--revision", default="R1")
    parser.add_argument("--serial", default=serial_number())
    parser.add_argument("--env-file", type=Path, default=Path("/etc/chaqimchi/sotqin.env"))
    parser.add_argument("--allow-http", action="store_true", help="Faqat lokal test uchun")
    args = parser.parse_args()

    try:
        cloud = validate_cloud_url(args.cloud, allow_http=args.allow_http)
    except ValueError as exc:
        parser.error(str(exc))
    code = args.code.strip().upper()
    if len(code) != 6 or any(char not in "0123456789ABCDEF" for char in code):
        parser.error("Pairing kod 6 xonali hexadecimal bo'lishi kerak")

    parent = args.env_file.parent
    if parent.exists() and not os.access(parent, os.W_OK):
        parser.error(f"{parent} ga yozish huquqi yo'q; sudo bilan bajaring")
    if args.env_file.exists() and not os.access(args.env_file, os.W_OK):
        parser.error(f"{args.env_file} ni yangilash huquqi yo'q; sudo bilan bajaring")

    try:
        response = httpx.post(
            f"{cloud}/api/v1/sotqin/claim",
            json={
                "pairing_code": code,
                "label": args.label,
                "hardware_id": hardware_id(),
                "product_name": "Sotqin",
                "hardware_model": args.model,
                "hardware_revision": args.revision,
                "serial_number": args.serial,
            },
            timeout=20,
        )
        response.raise_for_status()
        device = response.json()
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get("detail", "Pairing rad etildi")
        except Exception:
            detail = "Pairing rad etildi"
        parser.error(str(detail))
    except (httpx.HTTPError, ValueError) as exc:
        parser.error(f"Cloud bilan ulanish xatosi: {exc}")

    existing = args.env_file.read_text(encoding="utf-8") if args.env_file.is_file() else ""
    content = render_env(
        existing,
        {
            "CHAQIMCHI_CONFIG": "/opt/chaqimchi/current/config/sotqin.yaml",
            "CHAQIMCHI_CLOUD_URL": cloud,
            "CHAQIMCHI_SITE_ID": str(device["site_id"]),
            "CHAQIMCHI_DEVICE_ID": str(device["device_id"]),
            "CHAQIMCHI_DEVICE_TOKEN": str(device["device_token"]),
            "CHAQIMCHI_SOTQIN_MODEL": args.model,
            "CHAQIMCHI_SOTQIN_REVISION": args.revision,
            "CHAQIMCHI_SOTQIN_SERIAL": args.serial,
        },
    )
    atomic_write_env(args.env_file, content)
    print(f"Sotqin ulandi: site={device['site_id']} device={device['device_id']}")
    print("Keyingi qadam: sudo systemctl restart chaqimchi-sotqin")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
