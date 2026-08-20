#!/usr/bin/env python3
"""Xodim rasmlarini yangi model bilan qayta hisoblaydi.

Nima uchun kerak: yuz tanish modeli almashtirildi (InsightFace
`buffalo_l`, tadqiqot litsenziyasi → OpenVINO OMZ, Apache-2.0).  Yangi
model **256** o'lchamli vektor beradi, eskisi **512** — ya'ni bazadagi
mavjud embeddinglar yaroqsiz.  Ular jimgina "tanilmadi" bo'lib qolardi:
xodim kelib turadi, davomat esa bo'sh.

Rasmlarning o'zi saqlanib turibdi (MinIO/S3 `photo_key`), shuning uchun
qayta hisoblash mumkin — xodimni yangidan ro'yxatga olish shart emas.

Ishga tushirish (prod):

    docker compose -f docker-compose.chaqimchi.yml --env-file .env.production \
      exec cloud python scripts/reembed_faces.py

Avval nima bo'lishini ko'rish uchun:

    python scripts/reembed_faces.py --dry-run

Skript **qayta ishga tushirishga chidamli**: allaqachon yangi o'lchamdagi
yozuv chetlab o'tiladi, ya'ni yarim yo'lda uzilsa davom ettirsa bo'ladi.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloud import faces  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Xodim embeddinglarini qayta hisoblaydi")
    parser.add_argument("--site", help="Faqat shu obyekt (berilmasa — hammasi)")
    parser.add_argument(
        "--dry-run", action="store_true", help="Hech narsa yozmaydi, faqat hisoblab beradi"
    )
    args = parser.parse_args()

    ready, reason = faces.available()
    if not ready:
        raise SystemExit(f"XATO: yuz xizmati tayyor emas — {reason}")

    # Import shu yerda: `cloud.main` FastAPI ilovasini ko'taradi va uni
    # skript ishga tushishidan oldin yuklash keraksiz sekinlik.
    import cloud.main as main

    store = main.get_event_store()
    snapshots = main.get_snapshot_store()
    target_dim = faces.current_embedding_dim()

    rows = store.all_employee_faces(site_id=args.site)
    stale = [row for row in rows if int(row.get("embedding_dim") or 0) != target_dim]
    print(f"Jami rasm: {len(rows)} · qayta hisoblanadi: {len(stale)} · maqsad o'lcham: {target_dim}")
    if not stale:
        print("Hammasi joyida.")
        return 0
    if args.dry_run:
        for row in stale:
            print(f"  {row['site_id']} · {row['employee_id']} · {row['photo_key']}")
        return 0

    done = 0
    failed = 0
    for row in stale:
        try:
            payload = snapshots.get(row["photo_key"])
        except Exception as exc:  # noqa: BLE001 — bitta rasm butun ishni to'xtatmasin
            print(f"  RASM O'QILMADI {row['photo_key']}: {exc}")
            failed += 1
            continue
        if not payload:
            print(f"  RASM YO'Q {row['photo_key']}")
            failed += 1
            continue
        embedding = faces.get_face_service().embed_jpeg(payload)
        if embedding is None:
            # Eski model yuzni topgan, yangisi topmadi.  Rasm o'chirilmaydi:
            # mijoz o'zi ko'rib, kerak bo'lsa yangisini yuklasin.
            print(f"  YUZ TOPILMADI {row['photo_key']} (xodim: {row['employee_id']})")
            failed += 1
            continue
        store.update_employee_face_embedding(
            row["id"],
            embedding_b64=faces.encrypt_embedding(embedding.vector),
            embedding_dim=int(embedding.vector.shape[0]),
            det_score=round(float(embedding.det_score), 3),
        )
        done += 1

    print(f"\nTayyor: {done} ta qayta hisoblandi, {failed} ta muammoli.")
    if failed:
        print(
            "Muammoli rasmlar bazada ESKI holicha qoldi — ular moslashda "
            "ishlatilmaydi.  Mijozdan yangi rasm so'rash kerak."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
