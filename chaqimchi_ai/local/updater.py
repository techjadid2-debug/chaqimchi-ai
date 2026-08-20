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
import json
import logging
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
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

#: Yangilashdan keyin dastur ishga tushishga urinib (`phase="starting"`),
#: shuncha vaqt ichida `running` ga yetmasa — reliz buzuq deb topiladi va
#: oldingi versiya qaytariladi.  Hech kim dasturni ishga tushirmagan
#: bo'lsa (kompyuterga kirilmagan tun) hukm chiqarilmaydi — kutamiz.
ROLLBACK_GRACE_SEC = 30 * 60


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


def _version_key(version: str) -> tuple:
    """ "0.10.0 > 0.9.0" to'g'ri chiqishi uchun sonli taqqoslash."""
    parts = []
    for piece in str(version).split("."):
        try:
            parts.append(int(piece))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def _keep_dir() -> Path:
    path = paths.data_dir() / "update"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _state_path() -> Path:
    return _keep_dir() / "update-state.json"


def _read_state() -> Optional[Dict[str, Any]]:
    try:
        return json.loads(_state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_state(state: Dict[str, Any]) -> None:
    _state_path().write_text(json.dumps(state, indent=2), encoding="utf-8")


def _clear_state() -> None:
    _state_path().unlink(missing_ok=True)


def _read_alive() -> Optional[Dict[str, Any]]:
    try:
        return json.loads(paths.alive_marker_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_at(value: Any) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


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
    offered = str(payload.get("version"))
    if offered == __version__:
        logger.info("Allaqachon eng yangi versiya: %s", __version__)
        return None

    # Rollback'dan keyin buzuq deb topilgan versiya qayta taklif qilinsa
    # olinmaydi — aks holda "o'rnat → qulash → qaytar" abadiy aylanardi.
    # Yangiroq reliz chiqishi bilan blok o'z-o'zidan ahamiyatsiz qoladi.
    state = _read_state() or {}
    if state.get("blocked_version") and offered == str(state["blocked_version"]):
        logger.warning("Versiya %s buzuq deb belgilangan — o'tkazib yuborildi", offered)
        return None

    # Pastga tushish faqat admin ataylab `pin` qilganda mumkin.  Aks holda
    # serverga yozish huquqini olgan hujumchi eski (zaif) relizni qaytarib
    # o'rnatishi mumkin edi — imzolar muddati tugamaydi.
    policy = (payload.get("policy") or {}).get("channel", "")
    if policy != "pin" and _version_key(offered) <= _version_key(__version__):
        logger.warning("Eski versiya taklif qilindi (%s <= %s) — rad etildi", offered, __version__)
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
        raise UpdateError(f"Manifest versiyasi mos emas: {verified.get('version')} != {version}")

    logger.info("Paket tekshirildi: %s (%s)", installer.name, verified.get("sha256", "")[:16])
    return installer


def _ensure_rollback_target(
    releases_base: str, headers: Dict[str, str], exe: Path, manifest: Path
) -> bool:
    """Joriy versiyaning o'rnatuvchisini rollback nishoni sifatida oladi.

    Nishon "oldingi yangilanish qoldirgan fayl" edi.  Birinchi o'rnatish
    esa qo'lda yuklanadi va hech narsa qoldirmaydi — ya'ni **birinchi**
    masofaviy yangilanishda har do'konda rollback yo'q edi va buzuq
    reliz chiqsa usta do'konga borishi kerak bo'lardi.  Aynan eng
    kerakli payt.

    Yuklab bo'lmasa (eski versiya reliz serveridan olib tashlangan
    bo'lishi mumkin) yangilanish TO'XTAMAYDI: xavfsizlik tuzatishi yetib
    borishi rollback imkoniyatidan muhimroq.  Faqat jurnalga yoziladi.
    """
    if exe.is_file() and manifest.is_file():
        return True
    try:
        _download(f"{releases_base}/{exe.name}", exe, headers)
        _download(f"{releases_base}/{manifest.name}", manifest, headers)
    except (httpx.HTTPError, OSError) as exc:
        exe.unlink(missing_ok=True)
        manifest.unlink(missing_ok=True)
        logger.warning(
            "Rollback nishoni olinmadi (%s) — yangilanish davom etadi, "
            "lekin buzuq reliz chiqsa qo'lda qayta o'rnatish kerak bo'ladi",
            exc,
        )
        return False
    key = public_key_path()
    try:
        verify_release_manifest(exe, manifest, key)
    except (UpdateVerificationError, OSError) as exc:
        # Tekshiruvdan o'tmagan fayl nishon bo'lib qolsa, rollback paytida
        # imzosiz `.exe` ishga tushirilardi.
        exe.unlink(missing_ok=True)
        manifest.unlink(missing_ok=True)
        logger.warning("Rollback nishoni tekshiruvdan o'tmadi — saqlanmadi: %s", exc)
        return False
    logger.info("Rollback nishoni tayyor: %s", exe.name)
    return True


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


def _rollback(state: Dict[str, Any]) -> None:
    """Buzuq relizdan oldingi versiyaga qaytadi.

    Qoida o'zgarmaydi: tekshirilmagan fayl ishga tushirilmaydi.  Oldingi
    o'rnatuvchi ham qayta imzo tekshiruvidan o'tadi (manifesti u bilan
    birga saqlangan).  Tekshiruv o'tmasa yoki fayl yo'q bo'lsa rollback
    bo'lmaydi — lekin buzuq versiya "blocked" bo'lib qoladi va qayta
    o'rnatilmaydi.
    """
    broken = str(state.get("to_version", ""))
    prev_exe = Path(str(state.get("previous_installer") or ""))
    prev_manifest = Path(str(state.get("previous_manifest") or ""))
    _write_state(
        {
            "blocked_version": broken,
            "rolled_back_at": _now().isoformat(),
            "rolled_back_to": state.get("from_version", ""),
        }
    )
    if not prev_exe.is_file() or not prev_manifest.is_file():
        logger.error(
            "Versiya %s ishga tushmadi, lekin oldingi o'rnatuvchi saqlanmagan — "
            "qo'lda qayta o'rnatish kerak",
            broken,
        )
        return
    key = public_key_path()
    try:
        verify_release_manifest(prev_exe, prev_manifest, key)
    except (UpdateVerificationError, OSError) as exc:
        logger.error("Oldingi o'rnatuvchi tekshiruvdan o'tmadi — rollback yo'q: %s", exc)
        return
    logger.warning(
        "Versiya %s ishga tusha olmadi — %s ga qaytarilmoqda",
        broken,
        state.get("from_version"),
    )
    install(prev_exe)


def _resolve_pending(state: Dict[str, Any]) -> Optional[str]:
    """Oldingi yangilanish taqdirini hal qiladi.

    Qaytaradi: `"wait"` — hukm chiqarish erta (yangi tekshiruv boshlanmaydi);
    `None` — holat yopildi, davom etsa bo'ladi.
    """
    if "blocked_version" in state:
        return None  # blok `check()` da hisobga olinadi, bu yerda ish yo'q
    to_version = str(state.get("to_version", ""))
    from_version = str(state.get("from_version", ""))
    started_at = _parse_at(state.get("started_at")) or _now()

    if __version__ == from_version and __version__ != to_version:
        # Setup umuman ishlamagan (masalan tok o'chgan) — hech narsa
        # o'zgarmagan, keyingi tekshiruv odatdagidek davom etadi.
        logger.info("Oldingi yangilanish (%s) amalga oshmagan — qayta uriniladi", to_version)
        _clear_state()
        return None

    if __version__ != to_version:
        # Uchinchi versiya (qo'lda qayta o'rnatilgan) — holat eskirgan.
        _clear_state()
        return None

    # Biz yangi versiyamiz.  Panel ishga tushdimi?
    alive = _read_alive()
    alive_at = _parse_at(alive.get("at")) if alive else None
    if alive and alive_at and alive_at > started_at:
        if str(alive.get("version")) == to_version and alive.get("phase") == "running":
            logger.info("Yangilanish muvaffaqiyatli: %s ishlab turibdi", to_version)
            _clear_state()
            return None
        if (
            str(alive.get("version")) == to_version
            and alive.get("phase") == "starting"
            and (_now() - started_at).total_seconds() > ROLLBACK_GRACE_SEC
        ):
            # Dastur qayta-qayta ishga tushishga urinyapti, lekin
            # `running` ga hech yetmayapti — reliz buzuq.
            _rollback(state)
            return "wait"
    # Hali hech kim dasturni ishga tushirmagan (tunda yangilangan) yoki
    # eski jarayon hali yopilmagan — hukm chiqarish erta.
    return "wait"


def run_once(*, dry_run: bool = False) -> int:
    """Bir marta tekshiradi va kerak bo'lsa yangilaydi."""
    state = _read_state()
    if state and _resolve_pending(state) == "wait":
        return 0

    try:
        update = check()
    except UpdateError as exc:
        logger.info("%s", exc)
        return 0  # Aloqa yo'qligi xato emas — keyingi safar urinamiz.

    if update is None:
        return 0

    version = str(update["version"])
    logger.info("Yangi versiya: %s (joriy: %s)", version, __version__)
    with tempfile.TemporaryDirectory(prefix="chaqimchi-update-") as tmp:
        try:
            installer = download_and_verify(update, Path(tmp))
        except UpdateError as exc:
            logger.error("Yangilash bajarilmadi: %s", exc)
            return 1
        if dry_run:
            logger.info("dry-run: o'rnatilmadi, paket tekshiruvdan o'tdi")
            return 0
        # O'rnatuvchi (va rollback uchun manifesti) vaqtinchalik papkadan
        # ko'chiriladi: papka biz chiqishimiz bilan o'chadi, o'rnatuvchi
        # esa hali ishlayotgan bo'ladi.
        keep = _keep_dir()
        final = keep / installer.name
        final.write_bytes(installer.read_bytes())
        manifest_src = installer.with_suffix(".json")
        if manifest_src.is_file():
            (keep / manifest_src.name).write_bytes(manifest_src.read_bytes())

        # Joriy versiyaning o'rnatuvchisi (oldingi yangilanishdan qolgan)
        # rollback nishoni bo'ladi.  Qolgan eski fayllar o'chiriladi —
        # disk yangilanish arxiviga aylanib ketmasin.
        prev_exe = keep / f"chaqimchi-windows-{__version__}.exe"
        prev_manifest = keep / f"chaqimchi-windows-{__version__}.json"
        # Birinchi masofaviy yangilanishda nishon bo'lmaydi — uni reliz
        # serveridan olib qo'yamiz, aks holda buzuq reliz chiqsa do'kon
        # qo'lda tiklanishni kutib qolardi.
        raw = _cloud()
        _ensure_rollback_target(
            str(update["download_url"]).rsplit("/", 1)[0],
            {
                "X-Site-Id": str(raw["site_id"]),
                "X-Device-Id": str(raw["device_id"]),
                "X-Device-Token": str(raw["device_token"]),
            },
            prev_exe,
            prev_manifest,
        )
        wanted = {final, keep / manifest_src.name, prev_exe, prev_manifest}
        for stale in keep.glob("chaqimchi-windows-*"):
            if stale not in wanted:
                stale.unlink(missing_ok=True)

        _write_state(
            {
                "from_version": __version__,
                "to_version": version,
                "started_at": _now().isoformat(),
                "previous_installer": str(prev_exe) if prev_exe.is_file() else "",
                "previous_manifest": str(prev_manifest) if prev_manifest.is_file() else "",
            }
        )
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

    from logging.handlers import RotatingFileHandler

    # Har 15 daqiqada ishga tushadigan vazifa — rotatsiyasiz bu log yillar
    # davomida jimgina o'sib borardi.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            RotatingFileHandler(
                paths.logs_dir() / "update.log",
                maxBytes=2 * 1024 * 1024,
                backupCount=2,
                encoding="utf-8",
            ),
        ],
    )
    return run_once(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
