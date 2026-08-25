"""Tariflar va texnik cheklovlar."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Literal

from chaqimchi_ai.sotqin_profile import GUARANTEED_CAMERAS, MAX_CAMERAS

PlanTier = Literal[
    # ── Sotiladigan tariflar (2026-08-21) ────────────────────────────────
    #
    # Farq ikki o'lchovda: kamera soni VA funksiya to'plami.  Faqat kamera
    # bo'yicha bo'lsa kichik do'kon 2 kameraga rozi bo'lib qoladi va hech
    # qachon o'smaydi; faqat funksiya bo'yicha bo'lsa katta do'kon arzon
    # tarifda 4 kamera ishlatib ketaveradi.
    #
    # Uchinchi "tarif" — Tarmoq — bu yerda YO'Q va ataylab yo'q: u
    # ma'lumotlar bazasida alohida tarif emas, har do'kon o'zining `biznes`
    # obyekti sifatida ochiladi.  Aks holda narxsiz tarifga
    # `create_invoice` 0 so'mlik hisob-faktura yozib qo'yardi.
    "boshlangich",
    "biznes",
    # Eski nom — `biznes` ning cheklovlari, lekin narxi $20.  Yangi obyektga
    # berilmaydi (`SELLABLE_PLANS` da yo'q), lekin `PLANS` da QOLADI:
    # mavjud mijozlarni `biznes` ga ko'chirish ular uchun jimgina narx
    # ko'tarish bo'lardi ($20 → $23), holbuki sayt ularga $20 va'da qilgan.
    # Ular tarifni yangilashda, roziligi bilan ko'chiriladi.
    "lite",
    # Kamera bo'yicha — do'kon, ombor, ofis xavfsizligi
    "starter",
    "business",
    "enterprise",
    # Xodim bo'yicha — davomat. Qiymat kamera sonida emas, xodim sonida:
    # 200 xodimli zavodga 2 kamera yetadi, lekin 200 ta yuz kerak.
    "staff_starter",
    "staff_business",
    "staff_enterprise",
]

# Sotqin platforma bazasi; AI funksiyalar kamera bo'yicha ustiga qo'shiladi.
LITE_MONTHLY_PRICE_USD_CENTS = 2_000
DEFAULT_USD_RATE_UZS = 13_000

# ── Sotiladigan tariflarning narxi ───────────────────────────────────────
#
# Narx dollarda saqlanadi, so'mga `uzs_from_cents()` o'giradi.
BOSHLANGICH_MONTHLY_PRICE_USD_CENTS = 1_140
BIZNES_MONTHLY_PRICE_USD_CENTS = 2_300

#: So'm summasi shu qadamga yaxlitlanadi — YUQORIGA.
#:
#: Sababi amaliy: sent × kurs / 100 formulasi standart kursda sent × 130
#: beradi, ya'ni so'mdagi natija faqat butun dollarda yumaloq chiqadi.
#: Yaxlitlashsiz "148 200 so'm" degan narx chiqardi va do'kon egasiga
#: nimadir yashiringandek tuyulardi.  YUQORIGA — chunki `+99 // 100` ham
#: shunday ishlaydi: hisob-faktura hech qachon kamayib ketmasin.
#:
#: Mavjud narxlarning hammasi allaqachon mingga karrali ($20 → 260 000,
#: funksiyalar 39/65/78/104 ming), shuning uchun bu qadam ularni
#: o'zgartirmaydi.
UZS_ROUNDING_STEP = 1_000


def usd_rate_uzs() -> int:
    """Hisob-faktura uchun USD/UZS kursi.

    Lite narxi USD'da qat'iy ($20), Payme/Click esa UZS qabul qiladi. Kurs
    serverda boshqariladi va hisob ochilgan paytdagi UZS summa invoice ichida
    saqlanib qoladi. Tashqi kurs servisiga runtime bog'liqlik ataylab yo'q.
    """
    raw = os.environ.get("CHAQIMCHI_USD_RATE_UZS", "").strip()
    if not raw:
        return DEFAULT_USD_RATE_UZS
    try:
        rate = int(raw)
    except ValueError as exc:
        raise ValueError("CHAQIMCHI_USD_RATE_UZS butun son bo'lishi kerak") from exc
    if not 1_000 <= rate <= 100_000:
        raise ValueError("CHAQIMCHI_USD_RATE_UZS 1000–100000 oralig'ida bo'lishi kerak")
    return rate


def uzs_from_cents(cents: int) -> int:
    """Sentdagi narxni so'mga o'giradi va mingga yuqoriga yaxlitlaydi.

    Bitta joyda turishi shart: sayt, tarif kartasi va hisob-faktura shu
    funksiyani chaqiradi.  Ilgari formula `site.js` da qaytadan yozilgan
    edi va ikki joyda bir-biridan uzoqlashib ketish xavfi bor edi.
    """
    raw = (int(cents) * usd_rate_uzs() + 99) // 100
    return -(-raw // UZS_ROUNDING_STEP) * UZS_ROUNDING_STEP


@dataclass(frozen=True)
class PlanBullet:
    """Tarif kartasidagi bitta punkt.

    Ilgari bu oddiy satr edi va kartada oltita uzun jumla turardi —
    do'kon egasi ularni o'qimay, faqat narxga qarab qaror qilardi.
    Endi kartada FAQAT `label` (2-3 so'z) ko'rinadi, qolgani bosilganda
    ochiladi.

    `example` alohida maydon: umumiy ta'rifdan ko'ra aniq misol tez
    tushuniladi ("kassa oldida 3 barobar ko'p turishadi").
    """

    #: `cloud/static/icons.svg` dagi symbol id.
    icon: str
    #: 2-3 so'z — kartada doim ko'rinadi.
    label: str
    #: 1-2 gap: nima qiladi.
    detail: str = ""
    #: Aniq misol.  Bo'sh bo'lishi mumkin.
    example: str = ""

    @property
    def summary(self) -> str:
        """JS'siz ko'rinadigan bitta satr (`noscript`, panel, bot)."""
        return f"{self.label} — {self.detail}" if self.detail else self.label


@dataclass(frozen=True)
class PlanLimits:
    max_cameras: int
    max_persons: int
    retention_days: int
    telegram_allowed: bool
    #: Kamera tariflarida — aniq narx. Xodim tariflarida — eng kam narx
    #: ("... dan boshlab"). Aniq summa `monthly_price()` dan olinadi.
    monthly_price_uzs: int
    install_price_uzs: int
    #: Har bir xodim uchun narx. 0 — tarif kamera bo'yicha.
    price_per_person_uzs: int = 0
    #: USD'da sotiladigan tarif uchun sentdagi qat'iy narx. 0 — faqat UZS.
    monthly_price_usd_cents: int = 0
    #: Mijozga ko'rinadigan nom.  Bitta mahsulotning bitta ismi bo'lsin:
    #: `lite` bazada shu nom bilan qolsa ham, panelda "Biznes" deb ko'rinadi.
    display_name: str = ""
    #: Qurilma ishga tushiradigan funksiya kodlari
    #: (`cloud/store.py: DEFAULT_FEATURES`).  `/api/v1/edge/config` shu
    #: ro'yxatni yuboradi, qurilmada `retail_event_filter` uni hodisa
    #: turlariga aylantiradi.
    edge_features: tuple[str, ...] = ()
    #: Mijoz panelida ochiladigan bo'limlar.  Narxlanmaydi — faqat
    #: ko'rinadi yoki qulflangan holatda turadi.
    panel_features: tuple[str, ...] = ()
    #: Tarif kartasidagi punktlar.  Sayt ham, panel ham shu ro'yxatni
    #: o'qiydi — matn ikki joyda yozilib, bir-biridan uzoqlashmasin.
    bullets: tuple[PlanBullet, ...] = ()
    #: Yangi sotuvda taklif qilinmaydi, lekin hisob-kitob to'liq ishlaydi.
    legacy: bool = False

    @property
    def includes(self) -> tuple[str, ...]:
        """Tekis matnli ro'yxat — `bullets` dan HOSILA.

        Ikki ro'yxat qo'lda yuritilsa ular albatta uzoqlashadi: biri
        yangilanadi, ikkinchisi unutiladi va sayt bir narsani, panel
        boshqasini aytadi.  Shu sabab manba bitta.
        """
        return tuple(bullet.summary for bullet in self.bullets)

    @property
    def is_per_person(self) -> bool:
        return self.price_per_person_uzs > 0

    @property
    def monthly_price_usd(self) -> float:
        return self.monthly_price_usd_cents / 100

    def monthly_price(self, persons: int = 0) -> int:
        """Oylik to‘lov.

        Xodim tarifida: eng kam narx yoki `xodim × narx` — qaysi biri katta.
        Kamera tarifida `persons` e’tiborga olinmaydi.
        """
        if self.monthly_price_usd_cents:
            return uzs_from_cents(self.monthly_price_usd_cents)
        if not self.is_per_person:
            return self.monthly_price_uzs
        return max(self.monthly_price_uzs, self.price_per_person_uzs * max(0, persons))

    def effective_max_persons(self, persons: int = 0) -> int:
        """Bazaga necha kishi sig‘adi.

        Xodim tarifida mijoz nechta xodim uchun to‘lasa, shuncha qo‘sha oladi —
        101-chisini qo‘shmoqchi bo‘lsa tarifni kengaytirishi kerak. Tijorat
        mantiqi va texnik cheklov shu yerda bir joyga keladi.
        """
        if not self.is_per_person:
            return self.max_persons
        return max(0, persons) or self.max_persons


# ── Tarifga kiradigan qurilma funksiyalari ──────────────────────────────
#
# `davomat` bu ro'yxatlarda ATAYLAB yo'q va tarif kartasida ham
# ko'rinmaydi.  U `cloud/main.py` `_attendance_enabled()` bilan alohida
# boshqariladi — faqat `CHAQIMCHI_ATTENDANCE_PILOT` qo'yilgan serverda.
#
# Sabab endi litsenziya EMAS (modellar 2026-08-21 dan Apache-2.0,
# `cloud/faces.py`), balki ikkita ochiq band:
#   1. biometrik ma'lumot Yevropadagi serverda saqlanadi va bu
#      O'zbekiston talablariga mos kelishi yurist bilan tasdiqlanmagan;
#   2. yuz moslash aniqligi haqiqiy do'kon kadrlarida o'lchanmagan.
# Ikkalasi yopilgach shu yerga qo'shiladi — `docs/AUDIT_TAHLIL.md`
# KRITIK-2 va YUQORI-1.
#
# Bungacha karta ham buni SOTMASLIGI kerak: 2026-08-25 gacha Biznes
# kartasida "Xodim davomati — 10 xodimgacha, yuz orqali" bulleti
# turardi, `BIZNES_EDGE_FEATURES` esa uni bermasdi.
BOSHLANGICH_EDGE_FEATURES = ("person_count",)
BIZNES_EDGE_FEATURES = ("person_count", "queue_length", "store_security")

#: Biznes tarifidagi panel bo'limlari.  `boshlangich` da yo'qlari
#: qulflangan holatda ko'rinadi — yo'qolib qolgan bo'lim mijozga
#: "buzilibdi" degan taassurot beradi, qulf esa "ko'tarish mumkin".
BIZNES_PANEL_FEATURES = (
    "bugun",
    "hisobot",
    "telegram",
    "navbat",
    "xavfsizlik",
    "xarita",
    "demografiya",
)
BOSHLANGICH_PANEL_FEATURES = ("bugun", "hisobot", "telegram")

#: Boshlang'ich tarifidagi punktlar.
#:
#: Har punkt uch qismdan: kartada ko'rinadigan qisqa nom, bosilganda
#: ochiladigan izoh va ANIQ MISOL.  Misol ataylab: "kirish-chiqish
#: sanog'i" degan ta'rif do'kon egasiga hech narsa aytmaydi, "shanba
#: 18:00 da 41 kishi kirgan" esa darrov tushunarli.
BOSHLANGICH_BULLETS = (
    PlanBullet(
        icon="kamera",
        label="2 kameragacha",
        detail="Bitta do'konda ikkita kamera ulanadi.",
        example="Odatda: kirish eshigi va savdo zali.",
    ),
    PlanBullet(
        icon="odamlar",
        label="Kirish-chiqish sanog'i",
        detail="Nechta odam kirdi va chiqdi — soat bo'yicha. Do'konda hozir "
               "nechta odam borligi ham ko'rinadi.",
        example="Masalan: shanba kuni 18:00 da 41 kishi kirgan.",
    ),
    PlanBullet(
        icon="soat",
        label="Kunlik hisobot",
        detail="Har kuni kechqurun Telegramga o'sha kunning xulosasi keladi.",
        example="\u00abBugun 268 kishi kirdi, eng gavjum soat 18:00\u00bb.",
    ),
    PlanBullet(
        icon="qalqon",
        label="Kamera nazorati",
        detail="Kamera o'chsa yoki tasvir qotib qolsa darhol xabar beriladi.",
        example="Tunda kabel uzilsa — ertalab emas, o'sha zahoti bilasiz.",
    ),
    PlanBullet(
        icon="quti",
        label="Arxiv 30 kun",
        detail="Aniqlangan hodisalar va kunlik raqamlar 30 kun saqlanadi.",
        example="O'tgan oyning eng gavjum kunini solishtira olasiz.",
    ),
    PlanBullet(
        icon="yuklash",
        label="Avtomatik yangilanish",
        detail="Dastur imzolangan yangilanishni o'zi oladi — siz hech narsa "
               "o'rnatmaysiz.",
    ),
)

BIZNES_BULLETS = (
    PlanBullet(
        icon="kamera",
        label="4 kameragacha",
        detail="Bitta do'konda to'rtta kamera.",
        example="Kirish, kassa, savdo zali va ombor.",
    ),
    PlanBullet(
        icon="dokon",
        label="Boshlang'ichdagi hammasi",
        detail="Sanoq, kunlik hisobot, kamera nazorati va Telegram xabarlari.",
    ),
    PlanBullet(
        icon="navbat",
        label="Kassa navbati",
        detail="Kassada nechta odam turgani o'lchanadi; navbat uzayganda "
               "xabar keladi.",
        example="\u00abNavbatda 7 kishi \u2014 ikkinchi kassani oching\u00bb.",
    ),
    PlanBullet(
        icon="qalqon",
        label="Xavfsizlik signallari",
        detail="Ish vaqtidan tashqari harakat, taqiqlangan zonaga kirish va "
               "kamera buzilishi.",
        example="Do'kon yopiq, kamera esa odamni ko'rdi — telefon jiringlaydi.",
    ),
    PlanBullet(
        icon="xarita",
        label="Do'kon issiqlik xaritasi",
        detail="Mijozlar do'konning qaysi joyida ko'p turishini ko'rasiz — "
               "javonni shunga qarab joylashtirasiz.",
        example="Kirish yo'lagida ko'p, burchakda deyarli hech kim yo'q.",
    ),
    PlanBullet(
        icon="portret",
        label="Mijoz portreti",
        detail="Mijozlarning taxminiy yoshi va jinsi. Anonim baho: rasm "
               "saqlanmaydi.",
        example="Xaridorlarning 58% ayol, asosiy yosh guruhi 18-30.",
    ),
    PlanBullet(
        icon="yuklash",
        label="Avtomatik yangilanish",
        detail="Dastur imzolangan yangilanishni o'zi oladi.",
    ),
)

PLANS: Dict[PlanTier, PlanLimits] = {
    "boshlangich": PlanLimits(
        # Kichik do'kon uchun kirish nuqtasi: kirish eshigi + savdo zali.
        max_cameras=2,
        # Xodim davomati bu tarifda yo'q.  Nol — "cheksiz" emas, "umuman
        # yo'q": `_check_employee_limit` xodim qo'shishga yo'l bermaydi.
        max_persons=0,
        retention_days=30,
        telegram_allowed=True,
        monthly_price_uzs=BOSHLANGICH_MONTHLY_PRICE_USD_CENTS * DEFAULT_USD_RATE_UZS // 100,
        install_price_uzs=0,
        monthly_price_usd_cents=BOSHLANGICH_MONTHLY_PRICE_USD_CENTS,
        display_name="Boshlang'ich",
        edge_features=BOSHLANGICH_EDGE_FEATURES,
        panel_features=BOSHLANGICH_PANEL_FEATURES,
        bullets=BOSHLANGICH_BULLETS,
    ),
    "biznes": PlanLimits(
        # Asosiy tarif — `lite` ning aynan cheklovlari, narxi $20 → $23.
        max_cameras=GUARANTEED_CAMERAS,
        max_persons=10,
        retention_days=30,
        telegram_allowed=True,
        monthly_price_uzs=BIZNES_MONTHLY_PRICE_USD_CENTS * DEFAULT_USD_RATE_UZS // 100,
        install_price_uzs=0,
        monthly_price_usd_cents=BIZNES_MONTHLY_PRICE_USD_CENTS,
        display_name="Biznes",
        edge_features=BIZNES_EDGE_FEATURES,
        panel_features=BIZNES_PANEL_FEATURES,
        bullets=BIZNES_BULLETS,
    ),
    "lite": PlanLimits(
        # 8 kamera apparat maksimumi, ammo sotiladigan SLA hozir 4 kamera.
        max_cameras=GUARANTEED_CAMERAS,
        # Xodim davomati (Face ID) Lite ichida, tekin.  10 — ataylab
        # kichik: bitta do'konda shuncha xodim bo'ladi va har xodimning
        # embeddingi har yuz kadrida qayta deshifrlanadi, ya'ni son
        # o'sishi bilan tanish narxi ham o'sadi.  Ilgari bu yerda 200
        # turardi va hech qayerda majburlanmasdi.
        max_persons=10,
        retention_days=30,
        telegram_allowed=True,
        # Faqat fallback/display qiymat; amaldagi invoice `monthly_price()`
        # orqali CHAQIMCHI_USD_RATE_UZS bilan hisoblanadi.
        monthly_price_uzs=LITE_MONTHLY_PRICE_USD_CENTS * DEFAULT_USD_RATE_UZS // 100,
        # Sotqin, NVR/kameralar va montaj alohida smeta qilinadi.
        install_price_uzs=0,
        monthly_price_usd_cents=LITE_MONTHLY_PRICE_USD_CENTS,
        # Panelda "Biznes" deb ko'rinadi — mijoz uchun bu o'sha tarif,
        # faqat eski narxda.  Funksiyalar `biznes` bilan AYNAN bir xil:
        # sotuvdan chiqarilgani mavjud mijozning qurilmasidan funksiya
        # olib qo'ymasligi kerak.
        display_name="Biznes (2026-08 narxi)",
        edge_features=BIZNES_EDGE_FEATURES,
        panel_features=BIZNES_PANEL_FEATURES,
        bullets=BIZNES_BULLETS,
        legacy=True,
    ),
    "starter": PlanLimits(
        max_cameras=1,
        max_persons=50,
        retention_days=30,
        telegram_allowed=False,
        monthly_price_uzs=790_000,
        install_price_uzs=6_500_000,
        # Eski tarif.  Panelda hammasi ochiq: sotuvdan chiqarish mavjud
        # mijozdan ko'rinadigan bo'lim olib qo'ymasin (xarita ma'lumoti
        # jimgina yo'qolib qolardi).
        #
        # `edge_features` esa ataylab BO'SH: bu tariflar shartnoma
        # bo'yicha, `site_feature_assignments` orqali boshqariladi.
        panel_features=BIZNES_PANEL_FEATURES,
        legacy=True,
    ),
    "business": PlanLimits(
        max_cameras=3,
        max_persons=200,
        retention_days=90,
        telegram_allowed=True,
        monthly_price_uzs=1_490_000,
        install_price_uzs=9_500_000,
        # Eski tarif.  Panelda hammasi ochiq: sotuvdan chiqarish mavjud
        # mijozdan ko'rinadigan bo'lim olib qo'ymasin (xarita ma'lumoti
        # jimgina yo'qolib qolardi).
        #
        # `edge_features` esa ataylab BO'SH: bu tariflar shartnoma
        # bo'yicha, `site_feature_assignments` orqali boshqariladi.
        panel_features=BIZNES_PANEL_FEATURES,
        legacy=True,
    ),
    "enterprise": PlanLimits(
        max_cameras=8,
        max_persons=2000,
        retention_days=365,
        telegram_allowed=True,
        monthly_price_uzs=2_990_000,
        install_price_uzs=15_000_000,
        # Eski tarif.  Panelda hammasi ochiq: sotuvdan chiqarish mavjud
        # mijozdan ko'rinadigan bo'lim olib qo'ymasin (xarita ma'lumoti
        # jimgina yo'qolib qolardi).
        #
        # `edge_features` esa ataylab BO'SH: bu tariflar shartnoma
        # bo'yicha, `site_feature_assignments` orqali boshqariladi.
        panel_features=BIZNES_PANEL_FEATURES,
        legacy=True,
    ),
    # ── Davomat tariflari (xodim bo'yicha) ────────────────────────────────
    #
    # Katta tarifda xodim arzonroq — shuning uchun mijoz o'sganda ko'tarilishni
    # o'zi so'raydi: 100 xodimda Business, 300 xodimda Enterprise arzonroq.
    "staff_starter": PlanLimits(
        max_cameras=2,
        max_persons=100,  # `persons` berilmasa shu ishlaydi
        retention_days=30,
        telegram_allowed=True,
        monthly_price_uzs=500_000,  # eng kam
        install_price_uzs=6_500_000,
        price_per_person_uzs=15_000,
        # Eski tarif.  Panelda hammasi ochiq: sotuvdan chiqarish mavjud
        # mijozdan ko'rinadigan bo'lim olib qo'ymasin (xarita ma'lumoti
        # jimgina yo'qolib qolardi).
        #
        # `edge_features` esa ataylab BO'SH: bu tariflar shartnoma
        # bo'yicha, `site_feature_assignments` orqali boshqariladi.
        panel_features=BIZNES_PANEL_FEATURES,
        legacy=True,
    ),
    "staff_business": PlanLimits(
        max_cameras=5,
        max_persons=300,
        retention_days=90,
        telegram_allowed=True,
        monthly_price_uzs=1_200_000,
        install_price_uzs=9_500_000,
        price_per_person_uzs=12_000,
        # Eski tarif.  Panelda hammasi ochiq: sotuvdan chiqarish mavjud
        # mijozdan ko'rinadigan bo'lim olib qo'ymasin (xarita ma'lumoti
        # jimgina yo'qolib qolardi).
        #
        # `edge_features` esa ataylab BO'SH: bu tariflar shartnoma
        # bo'yicha, `site_feature_assignments` orqali boshqariladi.
        panel_features=BIZNES_PANEL_FEATURES,
        legacy=True,
    ),
    "staff_enterprise": PlanLimits(
        max_cameras=MAX_CAMERAS,
        max_persons=2000,
        retention_days=365,
        telegram_allowed=True,
        monthly_price_uzs=2_500_000,
        install_price_uzs=15_000_000,
        price_per_person_uzs=9_000,
        # Eski tarif.  Panelda hammasi ochiq: sotuvdan chiqarish mavjud
        # mijozdan ko'rinadigan bo'lim olib qo'ymasin (xarita ma'lumoti
        # jimgina yo'qolib qolardi).
        #
        # `edge_features` esa ataylab BO'SH: bu tariflar shartnoma
        # bo'yicha, `site_feature_assignments` orqali boshqariladi.
        panel_features=BIZNES_PANEL_FEATURES,
        legacy=True,
    ),
}


def cheapest_plan_for(persons: int) -> tuple[str, int]:
    """Shu xodim soniga eng arzon davomat tarifi. (tarif, oylik narx)

    Sotuvchi qo‘lda hisoblamasin — noto‘g‘ri tarif taklif qilish oson.
    """
    options = [
        (name, limits.monthly_price(persons))
        for name, limits in PLANS.items()
        if limits.is_per_person and persons <= limits.max_persons
    ]
    if not options:
        return "staff_enterprise", PLANS["staff_enterprise"].monthly_price(persons)
    return min(options, key=lambda x: x[1])


#: Hozir **sotiladigan** tariflar.
#:
#: `PLANS` dagi qolganlari (kamera bo'yicha starter/business/enterprise va
#: xodim bo'yicha staff_*) `docs/DOKON_MVP.md` bo'yicha sotilmaydi, lekin
#: kod va hisob-kitob mantiqidan olib tashlanmagan: mavjud yozuvlar va
#: hisob-fakturalar ular orqali hisoblanadi.  Yangi obyekt yaratishda
#: sotuvchiga faqat shu ro'yxat ko'rsatiladi — aks holda panelda sotilmaydigan
#: tarifni tanlash mumkin bo'lib qolardi.
SELLABLE_PLANS: frozenset[str] = frozenset({"boshlangich", "biznes"})


def plan_feature_codes(plan: str) -> tuple[str, ...]:
    """Tarifga kiradigan qurilma funksiyalari.

    Funksiya berish qarorida `is_sellable()` O'RNIGA shu ishlatiladi.
    Sabab jiddiy: `lite` sotuvdan chiqarilgach `is_sellable("lite")` False
    bo'ladi va shu tekshiruvga tayangan joy (`/api/v1/edge/config` zaxira
    mantiqi) MAVJUD to'lovchi mijozning qurilmasidan hamma funksiyani
    jimgina olib qo'yardi — do'kon nazoratsiz qolardi va hech qanday xato
    chiqmasdi.
    """
    limits = PLANS.get(plan.lower().strip())  # type: ignore[arg-type]
    return limits.edge_features if limits else ()


def plan_display_name(plan: str) -> str:
    """Mijozga ko'rsatiladigan tarif nomi."""
    limits = PLANS.get(plan.lower().strip())  # type: ignore[arg-type]
    if limits and limits.display_name:
        return limits.display_name
    return plan


def is_sellable(plan: str) -> bool:
    return plan.lower().strip() in SELLABLE_PLANS


def get_plan(plan: str) -> PlanLimits:
    key = plan.lower().strip()
    if key not in PLANS:
        raise ValueError(f"Noma'lum tarif: {plan}. Qabul: {list(PLANS)}")
    return PLANS[key]  # type: ignore[index]
