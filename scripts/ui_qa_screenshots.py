#!/usr/bin/env python3
"""Panel va sayt skrinshot QA harnesi.

`make_panel_screenshots.py` sotuv rasmini oladi; bu skript esa SIFATNI
tekshiradi: har marshrutni ikki tema × uch til × ikki kenglikda ochadi
va ko'z bilan ko'rmasdan ham tutiladigan nuqsonlarni sanaydi:

  * gorizontal toshish (`scrollWidth > clientWidth`) — telefonda sahifa
    yon tomonga «yuradi»;
  * ekranda xom i18n kaliti (`panel.x.y`) — katalogga kirmagan matn;
  * `console.error` va yuklanmagan resurs;
  * 3.5 soniyadan keyin ham turgan skelet — «yuklanmoqda» tugamagan;
    `--fail-api` rejimida (hamma API 500) skelet umuman qolmasligi shart —
    bir marta xato chizig'i bilan yonma-yon abadiy skelet turib qolgan edi;
  * `.page-actions` ichida ko'rinadigan tugmalar soni — telefonda
    sahifaning asosiy tugmalari yo'qolib qolmasin.

Nega mock API: haqiqiy cloud'siz, ma'lumot bazasisiz va tarmoqsiz
ishlaydi — deploydan oldin ham, CI'da ham (Playwright bo'lsa).
Chiqish katalogi ataylab loyihadan tashqarida (`--out`): suratlar
repoga tushmasin.

Ishlatish (avval `make ui-build` — qurilgan bundle suratga olinadi):

    .venv/bin/python scripts/ui_qa_screenshots.py --out /tmp/qa
    .venv/bin/python scripts/ui_qa_screenshots.py --out /tmp/qa --fail-api
    .venv/bin/python scripts/ui_qa_screenshots.py --out /tmp/qa --site
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from make_panel_screenshots import CAMERA_FRAMES, DEMO, NOW, STATIC, serve  # noqa: E402

#: Ega panelining hamma marshrutlari — yon menyu (8) + bo'lim tablari.
PANEL_ROUTES = (
    "home", "cameras", "cameras/setup", "cameras/zones",
    "alerts", "alerts/agent", "employees",
    "customers", "customers/demography", "customers/heatmap",
    "analytics", "reports",
    "settings", "settings/telegram", "settings/billing", "settings/branches",
)

#: Sayt sahifalari — statik HTML, `build_site.py` chiqishi.
SITE_PAGES = ("site.html", "site.ru.html", "site.en.html", "404.html", "aloqa.html")

#: Katalogga kirmagan kalit ekranda shu ko'rinishda qoladi.
RAW_KEY = re.compile(r"\b(?:panel|site|event|chart|digest)\.[a-z_]+(?:\.[a-z0-9_]+)+\b")

#: `tests/test_static_pages.py` bilan bir xil emoji qoidasi — sayt ikonka
#: sprite'dan foydalanadi, emoji shrift va platformaga qarab har xil chiqadi.
#: Tipografik belgilar (✓ → ·) ruxsat etilgan — ular hamma joyda bir xil.
ALLOWED_GLYPHS = set("─✓○★☑→←·")


def emoji_in(text: str) -> list[str]:
    return sorted({
        ch for ch in text
        if ord(ch) > 0x2100 and ch not in ALLOWED_GLYPHS and unicodedata.category(ch) == "So"
    })

#: Skelet yuklanish bilan birga yo'qolishi kerak bo'lgan muddat.  3.5 s:
#: mock API zudlik bilan javob beradi, panelning sekin so'rovi ham (kamera
#: kadri 3×15 s emas) shu vaqtda birinchi natijani ko'rsatadi.
SETTLE_MS = 3500

CHECKS_JS = """() => {
  const doc = document.documentElement;
  const visible = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  return {
    overflow: doc.scrollWidth - doc.clientWidth,
    text: document.body.innerText,
    skeletons: [...document.querySelectorAll('.skeleton')].filter(visible).length,
    actions: [...document.querySelectorAll('.page-actions button, .page-actions a, .page-actions .btn')].filter(visible).length,
    navHasButton: /button/i.test((document.querySelector('nav') || {}).outerHTML || ''),
  };
}"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", required=True, type=Path, help="suratlar va hisobot katalogi")
    parser.add_argument("--routes", default=",".join(PANEL_ROUTES))
    parser.add_argument("--themes", default="light,dark")
    parser.add_argument("--langs", default="uz,ru,en")
    parser.add_argument("--widths", default="390,1280")
    parser.add_argument("--fail-api", action="store_true", help="dashboard/sites dan boshqa hamma owner API 500 qaytaradi")
    parser.add_argument("--site", action="store_true", help="panel o'rniga sayt sahifalari")
    return parser.parse_args()


#: `--fail-api` rejimida ham javob beradigan yo'llar: ularsiz panel
#: umuman ochilmaydi («aloqa yo'q» ekrani) va sahifa skeletlari
#: tekshirilmay qoladi.
BOOTSTRAP = ("/api/v1/owner/dashboard", "/api/v1/owner/sites")


def make_api_router(base: str, fail: bool):
    def route_api(route):
        path = route.request.url.split(base)[-1].split("?")[0]
        if fail and path not in BOOTSTRAP:
            route.fulfill(status=500, content_type="application/json",
                          body='{"detail":"Internal Server Error"}')
            return
        body = DEMO.get(path)
        if body is None:
            route.fulfill(status=404, content_type="application/json",
                          body='{"detail":"demo yo\'q"}')
            return
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps(body, ensure_ascii=False))
    return route_api


