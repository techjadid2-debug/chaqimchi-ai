#!/usr/bin/env python3
"""Bosh sahifa uchun mijoz panelining haqiqiy ekran rasmlarini oladi.

Nima uchun: sotuv sahifasida chizilgan illyustratsiya emas, **haqiqiy
interfeys** turishi kerak — do'kon egasi nima sotib olayotganini ko'rsin.
Bozor tadqiqotlari ham shuni aytadi: haqiqiy panel ekrani 3D grafikadan
ko'ra ko'proq mijoz keltiradi.

Nima "haqiqiy" va nima "demo":

- **Interfeys haqiqiy** — `cloud/static/owner.html` ning o'zi, o'z CSS va
  JS'i bilan, brauzerda chizilgan;
- **Raqamlar demo** — bu yerdagi `DEMO` javoblari.  Haqiqiy mijozning
  ismi, telefoni yoki do'kon nomi ISHLATILMAYDI.

Server ko'tarilmaydi va login qilinmaydi: Playwright `/api/v1/owner/*`
so'rovlarini ushlab, tayyor JSON qaytaradi.  Shu sabab natija
takrorlanadigan — bir xil raqamlar, bir xil rasm.

    python scripts/make_panel_screenshots.py

Chiqadi: `cloud/static/panel-*.webp` (har biri 200 KB dan kichik —
`tests/test_static_pages.py` shuni talab qiladi).
"""

from __future__ import annotations

import http.server
import json
import subprocess
import sys
import threading
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "cloud" / "static"

#: Rasm o'lchami.  Tor ataylab: keng oynada kartalar cho'zilib, o'ng
#: tomonda katta bo'sh joy qoladi va rasm saytda mayda ko'rinadi.
#: 820 px — issiqlik xaritasi kanvasi (640 px) kartani deyarli to'ldiradi.
VIEWPORT = {"width": 820, "height": 900}

#: 48×27 to'r — `EventStore.HEATMAP_COLS/ROWS` bilan bir xil.
HEAT_COLS, HEAT_ROWS = 48, 27


def _heat_grid() -> list:
    """Kirish eshigidan kassagacha yo'lak — ishonarli issiqlik naqshi."""
    grid = [[0] * HEAT_COLS for _ in range(HEAT_ROWS)]
    for col in range(HEAT_COLS):
        # Diagonal yo'lak: chap yuqoridan o'ng pastga.
        row = int(4 + (HEAT_ROWS - 9) * (col / max(1, HEAT_COLS - 1)))
        for offset in range(-3, 4):
            target = row + offset
            if 0 <= target < HEAT_ROWS:
                grid[target][col] += max(0, 90 - abs(offset) * 22)
    # Kassa oldida to'planish.
    for row in range(HEAT_ROWS - 10, HEAT_ROWS - 3):
        for col in range(HEAT_COLS - 12, HEAT_COLS - 4):
            grid[row][col] += 70
    return grid


