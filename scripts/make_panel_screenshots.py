#!/usr/bin/env python3
"""Bosh sahifa uchun mijoz panelining haqiqiy ekran rasmlarini oladi.

Nima uchun: sotuv sahifasida chizilgan illyustratsiya emas, **haqiqiy
interfeys** turishi kerak — do'kon egasi nima sotib olayotganini ko'rsin.

Nima "haqiqiy" va nima "demo":

- **Interfeys haqiqiy** — `cloud/static/v2/owner.html` ning o'zi, o'z CSS
  va JS'i bilan, brauzerda chizilgan;
- **Raqamlar demo** — bu yerdagi `DEMO` javoblari.  Haqiqiy mijozning
  ismi, telefoni yoki do'kon nomi ISHLATILMAYDI.

Server ko'tarilmaydi va login qilinmaydi: Playwright `/api/v1/owner/*`
so'rovlarini ushlab, tayyor JSON qaytaradi.  Shu sabab natija
takrorlanadigan — bir xil raqamlar, bir xil rasm.

    python scripts/make_panel_screenshots.py

Chiqadi: `cloud/static/panel-*.webp` (har biri 200 KB dan kichik —
`tests/test_static_pages.py` shuni talab qiladi).

2026-08-24: eski panel (`owner.html`) o'rniga v2 panel suratga olinadi.
Ilgari sayt eski yashil-krem interfeysni reklama qilardi, mijoz esa
ochganda butunlay boshqa ko'k panelni ko'rardi.
"""

from __future__ import annotations

import http.server
import json
import math
import subprocess
import sys
import threading
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "cloud" / "static"

#: Rasm o'lchami.  Tor ataylab: keng oynada kartalar cho'zilib, o'ng
#: tomonda katta bo'sh joy qoladi va rasm saytda mayda ko'rinadi.
VIEWPORT = {"width": 980, "height": 900}

#: 48×27 to'r — `EventStore.HEATMAP_COLS/ROWS` bilan bir xil.
HEAT_COLS, HEAT_ROWS = 48, 27

NOW = datetime(2026, 8, 24, 18, 40)
TODAY = NOW.date().isoformat()


#: Do'kondagi to'planish joylari: (ustun, qator, kuch) — nisbiy
#: koordinatalarda.  Haqiqiy do'konda odam bir tekis yurmaydi: u
#: javon oldida to'xtaydi, kassada navbatda turadi va yo'lakdan
#: shunchaki o'tib ketadi.
HEAT_SPOTS = (
    (0.14, 0.22, 1.00),  # kirish eshigi
    (0.34, 0.20, 0.72),  # birinchi javon
    (0.58, 0.18, 0.90),  # aksiya javoni
    (0.80, 0.24, 0.66),
    (0.20, 0.62, 0.78),  # muzlatgich
    (0.46, 0.58, 0.55),
    (0.74, 0.66, 0.95),  # kassa navbati
    (0.90, 0.48, 0.40),
)


def _heat_grid() -> list:
    """Javon oldidagi to'planishlar — ishonarli issiqlik naqshi.

    Bungacha bu bitta diagonal yo'lak edi va rasmda uzun yashil chiziq
    bo'lib chiqardi: do'kon xaritasiga o'xshamasdi.  Endi bir nechta
    alohida issiq nuqta — mijoz rasmga qarab "javon oldida to'xtashadi"
    degan xulosani o'zi chiqaradi.
    """
    grid = [[0.0] * HEAT_COLS for _ in range(HEAT_ROWS)]
    for row in range(HEAT_ROWS):
        for col in range(HEAT_COLS):
            x = col / max(1, HEAT_COLS - 1)
            y = row / max(1, HEAT_ROWS - 1)
            total = 0.0
            for spot_x, spot_y, strength in HEAT_SPOTS:
                # Gauss: markazda kuchli, chekkasida tez so'nadi.
                dx, dy = (x - spot_x) / 0.055, (y - spot_y) / 0.085
                total += strength * math.exp(-(dx * dx + dy * dy) / 2)
            # Yo'laklardagi yengil o'tish oqimi — to'liq bo'sh joy
            # bo'lmasin, aks holda xarita "o'lik" ko'rinadi.
            total += 0.07 * math.exp(-(((y - 0.42) / 0.18) ** 2) / 2)
            grid[row][col] = round(total * 100, 1)
    return grid


