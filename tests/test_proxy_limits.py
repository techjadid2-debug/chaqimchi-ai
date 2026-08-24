"""Proxy (Caddy) limitlari app limitlaridan katta ekanini tekshiradi.

Bu sinf testlar umuman yo'q edi va aynan shu tirqishdan jiddiy xato
o'tib ketgan: `cloud/main.py` 50 MB gacha klip qabul qiladi, lekin
`deploy/Caddyfile` `max_size 10MB` bilan turgan.  Haqiqiy hodisa kliplari
15-22 MB chiqadi — Caddy ularni app'gacha yetkazmay 413 qaytarar,
edge 20 urinishdan keyin klipni dead_letter'ga tashlar va "hodisa videosi"
funksiyasi productionda jimgina ishlamas edi.  FastAPI darajasidagi
testlar buni ko'rmaydi, chunki ular proxy'siz ishlaydi — shuning uchun
bu fayl Caddyfile matnini o'zini tekshiradi.
"""

from __future__ import annotations

import re
from pathlib import Path

from cloud.main import CLIP_MAX_BYTES, SNAPSHOT_MAX_BYTES

ROOT = Path(__file__).resolve().parents[1]

#: Ikkala Caddyfile ham tekshiriladi.  Bungacha faqat `deploy/Caddyfile`
#: o'qilardi, holbuki **productionda `Caddyfile.chaqimchi` ishlatiladi**
#: (`docker-compose.chaqimchi.yml`).  Ya'ni bu test o'zi qo'riqlashi kerak
#: bo'lgan faylga umuman qaramas edi — va `Caddyfile.chaqimchi` ichidagi
#: `api.` izohida esa "tests/test_proxy_limits.py mosligini tekshiradi"
#: deb yozib qo'yilgan edi.  Soxta ishonch.
CADDYFILES = {
    "prod": ROOT / "deploy" / "Caddyfile",
    "chaqimchi": ROOT / "deploy" / "Caddyfile.chaqimchi",
}

_UNITS = {"KB": 1024, "MB": 1024**2, "GB": 1024**3}


def _vhost_limits(path: Path) -> dict[str, int]:
    """Har bir vhost uchun `max_size` (bayt).

    `Caddyfile.chaqimchi` da yettita turli `max_size` bor (1MB dan 60MB
    gacha).  Butun fayl bo'ylab birinchi mos kelganini olish — aynan
    shu testdagi xato edi: u `chaqimchi.uz` ning 5MB'ini topib,
    "limit klipdan kichik" deb yiqilardi yoki, aksincha, noto'g'ri
    vhostni tasdiqlardi.  Klip esa `api.` ga yuklanadi.
    """
    limits: dict[str, int] = {}
    host: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Vhost blokining boshi: chekinishsiz `nom {`.
        if not raw[:1].isspace() and line.endswith("{") and not line.startswith("("):
            host = line[:-1].strip()
            continue
        match = re.search(r"max_size\s+(\d+)\s*(KB|MB|GB)", line)
        if match and host:
            limits[host] = int(match.group(1)) * _UNITS[match.group(2)]
    return limits


def test_klip_yuklanadigan_vhost_limiti_yetarli() -> None:
    """Klip yuklanadigan vhost limiti `CLIP_MAX_BYTES` dan katta bo'lsin.

    Klip `PUT /api/v1/edge/events/{id}/clip` ga boradi, ya'ni
    `api.chaqimchi.uz` ga.  Teng bo'lishi ham yetarli emas: Content-Length
    dan tashqari header va chunk overhead bor.
    """
    for label, path in CADDYFILES.items():
        limits = _vhost_limits(path)
        assert limits, f"{path.name}: birorta max_size topilmadi"
        # Bitta vhostli fayl (prod) — o'sha yagona qiymat; subdomenli
        # faylda esa aynan API vhosti.
        api = [v for host, v in limits.items() if host.startswith("api.")]
        target = api[0] if api else next(iter(limits.values()))
        assert target > CLIP_MAX_BYTES, (
            f"{path.name} ({label}): klip yuklanadigan vhost limiti "
            f"{target} bayt, cloud esa {CLIP_MAX_BYTES} bayt qabul qiladi — "
            "kliplar proxy'da 413 bilan qaytadi va cloudga yetmaydi"
        )


def test_production_caddyfile_ham_tekshiriladi() -> None:
    """`Caddyfile.chaqimchi` haqiqatan o'qilyaptimi.

    Bu testning o'zi tirqishni qo'riqlaydi: kimdir yana faqat bitta
    faylni tekshiradigan qilib qo'ysa, shu yerda ushlanadi.
    """
    limits = _vhost_limits(CADDYFILES["chaqimchi"])
    assert "api.chaqimchi.uz" in limits, (
        "Productionda ishlatiladigan Caddyfile'da api vhosti topilmadi — "
        "test noto'g'ri faylga qarayotgan bo'lishi mumkin"
    )
    # Subdomenli faylda bir nechta turli limit borligi — normal holat.
    assert len(set(limits.values())) > 1


def test_klip_limiti_snapshot_limitidan_katta() -> None:
    # Sanity: konstantalar chalkashtirilmaganini ushlab turadi.
    assert CLIP_MAX_BYTES > SNAPSHOT_MAX_BYTES


