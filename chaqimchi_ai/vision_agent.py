"""Ko‘rish agenti — kadrni AI ko‘rib, nima bo‘layotganini o‘zbekcha aytadi.

Yuz tanish "bu kim?" degan savolga javob beradi. Bu modul boshqa savolga:
**"nima bo‘layapti?"** — kassada navbat, yiqilgan odam, omborda begona, eshik
ochiq qolgan. Yuz bazasi kerak emas.

## Eng muhimi: bu pul sarflaydigan modul

Har chaqiruv Anthropic API ga pul to‘laydi. Shuning uchun modul **ikki qavatli
tormoz** bilan yozilgan va ikkalasi ham majburiy:

1. **Har kadrda emas, faqat sababga ko‘ra.** Kamera sekundiga 25 kadr beradi.
   Ularning hammasini yuborish oyiga minglab dollar bo‘ladi. Agent faqat
   `min_interval_sec` o‘tgach va rostdan sabab bo‘lganda chaqiriladi.
2. **Qattiq limit.** Kunlik va oylik chaqiruvlar soni cheklangan; limit tugasa
   modul **butunlay to‘xtaydi** va logga yozadi. Kodda xato bo‘lsa ham hisob
   bo‘shab qolmaydi.

Sarf `data/vision_usage.db` da saqlanadi — server qayta ishga tushsa ham
hisob davom etadi.

## Narx

`estimate_cost_uzs()` haqiqiy hisobni qiladi. Taxminiy: bitta tahlil ≈ 900
kirish + 150 chiqish token ≈ **0.008 AQSh dollari**. Kuniga 100 tahlil ≈
oyiga 24 dollar. Kadrni kichraytirish (`max_side`) — narxni tushirishning eng
kuchli usuli, chunki rasm tokeni o‘lchamga bog‘liq.

Batafsil: docs/KORISH_AGENTI.md
"""

from __future__ import annotations

import base64
import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

#: Standart model. Narx: 1M kirish token = $5, 1M chiqish token = $25.
DEFAULT_MODEL = "claude-opus-5"

#: Narxlar (AQSh dollari / 1M token). Model o‘zgarsa shuni yangilang.
PRICE_INPUT_PER_MTOK = 5.0
PRICE_OUTPUT_PER_MTOK = 25.0

#: Rasm tokeni taxminan (kenglik × balandlik) / 750.
IMAGE_TOKENS_DIVISOR = 750

