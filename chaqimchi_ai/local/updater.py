"""Windows dasturini masofadan yangilash.

Bu modul mijoz kompyuterida **administrator huquqi** bilan bajariladi
(o'rnatuvchi qoldirgan rejalashtirilgan vazifa orqali).  Shuning uchun
bitta qat'iy qoida bor:

    Tekshirilmagan fayl hech qachon ishga tushirilmaydi.

Cloud buzilgan yoki DNS o'g'irlangan taqdirda ham hujumchi imzo yasay
olmaydi: manifest Ed25519 bilan imzolangan va ochiq kalit dastur bilan
birga o'rnatilgan (`deploy/update-public.pem`).  Tekshiruvning o'zi
`chaqimchi_ai/signed_update.py` da — Linux relizi bilan **bitta** kod.

Yangilash jarayoni:

    cloud'dan so'raydi → yangimi? → .exe va manifestni yuklaydi
      → sha256 + Ed25519 tekshiruvi → Setup.exe /S (jimgina o'rnatish)

Jimgina o'rnatish sozlamalarga tegmaydi: NSIS skripti `IfSilent` bilan
`%PROGRAMDATA%\\Chaqimchi` ni saqlab qoladi.  Ya'ni kamera sozlamalari,
chiziqlar va hisobot yangilashdan keyin joyida qoladi.

Ishga tushirish (odatda rejalashtirilgan vazifa chaqiradi):

    python -m chaqimchi_ai.local.updater
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from chaqimchi_ai import __version__
from chaqimchi_ai.local import config_store, paths
from chaqimchi_ai.signed_update import UpdateVerificationError, verify_release_manifest

logger = logging.getLogger(__name__)

#: Yuklab olish 70 MB atrofida — sekin internetda ham ulgursin.
DOWNLOAD_TIMEOUT_SEC = 900

#: Cloud so'rovi: tez javob bermasa keyingi safar urinamiz.
QUERY_TIMEOUT_SEC = 30


class UpdateError(Exception):
    """Yangilash bajarilmadi.  Dastur eski versiyada ishlashda davom etadi."""


def public_key_path() -> Path:
    """Imzo tekshiriladigan ochiq kalit.

    O'rnatuvchi uni dastur papkasiga qo'yadi.  Fayl yo'q bo'lsa
    yangilanish **umuman bajarilmaydi** — imzosiz o'rnatishdan ko'ra
    eski versiyada qolgan yaxshiroq.
    """
    override = os.environ.get("CHAQIMCHI_UPDATE_PUBLIC_KEY", "").strip()
    if override:
        return Path(override)
    return paths.app_root() / "deploy" / "update-public.pem"


def _cloud() -> Dict[str, Any]:
    raw = config_store.read_raw().get("cloud_sync") or {}
    if not raw.get("enabled") or not raw.get("device_token"):
        raise UpdateError("Cloudga ulanmagan — yangilanish tekshirilmaydi")
    return raw


def check(cloud: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Cloudda yangi versiya bormi.  Yo'q bo'lsa `None`."""
    raw = cloud or _cloud()
    headers = {
        "X-Site-Id": str(raw["site_id"]),
        "X-Device-Id": str(raw["device_id"]),
        "X-Device-Token": str(raw["device_token"]),
    }
    try:
        response = httpx.get(
            f"{str(raw['url']).rstrip('/')}/api/v1/edge/update",
            headers=headers,
            timeout=QUERY_TIMEOUT_SEC,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise UpdateError(f"Cloud bilan aloqa yo'q: {exc}") from exc

    if not payload.get("available"):
        logger.info("Yangilanish yo'q: %s", payload.get("reason", "eng yangi versiya"))
        return None
    if str(payload.get("version")) == __version__:
        logger.info("Allaqachon eng yangi versiya: %s", __version__)
        return None
    return payload


def _download(url: str, dest: Path, headers: Dict[str, str]) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    with httpx.stream(
        "GET", url, headers=headers, timeout=DOWNLOAD_TIMEOUT_SEC, follow_redirects=True
    ) as response:
        response.raise_for_status()
        with tmp.open("wb") as handle:
            for chunk in response.iter_bytes(1 << 20):
                handle.write(chunk)
    tmp.replace(dest)


def download_and_verify(update: Dict[str, Any], workdir: Path) -> Path:
    """Paketni yuklab oladi va imzosini tekshiradi.

    Tekshiruvdan o'tmasa fayl **o'chiriladi** — diskda ishga tushirilishi
    mumkin bo'lgan tekshirilmagan `.exe` qolib ketmasin.
    """
    raw = _cloud()
    headers = {
        "X-Site-Id": str(raw["site_id"]),
        "X-Device-Id": str(raw["device_id"]),
        "X-Device-Token": str(raw["device_token"]),
    }
    version = str(update["version"])
    installer = workdir / f"chaqimchi-windows-{version}.exe"
    manifest = workdir / f"chaqimchi-windows-{version}.json"

    try:
        _download(str(update["download_url"]), installer, headers)
        _download(str(update["manifest_url"]), manifest, headers)
    except httpx.HTTPError as exc:
        raise UpdateError(f"Yuklab olinmadi: {exc}") from exc

    key = public_key_path()
    if not key.is_file():
        installer.unlink(missing_ok=True)
        raise UpdateError(f"Imzo kaliti topilmadi: {key}")

    try:
        verified = verify_release_manifest(installer, manifest, key)
    except UpdateVerificationError as exc:
        installer.unlink(missing_ok=True)
        manifest.unlink(missing_ok=True)
        logger.error("IMZO TEKSHIRUVI YIQILDI — paket tashlandi: %s", exc)
        raise UpdateError(f"Paket imzosi noto'g'ri: {exc}") from exc

    if str(verified.get("version")) != version:
        installer.unlink(missing_ok=True)
        raise UpdateError(
            f"Manifest versiyasi mos emas: {verified.get('version')} != {version}"
        )

    logger.info("Paket tekshirildi: %s (%s)", installer.name, verified.get("sha256", "")[:16])
    return installer


def install(installer: Path) -> None:
    """O'rnatuvchini jim rejimda ishga tushiradi.

    `/S` — NSIS ning jim rejimi.  O'rnatuvchi eski versiyani o'zi
    o'chiradi va `IfSilent` tufayli sozlamalarga tegmaydi.

    Bu jarayon **o'zini ham to'xtatadi** (dastur qayta o'rnatiladi),
    shuning uchun natijani kutmaymiz — kutsak o'zimizni o'ldirgan
    jarayondan javob kutgan bo'lardik.
    """
    if os.name != "nt":
        raise UpdateError("Yangilash faqat Windows'da bajariladi")
    logger.info("O'rnatilmoqda: %s", installer.name)
    subprocess.Popen(  # noqa: S603 — yo'l bizniki, imzo tekshirilgan
        [str(installer), "/S"],
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
        close_fds=True,
    )


def run_once(*, dry_run: bool = False) -> int:
    """Bir marta tekshiradi va kerak bo'lsa yangilaydi."""
    try:
        update = check()
    except UpdateError as exc:
        logger.info("%s", exc)
        return 0  # Aloqa yo'qligi xato emas — keyingi safar urinamiz.

    if update is None:
        return 0

    logger.info("Yangi versiya: %s (joriy: %s)", update["version"], __version__)
    with tempfile.TemporaryDirectory(prefix="chaqimchi-update-") as tmp:
        try:
            installer = download_and_verify(update, Path(tmp))
        except UpdateError as exc:
            logger.error("Yangilash bajarilmadi: %s", exc)
            return 1
        if dry_run:
            logger.info("dry-run: o'rnatilmadi, paket tekshiruvdan o'tdi")
            return 0
        # O'rnatuvchi vaqtinchalik papkadan ko'chiriladi: papka biz
        # chiqishimiz bilan o'chadi, o'rnatuvchi esa hali ishlayotgan
        # bo'ladi.
        keep = paths.data_dir() / "update"
        keep.mkdir(parents=True, exist_ok=True)
        final = keep / installer.name
        final.write_bytes(installer.read_bytes())
        install(final)
    return 0


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="faqat tekshiradi va yuklab oladi, o'rnatmaydi",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(paths.logs_dir() / "update.log", encoding="utf-8"),
        ],
    )
    return run_once(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
