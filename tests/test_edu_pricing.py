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


def test_deep_analysis_replaces_the_plain_lesson_module() -> None:
    """Ikkalasi birga hisoblansa, mijoz bir xil ish uchun ikki marta
    to'lardi."""
    chosen = edu.normalise_modules(["faceid", "monitoring", "deep"])

    assert "deep" in chosen
    assert "monitoring" not in chosen


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
    assert edu.module_cameras(8, "monitoring") == 2
    assert edu.module_cameras(8, "fight") == 2


def test_there_is_always_at_least_one_entrance() -> None:
    assert edu.module_cameras(2, "faceid") == 1


def test_fight_detection_is_the_heaviest_module() -> None:
    """U bitta suratni emas, bir necha kadrdan iborat vaqt
    ketma-ketligini tahlil qiladi."""
    assert edu.LOAD_WEIGHTS["fight"] > edu.LOAD_WEIGHTS["faceid"]
    assert edu.LOAD_WEIGHTS["faceid"] > edu.LOAD_WEIGHTS["monitoring"]


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
    result = edu.monthly_price(
        kind="maktab", people=355, cameras=8, modules=["faceid", "monitoring", "fight"]
    )

    assert result["raw_total_uzs"] == 994_750
    assert result["monthly_uzs"] == 1_000_000


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
SPEC_EXAMPLES = [
    ("markaz", 132, 2, ["faceid"], "Mini", 310_000),
    ("markaz", 195, 4, ["faceid", "monitoring"], "Lite", 540_000),
    ("maktab", 240, 6, ["faceid", "monitoring"], "Lite", 680_000),
    ("maktab", 355, 8, ["faceid", "monitoring", "fight"], "Pro", 1_000_000),
    ("maktab", 540, 8, ["faceid", "monitoring", "fight"], "Pro", 1_080_000),
    ("oliygoh", 1_290, 16, ["faceid", "monitoring", "fight"], "Max", 1_740_000),
    ("oliygoh", 2_980, 24, ["faceid", "deep", "fight"], "Ultra Max", 2_520_000),
    ("oliygoh", 6_850, 40, ["faceid", "deep", "fight"], None, 3_450_000),
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
        "deep_replaces",
        "edge_catalog",
        "round_to_uzs",
    ):
        assert key in data, key


def test_the_catalog_leaks_no_cost_or_margin() -> None:
    """Do'kon katalogida tannarx bor va u ommaviy javobga chiqmaydi;
    Edu'da ham shu qoida saqlanadi."""
    text = str(edu.catalog())

    assert "cost" not in text
    assert "margin" not in text
