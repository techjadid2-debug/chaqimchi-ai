"""CI ishining kontrakti.

CI `make test` ni to'liq chaqirishi kerak, `pytest` ni emas.  Sabab
tarixiy: ish faqat `ruff` va `pytest -q` chaqirganda `i18n/*.json`
o'zgarib `catalogue.generated.ts` qayta qurilmagan, yoki
`cloud/site/*.html` o'zgarib `cloud/static/*.html` yangilanmagan commit
CI'da **yashil** bo'lardi — xato esa faqat deploydan keyin, panelda
eski matn ko'rinishida chiqardi.  `make test` shu uch tekshiruvni
(`ui-check`, `build_i18n --check`, `build_site --check`) pytest'dan
oldin bajaradi.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def _commands() -> str:
    """Ishning BUYRUQLARI — izohlarsiz.

    Izoh ichida buyruq nomi uchrashi mumkin (masalan «`npm install`
    emas» degan izoh), shuning uchun tekshiruv `#` dan keyingi qismni
    tashlab yuboradi.
    """
    lines = []
    for line in WORKFLOW.read_text(encoding="utf-8").splitlines():
        code = line.split("#", 1)[0]
        if code.strip():
            lines.append(code)
    return "\n".join(lines)


def test_ci_runs_the_whole_make_test() -> None:
    commands = _commands()

    assert "make test" in commands, "CI to'liq `make test` ni chaqirsin"
    assert "make lint" in commands, "ruff ham Makefile orqali — ro'yxat bir joyda"
    # To'g'ridan-to'g'ri chaqiruv `make test` ning oldingi qadamlarini
    # (typecheck, katalog, sayt) chetlab o'tadi.
    assert "pytest" not in commands, "pytest to'g'ridan-to'g'ri chaqirilmasin"
    assert "ruff" not in commands, "ruff to'g'ridan-to'g'ri chaqirilmasin"


def test_ci_installs_node_for_the_typecheck() -> None:
    """`make test` birinchi qadami `ui-check`, u esa `frontend/node_modules`
    yo'q bo'lsa ishni yiqitadi — ya'ni Node CI uchun ixtiyoriy emas."""
    commands = _commands()

    assert "actions/setup-node" in commands
    # `npm ci` lockfile'dan o'rnatadi.  `npm install` bo'lsa
    # `package.json` dagi `latest` versiyalar CI'ni har kuni boshqa
    # kutubxona bilan ishga tushirardi.
    assert "npm ci" in commands
    assert "npm install" not in commands
    assert (ROOT / "frontend" / "package-lock.json").is_file()
