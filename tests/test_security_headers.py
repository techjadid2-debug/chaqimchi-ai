"""Xavfsizlik sarlavhalari — ikkala Caddyfile'da bir xil.

Bu sinf tuzoq loyihada bir marta yeyilgan: `tests/test_proxy_limits.py`
uzoq vaqt faqat `deploy/Caddyfile` ni o'qigan, production esa
`deploy/Caddyfile.enes` bilan ishlagan — ya'ni test qo'riqlashi kerak
bo'lgan faylga umuman qaramagan.  Shuning uchun bu yerda sarlavhalar
IKKALA faylda ham va bir xil ekani tekshiriladi.
"""

from __future__ import annotations

import base64
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CADDYFILES = {
    "prod": ROOT / "deploy" / "Caddyfile",
    "enes": ROOT / "deploy" / "Caddyfile.enes",
}

#: Har javobda bo'lishi shart bo'lgan sarlavhalar.
REQUIRED = (
    "Strict-Transport-Security",
    "X-Content-Type-Options",
    "X-Frame-Options",
    "Referrer-Policy",
    "Permissions-Policy",
    "Content-Security-Policy",
)


def _csp(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(r'Content-Security-Policy(?:-Report-Only)?\s+"([^"]+)"', text)
    assert match, f"{path.name}: CSP sarlavhasi yo'q"
    return " ".join(match.group(1).split())


def test_both_caddyfiles_send_the_same_security_headers() -> None:
    for name, path in CADDYFILES.items():
        text = path.read_text(encoding="utf-8")
        for header in REQUIRED:
            assert header in text, f"{name}: `{header}` yo'q"

    assert _csp(CADDYFILES["prod"]) == _csp(CADDYFILES["enes"]), (
        "ikki Caddyfile'dagi CSP ajralib ketdi"
    )


def test_the_policy_is_enforced_not_report_only() -> None:
    """`-Report-Only` qaytib kelmasin.

    Kuzatuv rejimi hech narsani bloklamaydi — faqat konsolga yozadi.
    2026-09-12 da siyosat majburiy qilindi; sarlavha nomiga qo'shilgan
    bitta so'z butun himoyani jimgina o'chiradi va `REQUIRED` dagi
    `"Content-Security-Policy" in text` tekshiruvi buni KO'RMAYDI
    (u ham `-Report-Only` nomining ichida turadi).
    """
    for name, path in CADDYFILES.items():
        text = path.read_text(encoding="utf-8")
        offending = [
            line.strip()
            for line in text.splitlines()
            if "Content-Security-Policy-Report-Only" in line and not line.lstrip().startswith("#")
        ]
        assert not offending, f"{name}: siyosat kuzatuv rejimida qolib ketdi: {offending}"


def test_the_policy_still_blocks_the_dangerous_sources() -> None:
    """Siyosat bo'shab ketmasin.

    `script-src` ga `'unsafe-inline'` qo'shilishi butun CSP ning
    ma'nosini yo'qotadi — XSS aynan shu yo'l bilan ishlaydi.  Inline
    skriptlar tashqi faylga chiqarilishi kerak, siyosat esa emas.
    """
    policy = _csp(CADDYFILES["enes"])

    directives = dict(
        (part.split(None, 1) + [""])[:2]
        for part in (item.strip() for item in policy.split(";"))
        if part
    )

    assert "'unsafe-inline'" not in directives["script-src"]
    assert "'unsafe-eval'" not in directives["script-src"]
    assert directives["default-src"] == "'self'"
    assert directives["object-src"] == "'none'"
    # `X-Frame-Options: DENY` ning zamonaviy juftligi — ikkalasi ham
    # bo'lsin, eski brauzerlar CSP ni tushunmaydi.
    assert directives["frame-ancestors"] == "'none'"


def test_the_telegram_mini_app_sdk_is_allowed() -> None:
    """Panel qobig'i SDK'ni telegram.org dan yuklaydi; ro'yxatda
    bo'lmasa Mini App ichida kirish jimgina parol so'rashga aylanardi."""
    shell = (ROOT / "frontend" / "owner.html").read_text(encoding="utf-8")
    assert "https://telegram.org/js/telegram-web-app.js" in shell

    assert "https://telegram.org" in _csp(CADDYFILES["enes"])


# ── Inline skriptlar: CSP ni majburiy qilishga to'sqinlik qiladigan narsa ──
#
# `script-src` da `'unsafe-inline'` yo'q, ya'ni sahifadagi har bir
# ijro etiladigan `<script>` bloki va har bir `onclick="…"` atributi
# jonli saytda ISHLAMAY qoladi.  Brauzer buni ekranda ko'rsatmaydi —
# tugma shunchaki bosilmaydi.  Shu sabab qoida test bilan qulflanadi.

STATIC = ROOT / "cloud" / "static"

#: Ijro etiladigan inline blok.  `type="application/json"` va
#: `application/ld+json` — «data block»: brauzer ularni bajarmaydi va
#: CSP ham ularga tegmaydi, shuning uchun ro'yxatdan chiqariladi.
_INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)([^>]*)>(.*?)</script>", re.S)
_INLINE_HANDLER = re.compile(r"\son[a-z]+\s*=\s*[\"']")


