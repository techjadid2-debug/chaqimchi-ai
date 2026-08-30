"""Chizilgan chiziq va zonalarning YAROQLILIGI.

Panel chizmani 0..1 oralig'ida saqlaydi va qurilma ham aynan shu
oraliqda ishlaydi (`chaqimchi_ai/retail/lines.py` kesishmani,
`chaqimchi_ai/scene_analytics.py:_inside` esa nuqtani shu koordinatada
tekshiradi).  Shuning uchun "juda kichik" degan savolga shu yerda,
qurilma bilan bir xil o'lchovda javob berish mumkin.

**Nega kerak.**  2026-08-28 da sinov do'konining sozlamasida (revision
11) ikkita yaroqsiz chizma topildi va ikkalasi ham JIMGINA hech narsa
qilmasdi:

* `kirish` chizig'i — uzunligi **0.007** (640 px kadrda ~4 piksel);
* `Taqiqlangan zona` — 0.045 x 0.056 (**29 x 20 piksel**), kadr tepasida.

Ikkinchisi do'konning yagona `critical` xavfsizlik signali edi
(`telegram_min_severity: critical`) va ikki kun davomida **0 ta** hodisa
berdi.  Hech bir tekshiruv buni ushlamadi: chizma saqlandi, revision
o'sdi, qurilma sozlamani qabul qildi — faqat hodisa yo'q edi.  Ya'ni
nosozlik "xato" ko'rinishida emas, **jimlik** ko'rinishida keldi.

Bu modul chizmani rad ETMAYDI va do'kon egasiga ko'rinmaydi — u faqat
admin uchun ro'yxat tuzadi.  Sabab: o'rnatuvchi chizib turgan paytda
uni to'xtatish sozlashni buzadi, mijoz esa "zona kichik" degan texnik
gapdan xulosa chiqara olmaydi.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from chaqimchi_ai.camera_roles import face_id_check

#: Chiziqning eng kam uzunligi (kadr o'lchamiga nisbatan).
#:
#: Eshik odatda kadr enining 20-50% ini egallaydi.  5% dan qisqa chiziq
#: eshik bo'la olmaydi: 640 px kadrda bu 32 piksel, ya'ni odam o'tishi
#: uchun undan aynan shu tor joydan yurishi kerak bo'lardi.  Track'ning
#: bir kadrdagi qadami ~0.012 (17 FPS da odatiy yurish tezligi), ya'ni
#: 0.05 — qadamdan atigi to'rt barobar katta va bu allaqachon chegara.
MIN_LINE_LENGTH = 0.05

#: Zonaning eng kam yuzasi (kadr yuzasiga nisbatan).
#:
#: Zona odam ramkasining MARKAZI bo'yicha tekshiriladi
#: (`scene_analytics.py`), ya'ni nishon — bitta nuqta.  Yuzasi 0.01
#: bo'lgan kvadratning tomoni 0.1, bu esa bir kadrdagi qadamdan (~0.012)
#: sakkiz barobar katta: yuruvchi odamning markazi ichkarida sakkizta
#: kadr turadi va hodisa ishonchli chiqadi.  Bundan kichigida markaz
#: zonani sakrab o'tib ketishi mumkin.
MIN_ZONE_AREA = 0.01

#: Zonaning eng kam tomoni (o'rab turuvchi to'rtburchakda).
#:
#: Yuzasi yetarli, lekin ensiz uzun tasma bo'lgan zona ham aynan shu
#: sababdan ishlamaydi — markaz uni ko'ndalangiga kesib o'tadi.
MIN_ZONE_SIDE = 0.08

Point = Tuple[float, float]


def _point(value: Any) -> Point | None:
    """Xom JSON'dan nuqta.  Yaroqsiz bo'lsa `None` — tekshiruv yiqilmasin."""
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        return (float(value[0]), float(value[1]))
    except (TypeError, ValueError):
        return None


def _polygon(value: Any) -> List[Point]:
    if not isinstance(value, (list, tuple)):
        return []
    points = [_point(item) for item in value]
    return [item for item in points if item is not None]


def _length(start: Point, end: Point) -> float:
    return ((end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2) ** 0.5


def _area(polygon: Sequence[Point]) -> float:
    """Ko'pburchak yuzasi (shoelace).  Nuqtalar tartibi ahamiyatsiz."""
    if len(polygon) < 3:
        return 0.0
    total = 0.0
    for index, (x1, y1) in enumerate(polygon):
        x2, y2 = polygon[(index + 1) % len(polygon)]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def _px(value: float, pixels: int) -> int:
    """Normallashgan o'lchovni pikselga aylantiradi — admin shuni tushunadi."""
    return int(round(value * pixels))


