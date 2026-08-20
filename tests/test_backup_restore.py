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


def _archive_contents() -> list[str]:
    """`contents=(...)` — arxivga nima kirishi shu yerda hal bo'ladi."""
    groups = re.findall(r"contents=\(([^)]*)\)", BACKUP.read_text(encoding="utf-8"))
    assert groups, "arxiv mazmuni `contents=(...)` da yig'iladi"
    return groups


def test_the_archive_carries_the_encryption_keys() -> None:
    for group in _archive_contents():
        assert "env.production" in group, "sirlarsiz arxivdan kamera parollari va media tiklanmaydi"


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
    for destructive in ("dropdb", "mc mirror --overwrite", 'compose[@]}" stop'):
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


# ── Kunlik arxiv media'ni ko'tarmaydi ───────────────────────────────────
#
# Haqiqiy holat: har kecha butun MinIO diskka `mc mirror` qilinardi,
# arxiv 14 kun saqlanardi, ya'ni media hajmi diskda ~15 barobar
# takrorlanardi.  96 GB server ikki-uch do'kondan keyin to'lardi va
# birinchi belgi "disk 85%" degan Telegram xabari bo'lardi.

UNITS = SCRIPTS.parent / "deploy"


def test_the_daily_archive_leaves_media_out() -> None:
    groups = _archive_contents()
    daily = [g for g in groups if "postgres.dump" in g]
    assert daily, "kunlik arxivda PostgreSQL dump bo'lishi kerak"
    for group in daily:
        assert "minio" not in group, "kunlik arxivga media kirmasin — disk shu sabab to'lardi"


def test_media_backup_is_a_separate_opt_in_run() -> None:
    source = BACKUP.read_text(encoding="utf-8")
    assert "--media" in source, "media rejimi ataylab so'ralsin"
    assert "chaqimchi-media-$stamp" in source, "media arxivi alohida nom oladi"
    media = [g for g in _archive_contents() if "minio" in g]
    assert media, "media rejimida MinIO arxivga kirishi kerak"


def test_media_mirror_only_runs_in_media_mode() -> None:
    """`mc mirror` — eng qimmat qadam; u har kecha ishlamasin."""
    source = BACKUP.read_text(encoding="utf-8")
    guard = source.rindex('if [[ "$with_media" == "1" ]]; then', 0, source.index("mc mirror src/"))
    fi = source.index("\nfi", source.index("mc mirror src/"))
    assert guard < source.index("mc mirror src/") < fi, "mirror shart ichida bo'lsin"


def test_the_two_units_clean_up_different_files() -> None:
    """Kunlik unit media arxivini o'chirib yubormasin va aksincha."""
    daily = (UNITS / "chaqimchi-backup.service").read_text(encoding="utf-8")
    media = (UNITS / "chaqimchi-backup-media.service").read_text(encoding="utf-8")
    assert "chaqimchi-[0-9]*.tar.gz.enc" in daily, "kunlik tozalash faqat baza arxivlarini olsin"
    assert "chaqimchi-media-*.tar.gz.enc" in media
    assert "--media" in media, "haftalik unit media rejimida chaqirsin"
    assert (UNITS / "chaqimchi-backup-media.timer").is_file()


def test_the_snapshot_does_not_go_to_the_container_tmpfs() -> None:
    """Konteynerning `/tmp` i 64 MB tmpfs — `cloud.db` o'sganda backup
    jimgina yiqilardi va buni faqat tiklash kerak bo'lgan kuni bilardik."""
    source = BACKUP.read_text(encoding="utf-8")
    assert "/tmp/cloud-snapshot.db" not in source
    assert "/app/data/cloud/.backup-snapshot.db" in source


def test_restore_understands_both_archive_kinds() -> None:
    source = RESTORE.read_text(encoding="utf-8")
    assert 'kind="media"' in source and 'kind="baza"' in source
    # Media arxivi bazani o'chirib yubormasin.
    media_block = source[
        source.index('if [[ "$kind" == "media" ]]; then', source.index("Haqiqiy tiklash")) :
    ]
    media_block = media_block[: media_block.index("exit 0")]
    assert "dropdb" not in media_block, "media tiklash bazaga tegmasin"
    assert "mc mirror" in media_block


