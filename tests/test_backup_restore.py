"""Zaxira nusxa haqiqatan tiklanadigan bo'lsin.

Sinalmagan zaxira — zaxira emas.  Bu testlar ikkita aniq xatoni qaytib
kelishidan qo'riqlaydi:

1. Arxivda shifrlash kalitlari yo'q edi.  Kamera RTSP parollari
   `CHAQIMCHI_CAMERA_SECRET_KEY`, MinIO'dagi har bir rasm va klip esa
   `CHAQIMCHI_SNAPSHOT_KEY` bilan shifrlangan.  Server yo'qolsa arxivdan
   qatorlar va bloblar chiqadi, lekin ularni **o'qib bo'lmaydi**.
2. `cloud.db` (hisob-faktura, obuna, loginlar) uch fayl sifatida, dastur
   ishlab turganda nusxalanardi — yirtiq snapshot chiqishi mumkin edi.
"""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
BACKUP = SCRIPTS / "backup_production.sh"
RESTORE = SCRIPTS / "restore_production.sh"

#: Bularsiz tiklangan baza yaroqsiz.
CRITICAL_KEYS = ("CHAQIMCHI_CAMERA_SECRET_KEY", "CHAQIMCHI_SNAPSHOT_KEY")


def test_the_archive_carries_the_encryption_keys() -> None:
    source = BACKUP.read_text(encoding="utf-8")
    tar_line = next(line for line in source.splitlines() if line.startswith("tar -C"))
    assert "env.production" in tar_line, (
        "sirlarsiz arxivdan kamera parollari va media tiklanmaydi"
    )


def test_the_backup_password_does_not_live_in_the_archived_env() -> None:
    """Aylanma bog'liqlik bo'lmasin: arxivni ochadigan parol arxiv ichida
    turmasligi kerak."""
    example = (SCRIPTS.parent / ".env.production.example").read_text(encoding="utf-8")
    assert "CHAQIMCHI_BACKUP_PASSWORD" not in example


def test_cloud_db_is_copied_atomically() -> None:
    """WAL rejimidagi bazani uch alohida fayl sifatida ko'chirib bo'lmaydi."""
    source = BACKUP.read_text(encoding="utf-8")
    assert "src.backup(dst)" in source, "SQLite'ning o'z backup API'si ishlatilsin"
    assert "cloud:/app/data/cloud/." not in source, "xom fayl nusxasi qaytib kelmasin"


def test_a_restore_script_exists_and_is_runnable() -> None:
    assert RESTORE.is_file(), "tiklash skripti bo'lishi shart"
    assert os.stat(RESTORE).st_mode & stat.S_IXUSR, "bajariladigan bo'lsin"
    assert re.search(r"^#!/usr/bin/env bash", RESTORE.read_text(encoding="utf-8"))


def test_the_restore_drill_does_not_touch_production() -> None:
    """`--check` mashqi har chorakda bajariladi — u xavfsiz bo'lishi shart."""
    source = RESTORE.read_text(encoding="utf-8")
    check_block = source[source.index('if [[ "$mode" == "check" ]]') :]
    guard = source[: source.index('if [[ "$mode" == "check" ]]')]
    assert "exit 0" in check_block.split("fi")[0], "mashq tiklashgacha bormasin"
    for destructive in ("dropdb", "mc mirror --overwrite", "compose[@]}\" stop"):
        assert destructive not in guard, f"mashqdan oldin buzuvchi amal: {destructive}"


def test_the_restore_verifies_the_keys_are_present() -> None:
    source = RESTORE.read_text(encoding="utf-8")
    for key in CRITICAL_KEYS:
        assert key in source, f"{key} tekshirilmasa yaroqsiz arxiv sog'lom ko'rinadi"


def test_a_destructive_restore_needs_a_typed_confirmation() -> None:
    source = RESTORE.read_text(encoding="utf-8")
    assert 'answer" == "TIKLASH"' in source, "tasodifan bosib yuborilmasin"


def test_the_runbook_points_at_the_restore_script() -> None:
    """Ilgari runbook'da tiklash «hali o'tkazilmagan» deb turardi va
    ishga tushiradigan skript umuman yo'q edi."""
    runbook = (SCRIPTS.parent / "docs" / "PRODUCTION_RUNBOOK.md").read_text(encoding="utf-8")
    assert "restore_production.sh" in runbook


def test_a_failed_backup_is_not_silent() -> None:
    """`Type=oneshot` xatosi faqat jurnalga tushadi, papkada esa eski
    arxiv qoladi — hammasi joyidaday ko'rinadi.  Zaxira yo'qligi server
    yo'qolgandan keyin emas, o'sha kuniyoq bilinishi kerak."""
    unit = (SCRIPTS.parent / "deploy" / "chaqimchi-backup.service").read_text(encoding="utf-8")
    assert "OnFailure=" in unit
    notifier = SCRIPTS / "notify_backup_failure.sh"
    assert notifier.is_file() and os.stat(notifier).st_mode & stat.S_IXUSR
    assert (SCRIPTS.parent / "deploy" / "chaqimchi-backup-failed.service").is_file()


def test_the_backup_unit_example_matches_the_real_compose_file() -> None:
    """Namunada `docker-compose.contabo.yml` turardi, productionda esa
    boshqa fayl — `docker compose exec` konteynerni topa olmasdi va
    zaxira har kecha yiqilardi."""
    example = (SCRIPTS.parent / "deploy" / "backup.env.example").read_text(encoding="utf-8")
    compose = next(
        line.split("=", 1)[1].strip()
        for line in example.splitlines()
        if line.startswith("CHAQIMCHI_COMPOSE_FILE=")
    )
    assert (SCRIPTS.parent / compose).is_file(), f"{compose} repoda yo'q"