def _executable_inline_blocks(text: str) -> list[str]:
    return [body for attrs, body in _INLINE_SCRIPT.findall(text) if "json" not in attrs]


def _csp_hash(body: str) -> str:
    return "sha256-" + base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode()


def test_no_page_carries_an_inline_event_handler() -> None:
    """`onclick="…"` — CSP ostida o'lik tugma."""
    offenders = [
        str(path.relative_to(ROOT))
        for path in sorted(STATIC.rglob("*.html"))
        if _INLINE_HANDLER.search(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, "inline ishlov beruvchi (`data-act` + delegatsiya ishlating):\n" + "\n".join(offenders)


def test_every_inline_script_is_covered_by_a_hash() -> None:
    """Qolgan har bir inline blok siyosatda hash bilan ruxsat etilgan bo'lsin.

    Bugun bittasi bor: panel qobig'idagi tema bootstrap'i, u birinchi
    chizishdan OLDIN ishlashi shart (tashqi faylga chiqarilsa sahifa
    bir zumga yorug' ochilib, keyin qorayadi).  Skript o'zgarsa hash
    ham o'zgaradi va bu test yangi qiymatni aytadi — Caddyfile'ga
    o'shani qo'ying.
    """
    policy = _csp(CADDYFILES["enes"])
    missing = []
    for path in sorted(STATIC.rglob("*.html")):
        for body in _executable_inline_blocks(path.read_text(encoding="utf-8")):
            digest = _csp_hash(body)
            if f"'{digest}'" not in policy:
                missing.append(f"{path.relative_to(ROOT)}: '{digest}'")

    assert not missing, (
        "siyosatda hash yo'q — skriptni tashqi faylga chiqaring yoki "
        "quyidagini `script-src` ga qo'shing:\n" + "\n".join(missing)
    )


def test_the_shell_theme_script_is_the_only_hashed_one() -> None:
    """Hash ro'yxati o'smasin.

    Har yangi hash — qo'lda sinxron saqlanadigan yana bitta qiymat.
    Yangi inline skript yozish o'rniga uni `/assets/*.js` ga chiqaring;
    server qo'yadigan qiymat esa `application/json` blokiga (u ijro
    etilmaydi, ya'ni hash kerak emas).
    """
    policy = _csp(CADDYFILES["enes"])
    assert policy.count("sha256-") == 1, "faqat tema bootstrap'i hashda bo'lsin"

    shells = [STATIC / "v2" / "owner.html", STATIC / "v2" / "admin.html"]
    bodies = {body for page in shells for body in _executable_inline_blocks(page.read_text(encoding="utf-8"))}
    assert len(bodies) == 1, "ikkala qobiqda tema skripti AYNAN bir xil bo'lsin — hash bitta"
    assert "localStorage.getItem" in next(iter(bodies))
