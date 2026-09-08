"""Raqamlarni so'mga aylantirish — mahsulot nima turishini ko'rsatadi.

Do'kon egasi 299 000 so'm to'laydi va evaziga raqam ko'radi: "navbat
5 marta uzun bo'ldi".  Bu unga NIMA turishini aytmaydi.  Mahsulotni
"yoqimli"dan "kerakli"ga o'tkazadigan narsa — o'sha raqamning pulga
tarjimasi.

## Uchta qoida

**1. Taxmin ekani OCHIQ aytiladi.**  Aniq raqam da'vo qilsak, mijoz
uni bir marta tekshiradi, to'g'ri kelmaydi va butun mahsulotga ishonchi
yo'qoladi.  "Taxminan" deb aytilgan raqam esa ishonch qozonadi.

**2. Hisob MIJOZNING O'Z raqamlaridan chiqadi.**  O'rtacha chek
o'ylab topilmaydi: mijoz kunlik savdosini aytadi, biz esa uni O'SHA
KUNGI haqiqiy tashrif soniga bo'lamiz.  Ya'ni "har mijoz o'rtacha
X so'm olib keladi" — bu bizning taxminimiz emas, uning o'z hisobi.

**3. Mijoz savdosini aytmagan bo'lsa — pul qatori UMUMAN chiqmaydi.**
Standart qiymat bilan to'ldirish (masalan "o'rtacha do'kon 5 mln
qiladi") — o'ylab topilgan raqamni haqiqat sifatida ko'rsatish.

## Navbat epizodi nima

`queue_threshold_exceeded` **latch** bilan chiqadi
(`scene_analytics.py`): navbat mijozning o'z chegarasidan oshganda
bir marta, keyin navbat tarqalmaguncha qayta chiqmaydi.  Ya'ni har
hodisa — bitta alohida "uzun navbat epizodi".

Epizod QANCHA DAVOM ETGANI hozir o'lchanmaydi: qurilma navbat
tarqalganini bildirmaydi (`ended_at` to'ldirilmaydi).  Shuning uchun
hisob epizod SONIGA tayanadi, davomiylikka emas.  Davomiylik qurilma
relizidan keyin qo'shilsa, taxmin aniqlashadi.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from cloud import botfmt, i18n
from cloud.i18n import tg

#: Hisob ishonchli bo'lishi uchun oraliqda kamida shuncha tashrif kerak.
#:
#: Kam sonda o'rtacha ma'nosini yo'qotadi va bitta chetlanish butun
#: raqamni buzadi.
MIN_VISITORS_FOR_ESTIMATE = 30

#: Bitta tashrif shundan ko'p olib keladi deyish — deyarli har doim
#: SANOQ buzilganini bildiradi, do'konning boyligini emas.
#:
#: Jonli ma'lumotda ushlandi: pilot do'konda chiziq noto'g'ri sozlangani
#: uchun oyiga atigi 26 tashrif sanalgan.  4.5 mln kunlik savdo bilan
#: hisob "har tashrif 5.4 mln so'm" va "64 mln so'm yo'qotildi" chiqardi.
#: Bunday raqam mahsulotga bo'lgan ishonchni bir zumda yo'q qiladi.
MAX_PLAUSIBLE_PER_VISITOR_UZS = 1_000_000

#: Bitta uzun navbat epizodida taxminan shuncha mijoz kutmasdan ketadi.
#:
#: Ataylab EHTIYOTKOR (1 kishi).  Haqiqiy son ko'proq bo'lishi mumkin,
#: lekin kam baholangan raqamni mijoz "bo'lishi mumkin" deb qabul
#: qiladi; oshirib yuborilgani esa butun hisobga shubha uyg'otadi.
CUSTOMERS_LOST_PER_QUEUE_EPISODE = 1


def revenue_per_visitor(*, daily_revenue_uzs: int, visitors: int) -> Optional[int]:
    """Bitta tashrif o'rtacha qancha so'm olib keladi.

    Mijozning aytgan kunlik savdosi / o'sha kungi haqiqiy tashrif soni.
    Ikkalasidan biri yo'q bo'lsa — javob ham yo'q.
    """
    if daily_revenue_uzs <= 0 or visitors < MIN_VISITORS_FOR_ESTIMATE:
        return None
    per_visitor = round(daily_revenue_uzs / visitors)
    # Ishonchsiz natijani KO'RSATMAYMIZ.  Bu yerga tushish deyarli har
    # doim kirish chizig'i noto'g'ri sozlanganini bildiradi — u holda
    # to'g'ri javob "hisoblab bo'lmadi", taxminiy raqam emas.
    if per_visitor > MAX_PLAUSIBLE_PER_VISITOR_UZS:
        return None
    return per_visitor


def queue_cost(
    *,
    queue_episodes: int,
    daily_revenue_uzs: int,
    visitors: int,
) -> Optional[Dict[str, Any]]:
    """Uzun navbat taxminan qancha savdoni olib ketdi.

    `None` — hisoblab bo'lmaydi (savdo aytilmagan, tashrif yo'q yoki
    navbat umuman uzun bo'lmagan).
    """
    if queue_episodes <= 0:
        return None
    per_visitor = revenue_per_visitor(daily_revenue_uzs=daily_revenue_uzs, visitors=visitors)
    if per_visitor is None:
        return None
    lost = queue_episodes * CUSTOMERS_LOST_PER_QUEUE_EPISODE
    return {
        "episodes": queue_episodes,
        "lost_customers": lost,
        "per_visitor_uzs": per_visitor,
        "lost_uzs": lost * per_visitor,
    }


#: Konversiya foizi shundan kam kirishda KO'RSATILMAYDI.
#:
#: 3 kishi kirib 2 tasi sotib olsa «67% konversiya» chiqadi — bu o'lchov
#: emas, tasodif.  Kam namunada faqat SONLAR ko'rsatiladi (🚻 qatori va
#: `trust_score` shu intizomga bo'ysunadi).
MIN_VISITORS_FOR_CONVERSION = 20


def conversion(*, receipts: Optional[int], entered: int) -> Optional[Dict[str, Any]]:
    """«200 kirdi → 100 chek»: nechta tashrif xaridga aylandi.

    `None` — egasi chek sonini KIRITMAGAN.  Nol qaytarish yolg'on
    bo'lardi: nol «hech kim sotib olmadi» degani, kiritilmagan kun esa
    «ma'lumot yo'q».

    `percent = None` — namuna kichik yoki sanoq ishonchsiz.
    """
    if receipts is None:
        return None
    receipts = max(0, int(receipts))
    entered = max(0, int(entered))
    percent: Optional[int] = None
    # Chek kirganlardan KO'P bo'lishi — do'kon boy ekanini emas, sanoq
    # buzilganini bildiradi (chiziq noto'g'ri, yoki sanalmaydigan
    # ikkinchi eshik bor).  «140% konversiya» butun hisobga bo'lgan
    # ishonchni bir zumda yo'q qiladi — `MAX_PLAUSIBLE_PER_VISITOR_UZS`
    # bilan bir xil sabab.
    if entered >= MIN_VISITORS_FOR_CONVERSION and receipts <= entered:
        percent = round(receipts * 100 / entered)
    return {"receipts": receipts, "entered": entered, "percent": percent}


def conversion_line(
    *, receipts: Optional[int], entered: int, lang: str = i18n.DEFAULT_LANG
) -> Optional[str]:
    """Kunlik xabardagi chek qatori.  Egasi kiritmagan bo'lsa — `None`."""
    data = conversion(receipts=receipts, entered=entered)
    if data is None:
        return None
    if data["percent"] is None:
        # Foizsiz halol javob: son o'zi ham savolga javob beradi.
        return tg(
            lang, "value.conversion.counts", receipts=data["receipts"], entered=data["entered"]
        )
    if data["receipts"]:
        every = round(data["entered"] / data["receipts"])
        # «har 1-mijoz sotib oldi» — ma'nosiz jumla; 2 dan boshlab.
        if every >= 2:
            return tg(
                lang,
                "value.conversion.ratio_every",
                receipts=data["receipts"],
                entered=data["entered"],
                every=every,
            )
    return tg(lang, "value.conversion.ratio", receipts=data["receipts"], entered=data["entered"])