#: Javob shakllari HAQIQIY: `EventStore.retail_report` / `traffic_trend`
#: / `heatmap` nima qaytarsa — shu.  Bir marta taxmin bilan yozilgan edi
#: va panel `traffic.entered` ni topa olmay yiqilgan, ekranda esa login
#: oynasi qolgan edi.
DEMO = {
    "/api/v1/owner/health": {
        "devices": [
            {
                "device_id": "dev-1",
                "received_at": "2026-08-20T18:04:00+00:00",
                "health": {"cpu_percent": 41, "temperature_c": 58, "cameras_ok": 4},
            }
        ],
        "cameras_expected": 4,
        "cameras_active": 4,
        "connection": "online",
        "site_name": "Namuna do'kon",
        "minutes_since_seen": 1,
        "plan": {
            "code": "biznes",
            "name": "Biznes",
            "max_cameras": 4,
            "max_employees": 10,
            "panel_features": [
                "bugun", "hisobot", "telegram", "navbat",
                "xavfsizlik", "xarita", "demografiya",
            ],
        },
    },
    "/api/v1/owner/cameras": {
        "cameras": [
            {"camera_id": "camera-01", "label": "Kirish eshigi", "enabled": True,
             "probe_status": "ok"},
            {"camera_id": "camera-02", "label": "Kassa", "enabled": True, "probe_status": "ok"},
            {"camera_id": "camera-03", "label": "Savdo zali", "enabled": True,
             "probe_status": "ok"},
            {"camera_id": "camera-04", "label": "Ombor", "enabled": True, "probe_status": "ok"},
        ]
    },
    "/api/v1/owner/report": {
        "date": "2026-08-20",
        "traffic": {
            "entered": 268,
            "exited": 261,
            "inside_estimate": 7,
            "entered_yesterday": 246,
            "change_percent": 8.9,
            "busiest_hour": {"hour": 18, "entered": 31, "exited": 29},
            "hourly": [
                {"hour": hour, "entered": entered, "exited": max(0, entered - 2)}
                for hour, entered in enumerate(
                    [0, 0, 0, 0, 0, 0, 0, 0, 0,
                     9, 14, 19, 23, 21, 17, 22, 26, 31, 27, 20, 12, 7, 0, 0]
                )
            ],
            "xodim_chiqarilgan": 34,
        },
        "queue": {"alerts": 3, "longest": 6, "longest_at": "18:20", "average": 2.4},
        "dwell": [
            {"zone": "Kassa", "count": 41, "average_sec": 96.4, "longest_sec": 312.0},
            {"zone": "Sut mahsulotlari", "count": 63, "average_sec": 48.2, "longest_sec": 187.0},
            {"zone": "Non javoni", "count": 55, "average_sec": 31.7, "longest_sec": 122.0},
        ],
        "security": {
            "camera_tampered": 0,
            "after_hours_presence": 0,
            "restricted_zone": 0,
            "loitering": 2,
        },
        "demografiya": {
            "hisoblangan": 214,
            "jins": {"ayol": 58, "erkak": 42},
            "yosh": {"<18": 11, "18-30": 78, "31-45": 62, "46-60": 43, "60+": 20},
        },
    },
    "/api/v1/owner/trend": {
        "from": "2026-08-14",
        "to": "2026-08-20",
        "days": 7,
        "daily": [
            {"date": "2026-08-14", "weekday": "Juma", "entered": 231},
            {"date": "2026-08-15", "weekday": "Shanba", "entered": 342},
            {"date": "2026-08-16", "weekday": "Yakshanba", "entered": 298},
            {"date": "2026-08-17", "weekday": "Dushanba", "entered": 214},
            {"date": "2026-08-18", "weekday": "Seshanba", "entered": 226},
            {"date": "2026-08-19", "weekday": "Chorshanba", "entered": 246},
            {"date": "2026-08-20", "weekday": "Payshanba", "entered": 268},
        ],
        "total": 1825,
        "average": 260.7,
        "busiest_day": "2026-08-15",
        "quietest_day": "2026-08-17",
        "previous_total": 1712,
        "change_percent": 6.6,
    },
    "/api/v1/owner/events": {"events": [], "total": 0},
    "/api/v1/owner/config": {
        "revision": 7,
        "config": {
            "camera_labels": {
                "camera-01": "Kirish eshigi",
                "camera-02": "Kassa",
                "camera-03": "Savdo zali",
                "camera-04": "Ombor",
            },
            "camera_roles": {"camera-01": "entrance", "camera-02": "checkout"},
            "occupancy_limit": 20,
            "queue_limit": 5,
            "loitering_sec": 300,
            "open_from": "09:00",
            "open_to": "21:00",
            "attendance_camera_ids": [],
            "attendance_camera_roles": {},
            "zones": [],
            "lines": [],
        },
    },
    "/api/v1/owner/members": {"members": []},
    "/api/v1/owner/invoices": {"invoices": []},
    "/api/v1/owner/features": {"features": [], "requested": []},
    "/api/v1/owner/faces": {"employees": [], "max_employees": 10, "mode": "commercial"},
    "/api/v1/owner/heatmap": {
        "camera_id": "camera-03",
        "date": "2026-08-20",
        "hour": None,
        "cols": HEAT_COLS,
        "rows": HEAT_ROWS,
        "grid": _heat_grid(),
        "frames": 96_000,
        "points": 18_420,
    },
}