def test_missing_offsite_copy_is_reported() -> None:
    """Zaxira faqat serverda yotsa — bu jim qolmasin."""
    source = BACKUP.read_text(encoding="utf-8")
    assert "tashqi nusxa sozlanmagan" in source, "hech qaysi yo'l yoqilmasa aytilsin"
    preflight = (SCRIPTS / "production_preflight.py").read_text(encoding="utf-8")
    assert "def check_backup(" in preflight
    assert "RESTIC_REPOSITORY" in preflight
    assert "CHAQIMCHI_BACKUP_TELEGRAM_TOKEN" in preflight, (
        "Telegram yo'li ham tashqi nusxa hisoblansin"
    )


def test_a_healthy_archive_does_not_abort_the_drill() -> None:
    """`set -e` ostida `[[ ... ]] && fail=1` shakli test YOLG'ON bo'lganda —
    ya'ni arxiv SOG'LOM bo'lganda — butun skriptni to'xtatardi.

    Natija: mashq shifrlash kalitlari tekshiruvigacha yetmasdan 1 kod
    bilan chiqardi va sog'lom zaxira "yaroqsiz" bo'lib ko'rinardi.
    """
    code = [
        line
        for line in RESTORE.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    ]
    assert not [line for line in code if "&& fail=1" in line], (
        "`if` bilan yozilsin — `&&` bilan emas"
    )


def test_an_empty_media_archive_is_not_a_failure() -> None:
    """Hali do'kon ulanmagan tizimda media bo'sh bo'lishi normal.

    Aks holda haftalik unit har hafta yolg'on ogohlantirish yuborardi.
    """
    source = RESTORE.read_text(encoding="utf-8")
    block = source[source.index('if [[ "$kind" == "media" ]]; then', source.index("objects=")) :]
    block = block[: block.index("\nfi")]
    assert "fail=1" not in block


def test_the_drill_survives_an_archive_without_media() -> None:
    """`find` mavjud bo'lmagan papkada 1 qaytaradi, `set -o pipefail` esa
    uni butun quvurning kodi qiladi — `set -e` skriptni JIMGINA
    to'xtatardi.

    Kunlik arxivda `minio/` ataylab yo'q, ya'ni bu endi ODATIY yo'l:
    mashq shifrlash kalitlarini tekshirmasdan 1 kod bilan chiqib
    ketardi va sog'lom zaxira "yaroqsiz" bo'lib ko'rinardi.
    """
    source = RESTORE.read_text(encoding="utf-8")
    assert 'if [[ -d "$stage/minio" ]]; then' in source, "papka bor-yo'qligi tekshirilsin"
    guard = source.index('if [[ -d "$stage/minio" ]]; then')
    assert source.index('find "$stage/minio"') > guard, "`find` shart ichida bo'lsin"


# ── Tashqi nusxa ────────────────────────────────────────────────────────


def test_the_archive_can_leave_the_server_without_an_account() -> None:
    """Server yo'qolsa zaxira ham u bilan yo'qoladi.

    Telegram yo'li ataylab qo'shilgan: hisob ham, karta ham kerak emas —
    bot allaqachon bor va arxiv AES-256 bilan shifrlangan.
    """
    source = BACKUP.read_text(encoding="utf-8")
    assert "CHAQIMCHI_BACKUP_TELEGRAM_TOKEN" in source
    assert "sendDocument" in source


def test_the_bot_token_stays_out_of_the_process_list() -> None:
    """`curl https://api.telegram.org/bot<TOKEN>/...` argv'da qolardi va
    uni serverdagi har bir jarayon ro'yxati ko'rsatardi."""
    source = BACKUP.read_text(encoding="utf-8")
    assert "curl -sS -f -m 300 -K -" in source, "token stdin orqali berilsin"


def test_media_is_never_pushed_to_telegram() -> None:
    """Media o'nlab GB — 50 MB chegarasiga baribir sig'maydi."""
    source = BACKUP.read_text(encoding="utf-8")
    block = source[source.index("telegram_token=") :]
    assert '"$with_media" != "1"' in block[: block.index("\n")] or (
        '"$with_media" != "1"' in block[:400]
    )


def test_an_oversized_archive_warns_instead_of_failing_silently() -> None:
    source = BACKUP.read_text(encoding="utf-8")
    assert "45 * 1024 * 1024" in source
    assert "Telegram chegarasidan" in source
