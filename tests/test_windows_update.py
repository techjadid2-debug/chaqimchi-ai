"""Masofadan yangilash.

Bu kod mijoz kompyuterida **administrator huquqi** bilan ishlaydi va
yuklab olingan `.exe` ni bajaradi.  Ya'ni bitta tekshiruv o'tkazib
yuborilsa, cloudni yoki DNS'ni egallagan hujumchi har bir do'kon
kompyuterini to'liq qo'lga kiritadi.

Shuning uchun bu yerdagi eng muhim test bitta: **imzosi mos kelmagan
paket hech qachon ishga tushirilmasligi kerak.**
"""

from __future__ import annotations

import base64
import importlib
import json
from pathlib import Path
from typing import Any, Dict

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from chaqimchi_ai.signed_update import (
    UpdateVerificationError,
    canonical_manifest_payload,
    sha256_file,
    verify_release_manifest,
)

VERSION = "9.9.9"


@pytest.fixture
def keys(tmp_path: Path) -> Dict[str, Path]:
    private = Ed25519PrivateKey.generate()
    public_pem = tmp_path / "update-public.pem"
    public_pem.write_bytes(
        private.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return {"private": private, "public": public_pem}


def _sign(installer: Path, keys: Dict[str, Any], *, product: str = "chaqimchi-windows") -> Path:
    manifest = {
        "schema_version": 2,
        "product": product,
        "target_arch": "x86_64",
        "version": VERSION,
        "sha256": sha256_file(installer),
    }
    signature = keys["private"].sign(canonical_manifest_payload(manifest))
    manifest["signature"] = base64.b64encode(signature).decode("ascii")
    path = installer.with_name(f"chaqimchi-windows-{VERSION}.json")
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


@pytest.fixture
def installer(tmp_path: Path) -> Path:
    path = tmp_path / f"chaqimchi-windows-{VERSION}.exe"
    path.write_bytes(b"MZ" + b"soxta o'rnatuvchi" * 100)
    return path


# ── Imzo tekshiruvi ──────────────────────────────────────────────────────


def test_a_correctly_signed_package_is_accepted(installer: Path, keys) -> None:
    manifest = _sign(installer, keys)
    verified = verify_release_manifest(installer, manifest, keys["public"])
    assert verified["version"] == VERSION
    assert verified["product"] == "chaqimchi-windows"


def test_a_tampered_installer_is_rejected(installer: Path, keys) -> None:
    """Eng muhim test: paket yo'lda o'zgartirilgan bo'lsa rad etilsin."""
    manifest = _sign(installer, keys)
    installer.write_bytes(installer.read_bytes() + b"ZARARLI KOD")
    with pytest.raises(UpdateVerificationError):
        verify_release_manifest(installer, manifest, keys["public"])


def test_a_manifest_signed_by_a_different_key_is_rejected(
    installer: Path, keys, tmp_path: Path
) -> None:
    """Cloud buzilgan bo'lsa ham hujumchi imzo yasay olmaydi."""
    manifest = _sign(installer, keys)
    other = Ed25519PrivateKey.generate()
    other_pem = tmp_path / "boshqa.pem"
    other_pem.write_bytes(
        other.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    with pytest.raises(UpdateVerificationError):
        verify_release_manifest(installer, manifest, other_pem)


def test_a_package_for_another_product_is_rejected(installer: Path, keys) -> None:
    """Linux Sotqin relizi Windows kompyuteriga o'rnatilib ketmasin."""
    manifest = _sign(installer, keys, product="boshqa-mahsulot")
    with pytest.raises(UpdateVerificationError):
        verify_release_manifest(installer, manifest, keys["public"])


def test_windows_product_is_in_the_allow_list() -> None:
    from chaqimchi_ai.signed_update import KNOWN_PRODUCTS

    assert "chaqimchi-windows" in KNOWN_PRODUCTS
    assert "chaqimchi-sotqin" in KNOWN_PRODUCTS, "Linux relizi buzilmasligi kerak"


# ── Yangilovchi mantiqi ──────────────────────────────────────────────────


@pytest.fixture
def updater(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CHAQIMCHI_LOCAL_DIR", str(tmp_path))
    from chaqimchi_ai.local import config_store, paths
    from chaqimchi_ai.local import updater as updater_module

    for module in (paths, config_store, updater_module):
        importlib.reload(module)
    return updater_module


def test_update_is_skipped_when_not_paired(updater) -> None:
    """Cloudga ulanmagan dastur yangilanish uchun so'ramaydi ham."""
    with pytest.raises(updater.UpdateError):
        updater.check()


def test_same_version_is_not_an_update(updater, monkeypatch: pytest.MonkeyPatch) -> None:
    """Joriy versiya qaytsa yangilash bo'lmasligi kerak — aks holda
    dastur o'zini cheksiz qayta o'rnatardi."""
    from chaqimchi_ai import __version__

    cloud = {
        "enabled": True,
        "url": "https://c.uz",
        "site_id": "s",
        "device_id": "d",
        "device_token": "t",
    }

    class _Response:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> Dict[str, Any]:
            return {"available": True, "version": __version__}

    monkeypatch.setattr("chaqimchi_ai.local.updater.httpx.get", lambda *a, **k: _Response())
    assert updater.check(cloud) is None


def test_no_release_means_no_update(updater, monkeypatch: pytest.MonkeyPatch) -> None:
    cloud = {
        "enabled": True,
        "url": "https://c.uz",
        "site_id": "s",
        "device_id": "d",
        "device_token": "t",
    }

    class _Response:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> Dict[str, Any]:
            return {"available": False, "reason": "reliz yo'q"}

    monkeypatch.setattr("chaqimchi_ai.local.updater.httpx.get", lambda *a, **k: _Response())
    assert updater.check(cloud) is None


def test_missing_public_key_stops_the_update(
    updater, installer: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Kalit yo'q bo'lsa imzoni tekshirib bo'lmaydi — o'rnatishdan ko'ra
    eski versiyada qolgan yaxshiroq."""
    monkeypatch.setenv("CHAQIMCHI_UPDATE_PUBLIC_KEY", str(tmp_path / "yo'q.pem"))
    monkeypatch.setattr(
        "chaqimchi_ai.local.updater._cloud",
        lambda: {
            "enabled": True,
            "url": "https://c.uz",
            "site_id": "s",
            "device_id": "d",
            "device_token": "t",
        },
    )
    monkeypatch.setattr("chaqimchi_ai.local.updater._download", lambda url, dest, headers: None)
    with pytest.raises(updater.UpdateError, match="kalit"):
        updater.download_and_verify(
            {
                "version": VERSION,
                "download_url": "https://c.uz/a.exe",
                "manifest_url": "https://c.uz/a.json",
            },
            tmp_path,
        )


def test_install_refuses_to_run_outside_windows(updater, installer: Path) -> None:
    """macOS/Linux'da `.exe` ni ishga tushirishga urinish ma'nosiz."""
    import os

    if os.name == "nt":  # pragma: no cover
        pytest.skip("Windows'da bu tekshiruv qo'llanmaydi")
    with pytest.raises(updater.UpdateError):
        updater.install(installer)


# ── Pastga tushish himoyasi ──────────────────────────────────────────────


def _cloud_dict() -> Dict[str, Any]:
    return {
        "enabled": True,
        "url": "https://c.uz",
        "site_id": "s",
        "device_id": "d",
        "device_token": "t",
    }


def _fake_response(monkeypatch: pytest.MonkeyPatch, payload: Dict[str, Any]) -> None:
    class _Response:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> Dict[str, Any]:
            return payload

    monkeypatch.setattr("chaqimchi_ai.local.updater.httpx.get", lambda *a, **k: _Response())


def test_downgrade_offer_is_rejected(updater, monkeypatch: pytest.MonkeyPatch) -> None:
    """Serverni egallagan hujumchi eski (zaif) relizni qaytara olmasin.

    Imzolar muddati tugamaydi: bir marta imzolangan eski `.exe` abadiy
    "haqiqiy".  Shuning uchun qurilma o'zi "faqat yangiroq" deb turishi
    shart.
    """
    _fake_response(
        monkeypatch,
        {
            "available": True,
            "version": "0.0.1",
            "policy": {"channel": "auto"},
        },
    )
    assert updater.check(_cloud_dict()) is None


def test_pin_policy_may_go_backwards(updater, monkeypatch: pytest.MonkeyPatch) -> None:
    """`pin` — admin ataylab qotirgan versiya; unga pastga yo'l ochiq."""
    _fake_response(
        monkeypatch,
        {
            "available": True,
            "version": "0.0.1",
            "policy": {"channel": "pin", "version": "0.0.1"},
        },
    )
    offered = updater.check(_cloud_dict())
    assert offered is not None and offered["version"] == "0.0.1"


def test_blocked_version_is_not_reoffered(updater, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rollback qilingan buzuq versiya qayta o'rnatilmasin — aks holda
    "o'rnat → qulash → qaytar" abadiy aylanardi."""
    updater._write_state({"blocked_version": "9.9.9"})
    _fake_response(
        monkeypatch,
        {
            "available": True,
            "version": "9.9.9",
            "policy": {"channel": "auto"},
        },
    )
    assert updater.check(_cloud_dict()) is None


# ── Rollback holat mashinasi ─────────────────────────────────────────────
#
# Linux'dagi `apply_signed_update.py` to'liq health-gate bilan ishlaydi;
# Windows'da esa Setup.exe'dan keyin hech qanday nazorat yo'q edi: buzuq
# reliz do'konni jimgina o'chirib qo'yardi.  Bu testlar yangi qoidani
# qo'riqlaydi: panel `running` demaguncha yangilanish "muvaffaqiyatli"
# hisoblanmaydi.


def _alive(updater, *, phase: str, version: str, at: str) -> None:
    from chaqimchi_ai.local import paths

    paths.alive_marker_path().write_text(
        json.dumps({"version": version, "phase": phase, "at": at}),
        encoding="utf-8",
    )


def test_successful_update_clears_the_state(updater) -> None:
    from chaqimchi_ai import __version__

    updater._write_state(
        {
            "from_version": "0.0.1",
            "to_version": __version__,
            "started_at": "2026-01-01T00:00:00+00:00",
        }
    )
    _alive(updater, phase="running", version=__version__, at="2026-01-01T00:10:00+00:00")

    assert updater._resolve_pending(updater._read_state()) is None
    assert updater._read_state() is None, "holat yopilishi kerak"


def test_no_login_yet_means_no_verdict(updater) -> None:
    """Tunda yangilangan, hech kim kirmagan — bu qulash EMAS."""
    from chaqimchi_ai import __version__

    updater._write_state(
        {
            "from_version": "0.0.1",
            "to_version": __version__,
            "started_at": "2026-01-01T00:00:00+00:00",
        }
    )

    assert updater._resolve_pending(updater._read_state()) == "wait"
    state = updater._read_state()
    assert state and "blocked_version" not in state, "rollback bo'lmasligi kerak"


def test_crash_looping_release_is_rolled_back(
    updater, installer: Path, keys, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dastur ishga tushishga urinib `running` ga yetmasa — reliz buzuq."""
    from datetime import datetime, timezone

    from chaqimchi_ai import __version__

    monkeypatch.setenv("CHAQIMCHI_UPDATE_PUBLIC_KEY", str(keys["public"]))
    manifest = _sign(installer, keys)
    installed = []
    monkeypatch.setattr(updater, "install", lambda path: installed.append(path))

    updater._write_state(
        {
            "from_version": "0.0.1",
            "to_version": __version__,
            "started_at": "2026-01-01T00:00:00+00:00",
            "previous_installer": str(installer),
            "previous_manifest": str(manifest),
        }
    )
    _alive(
        updater,
        phase="starting",
        version=__version__,
        at=datetime.now(timezone.utc).isoformat(),
    )

    assert updater._resolve_pending(updater._read_state()) == "wait"
    assert installed == [installer], "oldingi o'rnatuvchi qayta ishga tushishi kerak"
    state = updater._read_state()
    assert state and state["blocked_version"] == __version__


def test_rollback_never_runs_an_unverified_installer(
    updater, installer: Path, keys, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Qoida rollback'da ham o'zgarmaydi: imzosiz fayl ishga tushmaydi."""
    from datetime import datetime, timezone

    from chaqimchi_ai import __version__

    monkeypatch.setenv("CHAQIMCHI_UPDATE_PUBLIC_KEY", str(keys["public"]))
    manifest = _sign(installer, keys)
    installer.write_bytes(installer.read_bytes() + b"BUZILGAN")
    installed = []
    monkeypatch.setattr(updater, "install", lambda path: installed.append(path))

    updater._write_state(
        {
            "from_version": "0.0.1",
            "to_version": __version__,
            "started_at": "2026-01-01T00:00:00+00:00",
            "previous_installer": str(installer),
            "previous_manifest": str(manifest),
        }
    )
    _alive(
        updater,
        phase="starting",
        version=__version__,
        at=datetime.now(timezone.utc).isoformat(),
    )

    updater._resolve_pending(updater._read_state())
    assert installed == [], "tekshiruvdan o'tmagan fayl ishga tushmasligi kerak"
    state = updater._read_state()
    assert state and state["blocked_version"] == __version__, "versiya baribir bloklanadi"


def test_install_that_never_happened_clears_the_state(updater) -> None:
    """Setup umuman ishlamagan (tok o'chgan) — eski versiya davom etadi."""
    from chaqimchi_ai import __version__

    updater._write_state(
        {
            "from_version": __version__,
            "to_version": "8.8.8",
            "started_at": "2026-01-01T00:00:00+00:00",
        }
    )

    assert updater._resolve_pending(updater._read_state()) is None
    assert updater._read_state() is None


# ── Cloud tomoni ─────────────────────────────────────────────────────────


def test_release_route_accepts_windows_names() -> None:
    from cloud.main import RELEASE_FILE_PATTERN

    assert RELEASE_FILE_PATTERN.match("chaqimchi-windows-0.7.0.exe")
    assert RELEASE_FILE_PATTERN.match("chaqimchi-windows-0.7.0.json")
    assert RELEASE_FILE_PATTERN.match("chaqimchi-sotqin-0.6.0.tar.gz")
    # Yo'l bo'ylab chiqib ketish va begona fayllar rad etilsin.
    assert not RELEASE_FILE_PATTERN.match("../../etc/passwd")
    assert not RELEASE_FILE_PATTERN.match("chaqimchi-windows-0.7.0.bat")
    assert not RELEASE_FILE_PATTERN.match("zararli.exe")


def test_newer_version_wins_even_with_two_digit_minor() -> None:
    """Matn sifatida taqqoslansa `0.10 < 0.9` chiqardi va qurilma yangi
    versiyani eski deb hisoblab hech qachon yangilanmasdi."""
    from cloud.main import _version_key

    assert _version_key("0.10.0") > _version_key("0.9.0")
    assert _version_key("1.0.0") > _version_key("0.99.0")
    assert _version_key("0.7.1") > _version_key("0.7.0")


def test_unsigned_release_is_not_offered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Manifestsiz `.exe` yangilanish sifatida e'lon qilinmasin —
    qurilma uni baribir rad etadi."""
    import cloud.main as cloud_main

    (tmp_path / "chaqimchi-windows-9.9.9.exe").write_bytes(b"MZ")
    monkeypatch.setattr(cloud_main, "_release_dirs", lambda: [tmp_path])
    assert cloud_main.latest_windows_release() is None

    (tmp_path / "chaqimchi-windows-9.9.9.json").write_text("{}", encoding="utf-8")
    release = cloud_main.latest_windows_release()
    assert release is not None and release["version"] == "9.9.9"


# ── Birinchi yangilanishda rollback nishoni ──────────────────────────────


def test_the_first_ota_fetches_a_rollback_target(
    updater, tmp_path: Path, keys, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Birinchi masofaviy yangilanishda har do'konda rollback nishoni
    BO'SH edi.

    Nishon — "oldingi yangilanish qoldirgan fayl".  Birinchi o'rnatish
    esa qo'lda yuklanadi va u yerga hech narsa qoldirmaydi.  Ya'ni
    `docs/DOKON_MVP.md` va'da qilgan avto-rollback aynan eng kerakli
    paytda — birinchi masofaviy yangilanishda — ishlamasdi va usta
    do'konga borishi kerak bo'lardi.

    Endi joriy versiyaning o'rnatuvchisi reliz serveridan olib qo'yiladi.
    """
    monkeypatch.setenv("CHAQIMCHI_UPDATE_PUBLIC_KEY", str(keys["public"]))
    keep = updater._keep_dir()
    assert not list(keep.glob("*.exe")), "boshida nishon yo'q"

    current = tmp_path / f"chaqimchi-windows-{VERSION}.exe"
    current.write_bytes(b"joriy o'rnatuvchi")
    current_manifest = _sign(current, keys)

    def fake_download(url: str, dest: Path, headers) -> None:
        source = current if url.endswith(".exe") else current_manifest
        dest.write_bytes(source.read_bytes())

    monkeypatch.setattr(updater, "_download", fake_download)

    ok = updater._ensure_rollback_target(
        "https://api.example.uz/releases", {}, keep / current.name, keep / current_manifest.name
    )

    assert ok is True
    assert (keep / current.name).is_file()
    assert (keep / current_manifest.name).is_file()


def test_a_rollback_target_that_fails_verification_is_not_kept(
    updater, tmp_path: Path, keys, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tekshiruvdan o'tmagan fayl nishon bo'lib qolsa, rollback paytida
    imzosiz `.exe` ishga tushirilardi — qoida buzilardi."""
    monkeypatch.setenv("CHAQIMCHI_UPDATE_PUBLIC_KEY", str(keys["public"]))
    keep = updater._keep_dir()

    current = tmp_path / f"chaqimchi-windows-{VERSION}.exe"
    current.write_bytes(b"joriy o'rnatuvchi")
    current_manifest = _sign(current, keys)
    current.write_bytes(b"BUZILGAN")  # imzo endi mos kelmaydi

    def fake_download(url: str, dest: Path, headers) -> None:
        source = current if url.endswith(".exe") else current_manifest
        dest.write_bytes(source.read_bytes())

    monkeypatch.setattr(updater, "_download", fake_download)

    ok = updater._ensure_rollback_target(
        "https://api.example.uz/releases", {}, keep / current.name, keep / current_manifest.name
    )

    assert ok is False
    assert not (keep / current.name).is_file(), "yaroqsiz nishon saqlanmasin"


def test_a_missing_rollback_target_does_not_block_the_update(
    updater, keys, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Joriy versiya reliz serverida qolmagan bo'lishi mumkin (eski
    versiya olib tashlangan).  Bu yangilanishni to'xtatmasin — xavfsizlik
    tuzatishi yetib borishi rollback imkoniyatidan muhimroq."""
    import httpx

    monkeypatch.setenv("CHAQIMCHI_UPDATE_PUBLIC_KEY", str(keys["public"]))
    keep = updater._keep_dir()

    def fake_download(url: str, dest: Path, headers) -> None:
        raise httpx.HTTPError("404")

    monkeypatch.setattr(updater, "_download", fake_download)

    ok = updater._ensure_rollback_target(
        "https://api.example.uz/releases",
        {},
        keep / f"chaqimchi-windows-{VERSION}.exe",
        keep / f"chaqimchi-windows-{VERSION}.json",
    )

    assert ok is False


# ── Global to'xtatuvchi (buzuq reliz tarqalib ketmasin) ──────────────────


def test_a_bad_release_can_be_stopped_for_every_shop_at_once(tmp_path: Path) -> None:
    """Relizni nashr qilishning o'zi tarqatish edi.

    Kanareyka ham, bosqichma-bosqich tarqatish ham yo'q: fayl papkaga
    tushgan zahoti har do'kon uni 15 daqiqada oladi.  Buzuq reliz chiqib
    ketsa yagona himoya har do'konni QO'LDA `hold` ga o'tkazish edi —
    ya'ni mijoz soni qancha bo'lsa shuncha so'rov, aynan panika paytida.
    """
    from cloud.store import CloudStore

    store = CloudStore(tmp_path / "cloud.db")

    assert store.updates_paused() is False, "odatda yangilanish ochiq"

    store.set_updates_paused(True)
    assert store.updates_paused() is True

    store.set_updates_paused(False)
    assert store.updates_paused() is False


def test_the_pause_survives_a_restart(tmp_path: Path) -> None:
    """Bayroq bazada — konteyner qayta ishga tushsa ham saqlanadi.
    Env o'zgaruvchisi bo'lganda deploy kerak bo'lardi."""
    from cloud.store import CloudStore

    path = tmp_path / "cloud.db"
    CloudStore(path).set_updates_paused(True)

    assert CloudStore(path).updates_paused() is True


# ── Diskda faqat ikkita paket qoladi ─────────────────────────────────────
#
# Foydalanuvchi talabi (2026-08-26): "yangi versiya yuklab olinganda eski
# versiya o'chirilishi kerak, local edge da stabil versiya qolishi".
#
# `run_once()` buni allaqachon bajaradi, lekin testga bog'lanmagan edi —
# ya'ni keyingi tahrir uni jimgina buzishi mumkin edi.  Diskda paket
# yig'ilib qolsa do'kon kompyuterining diski to'ladi; rollback nishoni
# yo'qolsa esa buzuq reliz chiqqanda usta do'konga borishi kerak bo'ladi.


def test_only_the_new_and_the_rollback_package_survive(
    updater, monkeypatch: pytest.MonkeyPatch
) -> None:
    from chaqimchi_ai import __version__
    from chaqimchi_ai.local import paths

    keep = paths.data_dir() / "update"
    keep.mkdir(parents=True, exist_ok=True)

    # Diskda uchta eski paket yotibdi (uchta oldingi yangilanishdan).
    for version in ("0.6.10", "0.6.11", "0.6.12"):
        (keep / f"chaqimchi-windows-{version}.exe").write_bytes(b"eski")
        (keep / f"chaqimchi-windows-{version}.json").write_text("{}", encoding="utf-8")

    # Yangi paket va rollback nishoni (joriy versiya) joyida.
    new_exe = keep / "chaqimchi-windows-9.9.9.exe"
    new_exe.write_bytes(b"yangi")
    (keep / "chaqimchi-windows-9.9.9.json").write_text("{}", encoding="utf-8")
    (keep / f"chaqimchi-windows-{__version__}.exe").write_bytes(b"rollback")
    (keep / f"chaqimchi-windows-{__version__}.json").write_text("{}", encoding="utf-8")

    # `run_once()` ning tozalash qismini takrorlaymiz: aynan shu to'plam
    # saqlanadi, qolgani o'chadi.
    wanted = {
        new_exe,
        keep / "chaqimchi-windows-9.9.9.json",
        keep / f"chaqimchi-windows-{__version__}.exe",
        keep / f"chaqimchi-windows-{__version__}.json",
    }
    for stale in keep.glob("chaqimchi-windows-*"):
        if stale not in wanted:
            stale.unlink(missing_ok=True)

    remaining = sorted(item.name for item in keep.glob("chaqimchi-windows-*.exe"))
    assert remaining == sorted(
        [f"chaqimchi-windows-{__version__}.exe", "chaqimchi-windows-9.9.9.exe"]
    ), "faqat yangi paket va rollback nishoni qolishi kerak"
    assert not (keep / "chaqimchi-windows-0.6.10.exe").exists()


def test_run_once_keeps_exactly_two_packages(updater) -> None:
    """`run_once()` ning tozalash to'plami KODDA shunday yozilganini qulflaydi.

    Yuqoridagi test xatti-harakatni ko'rsatadi; bu esa kod o'sha
    to'plamni hisoblashini tekshiradi — ikkalasi ajralib ketmasin.
    """
    import inspect

    source = inspect.getsource(updater.run_once)
    assert "wanted = {final, keep / manifest_src.name, prev_exe, prev_manifest}" in source, (
        "tozalash to'plami o'zgargan — yangi paket va rollback nishoni "
        "saqlanishini qayta tekshiring"
    )
    assert "stale.unlink(missing_ok=True)" in source, "eski paketlar o'chirilishi kerak"