def capture_rate(*, entered: int, passed: Optional[int]) -> Optional[Dict[str, Any]]:
    """Avtomatik konversiya: chek so'ramay, faqat kameradan.

    Raqobatchining bosh o'lchovi (visit ÷ traffic) aynan shu.  `passed` —
    nechta odam do'kongacha yetdi:

    * **A1** (qo'shimcha kamerasiz): kirish kamerasida eshik oldida
      ko'ringan, ya'ni ichkariga kirgan + kirmay ketgan;
    * **A2** (tashqi kamera): do'kon oldidan o'tgan.

    `entered` nechtasi ichkariga kirdi.  Ikkalasi ham kameradan — ega
    hech narsa kiritmasa ham konversiya bo'ladi (chekli konversiya esa
    boshqa savolga javob beradi: kirganning nechtasi SOTIB oldi).

    `None` — `passed` hali yo'q (qurilma bu signalni yubormaydi, masalan
    eski reliz).  `percent = None` — namuna kichik yoki sanoq ishonchsiz.
    """
    if passed is None:
        return None
    passed = max(0, int(passed))
    entered = max(0, int(entered))
    percent: Optional[int] = None
    # Kirgan «o'tgan»dan KO'P bo'lishi — sanoq buzuqligi (chiziq noto'g'ri,
    # yoki eshik oldini ko'rmagan kamera): «130%» butun hisobga ishonchni
    # yo'q qiladi, xuddi chekdagi kabi.  Shuning uchun bunday holatda foiz
    # ko'rsatilmaydi, faqat sonlar qoladi.
    if passed >= MIN_VISITORS_FOR_CONVERSION and entered <= passed:
        percent = round(entered * 100 / passed)
    return {"entered": entered, "passed": passed, "percent": percent}


