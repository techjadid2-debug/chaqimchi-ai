"""Event snapshotlari uchun local va S3/MinIO storage adapterlari."""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

from cryptography.fernet import Fernet


class SnapshotStore(Protocol):
    def put(
        self, key: str, data: bytes, *, content_type: str = "application/octet-stream"
    ) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


class LocalSnapshotStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError("Noto'g'ri snapshot key")
        return path

    def put(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class S3SnapshotStore:
    def __init__(self) -> None:
        try:
            from minio import Minio
        except ImportError as exc:  # pragma: no cover - production dependency
            raise RuntimeError("MinIO Python klienti o'rnatilishi kerak") from exc
        self.bucket = os.environ.get("CHAQIMCHI_S3_BUCKET", "chaqimchi-snapshots")
        encryption_key = os.environ.get("CHAQIMCHI_SNAPSHOT_KEY", "").strip()
        self.cipher = Fernet(encryption_key.encode()) if encryption_key else None
        raw_endpoint = os.environ.get("CHAQIMCHI_S3_ENDPOINT", "")
        parsed = urlparse(raw_endpoint)
        endpoint = parsed.netloc or parsed.path
        self.client = Minio(
            endpoint,
            access_key=os.environ.get("CHAQIMCHI_S3_ACCESS_KEY"),
            secret_key=os.environ.get("CHAQIMCHI_S3_SECRET_KEY"),
            secure=parsed.scheme == "https",
            region=os.environ.get("CHAQIMCHI_S3_REGION", "us-east-1"),
        )
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    def put(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> None:
        payload = self.cipher.encrypt(data) if self.cipher else data
        self.client.put_object(
            self.bucket,
            key,
            io.BytesIO(payload),
            len(payload),
            content_type="application/octet-stream" if self.cipher else content_type,
        )

    def get(self, key: str) -> bytes:
        response = self.client.get_object(self.bucket, key)
        try:
            payload = response.read()
            return self.cipher.decrypt(payload) if self.cipher else payload
        finally:
            response.close()
            response.release_conn()

    def delete(self, key: str) -> None:
        self.client.remove_object(self.bucket, key)


def snapshot_store_from_env(base_dir: Path) -> SnapshotStore:
    if os.environ.get("CHAQIMCHI_S3_ENDPOINT", "").strip():
        return S3SnapshotStore()
    return LocalSnapshotStore(base_dir / "data" / "cloud" / "snapshots")
