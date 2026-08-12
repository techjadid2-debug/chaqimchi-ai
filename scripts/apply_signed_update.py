#!/usr/bin/env python3
"""Imzolangan Sotqin paketini atomik o'rnatadi va xatoda rollback qiladi."""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path

from chaqimchi_ai.signed_update import UpdateVerificationError, verify_release_manifest


def _normalized_arch(value: str) -> str:
    aliases = {"arm64": "aarch64", "amd64": "x86_64"}
    key = value.strip().lower()
    return aliases.get(key, key)


def validate_release_target(manifest: dict, machine: str | None = None) -> None:
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


def _health(timeout: int = 90) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:8742/health", timeout=3) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(2)
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--public-key", type=Path, default=Path("/etc/chaqimchi/update-public.pem"))
    parser.add_argument("--root", type=Path, default=Path("/opt/chaqimchi"))
    args = parser.parse_args()

    try:
        manifest = verify_release_manifest(args.archive, args.manifest, args.public_key)
        validate_release_target(manifest)
    except UpdateVerificationError as exc:
        parser.error(str(exc))
    root = args.root.resolve()
    if str(root) in {"/", str(Path.home())}:
        parser.error("Xavfsiz install root talab qilinadi")
    releases = root / "releases"
    releases.mkdir(parents=True, exist_ok=True)
    destination = releases / manifest["version"]
    if destination.exists():
        parser.error("Bu versiya allaqachon o'rnatilgan")
    previous = (root / "current").resolve() if (root / "current").exists() else None

    with tempfile.TemporaryDirectory(dir=releases, prefix=".update-") as temp_name:
        stage = Path(temp_name)
        with tarfile.open(args.archive, "r:gz") as package:
            package.extractall(stage, filter="data")
        children = list(stage.iterdir())
        source = children[0] if len(children) == 1 and children[0].is_dir() else stage
        product = manifest.get("product", "chaqimchi-lite")
        if product == "chaqimchi-sotqin":
            required = source / "chaqimchi_ai" / "sotqin_agent.py"
        else:
            required = source / "webapp" / "main.py"
        if not required.is_file():
            parser.error(f"Paketda {required.relative_to(source)} yo'q")
        if source == stage:
            destination.mkdir()
            for child in children:
                shutil.move(str(child), destination / child.name)
        else:
            shutil.move(str(source), destination)

    shared_data = root / "shared" / "data"
    shared_models = root / "shared" / "models"
    shared_data.mkdir(parents=True, exist_ok=True)
    shared_models.mkdir(parents=True, exist_ok=True)
    for name, target in (("data", shared_data), ("models", shared_models)):
        link = destination / name
        if link.exists() and not link.is_symlink():
            shutil.move(str(link), str(destination / f"{name}.release"))
        link.symlink_to(target, target_is_directory=True)

    current_tmp = root / ".current-next"
    current_tmp.unlink(missing_ok=True)
    current_tmp.symlink_to(destination, target_is_directory=True)
    os.replace(current_tmp, root / "current")
    subprocess.run(["systemctl", "restart", "chaqimchi-sotqin"], check=True)
    if _health():
        print(f"Update muvaffaqiyatli: {manifest['version']}")
        return 0

    if previous is not None:
        rollback_tmp = root / ".current-rollback"
        rollback_tmp.unlink(missing_ok=True)
        rollback_tmp.symlink_to(previous, target_is_directory=True)
        os.replace(rollback_tmp, root / "current")
        subprocess.run(["systemctl", "restart", "chaqimchi-sotqin"], check=False)
    print("Health-check o'tmadi, oldingi versiyaga qaytildi")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