#: Qaysi bo'lim qaysi faylga tushadi.  `selector` — kartani aniq kesib
#: olish uchun: butun sahifa surati mayda va o'qib bo'lmaydigan chiqadi.
SHOTS = (
    {
        "name": "panel-bugun",
        "hash": "#/bugun",
        "selector": "#paneBugun",
        "caption": "Kunlik hisobot: kirdi, chiqdi, gavjum soat",
    },
    {
        "name": "panel-xarita",
        # Rang oralig'i o'zgargach fayl nomi ham o'zgarishi SHART:
        # nom bir xil qolsa qaytgan mijoz brauzer keshidan eski qizil
        # xaritani oladi va sayt panelda yo'q rangni reklama qiladi.
        "version": "v2",
        "hash": "#/tahlil",
        "selector": "#heatCard",
        "caption": "Do'kon xaritasi: mijozlar eng ko'p yurgan joylar",
    },
)


class _Handler(http.server.SimpleHTTPRequestHandler):
    """`/assets/...` ni ham `static/` dan beradi.

    Panel CSS va ikonkalarni MUTLAQ yo'l bilan chaqiradi
    (`/assets/owner.css`) — cloud'da `StaticFiles` shu manzilga
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
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            # Token sahifa YUKLANISHIDAN OLDIN turishi shart: panel uni
            # skript boshida bir marta o'qiydi va bo'sh bo'lsa login
            # oynasini ko'rsatadi.  Avval `goto` qilib, keyin
            # `localStorage` ga yozish kech edi.
            context = browser.new_context(viewport=VIEWPORT, device_scale_factor=2)
            context.add_init_script(
                "localStorage.setItem('chaqimchi_owner_token', 'demo-token')"
            )
            page = context.new_page()

            def route_api(route):
                path = route.request.url.split("?", 1)[0]
                path = path[len(base):] if path.startswith(base) else path
                body = DEMO.get(path)
                if body is None:
                    route.fulfill(status=404, body='{"detail":"demo yo\'q"}',
                                  content_type="application/json")
                    return
                route.fulfill(
                    status=200, content_type="application/json",
                    body=json.dumps(body, ensure_ascii=False),
                )

            # Kamera oldindan ko'rish rasmi yo'q — xaritada oddiy kulrang
            # fon qoladi (kadr hali kelmagan do'kon holati).  Bu marshrut
            # BIRINCHI: Playwright'da keyingi qoida ustun turadi va
            # `cameras/**` `cameras` ro'yxatini ham ushlab qolardi.
            page.route(
                "**/api/v1/owner/cameras/*/preview",
                lambda r: r.fulfill(status=404, body=""),
            )
            page.route("**/api/v1/owner/**", route_api)

            messages = []
            page.on("console", lambda msg: messages.append(f"{msg.type}: {msg.text}"))
            page.on(
                "requestfailed",
                lambda req: messages.append(f"failed: {req.url}"),
            )

            for shot in SHOTS:
                page.goto(f"{base}/owner.html{shot['hash']}")
                page.wait_for_timeout(3000)
                for line in messages[:12]:
                    print(f"  konsol: {line}")
                messages.clear()
                # Yopishqoq sarlavha va pastdagi bo'lim paneli kartaning
                # chetlarini yopib qo'yadi — suratga olish paytida ularni
                # vaqtincha olib turamiz.
                page.evaluate(
                    "document.querySelectorAll('header,.topbar,.app-head,.tabbar')"
                    ".forEach((el) => (el.style.display = 'none'))"
                )
                node = page.query_selector(shot["selector"])
                if node is None:
                    print(f"OGOHLANTIRISH: {shot['selector']} topilmadi — o'tkazib yuborildi")
                    continue
                png = out_dir / f"{shot['name']}.png"
                node.screenshot(path=str(png))
                webp = out_dir / f"{shot['name']}-{shot.get('version', 'v1')}.webp"
                to_webp(png, webp)
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
