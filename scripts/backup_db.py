#!/usr/bin/env python3
"""Yuz bazasi zaxira nusxasi — CLI.

Server ishlamayotgan bo‘lsa ham ishlaydi (diskdagi bazani to‘g‘ridan-to‘g‘ri
o‘qiydi), shuning uchun qurilma ishdan chiqqanda ham nusxa olish mumkin.

    python scripts/backup_db.py save                    # data/backups/ ga
    python scripts/backup_db.py save --out /Volumes/USB # fleshkaga
    python scripts/backup_db.py info nusxa.zip          # ichida nima bor
    python scripts/backup_db.py restore nusxa.zip       # tiklash (so‘raydi)
    python scripts/backup_db.py restore nusxa.zip --merge --yes

Baza shifrlangan bo‘lsa `CHAQIMCHI_EMBEDDING_KEY` muhit o‘zgaruvchisi kerak —
nusxa olishda ham, tiklashda ham **bir xil** kalit.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chaqimchi_ai.backup import (  # noqa: E402
    BackupError,
    read_backup,
    restore_backup,
    write_backup_file,
)
from chaqimchi_ai.database import FaceDatabase  # noqa: E402
from chaqimchi_ai.embedding_crypto import resolve_embedding_key  # noqa: E402
from chaqimchi_ai.settings import load_app_settings  # noqa: E402


def _open_db() -> tuple[FaceDatabase, bytes | None, str | None]:
    cfg = load_app_settings(ROOT)
    db = FaceDatabase(
        ROOT / cfg.paths.db_path,
        encrypt_embeddings=cfg.storage.encrypt_embeddings,
        vector_backend=cfg.storage.vector_backend,
    )
    key = resolve_embedding_key() if cfg.storage.encrypt_embeddings else None
    return db, key, cfg.license.site_id


def cmd_save(args: argparse.Namespace) -> int:
    db, key, site_id = _open_db()
    out = Path(args.out) if args.out else ROOT / "data" / "backups"
    path = write_backup_file(db, out, encryption_key=key, site_id=site_id)
    size_kb = path.stat().st_size / 1024
    print(f"✓ Nusxa tayyor: {path}")
    print(f"  {db.count} shaxs, {size_kb:.1f} KB, shifr: {'ha' if key else 'yo‘q'}")
    if not key:
        print("  Diqqat: fayl biometrik ma’lumot — himoyalangan joyda saqlang.")
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    data = Path(args.file).read_bytes()
    try:
        metadata, embeddings, manifest = read_backup(data, encryption_key=resolve_embedding_key())
    except BackupError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    print(f"Sana:     {manifest.get('created_at')}")
    print(f"Obyekt:   {manifest.get('site_id') or '—'}")
    print(f"Shaxslar: {len(metadata)}")
    print(f"Shifr:    {'ha' if manifest.get('encrypted') else 'yo‘q'}")
    if metadata:
        names = ", ".join(m.get("name", "?") for m in metadata[:5])
        more = " ..." if len(metadata) > 5 else ""
        print(f"Namuna:   {names}{more}")
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    db, _, _ = _open_db()
    data = Path(args.file).read_bytes()
    mode = "merge" if args.merge else "replace"

    if not args.yes:
        if mode == "replace":
            print(f"DIQQAT: hozirgi {db.count} shaxs o‘chib, nusxadagilar yoziladi.")
        else:
            print(f"Nusxadagi yangi shaxslar hozirgi {db.count} tasiga qo‘shiladi.")
        if input("Davom etilsinmi? (ha/yo'q): ").strip().lower() not in ("ha", "h", "yes", "y"):
            print("Bekor qilindi.")
            return 1

    try:
        result = restore_backup(db, data, encryption_key=resolve_embedding_key(), mode=mode)
    except BackupError as e:
        print(f"✗ {e}", file=sys.stderr)
        print("  Baza o‘zgarmadi.", file=sys.stderr)
        return 1

    print(
        f"✓ Tiklandi ({mode}): {result['persons_before']} → {result['persons_after']} shaxs"
        + (f", {result['skipped']} tasi allaqachon bor edi" if result["skipped"] else "")
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Chaqimchi AI — baza zaxira nusxasi")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_save = sub.add_parser("save", help="Nusxa olish")
    p_save.add_argument("--out", help="Papka yoki fayl yo‘li")
    p_save.set_defaults(func=cmd_save)

    p_info = sub.add_parser("info", help="Nusxa ichida nima bor")
    p_info.add_argument("file")
    p_info.set_defaults(func=cmd_info)

    p_rest = sub.add_parser("restore", help="Nusxadan tiklash")
    p_rest.add_argument("file")
    p_rest.add_argument("--merge", action="store_true", help="Almashtirmasdan qo‘shish")
    p_rest.add_argument("--yes", action="store_true", help="So‘ramasdan")
    p_rest.set_defaults(func=cmd_restore)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
