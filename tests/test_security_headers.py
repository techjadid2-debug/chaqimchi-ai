"""Xavfsizlik sarlavhalari — ikkala Caddyfile'da bir xil.

Bu sinf tuzoq loyihada bir marta yeyilgan: `tests/test_proxy_limits.py`
uzoq vaqt faqat `deploy/Caddyfile` ni o'qigan, production esa
`deploy/Caddyfile.enes` bilan ishlagan — ya'ni test qo'riqlashi kerak
bo'lgan faylga umuman qaramagan.  Shuning uchun bu yerda sarlavhalar
IKKALA faylda ham va bir xil ekani tekshiriladi.
"""

from __future__ import annotations

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
    "Content-Security-Policy-Report-Only",
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
