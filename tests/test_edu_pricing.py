"""Chaqimchi Edu narx modeli.

Bu yerdagi mezon oddiy: **spec'dagi tayyor hisob-kitob namunalari**.
Ular sotuvchi mijozga aytadigan raqamlar, ya'ni kod ulardan chetga
chiqsa sayt va taklif bir-biriga mos kelmay qoladi.

Ikkinchi mezon — bosqich chegaralari.  Progressiv shkalada eng oson
xato 100/101 va 300/301 chegaralarida bo'ladi: bitta kishi qo'shilishi
bilan hisob sakrab ketsa, mijoz buni adolatsiz deb hisoblaydi.
"""

from __future__ import annotations

import pytest

from chaqimchi_ai.licensing import edu

# ── Odam soni bo'yicha bosqichli narx ────────────────────────────────


def test_the_first_hundred_people_are_included() -> None:
    assert edu.person_fee(100) == 0


def test_the_hundred_and_first_person_costs_one_band_rate() -> None:
    """Bosqichli, tekis emas: 101-kishi qo'shilishi bilan hisob
    70 700 so'mga sakramaydi, faqat 700 so'm qo'shiladi."""
    assert edu.person_fee(101) == 700


def test_each_band_only_charges_the_people_inside_it() -> None:
    """355 kishi = 100 bepul + 200×700 + 55×450."""
    assert edu.person_fee(355) == 200 * 700 + 55 * 450


def test_the_last_band_has_no_ceiling() -> None:
    """3000 dan yuqori har bir kishi 120 so'mdan."""
    below = edu.person_fee(3_000)

    assert edu.person_fee(3_100) == below + 100 * 120


@pytest.mark.parametrize(
    ("people", "expected"),
    [
        (300, 200 * 700),
        (301, 200 * 700 + 450),
        (1_000, 200 * 700 + 700 * 450),
        (1_001, 200 * 700 + 700 * 450 + 250),
    ],
)
def test_the_band_edges_are_smooth(people: int, expected: int) -> None:
    assert edu.person_fee(people) == expected


# ── Kamera taxmini ───────────────────────────────────────────────────


def test_a_university_needs_more_cameras_than_a_course_centre() -> None:
    """Bir xil odam soni, boshqa bino: oliygohda ko'proq kirish
    nuqtasi va auditoriya bor."""
    assert edu.estimate_cameras(500, "oliygoh") > edu.estimate_cameras(500, "markaz")


@pytest.mark.parametrize(
    ("people", "kind", "expected"),
    [
        (150, "maktab", 4),
        (151, "maktab", 6),
        (350, "maktab", 6),
        (351, "maktab", 8),
        (10_000, "oliygoh", 40),
    ],
)
def test_the_camera_table_edges(people: int, kind: str, expected: int) -> None:
    assert edu.estimate_cameras(people, kind) == expected


# ── Modullar ─────────────────────────────────────────────────────────


def test_only_modules_that_exist_in_code_can_be_sold() -> None:
    """Kalkulyatorda narx ko'rsatish — va'da berish bilan teng.

    2026-08-25 auditi: bu ro'yxatda `monitoring`, `deep` va `fight`
    oyiga 129/249/199 ming so'mga sotilib turgan edi, holbuki kodda
    ularning birortasi ham yo'q.  Yangi modulga narx qo'yishdan oldin
    shu test sizni to'xtatadi: avval `PLANNED_MODULES` dan chiqaring,
    ya'ni funksiya rostdan ishlayotganini tasdiqlang.
    """
    assert set(edu.MODULES) == {"faceid", "branch"}
    assert set(edu.MODULES) & set(edu.PLANNED_MODULES) == set()