#: Javob sxemasi — model shu shaklda javob berishga majbur.
RESPONSE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "tavsif": {
            "type": "string",
            "description": "Kadrda nima bo‘layotgani, bir-ikki jumla, o‘zbek tilida",
        },
        "odamlar": {
            "type": "integer",
            "description": "Kadrda ko‘ringan odamlar soni",
        },
        "ogohlantirish": {
            "type": "boolean",
            "description": "Do‘kon egasi darhol bilishi kerak bo‘lgan holatmi",
        },
        "sabab": {
            "type": "string",
            "description": "Ogohlantirish sababi; ogohlantirish yo‘q bo‘lsa bo‘sh satr",
        },
    },
    "required": ["tavsif", "odamlar", "ogohlantirish", "sabab"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """Sen do‘kon xavfsizlik kamerasining kadrlarini kuzatuvchi yordamchisan.
Sening vazifang — kadrni ko‘rib, do‘kon egasiga qisqa va aniq xabar berish.

Qoidalar:
- Faqat o‘zbek tilida yoz.
- Ko‘rganingni ayt, taxmin qilma. Kadr xira yoki qorong‘i bo‘lsa shuni ayt.
- Odamlarning kimligini aniqlashga urinma — bu sening vazifang emas.
- `ogohlantirish` ni faqat do‘kon egasi **darhol** bilishi kerak bo‘lgan holatda
  rost qil: odam yiqilgan, janjal, tutun yoki olov, ish vaqtidan tashqari
  harakat, kassa yoki ombor oldida shubhali xatti-harakat.
- Oddiy holat — xaridor yuribdi, kassada navbat, xodim ishlayapti — ogohlantirish
  emas. Yolg‘on ogohlantirish do‘kon egasining ishonchini yo‘qotadi.
- Tavsif qisqa bo‘lsin: bir-ikki jumla, ortiqcha tafsilotsiz."""


class VisionAgentError(Exception):
    """Tahlil bajarilmadi."""


class BudgetExceeded(VisionAgentError):
    """Kunlik yoki oylik limit tugagan."""


@dataclass
class VisionConfig:
    enabled: bool = False
    model: str = DEFAULT_MODEL
    #: Kadr shu o‘lchamgacha kichraytiriladi. Kichikroq = arzonroq.
    max_side: int = 768
    jpeg_quality: int = 80
    #: Ikki tahlil orasidagi eng kam vaqt (kamera bo‘yicha).
    min_interval_sec: int = 300
    max_calls_per_day: int = 100
    max_calls_per_month: int = 2000
    #: `low` — arzon va tez; murakkab sahna uchun `medium`.
    effort: str = "low"
    max_tokens: int = 2048
    timeout_sec: float = 30.0
    #: Ogohlantirish bo‘lsa Telegramga yuborilsinmi.
    telegram_alerts: bool = True


@dataclass
class VisionResult:
    tavsif: str
    odamlar: int
    ogohlantirish: bool
    sabab: str
    camera_id: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tavsif": self.tavsif,
            "odamlar": self.odamlar,
            "ogohlantirish": self.ogohlantirish,
            "sabab": self.sabab,
            "camera_id": self.camera_id,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_tokens": self.cached_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "latency_ms": round(self.latency_ms, 1),
            "created_at": round(self.created_at, 1),
        }


# ── Narx hisobi ──────────────────────────────────────────────────────────


def image_tokens(width: int, height: int) -> int:
    """Rasm necha token bo‘lishini taxminlaydi."""
    return max(1, int(width * height / IMAGE_TOKENS_DIVISOR))


