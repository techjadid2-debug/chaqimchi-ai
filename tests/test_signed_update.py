import base64
import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from chaqimchi_ai.signed_update import UpdateVerificationError, verify_release_manifest


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
