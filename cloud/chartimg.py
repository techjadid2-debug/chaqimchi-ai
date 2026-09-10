"""Telegram uchun grafik rasmlar — kunlik va haftalik hisobot, tungi kadr.

Nega rasm.  Matnli hisobotdagi `▁▂▅█` blok-grafik telefonda o'qiladi,
lekin «qaysi soat gavjum, kecha bilan farq qancha» degan savolga ko'z
bilan bir qarashda javob bermaydi.  Rasm — xabarning birinchi ekrani,
matn esa tafsilot uchun ostida qoladi (`digest._deliver`).

Nega Pillow, cv2 emas.  Cloud konteynerida `cv2` allaqachon bor, lekin
`cv2.putText` kirillcha yozolmaydi — rus tilidagi a'zo bo'sh
to'rtburchaklar olardi.  Pillow + repo ichidagi DejaVu shrifti
(`cloud/assets/fonts/`, Bitstream Vera litsenziyasi) uch tilni ham
chizadi; `python:3.12-slim` da tizim shrifti yo'q, shuning uchun
shrift repoda.

Hammasi xotirada (`BytesIO`): konteyner `read_only`, disk yo'q.
Ranglar `cloud/static/tokens.css` ning YORUG' palitrasidan qo'lda
ko'chirilgan — Telegram xabari mijozning temasiga qaramaydi.
"""

from __future__ import annotations

import logging
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from cloud import botfmt
from cloud.i18n import tg

logger = logging.getLogger(__name__)

FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
FONT_REGULAR = FONT_DIR / "DejaVuSans.ttf"
FONT_BOLD = FONT_DIR / "DejaVuSans-Bold.ttf"

#: Rasm o'lchami.  Telegram rasmni ~1280 px gacha siqadi; 1200×600 da
#: yozuvlar telefonda ham o'qiladi, fayl esa 100 KB atrofida.
WIDTH, HEIGHT = 1200, 600
#: Rasm shundan katta bo'lsa nimadir noto'g'ri (Telegram chegarasi 10 MB,
#: lekin do'kon egasining trafigi arzon bo'lsin).
MAX_BYTES = 1_000_000

# tokens.css (yorug'): --surface, --surface-2, --fg, --muted, --border,
# --accent, --green, --yellow, --red.
BG = "#ffffff"
BG_SOFT = "#f4f7fb"
FG = "#0a0e14"
MUTED = "#5a6675"
BORDER = "#e3e8ef"
BLUE = "#2f8bff"
GREEN = "#34a853"
YELLOW = "#fbbc05"
RED = "#ea4335"


def _fonts(size: int, bold: bool = False):
    from PIL import ImageFont

    return ImageFont.truetype(str(FONT_BOLD if bold else FONT_REGULAR), size)


def _canvas():
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    return image, ImageDraw.Draw(image)