def make_frame_router(frames: list[bytes]):
    counter = {"index": 0}

    def route_frame(route):
        frame = frames[counter["index"] % len(frames)]
        counter["index"] += 1
        route.fulfill(status=200, content_type="image/webp", body=frame,
                      headers={"X-Frame-At": NOW.isoformat()})
    return route_frame


def run_panel(play, base: str, args: argparse.Namespace) -> dict:
    frames = [(STATIC / name).read_bytes() for name in CAMERA_FRAMES]
    report: dict[str, dict] = {}
    browser = play.chromium.launch()
    for theme in args.themes.split(","):
        for lang in args.langs.split(","):
            for width in (int(w) for w in args.widths.split(",")):
                mobile = width < 700
                context = browser.new_context(
                    viewport={"width": width, "height": 844 if mobile else 900},
                    device_scale_factor=2 if mobile else 1,
                    is_mobile=mobile, has_touch=mobile,
                )
                # Token sahifa yuklanishidan OLDIN turishi shart — panel uni
                # boshida bir marta o'qiydi, bo'sh bo'lsa login oynasi qoladi.
                context.add_init_script(
                    "localStorage.setItem('enes_owner_token','demo-token');"
                    f"localStorage.setItem('enes_theme','{theme}');"
                    f"localStorage.setItem('enes_lang','{lang}');"
                )
                page = context.new_page()
                console: list[str] = []
                page.on("console", lambda m: console.append(m.text[:160]) if m.type == "error" else None)
                page.on("pageerror", lambda e: console.append(f"pageerror: {str(e)[:160]}"))
                # Umumiy qoida BIRINCHI, aniq yo'llar KEYIN: oxirgi mos qoida ustun.
                page.route("**/api/v1/owner/**", make_api_router(base, args.fail_api))
                if not args.fail_api:
                    page.route("**/api/v1/owner/cameras/*/preview", make_frame_router(frames))
                    page.route("**/api/v1/owner/cameras/*/live-frame", make_frame_router(frames))
                for route in args.routes.split(","):
                    console.clear()
                    page.goto(f"{base}/v2/owner.html#/{route}", wait_until="networkidle", timeout=45_000)
                    page.wait_for_timeout(SETTLE_MS)
                    result = page.evaluate(CHECKS_JS)
                    name = f"{theme}_{lang}_{width}_{route.replace('/', '-')}"
                    page.screenshot(path=str(args.out / f"panel_{name}.png"), full_page=True)
                    # Service worker `owner-sw.js` statik serverda yo'q — bu
                    # tekshiruvga aloqasi yo'q, shovqin qilmasin.
                    # `--fail-api` da 500 — rejimning o'zi; u nuqson emas.
                    noise = [c for c in console if "owner-sw" not in c and "404" not in c
                             and not (args.fail_api and "500" in c)]
                    report[name] = {
                        "overflow": result["overflow"],
                        "raw_keys": sorted(set(RAW_KEY.findall(result["text"]))),
                        "skeletons": result["skeletons"],
                        "actions": result["actions"],
                        "console": noise[:5],
                    }
                context.close()
    browser.close()
    return report


def run_site(play, base: str, args: argparse.Namespace) -> dict:
    report: dict[str, dict] = {}
    browser = play.chromium.launch()
    for width in (int(w) for w in args.widths.split(",")):
        mobile = width < 700
        context = browser.new_context(
            viewport={"width": width, "height": 844 if mobile else 900},
            device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile,
        )
        page = context.new_page()
        console: list[str] = []
        page.on("console", lambda m: console.append(m.text[:160]) if m.type == "error" else None)
        page.on("pageerror", lambda e: console.append(f"pageerror: {str(e)[:160]}"))
        # Narx va reliz — saytning ikki tashqi so'rovi; mock javob sahifani
        # to'liq holatda (tarif kartalari bilan) suratga olish uchun.
        page.route("**/api/v1/public/**", lambda r: r.fulfill(
            status=200, content_type="application/json", body="{}"))
        for name in SITE_PAGES:
            if not (STATIC / name).is_file():
                continue
            console.clear()
            page.goto(f"{base}/{name}", wait_until="networkidle", timeout=45_000)
            page.wait_for_timeout(800)
            result = page.evaluate(CHECKS_JS)
            key = f"{width}_{name.replace('.html', '')}"
            page.screenshot(path=str(args.out / f"site_{key}.png"), full_page=True)
            report[key] = {
                "overflow": result["overflow"],
                "raw_keys": sorted(set(RAW_KEY.findall(result["text"]))),
                "emoji": emoji_in(result["text"]),
                "nav_button": result["navHasButton"],
                "console": [c for c in console if "404" not in c][:5],
            }
        context.close()
    browser.close()
    return report


def main() -> int:
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright

    base, server = serve(STATIC)
    try:
        with sync_playwright() as play:
            report = run_site(play, base, args) if args.site else run_panel(play, base, args)
    finally:
        server.shutdown()

    (args.out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    failures = 0
    for name, row in report.items():
        flags = []
        if row["overflow"] > 0:
            flags.append(f"TOSHISH+{row['overflow']}px")
        if row["raw_keys"]:
            flags.append("XOM_KALIT=" + ",".join(row["raw_keys"][:3]))
        if row.get("skeletons"):
            flags.append(f"SKELET={row['skeletons']}")
        if row.get("emoji"):
            flags.append("EMOJI=" + "".join(row["emoji"]))
        if row.get("nav_button"):
            flags.append("NAV_BUTTON")
        if row["console"]:
            flags.append("KONSOL=" + " | ".join(row["console"][:2]))
        if flags:
            failures += 1
        actions = f" tugma={row['actions']}" if "actions" in row else ""
        print(f"{name:44s}{actions:10s} {' '.join(flags) or 'ok'}")
    print(f"\n{len(report)} surat, {failures} nuqsonli → {args.out}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