def call_cost_usd(input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> float:
    """Bitta chaqiruv narxi (AQSh dollari).

    Keshdan o‘qilgan tokenlar 10 barobar arzon — shuning uchun tizim
    ko‘rsatmasi keshlanadi.
    """
    fresh = max(0, input_tokens)
    cost = fresh / 1_000_000 * PRICE_INPUT_PER_MTOK
    cost += cached_tokens / 1_000_000 * PRICE_INPUT_PER_MTOK * 0.1
    cost += max(0, output_tokens) / 1_000_000 * PRICE_OUTPUT_PER_MTOK
    return cost


def estimate_monthly_usd(calls_per_day: int, max_side: int = 768) -> float:
    """Oylik taxminiy xarajat — tarif hisoblashda kerak."""
    # Kadr 16:9 deb olinadi.
    w = max_side
    h = int(max_side * 9 / 16)
    per_call = call_cost_usd(
        input_tokens=image_tokens(w, h) + 120,  # rasm + qisqa savol
        output_tokens=150,
        cached_tokens=400,  # tizim ko'rsatmasi keshdan
    )
    return per_call * calls_per_day * 30


def encode_frame(frame_bgr: Any, *, max_side: int = 768, quality: int = 80) -> bytes:
    """BGR kadrni kichraytirib JPEG ga o‘giradi.

    Kichraytirish narxga to‘g‘ridan-to‘g‘ri ta’sir qiladi: rasm tokeni
    o‘lchamga proporsional. 1920×1080 kadr ≈ 2765 token, 768×432 ≈ 442 token —
    olti barobar arzon, do‘kondagi sahnani tushunish uchun esa yetarli.
    """
    import cv2  # og'ir import — faqat kerak bo'lganda
    import numpy as np

    arr = np.asarray(frame_bgr)
    if arr.size == 0:
        raise VisionAgentError("Kadr bo‘sh")

    h, w = arr.shape[:2]
    longest = max(h, w)
    if longest > max_side:
        scale = max_side / longest
        arr = cv2.resize(
            arr, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA
        )

    ok, buf = cv2.imencode(".jpg", arr, [cv2.IMWRITE_JPEG_QUALITY, int(quality)])
    if not ok:
        raise VisionAgentError("Kadrni JPEG ga o‘girib bo‘lmadi")
    return buf.tobytes()


# ── Sarf hisobi (diskda) ─────────────────────────────────────────────────


class UsageStore:
    """Chaqiruvlar va xarajatni saqlaydi.

    Diskda, chunki server qayta ishga tushganda limit nolga qaytmasligi kerak —
    aks holda tez-tez restart bo‘lsa limit umuman ishlamaydi.
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vision_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_id TEXT,
                created_at TEXT NOT NULL,
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                cached_tokens INTEGER NOT NULL DEFAULT 0,
                cost_usd REAL NOT NULL DEFAULT 0,
                alert INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.commit()
        conn.close()

    def record(self, result: VisionResult) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO vision_calls"
            " (camera_id, created_at, input_tokens, output_tokens, cached_tokens, cost_usd, alert)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                result.camera_id,
                datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                result.input_tokens,
                result.output_tokens,
                result.cached_tokens,
                result.cost_usd,
                int(result.ogohlantirish),
            ),
        )
        conn.commit()
        conn.close()

    def _count(self, since_expr: str) -> tuple[int, float]:
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(cost_usd), 0) FROM vision_calls"
            f" WHERE created_at >= {since_expr}"
        ).fetchone()
        conn.close()
        return int(row[0]), float(row[1])

    def today(self) -> tuple[int, float]:
        return self._count("datetime('now', 'start of day')")

    def this_month(self) -> tuple[int, float]:
        return self._count("datetime('now', 'start of month')")

    def recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM vision_calls ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]


# ── Agent ────────────────────────────────────────────────────────────────


class VisionAgent:
    """Kadrni Claude ga yuborib, o‘zbekcha tahlil oladi.

    `client` testlar uchun tashqaridan beriladi — shunda testlar tarmoqqa
    chiqmaydi va pul sarflamaydi.
    """

    def __init__(
        self,
        config: VisionConfig,
        usage: UsageStore,
        *,
        client: Optional[Any] = None,
    ) -> None:
        self.config = config
        self.usage = usage
        self._client = client
        #: Kamera bo'yicha oxirgi tahlil vaqti — oraliqni ushlab turish uchun.
        self._last_call: Dict[str, float] = {}

    # ── Tormozlar ────────────────────────────────────────────────────────

    def budget_left(self) -> Dict[str, Any]:
        day_calls, day_cost = self.usage.today()
        month_calls, month_cost = self.usage.this_month()
        return {
            "today_calls": day_calls,
            "today_cost_usd": round(day_cost, 4),
            "today_left": max(0, self.config.max_calls_per_day - day_calls),
            "month_calls": month_calls,
            "month_cost_usd": round(month_cost, 4),
            "month_left": max(0, self.config.max_calls_per_month - month_calls),
        }

    def check_budget(self) -> None:
        left = self.budget_left()
        if left["today_left"] <= 0:
            raise BudgetExceeded(
                f"Kunlik limit tugadi ({self.config.max_calls_per_day} tahlil)"
            )
        if left["month_left"] <= 0:
            raise BudgetExceeded(
                f"Oylik limit tugadi ({self.config.max_calls_per_month} tahlil)"
            )

    def should_analyze(self, camera_id: str, *, now: Optional[float] = None) -> bool:
        """Shu kamera uchun oraliq o‘tganmi."""
        now = now if now is not None else time.time()
        last = self._last_call.get(camera_id)
        if last is None:
            return True
        return (now - last) >= self.config.min_interval_sec

    # ── Chaqiruv ─────────────────────────────────────────────────────────

    def _build_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import anthropic
        except ImportError as e:  # pragma: no cover — bog'liqlik yo'q
            raise VisionAgentError(
                "anthropic kutubxonasi yo‘q: pip install -r requirements-optional.txt"
            ) from e
        self._client = anthropic.Anthropic(timeout=self.config.timeout_sec)
        return self._client

    def analyze(
        self,
        jpeg_bytes: bytes,
        *,
        camera_id: str = "cam",
        question: Optional[str] = None,
        now: Optional[float] = None,
    ) -> VisionResult:
        """Bitta kadrni tahlil qiladi. Bloklovchi — threadda chaqiring."""
        if not jpeg_bytes:
            raise VisionAgentError("Kadr bo‘sh")
        self.check_budget()

        started = time.perf_counter()
        client = self._build_client()
        prompt = question or "Bu kadrda nima bo‘layapti?"

        try:
            response = client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        # Ko'rsatma har chaqiruvda bir xil — keshdan o'qilsa
                        # 10 barobar arzon.
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                output_config={
                    "effort": self.config.effort,
                    "format": {"type": "json_schema", "schema": RESPONSE_SCHEMA},
                },
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": base64.standard_b64encode(jpeg_bytes).decode(),
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )
        except Exception as e:
            raise VisionAgentError(f"AI chaqiruvi muvaffaqiyatsiz: {e}") from e

        result = self._parse(response, camera_id=camera_id)
        result.latency_ms = (time.perf_counter() - started) * 1000
        self._last_call[camera_id] = now if now is not None else time.time()
        self.usage.record(result)
        return result

    def _parse(self, response: Any, *, camera_id: str) -> VisionResult:
        # Xavfsizlik klassifikatori rad etsa `content` bo'sh bo'ladi —
        # `content[0]` ni tekshirmasdan o'qish shu yerda yiqilardi.
        if getattr(response, "stop_reason", None) == "refusal":
            raise VisionAgentError("AI bu kadrni tahlil qilishdan bosh tortdi")

        text = ""
        for block in getattr(response, "content", []) or []:
            if getattr(block, "type", None) == "text":
                text = block.text
                break
        if not text:
            raise VisionAgentError("AI javobi bo‘sh")

        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError) as e:
            raise VisionAgentError("AI javobi JSON emas") from e

        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        cached = int(getattr(usage, "cache_read_input_tokens", 0) or 0)

        return VisionResult(
            tavsif=str(data.get("tavsif", "")).strip(),
            odamlar=int(data.get("odamlar", 0) or 0),
            ogohlantirish=bool(data.get("ogohlantirish", False)),
            sabab=str(data.get("sabab", "")).strip(),
            camera_id=camera_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached,
            cost_usd=call_cost_usd(input_tokens, output_tokens, cached),
        )

    def status(self) -> Dict[str, Any]:
        cfg = self.config
        return {
            "enabled": cfg.enabled,
            "model": cfg.model,
            "effort": cfg.effort,
            "max_side": cfg.max_side,
            "min_interval_sec": cfg.min_interval_sec,
            "limits": {
                "per_day": cfg.max_calls_per_day,
                "per_month": cfg.max_calls_per_month,
            },
            "usage": self.budget_left(),
            "estimated_monthly_usd": round(
                estimate_monthly_usd(cfg.max_calls_per_day, cfg.max_side), 2
            ),
        }


__all__ = [
    "DEFAULT_MODEL",
    "BudgetExceeded",
    "RESPONSE_SCHEMA",
    "SYSTEM_PROMPT",
    "UsageStore",
    "VisionAgent",
    "VisionAgentError",
    "VisionConfig",
    "VisionResult",
    "call_cost_usd",
    "encode_frame",
    "estimate_monthly_usd",
    "image_tokens",
]
