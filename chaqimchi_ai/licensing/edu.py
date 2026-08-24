"""Chaqimchi Edu — ta'lim muassasalari uchun narx modeli.

Do'kon tarifidan (`plans.py`) nima bilan farq qiladi: u yerda narx
kamera soniga bog'langan, bu yerda esa **odamlar soniga**.  Maktabda
kamera soni deyarli o'zgarmaydi, o'quvchilar soni esa har yili
o'zgaradi va Face ID bazasi ham shunga qarab o'sadi.

Nega alohida modul, `plans.py` ga qo'shilmadi: u yerdagi `PlanTier`
va `SELLABLE_PLANS` billing bilan bog'langan (obuna, hisob-faktura,
`create_site`).  Edu hozircha **sotuv bosqichida** — sayt
kalkulyatori ariza yig'adi, obuna esa qo'lda rasmiylashtiriladi.
Billing tayyor bo'lganda bu yerdagi konstantalar `plans.py` ga
ko'chiriladi.

**Narxlar boshlang'ich tijorat modeli.**  Ular Farg'ona va Namangandagi
pilot mijozlar bilan tekshirilishi kerak; ayniqsa Edge qurilmalarining
narxi to'g'ridan-to'g'ri import kelishuviga bog'liq.  Shuning uchun
sahifada ham "mo'ljal" deb yoziladi.

Butun hisob shu yerda — sahifadagi JavaScript faqat SHU yerdan kelgan
konstantalar bilan ishlaydi.  Narxni ikki joyda hisoblash eng oson
xato manbai bo'lardi: biri o'zgarib, ikkinchisi eskirib qolardi.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

#: Muassasa turi → (ko'rinadigan nom, bazaviy oylik narx).
#:
#: Oliygoh qimmatroq: u yerda bir nechta bino, fakultet kesimidagi
#: hisobot va kampus xavfsizligi kerak — ya'ni bir xil kamera soniga
#: ko'proq ish to'g'ri keladi.
INSTITUTIONS: Dict[str, Tuple[str, int]] = {
    "markaz": ("O'quv markazi", 149_000),
    "maktab": ("Xususiy maktab", 199_000),
    "oliygoh": ("Oliygoh", 349_000),
}

#: Bazaviy narxga kiradigan hajm.
BASE_INCLUDED_PEOPLE = 100
BASE_INCLUDED_CAMERAS = 2

#: Odam soni bo'yicha bosqichli narx: `(shu songacha, kishi boshiga)`.
#:
#: Bosqichlar **progressiv** — soliq shkalasi kabi.  355 kishilik
#: maktabda dastlabki 100 kishi bepul, keyingi 200 kishi 700 so'mdan,
#: qolgan 55 kishi 450 so'mdan hisoblanadi.  Tekis stavka bo'lganda
#: 301-kishi qo'shilishi bilan hisob keskin sakrab ketardi va mijoz
#: buni adolatsiz deb hisoblardi.
PERSON_BANDS: Tuple[Tuple[Optional[int], int], ...] = (
    (100, 0),
    (300, 700),
    (1000, 450),
    (3000, 250),
    (None, 120),
)

#: Odam soniga qarab AI tahliliga ulanadigan kameralar taxmini:
#: `(shu songacha, markaz, maktab, oliygoh)`.
#:
#: Bu muassasadagi BARCHA kameralar soni emas.  Maktabda 32 ta kamera
#: bo'lishi mumkin, lekin AI ulardan faqat kirish, sinflar va yo'lakni
#: tahlil qiladi — qolganlari avvalgidek yozib turaveradi.
CAMERA_TABLE: Tuple[Tuple[Optional[int], int, int, int], ...] = (
    (150, 2, 4, 4),
    (350, 4, 6, 6),
    (700, 6, 8, 10),
    (1500, 10, 12, 16),
    (4000, 16, 20, 24),
    (None, 24, 32, 40),
)

#: Bazaviy ikkitadan ortiq har bir faol AI kamera.
EXTRA_CAMERA_UZS = 29_000

#: AI modullari va ularning oylik narxi.
MODULES: Dict[str, Tuple[str, int]] = {
    "faceid": ("Face ID va avtomatik davomat", 129_000),
    "monitoring": ("AI dars monitoringi", 129_000),
    "deep": ("Chuqurlashtirilgan dars tahlili", 249_000),
    "fight": ("Janjal va tajovuzni aniqlash", 199_000),
    "branch": ("Qo'shimcha filial", 99_000),
}

#: Chuqur tahlil oddiy monitoring O'RNIGA ishlaydi — ikkalasi
#: birgalikda hisoblanmaydi.  Aks holda mijoz bir xil ish uchun ikki
#: marta to'lardi.
DEEP_REPLACES = "monitoring"

#: Har modul bitta kameraga qancha qo'shimcha hisoblash yuki beradi.
#:
#: Janjal tahlili eng og'ir: u bitta suratni emas, bir necha kadrdan
#: iborat VAQT KETMA-KETLIGINI tahlil qiladi.  Face ID ham og'ir,
#: lekin u faqat kirish nuqtalarida ishlaydi.
LOAD_WEIGHTS: Dict[str, float] = {
    "faceid": 1.25,
    "monitoring": 0.75,
    "deep": 2.25,
    "fight": 2.5,
}

#: Edge qurilmalari: `(shartli yuklama chegarasi, nom, tavsif, narx)`.
#:
#: Narxlar bir martalik va **mo'ljal**.  Mini va Lite uchun bu
#: qiymatlar to'g'ridan-to'g'ri import kelishuvi bo'lgandagina realist:
#: mahalliy e'lonlarda shunday mini-kompyuterlar qimmatroq uchraydi.
EDGE_CATALOG: Tuple[Tuple[int, str, str, int], ...] = (
    (4, "Mini", "Intel N95/N100, 8 GB RAM, 128 GB SSD", 1_790_000),
    (9, "Lite", "Intel N100/N150, 8-16 GB RAM, 256 GB SSD", 2_490_000),
    (15, "Plus", "Intel Core i3-N305, 16 GB RAM, 512 GB SSD", 4_490_000),
    (28, "Pro", "Intel Core i5-12400, RTX 3050 6 GB, 16 GB RAM", 7_490_000),
    (48, "Max", "Core i5, RTX 4060/5060 8 GB, 32 GB RAM, 1 TB SSD", 10_490_000),
    (80, "Ultra Max", "Core i7, RTX 5070 12 GB, 64 GB RAM, 2 TB SSD", 19_490_000),
)

#: Yakuniy summa shu qadamga yuqoriga yaxlitlanadi.
ROUND_TO_UZS = 10_000


def person_fee(people: int) -> int:
    """Odamlar soni uchun oylik qo'shimcha — bosqichma-bosqich."""
    remaining = max(0, int(people))
    previous = 0
    total = 0
    for ceiling, rate in PERSON_BANDS:
        if ceiling is None:
            total += max(0, remaining - previous) * rate
            break
        span = ceiling - previous
        counted = min(max(0, remaining - previous), span)
        total += counted * rate
        previous = ceiling
        if remaining <= ceiling:
            break
    return total


