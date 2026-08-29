"""Kamera rollari — yagona haqiqat manbai va taklif dvigateli.

Rol — kameraning MAHSULOT vazifasi: kirish (Face ID), kassa, savdo
zali, ombor.  U per-kamera maydon sifatida saqlanadi va kamera bilan
birga yashaydi (sayt-konfig dict EMAS — o'shanaqasi 2026-08-22 da
o'chirilgan edi: hech kim o'qimasdi va UI hamma kamerani jimgina
"Kirish" qilib qo'yardi, `cloud/main.py` dagi izohga qarang).

Bu modul ikkala tomonda ishlatiladi: sehrgar (lokal) va bulut paneli.
Shuning uchun bu yerda faqat sof mantiq — tarmoq ham, fayl ham yo'q.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from chaqimchi_ai.limits import SHOP_MAX_CAMERAS, face_min_bbox_ratio

#: Sim qiymatlari inglizcha — `setup.js` dagi `ROLE_PRESETS` kalitlari
#: bilan uzluksizlik uchun (ular 0.6.x dan beri shu nomlarda).
CAMERA_ROLES = ("entrance", "checkout", "sales", "storage")

#: Ochiq "tanlanmagan".  Bo'sh satr EMAS: bo'sh satr eski (rolni
#: bilmaydigan) qurilmadan keladi va bulut uni "yangilama" deb o'qiydi.
#: Yangi kod rolni olib tashlasa aynan shu qiymatni yuborishi shart —
#: aks holda o'chirish bulutga hech qachon yetib bormaydi.
ROLE_NONE = "none"

#: Rol → zanjir prioriteti.  Rol prioritetni ALMASHTIRMAYDI, faqat
#: standart qiymatini beradi: support kerak bo'lsa prioritetni roldan
#: mustaqil sozlay oladi (masalan, band kassa kamerasini vaqtincha
#: `security` ga ko'tarish).
ROLE_PRIORITY: Dict[str, str] = {
    "entrance": "security",
    "checkout": "retail",
    "sales": "retail",
    "storage": "background",
}

#: Mijozga ko'rinadigan nomlar.
ROLE_LABELS_UZ: Dict[str, str] = {
    "entrance": "Kirish eshigi",
    "checkout": "Kassa",
    "sales": "Savdo zali",
    "storage": "Ombor",
    ROLE_NONE: "Rol tanlanmagan",
}


def normalize_role(value: object) -> str:
    """Har qanday kirishni uch holatdan biriga keltiradi.

    `""` (noma'lum, eski qurilma) va `ROLE_NONE` (ochiq tanlanmagan)
    FARQLI: birinchisi "tegma", ikkinchisi "tozala" degani.
    """
    text = str(value or "").strip().lower()
    if text in CAMERA_ROLES or text == ROLE_NONE:
        return text
    return ""


# ── Taklif dvigateli ─────────────────────────────────────────────────────
#
# Halol signallargina ishlatiladi.  Kanal raqami ATAYLAB signal emas:
# "1-kanal — kirish" degan taxmin ilgari sehrgarda qotirilgan prefill
# edi va aynan shunaqa jim standartlar 2026-08-22 xatosini keltirgan.

#: NVR kanallari odatda o'rnatuvchi tomonidan nomlangan bo'ladi —
#: bu eng kuchli real signal.  uz/ru/en, kichik harfda solishtiriladi.
_ROLE_KEYWORDS: Dict[str, Sequence[str]] = {
    "entrance": ("kirish", "eshik", "entrance", "entry", "door", "вход", "дверь"),
    "checkout": ("kassa", "checkout", "cash", "касса"),
    "sales": ("zal", "savdo", "sales", "hall", "shop", "зал", "торгов"),
    "storage": ("ombor", "sklad", "storage", "store room", "склад", "подсоб"),
}

#: Nom mosligi ishonchi.  1.0 emas: nom ham yolg'on bo'lishi mumkin
#: (kamera ko'chirilgan, nom qolgan) — odam tasdig'i baribir shart.
_NAME_SCORE = 0.9

#: Harakat namunasi ishonchi.  Zaif signal: band zal ham, band kirish
#: ham bir xil ko'rinadi — u faqat nom bo'lmaganda yo'nalish beradi.
_TRAFFIC_SCORE = 0.4

#: Shu tezlikdan ko'p odam ko'ringan kamera "band" (kirish/zal nomzodi).
#: 2 odam/daqiqa — ochiq do'konda kirish uchun juda past bosqich, ya'ni
#: yolg'on-musbat kam.
_TRAFFIC_BUSY_PER_MIN = 2.0

#: Shu tezlikdan kam — "bo'sh" (ombor nomzodi): 10 daqiqada bitta ham
#: odam yo'q degani.
_TRAFFIC_EMPTY_PER_MIN = 0.1

#: Yuz tanish uchun odam ramkasi kadr balandligining shu ulushidan
#: oshmasligi kerak.  720p oqim 0.38 beradi (`face_min_bbox_ratio`) —
#: ya'ni 0.40 "720p va undan yaxshi" degani, formuladan kelib chiqqan.
_FACE_RATIO_OK = 0.40

#: Bundan yuqorisi amalda imkonsiz: odam kadrning 60%+ ini egallashi
#: kerak bo'lardi.  Bunday kamera kirish roliga TAKLIF QILINMAYDI
#: (qo'lda tanlash mumkin — taklif emas, ta'qiq emas).
_FACE_RATIO_LIMIT = 0.60

#: Taklif chiqarish bo'sag'asi: eng yaxshi ball shundan past bo'lsa
#: taklif YO'Q — "bilmayman" halol javob, noto'g'ri taklif esa jimgina
#: noto'g'ri sozlamaga aylanadi (2026-08-22 saboq).
_SUGGEST_MIN_SCORE = 0.5

#: Ikki rol deyarli teng ball olsa ham taklif YO'Q — tanlovni odam
#: qilsin.
_SUGGEST_MIN_MARGIN = 0.2


@dataclass(frozen=True)
class RoleCandidate:
    """Skanerdan kelgan bitta kamera/kanal haqida bilganlarimiz."""

    camera_id: str
    name: str = ""
    width: int = 0
    height: int = 0
    works: bool = True
    #: Namuna olishda o'lchangan odam soni (daqiqasiga).  `None` —
    #: namuna olinmagan (bu "nol odam" degani EMAS).
    traffic_per_min: Optional[float] = None


@dataclass
class RoleSuggestion:
    """Bitta kamera uchun taklif — sabablari bilan.

    `suggested_role=None` — taklif yo'q, odam tanlaydi.  Bu xato holati
    emas, halol javob.
    """

    camera_id: str
    suggested_role: Optional[str] = None
    confidence: float = 0.0
    reasons: List[str] = field(default_factory=list)
    #: Yuz tanishga yaroqlimi: True/False/None (o'lcham noma'lum).
    face_id_ok: Optional[bool] = None
    #: 4 talik tanlovda qolsinmi (skaner limitdan ko'p topganda).
    keep: bool = True


def face_id_check(height: int) -> tuple:
    """(face_id_ok, sabab) — oqim balandligidan yuz tanish imkoni."""
    if height <= 0:
        return None, "O'lcham noma'lum — yuz tanish imkonini aytib bo'lmaydi"
    ratio = face_min_bbox_ratio(height)
    if ratio <= _FACE_RATIO_OK:
        return True, f"{height}p oqim — yuz tanish uchun yetarli"
    if ratio <= _FACE_RATIO_LIMIT:
        return False, (
            f"{height}p oqim yuz tanish uchun chegarada — odam kameraga "
            "juda yaqin kelishi kerak bo'ladi"
        )
    return False, f"{height}p oqim yuz tanish uchun yetarli emas (720p kerak)"


def _score_candidate(item: RoleCandidate) -> Dict[str, float]:
    """Har rol uchun ball.  Sabablar alohida yig'iladi."""
    scores: Dict[str, float] = {role: 0.0 for role in CAMERA_ROLES}
    name = (item.name or "").strip().lower()
    if name:
        for role, keywords in _ROLE_KEYWORDS.items():
            if any(keyword in name for keyword in keywords):
                scores[role] = max(scores[role], _NAME_SCORE)
    if item.traffic_per_min is not None:
        if item.traffic_per_min >= _TRAFFIC_BUSY_PER_MIN:
            scores["entrance"] = max(scores["entrance"], _TRAFFIC_SCORE)
            scores["sales"] = max(scores["sales"], _TRAFFIC_SCORE)
        elif item.traffic_per_min <= _TRAFFIC_EMPTY_PER_MIN:
            scores["storage"] = max(scores["storage"], _TRAFFIC_SCORE)
    return scores


def suggest_role(item: RoleCandidate) -> RoleSuggestion:
    """Bitta kamera uchun taklif."""
    suggestion = RoleSuggestion(camera_id=item.camera_id)
    face_ok, face_reason = face_id_check(item.height)
    suggestion.face_id_ok = face_ok

    scores = _score_candidate(item)
    name = (item.name or "").strip()

    # Past sifatli oqimga kirish roli TAKLIF qilinmaydi — davomat unda
    # printsipial ishlamaydi va mijoz "Face ID buzilgan" deb o'ylaydi.
    if face_ok is False and item.height > 0:
        ratio = face_min_bbox_ratio(item.height)
        if ratio > _FACE_RATIO_LIMIT and scores["entrance"] > 0:
            scores["entrance"] = 0.0
            suggestion.reasons.append(face_reason)

    ranked = sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
    best_role, best_score = ranked[0]
    margin = best_score - ranked[1][1]

    if best_score >= _SUGGEST_MIN_SCORE and margin >= _SUGGEST_MIN_MARGIN:
        suggestion.suggested_role = best_role
        suggestion.confidence = round(best_score, 2)
        if name and best_score >= _NAME_SCORE:
            suggestion.reasons.append(f"Nomida «{name}» yozilgan")
        elif item.traffic_per_min is not None:
            if best_role == "storage":
                suggestion.reasons.append("Namuna paytida odam ko'rinmadi")
            else:
                suggestion.reasons.append(
                    f"Harakat ko'p ({item.traffic_per_min:.1f} odam/daqiqa)"
                )
        if best_role == "entrance":
            suggestion.reasons.append(face_reason)
    else:
        suggestion.reasons.append(
            "Ishonchli belgi topilmadi — rolni o'zingiz tanlang"
        )
    return suggestion


def suggest_roles(
    candidates: Sequence[RoleCandidate],
    *,
    limit: int = SHOP_MAX_CAMERAS,
) -> List[RoleSuggestion]:
    """Hamma kamera uchun taklif + limitdan ko'p bo'lsa 4 talik tanlov.

    Tanlov tartibi: rol qamrovi (ishonchli kirish, keyin kassa —
    ular mahsulot va'dasining o'zagi) → oqim balandligi → ishlashi.
    Ishlamaydigan (`works=False`) kamera hech qachon ishlaydiganini
    siqib chiqarmaydi.
    """
    suggestions = [suggest_role(item) for item in candidates]
    if len(candidates) <= limit:
        return suggestions

    by_id = {item.camera_id: item for item in candidates}
    for suggestion in suggestions:
        suggestion.keep = False

    def sort_key(suggestion: RoleSuggestion) -> tuple:
        item = by_id[suggestion.camera_id]
        return (item.works, item.height, suggestion.confidence)

    chosen: List[RoleSuggestion] = []
    # Avval yagona rollar: kirishsiz davomat yo'q, kassasiz navbat yo'q.
    for role in ("entrance", "checkout"):
        matching = [
            s
            for s in suggestions
            if s.suggested_role == role and by_id[s.camera_id].works
        ]
        if matching:
            chosen.append(max(matching, key=sort_key))
    for suggestion in sorted(suggestions, key=sort_key, reverse=True):
        if len(chosen) >= limit:
            break
        if suggestion not in chosen:
            chosen.append(suggestion)
    for suggestion in chosen[:limit]:
        suggestion.keep = True
    for suggestion in suggestions:
        if not suggestion.keep:
            suggestion.reasons.append(
                f"Chegara {limit} ta — bu kamera tanlovdan tashqarida qoldi"
            )
    return suggestions
