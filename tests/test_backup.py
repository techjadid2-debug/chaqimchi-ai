import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pytest

from chaqimchi_ai.backup import (
    BACKUP_VERSION,
    BackupError,
    backup_filename,
    create_backup,
    read_backup,
    restore_backup,
    write_backup_file,
)
from chaqimchi_ai.database import FaceDatabase

EMBED_DIM = 512


def _vec(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    v = rng.normal(size=EMBED_DIM).astype(np.float32)
    return v / np.linalg.norm(v)


def _db(tmp_path: Path, names: list[str], **kwargs) -> FaceDatabase:
    db = FaceDatabase(tmp_path / "db", **kwargs)
    for i, name in enumerate(names):
        db.add_face(name, _vec(i))
    return db


# ── Nusxa olish ──────────────────────────────────────────────────────────


def test_backup_contains_expected_files(tmp_path: Path) -> None:
    db = _db(tmp_path, ["Ali", "Vali"])

    blob = create_backup(db, site_id="s1")

    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = set(zf.namelist())
        assert names == {"manifest.json", "metadata.json", "embeddings.npy"}
        manifest = json.loads(zf.read("manifest.json"))
    assert manifest["version"] == BACKUP_VERSION
    assert manifest["persons"] == 2
    assert manifest["site_id"] == "s1"
    assert manifest["encrypted"] is False


def test_backup_of_empty_db(tmp_path: Path) -> None:
    db = FaceDatabase(tmp_path / "db")
    metadata, embeddings, manifest = read_backup(create_backup(db))
    assert metadata == []
    assert embeddings.shape[0] == 0
    assert manifest["persons"] == 0


def test_backup_filename_has_site_and_zip_suffix() -> None:
    assert backup_filename("dokon1").startswith("chaqimchi-dokon1-")
    assert backup_filename().endswith(".zip")


# ── Aylanma: nusxa → tiklash ─────────────────────────────────────────────


def test_roundtrip_preserves_names_and_vectors(tmp_path: Path) -> None:
    src = _db(tmp_path / "a", ["Ali", "Vali", "Guli"])
    blob = create_backup(src)

    dst = FaceDatabase(tmp_path / "b" / "db")
    result = restore_backup(dst, blob)

    assert result["persons_after"] == 3
    assert [m["name"] for m in dst.metadata] == ["Ali", "Vali", "Guli"]
    assert np.allclose(dst.embeddings, src.embeddings)


def test_restored_db_can_still_search(tmp_path: Path) -> None:
    """Eng muhimi: tiklangandan keyin tanish rostdan ishlaydi."""
    src = _db(tmp_path / "a", ["Ali", "Vali"])
    query = src.embeddings[1].copy()

    dst = FaceDatabase(tmp_path / "b" / "db")
    restore_backup(dst, create_backup(src))

    hits = dst.search(query, threshold=0.4)
    assert hits and hits[0]["name"] == "Vali"
    assert hits[0]["score"] > 0.99


def test_restore_survives_reopen_from_disk(tmp_path: Path) -> None:
    """Tiklangan baza diskka yozilgan — server qayta ishga tushsa ham qoladi."""
    src = _db(tmp_path / "a", ["Ali"])
    dst_path = tmp_path / "b" / "db"
    restore_backup(FaceDatabase(dst_path), create_backup(src))

    reopened = FaceDatabase(dst_path)
    assert reopened.count == 1
    assert reopened.metadata[0]["name"] == "Ali"


def test_write_backup_file_to_directory(tmp_path: Path) -> None:
    db = _db(tmp_path / "a", ["Ali"])
    out_dir = tmp_path / "backups"

    path = write_backup_file(db, out_dir, site_id="s9")

    assert path.parent == out_dir
    assert path.suffix == ".zip"
    assert read_backup(path.read_bytes())[2]["persons"] == 1


# ── Rejimlar ─────────────────────────────────────────────────────────────


def test_replace_mode_drops_existing_persons(tmp_path: Path) -> None:
    src = _db(tmp_path / "a", ["Ali"])
    dst = _db(tmp_path / "b", ["Eski1", "Eski2"])

    result = restore_backup(dst, create_backup(src), mode="replace")

    assert result["persons_before"] == 2
    assert dst.count == 1
    assert [m["name"] for m in dst.metadata] == ["Ali"]


def test_merge_mode_keeps_existing_and_adds_new(tmp_path: Path) -> None:
    src = _db(tmp_path / "a", ["Yangi"])
    dst = _db(tmp_path / "b", ["Eski"])

    result = restore_backup(dst, create_backup(src), mode="merge")

    assert result["added"] == 1
    assert dst.count == 2
    assert {m["name"] for m in dst.metadata} == {"Eski", "Yangi"}
    assert dst.embeddings.shape == (2, EMBED_DIM)


def test_merge_skips_ids_already_present(tmp_path: Path) -> None:
    """O‘sha nusxani ikki marta merge qilish dublikat yaratmaydi."""
    src = _db(tmp_path / "a", ["Ali", "Vali"])
    blob = create_backup(src)
    dst = FaceDatabase(tmp_path / "b" / "db")

    restore_backup(dst, blob, mode="merge")
    result = restore_backup(dst, blob, mode="merge")

    assert result["added"] == 0
    assert result["skipped"] == 2
    assert dst.count == 2


def test_merge_into_empty_db(tmp_path: Path) -> None:
    src = _db(tmp_path / "a", ["Ali"])
    dst = FaceDatabase(tmp_path / "b" / "db")

    restore_backup(dst, create_backup(src), mode="merge")

    assert dst.count == 1


def test_unknown_mode_rejected(tmp_path: Path) -> None:
    db = _db(tmp_path, ["Ali"])
    with pytest.raises(BackupError, match="rejim"):
        restore_backup(db, create_backup(db), mode="nimadir")


# ── Shifrlangan baza ─────────────────────────────────────────────────────


def _fernet_key() -> bytes:
    Fernet = pytest.importorskip("cryptography.fernet").Fernet
    return Fernet.generate_key()


def test_encrypted_backup_roundtrip(tmp_path: Path) -> None:
    key = _fernet_key()
    src = _db(tmp_path / "a", ["Ali"], encrypt_embeddings=True, embedding_key=key)

    blob = create_backup(src, encryption_key=key)

    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        assert "embeddings.enc" in zf.namelist()
        assert "embeddings.npy" not in zf.namelist()

    dst = FaceDatabase(tmp_path / "b" / "db", encrypt_embeddings=True, embedding_key=key)
    restore_backup(dst, blob, encryption_key=key)
    assert np.allclose(dst.embeddings, src.embeddings)


def test_encrypted_backup_without_key_fails(tmp_path: Path) -> None:
    key = _fernet_key()
    src = _db(tmp_path / "a", ["Ali"], encrypt_embeddings=True, embedding_key=key)
    blob = create_backup(src, encryption_key=key)

    with pytest.raises(BackupError, match="KEY"):
        read_backup(blob)


def test_encrypted_backup_with_wrong_key_fails(tmp_path: Path) -> None:
    key = _fernet_key()
    src = _db(tmp_path / "a", ["Ali"], encrypt_embeddings=True, embedding_key=key)
    blob = create_backup(src, encryption_key=key)

    with pytest.raises(BackupError, match="Shifr yechilmadi"):
        read_backup(blob, encryption_key=_fernet_key())


# ── Buzuq nusxalar ───────────────────────────────────────────────────────


def test_not_a_zip(tmp_path: Path) -> None:
    with pytest.raises(BackupError, match="ZIP"):
        read_backup(b"bu zip emas")


def test_zip_without_manifest() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("boshqa.txt", "salom")
    with pytest.raises(BackupError, match="manifest"):
        read_backup(buf.getvalue())


def test_version_mismatch(tmp_path: Path) -> None:
    db = _db(tmp_path, ["Ali"])
    blob = create_backup(db)

    src = zipfile.ZipFile(io.BytesIO(blob))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        for item in src.namelist():
            data = src.read(item)
            if item == "manifest.json":
                m = json.loads(data)
                m["version"] = 99
                data = json.dumps(m).encode()
            zf.writestr(item, data)

    with pytest.raises(BackupError, match="versiyasi"):
        read_backup(out.getvalue())


def test_corrupted_embeddings_detected_by_checksum(tmp_path: Path) -> None:
    """Checksum bo‘lmasa buzuq vektorlar jimgina bazaga tushib ketardi."""
    db = _db(tmp_path, ["Ali"])
    blob = create_backup(db)

    src = zipfile.ZipFile(io.BytesIO(blob))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        for item in src.namelist():
            data = src.read(item)
            if item == "embeddings.npy":
                data = data[:-8] + b"\x00" * 8
            zf.writestr(item, data)

    with pytest.raises(BackupError, match="buzilgan"):
        read_backup(out.getvalue())


def test_count_mismatch_detected(tmp_path: Path) -> None:
    db = _db(tmp_path, ["Ali", "Vali"])
    blob = create_backup(db)

    src = zipfile.ZipFile(io.BytesIO(blob))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        for item in src.namelist():
            data = src.read(item)
            if item == "metadata.json":
                data = json.dumps(json.loads(data)[:1]).encode()
            elif item == "manifest.json":
                m = json.loads(data)
                m["files"] = {}  # checksumni o'chirib, count tekshiruviga yetib boramiz
                data = json.dumps(m).encode()
            zf.writestr(item, data)

    with pytest.raises(BackupError, match="buzuq"):
        read_backup(out.getvalue())


def test_failed_restore_leaves_db_untouched(tmp_path: Path) -> None:
    """Eng muhim kafolat: buzuq fayl bazani buzmaydi."""
    dst = _db(tmp_path / "b", ["Eski1", "Eski2"])
    before = dst.embeddings.copy()

    with pytest.raises(BackupError):
        restore_backup(dst, b"buzuq fayl")

    assert dst.count == 2
    assert np.allclose(dst.embeddings, before)
    assert FaceDatabase(tmp_path / "b" / "db").count == 2


# ── API ──────────────────────────────────────────────────────────────────


@pytest.fixture
def client(tmp_path: Path):
    from fastapi.testclient import TestClient

    from chaqimchi_ai.audit import AuditLog
    from chaqimchi_ai.events import EventLog
    from chaqimchi_ai.runtime.container import AppContainer
    from chaqimchi_ai.settings import AppSettings
    from webapp.main import create_app

    container = AppContainer(
        tmp_path,
        settings=AppSettings(),
        db=_db(tmp_path / "live", ["Ali", "Vali"]),
        events=EventLog(tmp_path / "events.db"),
        audit=AuditLog(tmp_path / "audit.db"),
    )
    # `with` yo'q — lifespan (kameralar, model) ishga tushmasin.
    return TestClient(create_app(container))


def test_api_download_returns_valid_zip(client) -> None:
    r = client.get("/api/backup")

    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert ".zip" in r.headers["content-disposition"]
    metadata, _, manifest = read_backup(r.content)
    assert manifest["persons"] == 2
    assert {m["name"] for m in metadata} == {"Ali", "Vali"}


def test_api_restore_roundtrip(client, tmp_path: Path) -> None:
    blob = client.get("/api/backup").content
    other = _db(tmp_path / "other", ["Boshqa"])

    r = client.post(
        "/api/backup/restore",
        files={"file": ("nusxa.zip", create_backup(other), "application/zip")},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["persons_before"] == 2
    assert body["persons_after"] == 1
    # Eski nusxani qaytarib tiklash ham ishlaydi.
    back = client.post(
        "/api/backup/restore",
        files={"file": ("nusxa.zip", blob, "application/zip")},
    )
    assert back.json()["persons_after"] == 2


def test_api_restore_merge_mode(client, tmp_path: Path) -> None:
    other = _db(tmp_path / "other", ["Boshqa"])

    r = client.post(
        "/api/backup/restore",
        data={"mode": "merge"},
        files={"file": ("n.zip", create_backup(other), "application/zip")},
    )

    assert r.json()["persons_after"] == 3


def test_api_restore_rejects_garbage(client) -> None:
    r = client.post(
        "/api/backup/restore",
        files={"file": ("n.zip", b"buzuq", "application/zip")},
    )

    assert r.status_code == 400
    assert r.json()["ok"] is False
    # Baza tegilmagan.
    assert len(client.get("/api/persons").json()) == 2


def test_api_restore_rejects_empty_file(client) -> None:
    r = client.post("/api/backup/restore", files={"file": ("n.zip", b"", "application/zip")})
    assert r.status_code == 400


def test_api_backup_requires_key_when_enabled(client) -> None:
    sec = client.app.state.container.settings.security
    sec.api_key_enabled = True
    sec.api_key = "maxfiy"
    try:
        assert client.get("/api/backup").status_code == 401
        assert client.get("/api/backup", headers={"X-API-Key": "maxfiy"}).status_code == 200
        assert (
            client.post(
                "/api/backup/restore", files={"file": ("n.zip", b"x", "application/zip")}
            ).status_code
            == 401
        )
    finally:
        sec.api_key_enabled = False
        sec.api_key = None


def test_api_restore_warns_when_over_plan_limit(client, tmp_path: Path) -> None:
    from chaqimchi_ai.licensing.models import LicenseState

    client.app.state.container.license_state = LicenseState(
        site_id="s1",
        plan="starter",
        status="active",
        subscription_until="2030-01-01",
        max_cameras=1,
        max_persons=1,
        retention_days=30,
        telegram_allowed=True,
    )
    other = _db(tmp_path / "other", ["A", "B", "C"])

    r = client.post(
        "/api/backup/restore",
        files={"file": ("n.zip", create_backup(other), "application/zip")},
    )

    assert r.status_code == 200
    assert "Tarif limiti" in r.json()["warning"]
