"""Reliz imzolash: kalit yaratish va manifest yozish.

Eng muhim shart — **imzolovchi va tekshiruvchi bir xil baytlarni** ko'rishi.
Ular ajralib qolsa qurilma `"Release imzosi yaroqsiz"` deb rad etadi va
sababini aytmaydi. Shuning uchun imzolovchi `canonical_manifest_payload` ni
import qiladi va bu yerda round-trip test bor.

Ikkinchi shart — arxiv nomi va ichidagi kod bir xil versiyani ko'rsatishi.
Diskda aynan shunday buzilgan tarball topilgan: nomi `0.5.0`, ichi esa
boshqa kod, va u `/downloads/sotqin-installer.sh` orqali mijozga ketardi.
"""

from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

import pytest

from enes.signed_update import UpdateVerificationError, verify_release_manifest
from scripts import generate_update_key, sign_release


@pytest.fixture
def keys(tmp_path: Path) -> tuple[Path, Path]:
    private = tmp_path / "maxfiy.pem"
    public = tmp_path / "ochiq.pem"
    generate_update_key.generate(private, public)
    return private, public


def make_archive(path: Path, *, version: str = "0.6.0", top: str = "enes-sotqin-0.6.0"):
    """Ichida `enes/__init__.py` bo'lgan haqiqiy tar.gz."""
    source = f'__version__ = "{version}"\n'.encode()
    with tarfile.open(path, "w:gz") as package:
        info = tarfile.TarInfo(f"{top}/enes/__init__.py")
        info.size = len(source)
        package.addfile(info, io.BytesIO(source))
    return path


# ── Kalit yaratish ───────────────────────────────────────────────────────


def test_private_key_is_owner_only_and_outside_the_repo(tmp_path: Path) -> None:
    """`.gitignore` ga ishonish yetarli emas: `git add -f`, repo ildizidan
    olingan `tar` yoki Docker konteksti kalitni ilib ketishi mumkin."""
    private = tmp_path / "maxfiy.pem"
    generate_update_key.generate(private, tmp_path / "ochiq.pem")

    assert private.stat().st_mode & 0o777 == 0o600
    # Standart yo'l repo ichida emas.
    # Repo papkasi diskda hali "Chaqimchi AI" — kalit uning ichida bo'lmasin.
    assert "Chaqimchi AI" not in str(generate_update_key.DEFAULT_PRIVATE)
    assert generate_update_key.DEFAULT_PRIVATE.name.endswith(".pem")


def test_an_existing_key_is_never_overwritten(tmp_path: Path) -> None:
    """Kalit almashsa mavjud qurilmalar yangilanmay qoladi."""
    private = tmp_path / "maxfiy.pem"
    public = tmp_path / "ochiq.pem"
    generate_update_key.generate(private, public)
    original = private.read_bytes()

    with pytest.raises(FileExistsError):
        generate_update_key.generate(private, public)
    assert private.read_bytes() == original


def test_the_public_key_is_a_pem_ed25519_key(tmp_path: Path) -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    public = tmp_path / "ochiq.pem"
    generate_update_key.generate(tmp_path / "maxfiy.pem", public)

    key = serialization.load_pem_public_key(public.read_bytes())
    assert isinstance(key, Ed25519PublicKey)


def test_the_committed_public_key_is_valid() -> None:
    """Repodagi kalit qurilmaga boradi — u yaroqli bo'lishi shart."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    path = Path(__file__).resolve().parents[1] / "deploy" / "update-public.pem"
    assert path.is_file(), "deploy/update-public.pem commit qilinmagan"

    key = serialization.load_pem_public_key(path.read_bytes())
    assert isinstance(key, Ed25519PublicKey)


# ── Imzolash ─────────────────────────────────────────────────────────────


def test_a_signed_manifest_verifies_on_the_device(tmp_path: Path, keys) -> None:
    """Butun modulning ma'nosi: imzolovchi va tekshiruvchi bir xil
    baytlarni ko'rsin."""
    private, public = keys
    archive = make_archive(tmp_path / "enes-sotqin-0.6.0.tar.gz")

    assert (
        sign_release.main(
            [str(archive), "--private-key", str(private), "--public-key", str(public)]
        )
        == 0
    )

    manifest_path = tmp_path / "enes-sotqin-0.6.0.json"
    verified = verify_release_manifest(archive, manifest_path, public)
    assert verified["version"] == "0.6.0"
    assert verified["schema_version"] == 2
    assert verified["product"] == "enes-sotqin"
    assert verified["target_arch"] == "x86_64"


def test_the_manifest_has_exactly_the_expected_fields(tmp_path: Path, keys) -> None:
    """V2 hamma maydonni imzolaydi — har qo'shimcha maydon abadiy
    majburiyat bo'lib qoladi."""
    private, public = keys
    archive = make_archive(tmp_path / "enes-sotqin-0.6.0.tar.gz")
    sign_release.main([str(archive), "--private-key", str(private), "--public-key", str(public)])

    manifest = json.loads((tmp_path / "enes-sotqin-0.6.0.json").read_text(encoding="utf-8"))

    assert set(manifest) == {
        "schema_version",
        "product",
        "target_arch",
        "version",
        "sha256",
        "signature",
    }