#: Soatlik oqim: ertalab sekin, tushda va kechqurun ikkita cho'qqi.
_HOURLY = [0, 0, 0, 0, 0, 0, 2, 9, 21, 34, 47, 58, 63, 55, 44, 51, 62, 71, 66, 52, 33, 18, 6, 1]

#: Javob shakllari HAQIQIY: `EventStore.retail_report` va
#: `owner_dashboard` nima qaytarsa — shu.  Bir marta taxmin bilan
#: yozilgan edi va panel `traffic.entered` ni topa olmay yiqilgan,
#: ekranda esa login oynasi qolgan edi.
DEMO = {
    "/api/v1/owner/sites": {
        "sites": [
            {
                "id": "demo-1",
                "name": "Namuna do‘kon — Markaziy",
                "address": "Toshkent sh., Chilonzor",
                "connection": "online",
                "cameras_active": 4,
                "cameras_expected": 4,
            },
            {
                "id": "demo-2",
                "name": "Namuna do‘kon — Yunusobod",
                "address": "Toshkent sh., Yunusobod",
                "connection": "online",
                "cameras_active": 3,
                "cameras_expected": 3,
            },
        ]
    },
    "/api/v1/owner/dashboard": {
        "site": {
            "id": "demo-1",
            "name": "Namuna do‘kon — Markaziy",
            "address": "Toshkent sh., Chilonzor",
            "connection": "online",
            "minutes_since_seen": 1,
            "cameras_active": 4,
            "cameras_expected": 4,
            "plan": {"name": "Biznes"},
        },
        "today": {
            "date": TODAY,
            "traffic": {
                "entered": 268,
                "exited": 261,
                "inside_estimate": 7,
                "entered_yesterday": 246,
                "change_percent": 8.9,
                "busiest_hour": {"hour": 17, "entered": 71},
                "hourly": [
                    {"hour": hour, "entered": entered, "exited": max(0, entered - 2)}
                    for hour, entered in enumerate(_HOURLY)
                ],
                "xodim_chiqarilgan": 34,
            },
            "queue": {"alerts": 3, "longest": 6, "longest_at": "18:20", "average": 2.4},
            "dwell": [
                {"zone": "Kassa", "count": 41, "average_sec": 96.4, "longest_sec": 312.0},
                {"zone": "Sut mahsulotlari", "count": 63, "average_sec": 48.2, "longest_sec": 187.0},
                {"zone": "Non javoni", "count": 55, "average_sec": 31.7, "longest_sec": 122.0},
                {"zone": "Kirish eshigi", "count": 22, "average_sec": 18.5, "longest_sec": 64.0},
            ],
            "security": {
                "camera_tampered": 0,
                "after_hours_presence": 0,
                "restricted_zone": 0,
                "loitering": 2,
            },
        },
        "cameras": [
            {"camera_id": "camera-01", "label": "Kirish eshigi", "enabled": True},
            {"camera_id": "camera-02", "label": "Kassa zonasi", "enabled": True},
            {"camera_id": "camera-03", "label": "Savdo zali", "enabled": True},
            {"camera_id": "camera-04", "label": "Ombor", "enabled": True},
        ],
        "camera_states": [
            {"camera_id": "camera-01", "state": "online", "reason": "Kadr 2 soniya oldin"},
            {"camera_id": "camera-02", "state": "online", "reason": "Kadr 1 soniya oldin"},
            {"camera_id": "camera-03", "state": "online", "reason": "Kadr 3 soniya oldin"},
            {"camera_id": "camera-04", "state": "online", "reason": "Kadr 2 soniya oldin"},
        ],
        "events": [
            {"id": "e1", "event_type": "queue_threshold_exceeded", "label": "Kassada navbat ortdi",
             "camera_id": "Kassa zonasi", "occurred_at": f"{TODAY}T18:20:00"},
            {"id": "e2", "event_type": "loitering", "label": "Zonada uzoq turish",
             "camera_id": "Sut mahsulotlari", "occurred_at": f"{TODAY}T17:48:00"},
            {"id": "e3", "event_type": "line_crossed", "label": "Kirish cho‘qqisi qayd etildi",
             "camera_id": "Kirish eshigi", "occurred_at": f"{TODAY}T17:05:00"},
            {"id": "e4", "event_type": "queue_threshold_exceeded", "label": "Kassada navbat ortdi",
             "camera_id": "Kassa zonasi", "occurred_at": f"{TODAY}T13:12:00"},
            {"id": "e5", "event_type": "loitering", "label": "Zonada uzoq turish",
             "camera_id": "Non javoni", "occurred_at": f"{TODAY}T11:34:00"},
        ],
        "trend": [
            {"date": (NOW - timedelta(days=offset)).date().isoformat(), "entered": entered}
            for offset, entered in zip(range(13, -1, -1),
                                       [214, 226, 246, 231, 342, 298, 221, 238, 259, 244, 271, 233, 246, 268])
        ],
        "subscription": {
            "status": "active",
            "days_left": 24,
            "monthly_price_uzs": 299_000,
            "subscription_until": (NOW + timedelta(days=24)).isoformat(),
        },
        "updated_at": NOW.isoformat(),
    },
    # Davomat va Telegram — bo'sh: sotuv sahifasida yopiq pilot
    # funksiyalari va'da qilinmasin.
    "/api/v1/owner/members": {"members": []},
    "/api/v1/owner/heatmap": {
        "camera_id": "camera-03",
        "date": TODAY,
        "hour": None,
        "cols": HEAT_COLS,
        "rows": HEAT_ROWS,
        "grid": _heat_grid(),
        "frames": 96_000,
        "points": 18_420,
    },
}

