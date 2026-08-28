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


# ── Teskari yo'nalish: ishlab chiqarilgan kalit YO'QOLMASIN ──────────────
#
# Yuqoridagi testlar "so'ralgan kalit bormi" ni tekshiradi va aynan shu
# ularning ko'r nuqtasi edi: kalit UNUTILGANDA hech kim uni so'ramaydi,
# ya'ni yuqoridagi testlar ham jim qoladi.  Uch marta takrorlangan xato
# aynan shunday o'tgan.
#
# Quyidagi ro'yxatlar ATAYLAB uzun va sababli: yangi hisoblagich
# qo'shgan odam uni cloudga yubormasa, testni yashil qilish uchun shu
# yerga yozib, NEGA yubormasligini aytishi kerak bo'ladi.


def _returned_keys(node: ast.AST) -> Set[str]:
    """Faqat QAYTARILADIGAN lug'atning birinchi darajali kalitlari.

    `_writes` ichma-ich lug'atlarni ham yig'adi va teskari tekshiruv
    uchun bu juda shovqinli: "written", "found", "attempts" kabi ichki
    kalitlar bo'g'indan bo'g'inga ko'chmaydi, chunki ular butun lug'at
    bilan birga uzatiladi.
    """
    for child in ast.walk(node):
        target = None
        if isinstance(child, ast.Return) and isinstance(child.value, ast.Dict):
            target = child.value
        elif isinstance(child, ast.Assign) and isinstance(child.value, ast.Dict):
            names = [item.id for item in child.targets if isinstance(item, ast.Name)]
            if any(name in ("payload", "status") for name in names):
                target = child.value
        if target is not None:
            return {
                key.value
                for key in target.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
    raise AssertionError("qaytariladigan lug'at topilmadi")


#: Zanjir statistikasidan holat fayliga ATAYLAB o'tmaydiganlar.
STATS_STAYS_LOCAL = {
    "offered": "brokerning ichki hisobi — panelda ham ko'rsatilmaydi",
    "gated": "harakat filtri o'tkazganlari — nosozlik belgisi emas",
    "suppressed": "qoidalarning ongli qarori (cooldown), xato emas",
    "actions": "harakatlar kesimi — faqat lokal jurnal uchun",
    "after_hours": "hodisa sifatida allaqachon cloudga boradi",
    "tamper_alerts": "hodisa sifatida allaqachon cloudga boradi",
    "freezes": "hodisa sifatida allaqachon cloudga boradi",
    "broker": "faqat `fps` va `p95_latency_ms` olinadi (service.py)",
}

#: Holat faylidan supervisorga o'tmaydiganlar.
STATUS_FILE_STAYS_LOCAL = {
    "pid": "supervisor uni ALOHIDA o'qiydi (yetim zanjirni topish uchun)",
    "updated_at": "`status_stale` ga aylanadi (supervisor.py)",
}

#: Supervisordan cloudga o'tmaydiganlar.
SUPERVISOR_STAYS_LOCAL = {
    "running": "aloqaning o'zi qurilma tirikligini bildiradi",
    "auto_restart": "lokal panel sozlamasi",
    "started_at": "cloud `uptime_sec` ni mashinadan oladi",
    "uptime_sec": "zanjirniki; cloudga MASHINA uptime'i boradi (_system_metrics)",
    "retry_in_sec": "lokal paneldagi 'necha daqiqadan keyin urinadi'",
    "error": "oxirgi xato matni — lokal panelda ko'rsatiladi",
    "log_path": "diskdagi yo'l, cloudda ma'nosi yo'q",
    # Nomi o'zgarganlar: qiymat cloudga BORADI, faqat kalit boshqa.
    "errors": "cloudga `analysis_errors` nomi bilan boradi",
    "action_errors": "cloudga `queue_errors` nomi bilan boradi",
    "restart_count": "cloudga `chain_restarts` nomi bilan boradi",
    "fps": "cloudga `_system_metrics()` orqali qo'shiladi",
    "inference_latency_ms": "cloudga `_system_metrics()` orqali qo'shiladi",
}


def test_nothing_the_pipeline_measures_is_silently_dropped() -> None:
    stats = _returned_keys(_function("chaqimchi_ai/retail/pipeline.py", "_stats"))
    written = _returned_keys(_function("chaqimchi_ai/retail/service.py", "write_status"))

    dropped = stats - written - set(STATS_STAYS_LOCAL)

    assert dropped == set(), (
        "zanjir o'lchagan, holat fayliga yozilmagan: "
        f"{sorted(dropped)} — yuboring yoki STATS_STAYS_LOCAL ga sabab bilan qo'shing"
    )


def test_nothing_in_the_status_file_is_silently_dropped() -> None:
    written = _returned_keys(_function("chaqimchi_ai/retail/service.py", "write_status"))
    supervisor = _returned_keys(_function("chaqimchi_ai/local/supervisor.py", "status"))

    dropped = written - supervisor - set(STATUS_FILE_STAYS_LOCAL)

    assert dropped == set(), (
        "holat faylida bor, supervisor o'tkazmagan: "
        f"{sorted(dropped)} — o'tkazing yoki STATUS_FILE_STAYS_LOCAL ga qo'shing"
    )


def test_nothing_the_supervisor_knows_is_silently_dropped() -> None:
    """Zanjirning eng ko'p uziladigan bo'g'ini — uchala xato ham shu yerda."""
    supervisor = _returned_keys(_function("chaqimchi_ai/local/supervisor.py", "status"))
    heartbeat = _returned_keys(_function("chaqimchi_ai/local/cloud_config.py", "send_heartbeat"))

    dropped = supervisor - heartbeat - set(SUPERVISOR_STAYS_LOCAL)

    assert dropped == set(), (
        "supervisor biladi, cloud bilmaydi: "
        f"{sorted(dropped)} — yuboring yoki SUPERVISOR_STAYS_LOCAL ga sabab bilan qo'shing"
    )


def test_every_reason_in_the_allowlists_is_a_sentence() -> None:
    """Ro'yxatga qo'shish ARZON bo'lmasin: sabab yozilishi shart."""
    for name, mapping in (
        ("STATS_STAYS_LOCAL", STATS_STAYS_LOCAL),
        ("STATUS_FILE_STAYS_LOCAL", STATUS_FILE_STAYS_LOCAL),
        ("SUPERVISOR_STAYS_LOCAL", SUPERVISOR_STAYS_LOCAL),
    ):
        for key, reason in mapping.items():
            assert len(reason) >= 15, f"{name}['{key}'] sababi juda qisqa: {reason!r}"


def test_the_new_clip_diagnostics_survive_the_whole_chain() -> None:
    """`clips.no_segments` / `cut_failed` cloudga YETSIN.

    Klip hisoblagichi `clips` lug'ati ichida ketadi, lekin heartbeat uni
    KALIT BO'YICHA ko'chiradi (`for key in (...)`) — ya'ni yangi kalit
    lug'atda bo'lsa ham cloudga chiqmasligi mumkin.  Aynan shu naqsh
    zanjirning eng nozik joyi.
    """
    source = (ROOT / "chaqimchi_ai/local/cloud_config.py").read_text(encoding="utf-8")
    for key in ("no_segments", "cut_failed"):
        assert f'"{key}"' in source, f"'clips.{key}' heartbeatga ko'chirilmagan"

    body = (ROOT / "cloud/main.py").read_text(encoding="utf-8")
    for field in ("clips_last_error", "snapshots", "cameras_configured", "status_stale"):
        assert f"{field}:" in body, f"'{field}' cloud modelida qabul qilinmaydi"