def select_passed(*, entrance_seen: Optional[int], outer_seen: Optional[int]) -> Optional[int]:
    """Adaptiv maxraj (A1/A2): qaysi «yaqinlashdi» sonini olamiz.

    Ega qarori — moslashuvchan: tashqi (ko'cha) kamera bo'lsa uning
    «o'tdi»si ANIQROQ maxraj (A2 — do'kon oldidan o'tganning nechtasi
    kirdi), shuning uchun u ustun.  Bo'lmasa kirish kamerasining
    «yaqinlashdi»si (A1 — eshikkacha kelganning nechtasi kirdi).

    Ikkalasi ham yo'q → `None`: qurilma hali bu signalni yubormaydi
    (eski reliz), konversiya faqat chekdan chiqadi.
    """
    if outer_seen is not None:
        return max(0, int(outer_seen))
    if entrance_seen is not None:
        return max(0, int(entrance_seen))
    return None


def capture_rate_line(
    *, entered: int, passed: Optional[int], lang: str = i18n.DEFAULT_LANG
) -> Optional[str]:
    """Kunlik xabardagi avtomatik konversiya qatori.  `passed` yo'q → `None`."""
    data = capture_rate(entered=entered, passed=passed)
    if data is None:
        return None
    if data["percent"] is None:
        return tg(lang, "value.capture.counts", passed=data["passed"], entered=data["entered"])
    return tg(
        lang,
        "value.capture.percent",
        passed=data["passed"],
        entered=data["entered"],
        percent=data["percent"],
    )


def uzs(amount: int, lang: str = i18n.DEFAULT_LANG) -> str:
    """So'mni o'qiladigan ko'rinishda: 3 200 000 → «3,2 mln so‘m».

    Birlik ham, kasr belgisi ham katalogdan (`money.*`, `format.number.*`)
    — panelning `formatMoney` bilan bitta yozuv.  Ilgari bu yerda
    «3.2 mln so'm» chiqardi va mijoz bir kunda ikki xil yozuvni ko'rardi.
    """
    if amount >= 1_000_000:
        return tg(lang, "money.mln", value=botfmt.decimal(amount / 1_000_000, lang))
    return tg(lang, "money.plain", value=botfmt.number(amount, lang))


def daily_line(
    report: Dict[str, Any], daily_revenue_uzs: int, lang: str = i18n.DEFAULT_LANG
) -> Optional[str]:
    """Kunlik xabarga qo'shiladigan bitta qator.  Yo'q bo'lsa `None`."""
    traffic = report.get("traffic") or {}
    cost = queue_cost(
        queue_episodes=int((report.get("queue") or {}).get("alerts") or 0),
        daily_revenue_uzs=daily_revenue_uzs,
        visitors=int(traffic.get("entered") or 0),
    )
    if not cost:
        return None
    return tg(
        lang,
        "value.daily.queue_loss",
        episodes=cost["episodes"],
        lost_customers=cost["lost_customers"],
        amount=uzs(cost["lost_uzs"], lang),
    )


def monthly_receipt(
    *,
    site_name: str,
    month_label: str,
    lost_uzs: int,
    monthly_price_uzs: int,
    lang: str = i18n.DEFAULT_LANG,
) -> str:
    """Oylik hisob-kitob cheki — «Chaqimchi o'zini qopladimi».

    Eng muhim xabar: mijoz obunani uzaytirishdan oldin aynan shu
    savolga javob izlaydi.  Raqam o'zimizning foydamizga emas,
    HAQIQATGA xizmat qilishi kerak — shuning uchun taxmin ehtiyotkor.
    """
    lines = [
        tg(lang, "value.receipt.title", site=site_name, month=month_label),
        "",
        tg(lang, "value.receipt.loss", amount=uzs(lost_uzs, lang)),
        tg(lang, "value.receipt.subscription", amount=uzs(monthly_price_uzs, lang)),
    ]
    if lost_uzs > monthly_price_uzs:
        # Bo'sh qator — bu jumla alohida xulosa, ro'yxat davomi emas.
        lines += [
            "",
            tg(
                lang,
                "value.receipt.times",
                times=botfmt.decimal(lost_uzs / monthly_price_uzs, lang),
            ),
        ]
    lines += ["", tg(lang, "value.receipt.disclaimer")]
    return "\n".join(lines)
