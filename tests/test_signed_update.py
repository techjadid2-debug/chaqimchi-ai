import base64
import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from chaqimchi_ai.signed_update import (
    UpdateVerificationError,
    canonical_manifest_payload,
    verify_release_manifest,
)
from scripts.apply_signed_update import validate_release_target


def test_signed_release_verification(tmp_path: Path) -> None:
    archive = tmp_path / "release.tar.gz"
    archive.write_bytes(b"release")
    digest = hashlib.sha256(b"release").hexdigest()
    private = Ed25519PrivateKey.generate()
    public_path = tmp_path / "public.pem"
    public_path.write_bytes(
        private.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    manifest = {
        "version": "1.0.0",
        "sha256": digest,
        "signature": base64.b64encode(private.sign(f"1.0.0:{digest}".encode())).decode(),
    }
    manifest_path = tmp_path / "release.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert verify_release_manifest(archive, manifest_path, public_path)["version"] == "1.0.0"

    archive.write_bytes(b"tampered")
    with pytest.raises(UpdateVerificationError):
        verify_release_manifest(archive, manifest_path, public_path)


def test_v2_manifest_signs_product_and_architecture(tmp_path: Path) -> None:
    archive = tmp_path / "release.tar.gz"
    archive.write_bytes(b"lite-release")
    private = Ed25519PrivateKey.generate()
    public_path = tmp_path / "public.pem"
    public_path.write_bytes(
        private.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    manifest = {
        "schema_version": 2,
        "product": "chaqimchi-sotqin",
        "target_arch": "x86_64",
        "version": "0.4.0",
        "sha256": hashlib.sha256(b"lite-release").hexdigest(),
    }
    manifest["signature"] = base64.b64encode(
        private.sign(canonical_manifest_payload(manifest))
    ).decode()
    path = tmp_path / "release.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    verified = verify_release_manifest(archive, path, public_path)
    validate_release_target(verified, "amd64")

    manifest["target_arch"] = "aarch64"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(UpdateVerificationError):
        verify_release_manifest(archive, path, public_path)


def test_v2_manifest_rejects_wrong_device_architecture() -> None:
    with pytest.raises(UpdateVerificationError, match="arxitekturasi"):
        validate_release_target(
            {
                "schema_version": 2,
                "product": "chaqimchi-sotqin",
                "target_arch": "x86_64",
            },
            "aarch64",
        )