#: Kamera plitkalari uchun haqiqiy kadr o'rniga do'kon fotosuratlari.
#: Bo'sh plitka ("Kadr kelmadi") sotuv sahifasida tizim ishlamayotgandek
#: ko'rinardi.
CAMERA_FRAMES = ["design2-retail.webp", "design2-aisle.webp", "design2-warehouse.webp"]

#: Qaysi bo'lim qaysi faylga tushadi.  Sahifa yuklangach `hide` dagi
#: elementlar olib tashlanadi va `selector` kesib olinadi: butun sahifa
#: surati mayda va o'qib bo'lmaydigan chiqadi.
SHOTS = (
    {
        "name": "panel-bugun",
        "version": "v3",
        "route": "#/home",
        "selector": ".content",
        # Saytda rasm ~570 px kenglikda ko'rinadi: uzun ustun mayda va
        # o'qib bo'lmaydigan bo'lib qoladi.  Shuning uchun o'ng ustun
        # (hodisalar, tarif, Telegram), faol zonalar va filiallar
        # jadvali kesiladi — ular ikkinchi rasmda va panelning o'zida
        # baribir ko'rinadi.
        "hide": [
            ".sidebar", ".topbar", ".bottom-nav",
            ".home-grid > .stack:last-child",
            ".split-grid > .card:last-child",
            ".home-grid > .stack > .card:last-child",
        ],
        # To'rtta kamera kadri rasmning katta qismini tashkil qiladi va
        # 82 sifatda fayl 200 KB chegarasidan oshib ketadi.  Fotoda
        # 68 sifat ko'z bilan sezilmaydi, matn esa baribir tiniq
        # qoladi — u alohida qatlam emas, bir xil siqiladi.
        "quality": 68,
        "caption": "Kunlik hisobot: kirdi, gavjum soat, jonli kameralar",
    },
    {
        "name": "panel-xarita",
        "version": "v4",
        "route": "#/heatmap",
        "selector": ".content",
        "hide": [".sidebar", ".topbar", ".bottom-nav"],
        "caption": "Do‘kon xaritasi: mijozlar eng ko‘p yurgan joylar",
    },
)


class _Handler(http.server.SimpleHTTPRequestHandler):
    """`/assets/...` ni ham `static/` dan beradi.

    Panel CSS va ikonkalarni MUTLAQ yo'l bilan chaqiradi
    (`/assets/v2/assets/...`) — cloud'da `StaticFiles` shu manzilga
    ulangan.  Buni takrorlamasak sahifa uslubsiz chiqadi.
    """

    def translate_path(self, path: str) -> str:
        if path.startswith("/assets/"):
            path = path[len("/assets") :]
        return super().translate_path(path)

    def log_message(self, *args) -> None:  # noqa: D102 - jim ishlasin
        pass


def serve(directory: Path) -> tuple[str, http.server.HTTPServer]:
    handler = partial(_Handler, directory=str(directory))
    server = http.server.HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_port}", server