def test_a_mismatched_version_inside_the_archive_is_refused(tmp_path: Path, keys) -> None:
    """Diskda aynan shunday tarball topilgan: nomi 0.5.0, ichi boshqa kod."""
    private, public = keys
    archive = make_archive(tmp_path / "enes-sotqin-0.6.0.tar.gz", version="0.5.0")

    code = sign_release.main(
        [str(archive), "--private-key", str(private), "--public-key", str(public)]
    )

    assert code == 1
    assert not (tmp_path / "enes-sotqin-0.6.0.json").exists()


def test_signing_with_the_wrong_key_fails_on_the_laptop(tmp_path: Path, keys) -> None:
    """O'z-o'zini tekshirish: noto'g'ri kalit obyektda emas, bu yerda
    ma'lum bo'lsin."""
    private, _public = keys
    other_public = tmp_path / "boshqa.pem"
    generate_update_key.generate(tmp_path / "boshqa-maxfiy.pem", other_public)
    archive = make_archive(tmp_path / "enes-sotqin-0.6.0.tar.gz")

    code = sign_release.main(
        [str(archive), "--private-key", str(private), "--public-key", str(other_public)]
    )

    assert code == 1
    # Yaroqsiz manifest diskda qolmasin.
    assert not (tmp_path / "enes-sotqin-0.6.0.json").exists()


def test_a_tampered_archive_no_longer_verifies(tmp_path: Path, keys) -> None:
    private, public = keys
    archive = make_archive(tmp_path / "enes-sotqin-0.6.0.tar.gz")
    sign_release.main([str(archive), "--private-key", str(private), "--public-key", str(public)])

    archive.write_bytes(archive.read_bytes() + b"qo-shimcha")

    with pytest.raises(UpdateVerificationError, match="SHA-256"):
        verify_release_manifest(archive, tmp_path / "enes-sotqin-0.6.0.json", public)


@pytest.mark.parametrize("name", ["boshqa-paket-1.0.tar.gz", "enes-sotqin.tar.gz"])
def test_an_unexpected_archive_name_is_refused(tmp_path: Path, keys, name: str) -> None:
    private, public = keys
    archive = make_archive(tmp_path / name)

    assert (
        sign_release.main(
            [str(archive), "--private-key", str(private), "--public-key", str(public)]
        )
        == 1
    )


def test_a_version_the_device_would_reject_is_refused(tmp_path: Path, keys) -> None:
    """`signed_update.py` versiyani papka nomi sifatida ishlatadi, shuning
    uchun belgilar ro'yxati qat'iy. Bu tekshiruvsiz xato faqat qurilmada
    chiqardi."""
    private, public = keys
    archive = make_archive(tmp_path / "enes-sotqin-0.6.0+yomon.tar.gz", version="0.6.0+yomon")

    assert (
        sign_release.main(
            [str(archive), "--private-key", str(private), "--public-key", str(public)]
        )
        == 1
    )


def test_a_missing_private_key_says_what_to_run(tmp_path: Path, capsys) -> None:
    archive = make_archive(tmp_path / "enes-sotqin-0.6.0.tar.gz")

    code = sign_release.main([str(archive), "--private-key", str(tmp_path / "yo-q.pem")])

    assert code == 1
    assert "generate_update_key.py" in capsys.readouterr().err


# ── Brend almashuvi: o'tish relizi ───────────────────────────────────────
#
# Daladagi 0.6.25 qurilmasi FAQAT eski `product` nomlarini biladi.  Yangi
# nom bilan chiqqan reliz uni "Release product noma'lum" deb rad etardi,
# ya'ni rebrend avto-yangilanish zanjirini uzardi va pilotni qo'lda
# qayta o'rnatish kerak bo'lardi.  Yechim — bitta o'tish relizi ESKI nom
# bilan; shundan keyingisi yangi nomda.


def test_a_transition_release_may_carry_the_old_product_name(tmp_path: Path, keys) -> None:
    private, public = keys
    archive = make_archive(tmp_path / "chaqimchi-sotqin-0.6.0.tar.gz")

    assert (
        sign_release.main(
            [
                str(archive),
                "--product",
                "chaqimchi-sotqin",
                "--private-key",
                str(private),
                "--public-key",
                str(public),
            ]
        )
        == 0
    )

    verified = verify_release_manifest(
        archive, tmp_path / "chaqimchi-sotqin-0.6.0.json", public
    )
    assert verified["product"] == "chaqimchi-sotqin"


def test_the_new_device_still_accepts_the_old_manifest_it_kept() -> None:
    """Orqaga qaytish yo'li tirik qolsin.

    O'tish relizi o'rnatilgach qurilmada ESKI manifest saqlanib qoladi
    (`updater.py` uni `prev_manifest` sifatida qayta tekshiradi).  Eski
    nom ro'yxatdan chiqsa qaytish yo'li jimgina o'lardi.
    """
    from enes.signed_update import KNOWN_PRODUCTS

    assert {"chaqimchi-windows", "chaqimchi-sotqin", "chaqimchi-lite"} <= KNOWN_PRODUCTS
    assert {"enes-windows", "enes-sotqin", "enes-lite"} <= KNOWN_PRODUCTS
