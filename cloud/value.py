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


def uzs(amount: int) -> str:
    """So'mni o'qiladigan ko'rinishda: 3 200 000 → «3.2 mln so'm»."""
    if amount >= 1_000_000:
        millions = amount / 1_000_000
        text = f"{millions:.1f}".rstrip("0").rstrip(".")
        return f"{text} mln so'm"
    return f"{amount:,}".replace(",", " ") + " so'm"


def daily_line(report: Dict[str, Any], daily_revenue_uzs: int) -> Optional[str]:
    """Kunlik xabarga qo'shiladigan bitta qator.  Yo'q bo'lsa `None`."""
    traffic = report.get("traffic") or {}
    cost = queue_cost(
        queue_episodes=int((report.get("queue") or {}).get("alerts") or 0),
        daily_revenue_uzs=daily_revenue_uzs,
        visitors=int(traffic.get("entered") or 0),
    )
    if not cost:
        return None
    return (
        f"💸 Uzun navbat {cost['episodes']} marta bo'ldi. Taxminan "
        f"<b>{cost['lost_customers']}</b> mijoz kutmasdan ketgan bo'lishi mumkin "
        f"≈ <b>{uzs(cost['lost_uzs'])}</b>"
    )


def monthly_receipt(
    *,
    site_name: str,
    month_label: str,
    lost_uzs: int,
    monthly_price_uzs: int,
) -> str:
    """Oylik hisob-kitob cheki — «Chaqimchi o'zini qopladimi».

    Eng muhim xabar: mijoz obunani uzaytirishdan oldin aynan shu
    savolga javob izlaydi.  Raqam o'zimizning foydamizga emas,
    HAQIQATGA xizmat qilishi kerak — shuning uchun taxmin ehtiyotkor.
    """
    lines = [
        f"🧾 <b>{site_name}</b> — {month_label} hisob-kitobi",
        "",
        f"Chaqimchi ko'rsatgan yo'qotish: <b>{uzs(lost_uzs)}</b>",
        f"Obuna: {uzs(monthly_price_uzs)}",
    ]
    if lost_uzs > monthly_price_uzs:
        times = lost_uzs / monthly_price_uzs
        lines.append(f"\nYa'ni obuna narxidan <b>{times:.1f}×</b> ko'p.")
    lines.append(
        "\nBu <i>taxminiy</i> hisob: uzun navbat har safar bitta mijozni "
        "yo'qotadi deb olindi va o'rtacha chek sizning kunlik savdongizdan "
        "hisoblandi."
    )
    return "\n".join(lines)