def estimate_cameras(people: int, kind: str) -> int:
    """AI tahliliga ulanadigan kameralar taxmini.

    Mijozdan kamera sonini so'rash noto'g'ri boshlanish bo'lardi: u
    "nechta kamerangiz bor?" degan savolga 32 deb javob beradi va narx
    keraksiz qimmat chiqadi.  Shuning uchun avval odam soni so'raladi,
    kalkulyator esa taxminni o'zi qo'yadi — mijoz uni keyin
    aniqlashtirishi mumkin.
    """
    column = {"markaz": 1, "maktab": 2, "oliygoh": 3}.get(kind, 2)
    count = max(0, int(people))
    for row in CAMERA_TABLE:
        ceiling = row[0]
        if ceiling is None or count <= ceiling:
            return int(row[column])
    return int(CAMERA_TABLE[-1][column])


def normalise_modules(modules: List[str]) -> List[str]:
    """Chuqur tahlil tanlansa oddiy monitoring o'chiriladi."""
    chosen = [code for code in modules if code in MODULES]
    if "deep" in chosen:
        chosen = [code for code in chosen if code != DEEP_REPLACES]
    return chosen


def module_cameras(cameras: int, code: str) -> int:
    """Modul nechta kameraga tegadi.

    Modul yoqilgani "hamma kamerada ishlaydi" degani EMAS va bu
    yuklama hisobidagi eng katta farq.  Haqiqiy maktabda:

    * Face ID faqat KIRISH eshiklarida — sinf kamerasida yuz tanish
      shart emas va u yerdagi burchak buning uchun yaroqsiz ham;
    * dars monitoringi faqat SINF xonalarida;
    * janjal tahlili yo'lak, hovli va oshxonada — ya'ni tanaffusda
      odam to'planadigan joylarda.

    Nisbatlar odatiy maktab tarkibidan olingan va `spec` dagi
    misollarni aynan qaytaradi (8 kamera → 1 kirish, 2 sinf,
    2 yo'lak).
    """
    count = max(0, int(cameras))
    if code == "faceid":
        # Kamida bitta kirish eshigi doim bo'ladi.
        return max(1, count // 8) if count else 0
    if code in ("monitoring", "deep", "fight"):
        return count // 4
    return 0


def compute_load(cameras: int, modules: List[str]) -> float:
    """Edge qurilmasi uchun shartli hisoblash yuki.

    Har faol kamera bittadan hisoblanadi, modullar esa O'ZI TEGADIGAN
    kameralar soniga ko'paytirilib ustiga qo'shiladi.
    """
    chosen = normalise_modules(modules)
    total = float(max(0, int(cameras)))
    for code in chosen:
        weight = LOAD_WEIGHTS.get(code)
        if weight is None:
            continue
        total += weight * module_cameras(cameras, code)
    return round(total, 2)


def edge_for_load(load: float) -> Optional[Dict[str, Any]]:
    """Yuklama uchun mos qurilma.  `None` — bitta qurilma yetmaydi."""
    for ceiling, name, spec, price in EDGE_CATALOG:
        if load <= ceiling:
            return {
                "name": f"Chaqimchi Edge {name}",
                "spec": spec,
                "price_uzs": price,
                "max_load": ceiling,
            }
    return None


def monthly_price(
    *,
    kind: str,
    people: int,
    cameras: int,
    modules: List[str],
    branches: int = 0,
) -> Dict[str, Any]:
    """Oylik obunani bosqichma-bosqich hisoblaydi.

    Qaytarilgan `breakdown` sahifada ko'rsatiladi: mijoz raqam qayerdan
    kelganini ko'rmasa, unga ishonmaydi va bog'lanmaydi.
    """
    if kind not in INSTITUTIONS:
        raise ValueError(f"Noma'lum muassasa turi: {kind}")

    label, base = INSTITUTIONS[kind]
    chosen = normalise_modules(modules)
    camera_count = max(BASE_INCLUDED_CAMERAS, int(cameras))
    extra_cameras = max(0, camera_count - BASE_INCLUDED_CAMERAS)
    branch_count = max(0, int(branches))

    breakdown: List[Dict[str, Any]] = [
        {"label": f"{label} — bazaviy obuna", "amount_uzs": base}
    ]

    people_fee = person_fee(people)
    if people_fee:
        breakdown.append(
            {
                "label": f"{max(0, people - BASE_INCLUDED_PEOPLE)} kishi (bosqichli)",
                "amount_uzs": people_fee,
            }
        )

    camera_fee = extra_cameras * EXTRA_CAMERA_UZS
    if camera_fee:
        breakdown.append(
            {"label": f"{extra_cameras} ta qo'shimcha AI kamera", "amount_uzs": camera_fee}
        )

    for code in chosen:
        if code == "branch":
            continue
        module_label, price = MODULES[code]
        breakdown.append({"label": module_label, "amount_uzs": price})

    branch_fee = branch_count * MODULES["branch"][1]
    if branch_fee:
        breakdown.append(
            {"label": f"{branch_count} ta qo'shimcha filial", "amount_uzs": branch_fee}
        )

    raw_total = sum(int(row["amount_uzs"]) for row in breakdown)
    total = int(math.ceil(raw_total / ROUND_TO_UZS) * ROUND_TO_UZS)

    load = compute_load(camera_count, chosen)
    return {
        "institution": label,
        "people": max(0, int(people)),
        "cameras": camera_count,
        "modules": chosen,
        "branches": branch_count,
        "breakdown": breakdown,
        "raw_total_uzs": raw_total,
        "monthly_uzs": total,
        "load": load,
        "edge": edge_for_load(load),
    }


def catalog() -> Dict[str, Any]:
    """Sahifaga beriladigan konstantalar.

    Sahifa hisobni O'ZI qiladi (har bosishda so'rov yubormasin), lekin
    RAQAMLAR faqat shu yerdan keladi — ular ikki joyda saqlansa biri
    o'zgarib, ikkinchisi eskirib qolardi.
    """
    return {
        "institutions": [
            {"code": code, "name": name, "base_uzs": price}
            for code, (name, price) in INSTITUTIONS.items()
        ],
        "included": {"people": BASE_INCLUDED_PEOPLE, "cameras": BASE_INCLUDED_CAMERAS},
        "person_bands": [{"up_to": ceiling, "uzs": rate} for ceiling, rate in PERSON_BANDS],
        "camera_table": [
            {"up_to": row[0], "markaz": row[1], "maktab": row[2], "oliygoh": row[3]}
            for row in CAMERA_TABLE
        ],
        "extra_camera_uzs": EXTRA_CAMERA_UZS,
        "modules": [
            {
                "code": code,
                "name": name,
                "uzs": price,
                "load": LOAD_WEIGHTS.get(code, 0.0),
            }
            for code, (name, price) in MODULES.items()
        ],
        "deep_replaces": DEEP_REPLACES,
        "edge_catalog": [
            {"max_load": ceiling, "name": name, "spec": spec, "price_uzs": price}
            for ceiling, name, spec, price in EDGE_CATALOG
        ],
        "round_to_uzs": ROUND_TO_UZS,
        # Sahifa shu izohni ko'rsatadi: narxlar pilot mijozlar bilan
        # tekshirilmagan boshlang'ich model.
        "price_note": "mo'ljal",
    }


__all__ = [
    "CAMERA_TABLE",
    "EDGE_CATALOG",
    "INSTITUTIONS",
    "MODULES",
    "PERSON_BANDS",
    "catalog",
    "compute_load",
    "edge_for_load",
    "estimate_cameras",
    "module_cameras",
    "monthly_price",
    "normalise_modules",
    "person_fee",
]