def test_a_planned_module_cannot_be_bought_even_if_asked_for() -> None:
    """Eski havola yoki saqlangan tanlov narxni oshirib yubormasin."""
    with_planned = edu.monthly_price(
        kind="maktab", people=355, cameras=8, modules=["faceid", "fight", "deep"]
    )
    only_real = edu.monthly_price(kind="maktab", people=355, cameras=8, modules=["faceid"])

    assert with_planned["monthly_uzs"] == only_real["monthly_uzs"]
    assert with_planned["modules"] == ["faceid"]


def test_a_planned_module_does_not_inflate_the_device_quote() -> None:
    """Auditgacha janjal 2.5, chuqur tahlil 2.25 og'irlikda turardi va
    o'ylab topilgan bu raqamlar mijozga 19 490 000 so'mlik qurilmagacha
    tavsiya qildirardi."""
    for code in edu.PLANNED_MODULES:
        assert code not in edu.LOAD_WEIGHTS, code
        assert edu.module_cameras(40, code) == 0, code


def test_only_the_first_two_cameras_are_free() -> None:
    result = edu.monthly_price(kind="markaz", people=50, cameras=5, modules=[])
    labels = " ".join(str(row["label"]) for row in result["breakdown"])

    assert "3 ta qo'shimcha AI kamera" in labels


# ── Yuklama va qurilma ───────────────────────────────────────────────


def test_a_module_does_not_run_on_every_camera() -> None:
    """Bu yuklama hisobidagi eng katta farq.  Face ID faqat kirish
    eshiklarida ishlaydi — sinf kamerasida yuz tanish shart emas va
    u yerdagi burchak buning uchun yaroqsiz ham."""
    assert edu.module_cameras(8, "faceid") == 1
    assert edu.module_cameras(40, "faceid") == 5


def test_there_is_always_at_least_one_entrance() -> None:
    assert edu.module_cameras(2, "faceid") == 1


@pytest.mark.parametrize(
    ("load", "expected"),
    [(4, "Mini"), (4.1, "Lite"), (9, "Lite"), (15, "Plus"), (28, "Pro"), (48, "Max"), (80, "Ultra Max")],
)
def test_each_edge_covers_up_to_its_limit(load: float, expected: str) -> None:
    edge = edu.edge_for_load(load)

    assert edge is not None
    assert edge["name"] == f"Chaqimchi Edge {expected}"


def test_beyond_the_biggest_box_we_propose_several() -> None:
    """Katta kampusda bitta qurilma yetmaydi — "Ultra Max sotamiz"
    deb va'da berish yolg'on bo'lardi."""
    assert edu.edge_for_load(81) is None


# ── Yakuniy hisob ────────────────────────────────────────────────────


def test_the_total_is_rounded_up_to_ten_thousand() -> None:
    """994 750 → 1 000 000.  Pastga yaxlitlash bizning zararimiz,
    tiyinli raqam esa mijozni chalg'itadi."""
    result = edu.monthly_price(kind="maktab", people=355, cameras=8, modules=["faceid"])

    # 199 000 baza + 164 750 (355 kishi) + 174 000 (6 kamera) + 129 000
    assert result["raw_total_uzs"] == 666_750
    assert result["monthly_uzs"] == 670_000


def test_the_breakdown_explains_where_the_number_came_from() -> None:
    """Mijoz raqam qayerdan kelganini ko'rmasa, unga ishonmaydi."""
    result = edu.monthly_price(kind="maktab", people=355, cameras=8, modules=["faceid"])

    assert len(result["breakdown"]) >= 3
    assert sum(int(row["amount_uzs"]) for row in result["breakdown"]) == result["raw_total_uzs"]


def test_an_unknown_institution_is_refused() -> None:
    with pytest.raises(ValueError):
        edu.monthly_price(kind="bogcha", people=100, cameras=2, modules=[])