def to_webp(png: Path, webp: Path, quality: int = 82) -> None:
    """PNG → WebP.  cwebp bo'lmasa Pillow, u ham bo'lmasa PNG qoladi."""
    if subprocess.run(["which", "cwebp"], capture_output=True).returncode == 0:
        subprocess.run(
            ["cwebp", "-quiet", "-q", str(quality), str(png), "-o", str(webp)], check=True
        )
        return
    try:
        from PIL import Image
    except ImportError:
        raise SystemExit(
            "XATO: WebP uchun `cwebp` (brew install webp) yoki Pillow kerak"
        ) from None
    Image.open(png).save(webp, "WEBP", quality=quality, method=6)


def main() -> int:
    from playwright.sync_api import sync_playwright

    base, server = serve(STATIC)
    out_dir = STATIC
    frames = [(STATIC / name).read_bytes() for name in CAMERA_FRAMES]

    try:
        with sync_playwright() as play:
            browser = play.chromium.launch()
            # Token sahifa YUKLANISHIDAN OLDIN turishi shart: panel uni
            # skript boshida bir marta o'qiydi va bo'sh bo'lsa login
            # oynasini ko'rsatadi.
            # 1.5× — retinada ham tiniq, lekin 2× dagi kamera kadrlari
            # rasmni 200 KB chegarasidan chiqarib yuborardi.
            context = browser.new_context(viewport=VIEWPORT, device_scale_factor=1.5)
            context.add_init_script(
                "localStorage.setItem('chaqimchi_owner_token_v2', 'demo-token')"
            )
            page = context.new_page()

            def route_api(route):
                path = route.request.url.split(base)[-1].split("?")[0]
                body = DEMO.get(path)
                if body is None:
                    route.fulfill(status=404, body='{"detail":"demo yo\'q"}',
                                  content_type="application/json")
                    return
                route.fulfill(
                    status=200, content_type="application/json",
                    body=json.dumps(body, ensure_ascii=False),
                )

            # Umumiy qoida BIRINCHI, aniq yo'llar KEYIN: Playwright'da
            # oxirgi mos qoida ustun turadi.  Teskarisi bo'lsa
            # `cameras/**` kamera ro'yxatini ham ushlab qolardi.
            page.route("**/api/v1/owner/**", route_api)

            counter = {"index": 0}

            def route_frame(route):
                frame = frames[counter["index"] % len(frames)]
                counter["index"] += 1
                route.fulfill(status=200, content_type="image/webp", body=frame)

            page.route("**/api/v1/owner/cameras/*/preview*", route_frame)
            page.route("**/api/v1/owner/cameras/*/live-frame*", route_frame)

            messages: list[str] = []
            page.on("console", lambda msg: messages.append(f"{msg.type}: {msg.text}"))
            page.on("requestfailed", lambda req: messages.append(f"failed: {req.url}"))

            for shot in SHOTS:
                page.goto(f"{base}/v2/owner.html{shot['route']}")
                page.wait_for_timeout(3500)
                for line in messages[:12]:
                    print(f"  konsol: {line}")
                messages.clear()

                # Yopishqoq sarlavha, yon menyu va pastdagi bo'lim
                # paneli kartaning chetlarini yopib qo'yadi.
                page.evaluate(
                    "(selectors) => selectors.forEach((selector) => {"
                    "  document.querySelectorAll(selector).forEach((el) => el.remove());"
                    "})",
                    shot["hide"],
                )
                page.evaluate(
                    "() => { const main = document.querySelector('.main-shell');"
                    "  if (main) main.style.paddingLeft = '0';"
                    "  const content = document.querySelector('.content');"
                    "  if (content) content.style.padding = '20px'; }"
                )
                page.wait_for_timeout(400)

                node = page.query_selector(shot["selector"])
                if node is None:
                    print(f"OGOHLANTIRISH: {shot['selector']} topilmadi — o'tkazib yuborildi")
                    continue
                png = out_dir / f"{shot['name']}.png"
                node.screenshot(path=str(png))
                webp = out_dir / f"{shot['name']}-{shot['version']}.webp"
                to_webp(png, webp, quality=shot.get("quality", 82))
                png.unlink(missing_ok=True)
                size_kb = webp.stat().st_size // 1024
                print(f"OK: {webp.name} ({size_kb} KB) — {shot['caption']}")
                if size_kb >= 200:
                    print("  DIQQAT: 200 KB dan katta — test yiqiladi, sifatni pasaytiring")
            browser.close()
    finally:
        server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
