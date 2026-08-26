#!/usr/bin/env python3
"""Moslash chegarasini HAQIQIY do'kon kadrlarida o'lchaydi.

Nima uchun kerak: `cloud/faces.py` dagi standart chegara (0.6) sun'iy
sinovda o'lchangan — yorug'lik, masofa va kamera sifati boshqacha.
Do'kon kamerasidan kelgan crop odatda kichik va xira; chegara juda
baland bo'lsa xodim "tanilmadi" bo'lib qoladi, juda past bo'lsa begona
odam xodim deb tanilishi mumkin.  Ikkalasi ham jimgina xato.

Skript bazadagi saqlangan xodim rasmlaridan foydalanadi:

- **bir xil odam** juftliklari — bitta xodimning ikki rasmi;
- **boshqa odam** juftliklari — turli xodimlarning rasmlari.

Chiqadigan jadval ikki taqsimotni ko'rsatadi va ular orasidagi eng keng
bo'shliqni tavsiya qiladi.

    docker compose -f docker-compose.chaqimchi.yml --env-file .env.production \
      exec cloud python scripts/calibrate_face_threshold.py

Bitta obyekt bo'yicha:

    python scripts/calibrate_face_threshold.py --site fd8b8a1a-0af

MUHIM: har xodimda kamida 2 ta rasm bo'lishi kerak, aks holda "bir xil
odam" juftligi umuman chiqmaydi va tavsiya berilmaydi.
"""

from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloud import faces  # noqa: E402


def percentile(values: list, fraction: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser(description="Yuz moslash chegarasini o'lchaydi")
    parser.add_argument("--site", help="Faqat shu obyekt (berilmasa — hammasi)")
    args = parser.parse_args()

    ready, reason = faces.available()
    if not ready:
        raise SystemExit(f"XATO: yuz xizmati tayyor emas — {reason}")

    import numpy as np

    import cloud.main as main

    store = main.get_event_store()
    target_dim = faces.current_embedding_dim()

    # Embedding `face_embeddings()` dan olinadi.
    #
    # Ilgari bu yerda `employee_face()` chaqirilardi — u esa embeddingni
    # UMUMAN qaytarmaydi (panel uchun mo'ljallangan: `id`, `photo_key`,
    # `det_score`, ...).  Ya'ni skript hech qachon ishlamagan: birinchi
    # qatordayoq `KeyError: 'embedding_b64'` bilan yiqilardi.
    # 2026-08-26 da jonli bazada aynan shu ko'rindi.
    sites = [args.site] if args.site else sorted(
        {str(row["site_id"]) for row in store.all_employee_faces()}
    )

    by_employee: dict = {}
    skipped = 0
    for site in sites:
        for record in store.face_embeddings(site):
            if int(record.get("embedding_dim") or 0) != target_dim:
                skipped += 1
                continue
            vectors = by_employee.setdefault((site, record["employee_id"]), [])
            vectors.append(faces.decrypt_embedding(record["embedding_b64"]))

    if skipped:
        print(
            f"OGOHLANTIRISH: {skipped} ta rasm eski modeldan — hisobga "
            "olinmadi (scripts/reembed_faces.py)"
        )

    same: list = []
    for vectors in by_employee.values():
        for left, right in itertools.combinations(vectors, 2):
            same.append(float(np.dot(left, right)))

    different: list = []
    keys = list(by_employee)
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            for left in by_employee[keys[i]]:
                for right in by_employee[keys[j]]:
                    different.append(float(np.dot(left, right)))

    print(f"\nXodim: {len(by_employee)} · bir xil juftlik: {len(same)} · boshqa: {len(different)}")
    if not same:
        print(
            "\nBir xil odam juftligi yo'q — har xodimga kamida 2 ta rasm "
            "yuklangandan keyin qayta ishga tushiring."
        )
        return 1

    print("\nBIR XIL ODAM (yuqori bo'lishi kerak)")
    print(f"  eng past   {min(same):.3f}")
    print(f"  1%         {percentile(same, 0.01):.3f}")
    print(f"  o'rtacha   {sum(same) / len(same):.3f}")

    if different:
        print("\nBOSHQA ODAM (past bo'lishi kerak)")
        print(f"  eng baland {max(different):.3f}")
        print(f"  99%        {percentile(different, 0.99):.3f}")
        print(f"  o'rtacha   {sum(different) / len(different):.3f}")

    floor = percentile(same, 0.01)
    ceiling = percentile(different, 0.99) if different else 0.0
    print(f"\nHozirgi chegara: {faces.match_threshold():.2f}")
    if ceiling >= floor:
        # Taqsimotlar KESISHADI: bunda hech qanday chegara ikkala xatoni
        # ham yo'q qila olmaydi.  Raqam taklif qilish yolg'on bo'ladi.
        print(
            "\nDIQQAT: ikki taqsimot kesishmoqda "
            f"(boshqa odam {ceiling:.3f} ≥ bir xil odam {floor:.3f}).\n"
            "Bu chegara masalasi emas — rasm sifati masalasi.  Sifatsiz "
            "yoki noto'g'ri belgilangan rasmlarni tekshiring."
        )
        return 1

    recommended = round((floor + ceiling) / 2, 2)
    print(f"TAVSIYA: {recommended:.2f}  (CHAQIMCHI_FACE_MATCH_THRESHOLD)")
    print(f"  bo'shliq: {ceiling:.3f} … {floor:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
