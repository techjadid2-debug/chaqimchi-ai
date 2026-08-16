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

    cloud = {"enabled": True, "url": "https://c.uz", "site_id": "s",
             "device_id": "d", "device_token": "t"}

    class _Response:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> Dict[str, Any]:
            return {"available": True, "version": __version__}

    monkeypatch.setattr("chaqimchi_ai.local.updater.httpx.get", lambda *a, **k: _Response())
    assert updater.check(cloud) is None


def test_no_release_means_no_update(updater, monkeypatch: pytest.MonkeyPatch) -> None:
    cloud = {"enabled": True, "url": "https://c.uz", "site_id": "s",
             "device_id": "d", "device_token": "t"}

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
        lambda: {"enabled": True, "url": "https://c.uz", "site_id": "s",
                 "device_id": "d", "device_token": "t"},
    )
    monkeypatch.setattr(
        "chaqimchi_ai.local.updater._download", lambda url, dest, headers: None
    )
    with pytest.raises(updater.UpdateError, match="kalit"):
        updater.download_and_verify(
            {"version": VERSION, "download_url": "https://c.uz/a.exe",
             "manifest_url": "https://c.uz/a.json"},
            tmp_path,
        )


def test_install_refuses_to_run_outside_windows(updater, installer: Path) -> None:
    """macOS/Linux'da `.exe` ni ishga tushirishga urinish ma'nosiz."""
    import os

    if os.name == "nt":  # pragma: no cover
        pytest.skip("Windows'da bu tekshiruv qo'llanmaydi")
    with pytest.raises(updater.UpdateError):
        updater.install(installer)


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