def test_http3_advertised_bo_lsa_udp_porti_ochiq_bo_lsin() -> None:
    """Caddy HTTP/3 ni o'zi yoqadi — UDP porti ham ochiq bo'lishi shart.

    Docker standart holda faqat TCP ni ochadi.  UDP yo'q bo'lsa Caddy
    `alt-svc: h3=":443"` deb e'lon qilaveradi, brauzer QUIC'ga urinadi,
    paket konteynerga yetmaydi va u TCP'ga qaytadi — har ulanishda
    bekorga kutish.  Jonli saytda o'lchandi: sarlavha bor edi, port yopiq.
    """
    import yaml

    for name in ("docker-compose.chaqimchi.yml", "docker-compose.prod.yml"):
        compose = yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))
        ports = [str(p) for p in compose["services"]["caddy"]["ports"]]
        assert "443:443" in ports, f"{name}: HTTPS uchun TCP porti yo'q"
        assert "443:443/udp" in ports, (
            f"{name}: 443/udp yo'q — Caddy HTTP/3 ni e'lon qiladi, lekin "
            "QUIC paketlari konteynerga yetmaydi"
        )


def test_har_bir_reverse_proxy_haqiqiy_mijoz_manzilini_yuboradi() -> None:
    """Mijoz yuborgan `X-Forwarded-For` qabul qilinmasin.

    Caddy standart holda mijoz yuborgan qiymatga O'ZINIKINI QO'SHADI, uvicorn
    esa `--forwarded-allow-ips "*"` bilan ro'yxatdagi eng CHAPDAGI qiymatni
    oladi (`uvicorn/middleware/proxy_headers.py`: `always_trust` →
    `x_forwarded_for_hosts[0]`).  Ya'ni mijoz o'zi `X-Forwarded-For: 1.2.3.4`
    yozib yuborsa, server o'shani haqiqiy manzil deb bilardi.

    Oqibati: IP bo'yicha BARCHA cheklovlar aylanib o'tilardi — bepul sinovga
    ro'yxatdan o'tish (soatiga 3 ta), kirish urinishlari, ariza yuborish.
    Sarlavhani har safar qayta yozib chiqish kifoya edi.

    Yechim: Caddy qiymatni qo'shmaydi, ALMASHTIRADI.  Shunda uvicorn `*`
    bilan ham to'g'ri manzilni oladi.
    """
    for name, path in CADDYFILES.items():
        text = path.read_text(encoding="utf-8")
        proxies = text.count("reverse_proxy cloud:8750")
        guards = text.count("header_up X-Forwarded-For {remote_host}")
        assert proxies > 0, f"{path.name}: reverse_proxy topilmadi"
        assert guards == proxies, (
            f"{path.name} ({name}): {proxies} ta reverse_proxy bor, lekin "
            f"{guards} tasida X-Forwarded-For almashtirilyapti — qolganida "
            "mijoz o'z manzilini o'zi yozib yubora oladi"
        )


def test_statik_fayllarda_kesh_muddati_bor() -> None:
    """`Cache-Control` bo'lmasa brauzer har safar qayta so'rab chiqadi.

    Starlette `StaticFiles` faqat `ETag` va `Last-Modified` qo'yadi —
    ular "o'zgardimi?" degan savolga javob beradi, lekin savolning
    O'ZINI yo'qotmaydi.  Natijada qayta kelgan mijoz bosh sahifa uchun
    14 ta bekorga borib-kelish qiladi; Toshkentdan serverga bitta
    borib-kelish ~120 ms (jonli o'lchov).

    Mazmun bo'yicha nomlangan fayl (`?v=<hash>`) hech qachon o'zgarmaydi,
    ya'ni uni bir yilga keshlash xavfsiz.
    """
    for name, path in CADDYFILES.items():
        text = path.read_text(encoding="utf-8")
        assert "Cache-Control" in text, (
            f"{path.name} ({name}): statik fayllar uchun Cache-Control yo'q — "
            "keshlash ishlamaydi va har tashrifda hamma fayl qayta so'raladi"
        )
        assert "immutable" in text, (
            f"{path.name} ({name}): `?v=<hash>` li fayllar uchun `immutable` "
            "yo'q — mazmun bo'yicha nomlangan fayl bekorga qayta so'raladi"
        )


def test_owner_pwa_worker_app_subdomainida_ochiq() -> None:
    """V2 panel worker'ni ro'yxatdan o'tkazadi; Caddy uni 404 qilmasin."""
    text = CADDYFILES["chaqimchi"].read_text(encoding="utf-8")
    app_block = text.split("app.chaqimchi.uz {", 1)[1].split("partner.chaqimchi.uz {", 1)[0]
    assert "/owner-sw.js" in app_block


def test_ulash_ekrani_uchun_zarur_yollar_app_subdomainida_ochiq() -> None:
    """Ega qurilmani ulayotganda hali HISOBSIZ bo'lishi mumkin.

    `device-connect` (qurilmani ko'rsatish) va `quick-trial` (ro'yxatdan
    o'tish) `/api/v1/owner/*` ostiga tushmaydi, ya'ni ular alohida
    ruxsat etilishi kerak.  Ro'yxatda bo'lmasa panel «Havola eskirgan»
    deb ko'rsatadi va sabab hech qayerda ko'rinmaydi: Caddy jimgina 404
    qaytaradi, bulut log'ida esa hech narsa yo'q.

    2026-08-24 da deploy'dan keyin aynan shu bo'ldi.
    """
    text = CADDYFILES["chaqimchi"].read_text(encoding="utf-8")
    app_block = text.split("app.chaqimchi.uz {", 1)[1].split("partner.chaqimchi.uz {", 1)[0]

    for path in ("/api/v1/public/device-connect", "/api/v1/public/quick-trial"):
        assert path in app_block, (
            f"{path} app.chaqimchi.uz ruxsat ro'yxatida yo'q — "
            "qurilmani ulash ekrani ishlamaydi"
        )
    # Tasdiqlash va kirish allaqachon qamrab olingan — ular ham
    # yo'qolmasin.
    assert "/api/v1/owner/*" in app_block
    assert "/api/v1/auth/*" in app_block
