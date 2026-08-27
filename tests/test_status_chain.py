"""Hisoblagich zanjiri: zanjir → holat fayli → supervisor → heartbeat.

Nega bu test bor.  Qurilma o'lchagan raqam cloudga yetguncha **to'rtta**
qo'ldan o'tadi:

    RetailPipeline._stats()        (chaqimchi_ai/retail/pipeline.py)
      → write_status()             (chaqimchi_ai/retail/service.py)
        → RetailSupervisor.status()(chaqimchi_ai/local/supervisor.py)
          → send_heartbeat()       (chaqimchi_ai/local/cloud_config.py)

Har qo'lda kalit qo'lda ko'chiriladi va bittasini unutish **jimgina**
nolga aylantiradi: hisoblagich bor, so'rov bor, javob bor — faqat
qiymat doim nol.  Bu uch marta sodir bo'lgan:

1. `analyzed` / `errors` / `action_errors` — supervisor o'tkazmasdi,
   cloudning "qurilma jimgina o'lgan" detektori Windows'da umuman
   ishlamasdi;
2. `fps` / `inference_latency_ms` / `pressure` — admin paneldagi
   ustunlar hech qachon to'lmagan;
3. `face_crops` / `demography` (2026-08-26 da qo'shilib, 2026-08-27 da
   topilgan) — davomat va mijoz portreti diagnostikasi uch kun davomida
   YOLG'ON nol ko'rsatdi va bu "davomat o'chiq" degan noto'g'ri
   tashxisga olib keldi.  Aslida demografiya ishlayotgan edi.

Uchalasi ham koddan ko'rinmasdi, chunki har modul alohida to'g'ri edi.
Shuning uchun test modul ICHINI emas, **ular orasidagi zanjirni**
tekshiradi.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Set

ROOT = Path(__file__).resolve().parents[1]

#: Zanjirdan tashqarida tug'iladigan kalitlar — ular yuqoridagi manbadan
#: kelmaydi va yo'qligi xato emas.  Ro'yxat ATAYLAB qisqa: har yangi
#: yozuv "bu kalit qayerdan keladi" degan savolga javob talab qiladi.
OUTSIDE_THE_CHAIN = {
    # `runner.py:442,459` yozadi — zanjir statistikasi emas, oqim holati.
    "streams",
    "pressure",
    # Supervisor o'zi qo'yadi: holat fayli eskirganmi
    # (`supervisor.py:391`), zanjir o'lchovi emas.
    "stale",
}


def _function(relative: str, name: str) -> ast.FunctionDef:
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name}() topilmadi: {relative}")


def _reads(node: ast.AST, receiver: str) -> Set[str]:
    """`receiver.get("kalit")` — funksiya nimani KUTAYOTGANI."""
    found: Set[str] = set()
    for child in ast.walk(node):
        if (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr == "get"
            and isinstance(child.func.value, ast.Name)
            and child.func.value.id == receiver
            and child.args
            and isinstance(child.args[0], ast.Constant)
            and isinstance(child.args[0].value, str)
        ):
            found.add(child.args[0].value)
    return found


def _writes(node: ast.AST) -> Set[str]:
    """Funksiya ichidagi lug'at kalitlari — u nimani BERAYOTGANI."""
    found: Set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Dict):
            for key in child.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    found.add(key.value)
    return found


def test_the_status_file_gets_everything_it_asks_the_pipeline_for() -> None:
    stats = _writes(_function("chaqimchi_ai/retail/pipeline.py", "_stats"))
    write_status = _function("chaqimchi_ai/retail/service.py", "write_status")

    missing = _reads(write_status, "stats") - stats - OUTSIDE_THE_CHAIN

    assert missing == set(), (
        "`write_status()` zanjirdan yo'q kalitni so'rayapti — natija jimgina "
        f"nol bo'ladi: {sorted(missing)}"
    )


def test_the_supervisor_gets_everything_it_asks_the_status_file_for() -> None:
    written = _writes(_function("chaqimchi_ai/retail/service.py", "write_status"))
    supervisor = _function("chaqimchi_ai/local/supervisor.py", "status")

    missing = _reads(supervisor, "status_file") - written - OUTSIDE_THE_CHAIN

    assert missing == set(), (
        "`supervisor.status()` holat faylida yo'q kalitni so'rayapti: " f"{sorted(missing)}"
    )


def test_the_heartbeat_gets_everything_it_asks_the_supervisor_for() -> None:
    supervisor = _writes(_function("chaqimchi_ai/local/supervisor.py", "status"))
    heartbeat = _function("chaqimchi_ai/local/cloud_config.py", "send_heartbeat")

    missing = _reads(heartbeat, "status") - supervisor - OUTSIDE_THE_CHAIN

    assert missing == set(), (
        "`send_heartbeat()` supervisor bermaydigan kalitni so'rayapti — cloudga "
        f"doim nol boradi: {sorted(missing)}"
    )


def test_the_diagnostics_that_answer_does_attendance_work_survive_the_whole_chain() -> None:
    """Nomma-nom qulf: bu ikkitasi aynan shu zanjirda uzilgan edi.

    Yuqoridagi uchta test umumiy qoidani tekshiradi; bu esa 2026-08-27 da
    topilgan aniq holatni qaytib kelishidan saqlaydi.
    """
    chain = [
        _writes(_function("chaqimchi_ai/retail/pipeline.py", "_stats")),
        _writes(_function("chaqimchi_ai/retail/service.py", "write_status")),
        _writes(_function("chaqimchi_ai/local/supervisor.py", "status")),
        _writes(_function("chaqimchi_ai/local/cloud_config.py", "send_heartbeat")),
    ]

    for key in ("face_crops", "demography", "clips"):
        for step, keys in enumerate(chain):
            assert key in keys, f"'{key}' zanjirning {step + 1}-bo'g'inida yo'qolgan"