def geometry_problems(
    config: Dict[str, Any],
    *,
    frame_width: int = 640,
    frame_height: int = 360,
) -> List[Dict[str, Any]]:
    """Hech qachon hodisa bermaydigan chiziq va zonalar ro'yxati.

    `frame_width`/`frame_height` faqat admin ko'radigan piksel raqami
    uchun — qaror normallashgan o'lchovda qabul qilinadi, ya'ni oqim
    sifati o'zgarsa ham xulosa o'zgarmaydi.
    """
    problems: List[Dict[str, Any]] = []

    for line in config.get("lines") or []:
        if not isinstance(line, dict):
            continue
        start = _point(line.get("start"))
        end = _point(line.get("end"))
        name = str(line.get("name") or "nomsiz")
        camera_id = str(line.get("camera_id") or "—")
        if start is None or end is None:
            problems.append(
                {
                    "kind": "line",
                    "name": name,
                    "camera_id": camera_id,
                    "problem": "Chiziq koordinatalari buzuq — qayta chizilsin.",
                    "measure": None,
                }
            )
            continue
        length = _length(start, end)
        if length < MIN_LINE_LENGTH:
            problems.append(
                {
                    "kind": "line",
                    "name": name,
                    "camera_id": camera_id,
                    "problem": (
                        f"Chiziq juda qisqa: {_px(length, frame_width)} piksel. "
                        "Odam uni kesib o'tmaydi — kirish sanalmaydi. "
                        "Chiziq eshikni to'liq to'sib turishi kerak."
                    ),
                    "measure": round(length, 4),
                }
            )

    for zone in config.get("zones") or []:
        if not isinstance(zone, dict):
            continue
        polygon = _polygon(zone.get("polygon"))
        name = str(zone.get("name") or "nomsiz")
        camera_id = str(zone.get("camera_id") or "—")
        if len(polygon) < 3:
            problems.append(
                {
                    "kind": "zone",
                    "name": name,
                    "camera_id": camera_id,
                    "problem": "Zona uch nuqtadan kam — qayta chizilsin.",
                    "measure": None,
                }
            )
            continue

        area = _area(polygon)
        width = max(point[0] for point in polygon) - min(point[0] for point in polygon)
        height = max(point[1] for point in polygon) - min(point[1] for point in polygon)

        if area < MIN_ZONE_AREA:
            problems.append(
                {
                    "kind": "zone",
                    "name": name,
                    "camera_id": camera_id,
                    "problem": (
                        f"Zona juda kichik: {_px(width, frame_width)}x"
                        f"{_px(height, frame_height)} piksel. Odam ramkasining "
                        "markazi unga tushmaydi — hodisa hech qachon chiqmaydi."
                    ),
                    "measure": round(area, 5),
                }
            )
        elif min(width, height) < MIN_ZONE_SIDE:
            problems.append(
                {
                    "kind": "zone",
                    "name": name,
                    "camera_id": camera_id,
                    "problem": (
                        f"Zona juda ensiz: {_px(width, frame_width)}x"
                        f"{_px(height, frame_height)} piksel. Odam markazi uni "
                        "sezilmasdan kesib o'tadi."
                    ),
                    "measure": round(min(width, height), 4),
                }
            )

    return problems