#: Spec'dagi «Tayyor hisob-kitob namunalari» jadvali.
#:
#: Bular sotuvchi mijozga aytadigan raqamlar — kod ulardan chetga
#: chiqsa, sayt va taklif bir-biriga mos kelmay qoladi.
#:
#: 2026-08-25 da qayta hisoblandi: avvalgi namunalar `monitoring`,
#: `deep` va `fight` modullarini ham qo'shib hisoblardi, ular esa
#: kodda yo'q edi (`PLANNED_MODULES` ga qarang).  Ya'ni eski raqamlar
#: yetkazib berilmaydigan ish uchun pul so'rardi.  Har qatorning
#: hisobi: baza + kishi (bosqichli) + (kamera−2)×29 000 + 129 000
#: (Face ID), 10 000 ga yuqoriga yaxlitlanadi.
SPEC_EXAMPLES = [
    # 149 000 + 22 400 + 0 + 129 000 = 300 400
    ("markaz", 132, 2, ["faceid"], "Mini", 310_000),
    # 149 000 + 66 500 + 58 000 + 129 000 = 402 500
    ("markaz", 195, 4, ["faceid"], "Lite", 410_000),
    # 199 000 + 98 000 + 116 000 + 129 000 = 542 000
    ("maktab", 240, 6, ["faceid"], "Lite", 550_000),
    # 199 000 + 164 750 + 174 000 + 129 000 = 666 750
    ("maktab", 355, 8, ["faceid"], "Plus", 670_000),
    # 199 000 + 248 000 + 174 000 + 129 000 = 750 000
    ("maktab", 540, 8, ["faceid"], "Plus", 750_000),
    # 349 000 + 527 500 + 406 000 + 129 000 = 1 411 500
    ("oliygoh", 1_290, 16, ["faceid"], "Pro", 1_420_000),
    # 349 000 + 950 000 + 638 000 + 129 000 = 2 066 000
    ("oliygoh", 2_980, 24, ["faceid"], "Pro", 2_070_000),
    # 349 000 + 1 417 000 + 1 102 000 + 129 000 = 2 997 000
    ("oliygoh", 6_850, 40, ["faceid"], "Max", 3_000_000),
]


@pytest.mark.parametrize(("kind", "people", "cameras", "modules", "edge", "price"), SPEC_EXAMPLES)
def test_the_published_examples_still_hold(
    kind: str, people: int, cameras: int, modules: list, edge: str, price: int
) -> None:
    result = edu.monthly_price(kind=kind, people=people, cameras=cameras, modules=modules)

    assert result["monthly_uzs"] == price
    if edge is None:
        assert result["edge"] is None
    else:
        assert result["edge"]["name"] == f"Chaqimchi Edge {edge}"


# ── Sahifaga beriladigan katalog ─────────────────────────────────────


def test_the_catalog_carries_every_number_the_page_needs() -> None:
    """Sahifa hisobni o'zi qiladi, lekin RAQAMLAR faqat shu yerdan
    keladi — ular ikki joyda saqlansa biri eskirib qolardi."""
    data = edu.catalog()

    for key in (
        "institutions",
        "included",
        "person_bands",
        "camera_table",
        "extra_camera_uzs",
        "modules",
        "planned_modules",
        "deep_replaces",
        "edge_catalog",
        "round_to_uzs",
    ):
        assert key in data, key


def test_the_catalog_never_puts_a_price_on_a_planned_module() -> None:
    """Sahifa narxni faqat shu yerdan oladi.  Rejadagi modulda `uzs`
    maydoni bo'lsa, kalkulyator uni sotib yuborardi."""
    data = edu.catalog()

    assert [mod["code"] for mod in data["modules"]] == ["faceid", "branch"]
    for mod in data["planned_modules"]:
        assert set(mod) == {"code", "name"}, mod


def test_the_catalog_leaks_no_cost_or_margin() -> None:
    """Do'kon katalogida tannarx bor va u ommaviy javobga chiqmaydi;
    Edu'da ham shu qoida saqlanadi."""
    text = str(edu.catalog())

    assert "cost" not in text
    assert "margin" not in text