def _png(image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    data = buffer.getvalue()
    if len(data) > MAX_BYTES:
        # Sifatni tushirib bo'lmaydi (PNG), lekin bu holat amalda bo'lmaydi:
        # 1200×600 chizma ~100 KB.  Katta chiqsa — logga, xabar baribir ketadi.
        logger.warning("Grafik rasmi kutilganidan katta: %d bayt", len(data))
    return data


def _bars(draw, *, values: Sequence[float], labels: Sequence[str], box, color: str,
          label_every: int = 1, ghost: Optional[Sequence[float]] = None) -> None:
    """Ustunlar `box=(x0, y0, x1, y1)` ichida.  `ghost` — xira taqqoslash qatori."""
    x0, y0, x1, y1 = box
    count = max(1, len(values))
    peak = max([*values, *(ghost or []), 1.0])
    slot = (x1 - x0) / count
    gap = max(2, slot * 0.18)
    font = _fonts(15)
    small = _fonts(14, bold=True)
    for line in range(1, 4):
        y = y1 - (y1 - y0) * line / 4
        draw.line([(x0, y), (x1, y)], fill=BORDER, width=1)
    for index, value in enumerate(values):
        left = x0 + index * slot + gap / 2
        right = left + slot - gap
        if ghost is not None and index < len(ghost):
            gh = y1 - (y1 - y0) * (ghost[index] / peak)
            draw.rectangle([left + (right - left) * 0.5, gh, right, y1], fill=BORDER)
        top = y1 - (y1 - y0) * (value / peak)
        if value > 0:
            draw.rounded_rectangle([left, top, right, y1], radius=4, fill=color)
            text = botfmt.number(int(value))
            tw = draw.textlength(text, font=small)
            draw.text(((left + right) / 2 - tw / 2, top - 22), text, font=small, fill=FG)
        if index % label_every == 0 and index < len(labels):
            tw = draw.textlength(labels[index], font=font)
            draw.text(((left + right) / 2 - tw / 2, y1 + 10), labels[index], font=font, fill=MUTED)


def _header(draw, title: str, subtitle: str, right: str = "") -> None:
    draw.text((48, 36), title, font=_fonts(34, bold=True), fill=FG)
    draw.text((48, 84), subtitle, font=_fonts(20), fill=MUTED)
    if right:
        font = _fonts(26, bold=True)
        draw.text((WIDTH - 48 - draw.textlength(right, font=font), 44), right, font=font, fill=BLUE)


def _legend(draw, items: Sequence[tuple[str, str]], y: int) -> None:
    font = _fonts(16)
    x = 48
    for label, color in items:
        draw.rounded_rectangle([x, y + 3, x + 14, y + 17], radius=3, fill=color)
        draw.text((x + 22, y), label, font=font, fill=MUTED)
        x += 22 + draw.textlength(label, font=font) + 28


def daily_png(report: Dict[str, Any], lang: str, *, site_name: str = "") -> bytes:
    """Kunning soatlik kirdi (ustun) va chiqdi (chiziq) grafigi."""
    traffic = report.get("traffic") or {}
    hourly = traffic.get("hourly") or []
    entered = [float((item or {}).get("entered") or 0) for item in hourly]
    exited = [float((item or {}).get("exited") or 0) for item in hourly]
    labels = [f"{int((item or {}).get('hour') or index):02d}" for index, item in enumerate(hourly)]
    image, draw = _canvas()
    day = str(report.get("date") or "")
    title = tg(lang, "chart.daily.title", site=site_name or "", day=botfmt.day_title(day + "T12:00:00+05:00", lang) or day).strip(" —")
    busiest = traffic.get("busiest_hour") or {}
    subtitle = tg(lang, "chart.daily.busiest", hour=f"{int(busiest.get('hour') or 0):02d}") if busiest else tg(lang, "chart.no_data")
    _header(draw, title, subtitle, tg(lang, "chart.total", count=botfmt.number(int(traffic.get("entered") or 0), lang)))
    box = (48, 150, WIDTH - 48, HEIGHT - 80)
    if entered:
        _bars(draw, values=entered, labels=labels, box=box, color=BLUE, label_every=2)
        # Chiqdi — chiziq: ikkinchi ustun qatori 24 soatda o'qilmas bo'lardi.
        peak = max([*entered, *exited, 1.0])
        slot = (box[2] - box[0]) / len(entered)
        points = [
            (box[0] + (index + 0.5) * slot, box[3] - (box[3] - box[1]) * (value / peak))
            for index, value in enumerate(exited)
        ]
        if len(points) > 1:
            draw.line(points, fill=GREEN, width=3, joint="curve")
    _legend(draw, [(tg(lang, "chart.entered"), BLUE), (tg(lang, "chart.exited"), GREEN)], HEIGHT - 40)
    return _png(image)


def weekly_png(trend: Dict[str, Any], lang: str, *, site_name: str = "") -> bytes:
    """Hafta kunlari bo'yicha kirdi; o'tgan hafta xira ustun bilan taqqoslanadi."""
    daily: List[Dict[str, Any]] = list(trend.get("daily") or [])
    values = [float(item.get("entered") or 0) for item in daily]
    labels = []
    for item in daily:
        try:
            labels.append(botfmt.weekday_name(date.fromisoformat(str(item.get("date"))).weekday(), lang))
        except (TypeError, ValueError):
            labels.append(str(item.get("weekday") or ""))
    image, draw = _canvas()
    change = trend.get("change_percent")
    if change is None:
        subtitle = tg(lang, "chart.weekly.range", start=str(trend.get("from") or ""), end=str(trend.get("to") or ""))
    else:
        arrow = "▲" if change >= 0 else "▼"
        subtitle = tg(lang, "digest.weekly.vs_previous", arrow=arrow, percent=abs(change))
    _header(
        draw,
        tg(lang, "chart.weekly.title", site=site_name or "").strip(" —"),
        subtitle,
        tg(lang, "chart.total", count=botfmt.number(int(trend.get("total") or 0), lang)),
    )
    # O'tgan hafta faqat YIG'INDI sifatida ma'lum — uni kunlarga teng
    # taqsimlab «xira ustun» qilib chizish: taqqoslash uchun yetarli,
    # kunlik aniqlik da'vo qilinmaydi.
    previous = trend.get("previous_total")
    ghost = None
    if previous and values:
        ghost = [float(previous) / len(values)] * len(values)
    if values:
        _bars(draw, values=values, labels=labels, box=(48, 150, WIDTH - 48, HEIGHT - 80), color=BLUE, ghost=ghost)
    legend = [(tg(lang, "chart.entered"), BLUE)]
    if ghost:
        legend.append((tg(lang, "chart.weekly.previous"), BORDER))
    _legend(draw, legend, HEIGHT - 40)
    return _png(image)


def annotate_snapshot(jpeg: bytes, title: str, subtitle: str = "") -> bytes:
    """Kadr ustiga tasma: «23:41 · Kassa» va oy belgisi (tungi hodisa).

    Xato bo'lsa ASL kadr qaytadi — annotatsiya bezak, xabar esa
    yetib borishi shart.
    """
    try:
        from PIL import Image, ImageDraw

        image = Image.open(BytesIO(jpeg)).convert("RGB")
        width, height = image.size
        band = max(44, height // 11)
        overlay = Image.new("RGBA", (width, band), (10, 14, 20, 200))
        draw = ImageDraw.Draw(overlay)
        size = max(18, band // 2)
        # Oy belgisi: sariq doira ustiga tasma rangidagi doira — emoji
        # shriftga bog'liq emas, har muhitda bir xil.
        radius = size // 2
        cx, cy = 16 + radius, band // 2
        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=YELLOW)
        draw.ellipse([cx - radius + radius * 0.7, cy - radius - radius * 0.3, cx + radius + radius * 0.7, cy + radius - radius * 0.3], fill=(10, 14, 20, 200))
        x = cx + radius + 14
        draw.text((x, cy - size // 2 - 2), title, font=_fonts(size, bold=True), fill="#ffffff")
        if subtitle:
            x += draw.textlength(title, font=_fonts(size, bold=True)) + 16
            draw.text((x, cy - size // 2), subtitle, font=_fonts(max(14, size - 4)), fill="#d5dbe6")
        image.paste(overlay, (0, 0), overlay)
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=85)
        return buffer.getvalue()
    except Exception:  # noqa: BLE001 — bezak xabarni yiqitmasin
        logger.warning("Tungi kadr annotatsiyasi chizilmadi", exc_info=True)
        return jpeg