def role_problems(
    cameras: Sequence[Dict[str, Any]],
    config: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Rol va'da qilgan, geometriya esa yo'q — jimlik ro'yxati.

    Rol o'z-o'zidan hodisa chiqarmaydi: «kirish» chizilgan chiziq bilan,
    «kassa» navbat zonasi bilan ishlaydi.  Nomuvofiqlik xato ko'rinishida
    emas, JIMLIK ko'rinishida keladi — 2026-08-22 da o'chirilgan rol
    maydoni aynan shu jimlikda edi (rol bor, o'qiydigan yo'q).  Endi rol
    o'qiladi, lekin geometriyasiz qolgan rol ham xuddi shunday jim —
    shu ro'yxat uni admin ko'ziga chiqaradi.
    """
    problems: List[Dict[str, Any]] = []
    line_cameras = {
        str(line.get("camera_id"))
        for line in (config.get("lines") or [])
        if isinstance(line, dict)
    }
    queue_cameras = {
        str(zone.get("camera_id"))
        for zone in (config.get("zones") or [])
        if isinstance(zone, dict) and zone.get("queue")
    }
    for camera in cameras:
        if not isinstance(camera, dict):
            continue
        role = str(camera.get("role") or "")
        camera_id = str(camera.get("camera_id") or "")
        label = str(camera.get("label") or camera_id)
        if role == "entrance":
            if camera_id not in line_cameras:
                problems.append(
                    {
                        "kind": "role",
                        "name": label,
                        "camera_id": camera_id,
                        "problem": (
                            "Rol «Kirish», lekin kirish chizig'i chizilmagan — "
                            "sanash ham, Face ID ham ishlamaydi."
                        ),
                        "measure": None,
                    }
                )
            # Balandlik faqat probe'dan keladi; noma'lum bo'lsa bu muammo
            # emas — yolg'on trevoga bermaslik uchun jim qolamiz.
            height = camera.get("height")
            if height:
                ok, reason = face_id_check(int(height))
                if ok is False:
                    problems.append(
                        {
                            "kind": "role",
                            "name": label,
                            "camera_id": camera_id,
                            "problem": f"Rol «Kirish», lekin {reason}.",
                            "measure": int(height),
                        }
                    )
        elif role == "checkout" and camera_id not in queue_cameras:
            problems.append(
                {
                    "kind": "role",
                    "name": label,
                    "camera_id": camera_id,
                    "problem": (
                        "Rol «Kassa», lekin navbat zonasi chizilmagan — "
                        "navbat ham, «kassada hech kim yo'q» ham ishlamaydi."
                    ),
                    "measure": None,
                }
            )
    return problems


#: Obuna shu holatlarda mijoz xizmatni OLISHI kerak.  `grace` ham shu
#: yerda: sayt "obuna tugagach tizim yana 14 kun ishlaydi" deb va'da
#: qiladi, ya'ni bu davrda jimlik ham nosozlik.
SERVING_SUBSCRIPTION_STATES = frozenset({"active", "grace"})


def feature_problems(
    subscription: Dict[str, Any],
    cloud_features: Sequence[Dict[str, Any]],
    health: Optional[Dict[str, Any]] = None,
    *,
    yesterday_events: Optional[int] = None,
    device_online: bool = False,
) -> List[Dict[str, Any]]:
    """To'lovchi mijoz hodisa olmayotgan holat — jimlik ro'yxati.

    **Nega kerak.**  2026-08-29 dan 08-30 gacha "Do'kon (5070)" ning
    HAMMA biznes hodisasi qurilmada tashlandi: bulut unga bo'sh funksiya
    ro'yxatini yuborardi, `retail_event_filter` esa bo'sh ro'yxatni
    ko'rib har bir hodisani rad etardi.  Besh kun davomida na log, na
    panel, na ogohlantirish — mijoz nol raqamli kunlik hisobot oldi va
    nosozlikni faqat qo'lda tekshiruv topdi.

    Ikkita mustaqil tekshiruv bor va ular ATAYLAB bir-birini takrorlaydi:

    * **sabab** — obuna faol, lekin qurilmaga ketadigan ro'yxat bo'sh;
    * **natija** — qurilmaning oxirgi heartbeat'ida `plan_filtered`
      `events` ga TENG, ya'ni u amalda hammasini tashlayapti.

    Ikkinchisi kuchliroq: u sababdan qat'i nazar ishlaydi.  Aynan shu
    raqam besh kun davomida heartbeat ichida turgan edi — uni hech kim
    o'qimagani uchun nosozlik ko'rinmadi.
    """
    problems: List[Dict[str, Any]] = []
    status = str(subscription.get("status") or "")

    if status in SERVING_SUBSCRIPTION_STATES and not cloud_features:
        problems.append(
            {
                "kind": "feature",
                "name": "Funksiya ro'yxati",
                "camera_id": "—",
                "problem": (
                    "Obuna faol, lekin qurilmaga birorta funksiya ketmayapti — "
                    "hamma hodisa qurilmada tashlanadi."
                ),
                "measure": f"obuna: {status}, funksiya: 0 ta",
            }
        )

    events = _int((health or {}).get("events"))
    filtered = _int((health or {}).get("plan_filtered"))
    if events > 0 and filtered >= events:
        problems.append(
            {
                "kind": "feature",
                "name": "Tarif filtri",
                "camera_id": "—",
                "problem": (
                    "Qurilma yaratgan hodisaning HAMMASINI tashlayapti — "
                    "bulutga hech narsa yetib bormaydi."
                ),
                "measure": f"{events} ta hodisadan {filtered} tasi tashlangan",
            }
        )

    # Uchinchi tekshiruv — KUN darajasida, sababdan butunlay mustaqil.
    #
    # Yuqoridagi ikkisi qurilma nima deyayotganiga tayanadi.  Bu esa
    # bizda NIMA SAQLANGANIGA qaraydi: qurilma tirik-u, tugagan kunga
    # birorta hodisa yozilmagan bo'lsa — sababi nima bo'lishidan qat'i
    # nazar, o'sha kun mijoz uchun yo'q.  2026-08-29 dagi besh kunlik
    # jimlik aynan shunday ko'rinardi va uni hech narsa aytmadi.
    #
    # Yolg'on ogohlantirish mumkin (dam olish kuni, ta'til) — lekin u
    # faqat admin ro'yxatida bir qator, jimlikning narxi esa besh kun edi.
    if (
        status in SERVING_SUBSCRIPTION_STATES
        and device_online
        and yesterday_events is not None
        and yesterday_events == 0
    ):
        problems.append(
            {
                "kind": "feature",
                "name": "Kechagi kun",
                "camera_id": "—",
                "problem": (
                    "Qurilma aloqada, lekin kecha butun kun davomida birorta "
                    "hodisa saqlanmagan — do'kon yopiq bo'lmasa, bu nosozlik."
                ),
                "measure": "kecha: 0 ta hodisa",
            }
        )

    return problems


def _int(value: Any) -> int:
    """Heartbeat maydoni yo'q yoki buzuq bo'lsa tekshiruv yiqilmasin."""
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
