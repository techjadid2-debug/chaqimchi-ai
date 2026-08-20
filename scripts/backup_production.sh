#!/usr/bin/env bash
#
# Zaxira nusxa olish.  IKKI REJIM bor va bu ataylab:
#
#   (standart)  faqat baza — PostgreSQL + cloud.db + kalitlar.  ~50-200 MB.
#               Har kuni olinadi va tashqi omborga (restic) chiqadi.
#   --media     media ham — MinIO'dagi rasm va kliplar.  O'nlab GB.
#               Haftada bir marta, kam nusxa saqlanadi.
#
# Nega bo'lindi: ilgari har kecha butun MinIO diskka nusxalanardi, arxiv
# 14 kun saqlanardi va yana `mc mirror` uchun vaqtinchalik nusxa olinardi.
# Ya'ni media hajmi diskda ~15 barobar takrorlanardi va 96 GB server
# ikki-uch do'kondan keyin to'lardi.  Hisob-faktura va akkauntlar
# yo'qolsa biznes to'xtaydi, bir haftalik klip yo'qolsa — yo'q.
#
set -euo pipefail
umask 077

# Media rejimi: `--media` argumenti yoki CHAQIMCHI_BACKUP_MEDIA=1
with_media=0
for arg in "$@"; do
  case "$arg" in
    --media) with_media=1 ;;
    *) echo "Noma'lum argument: $arg (faqat --media)" >&2; exit 2 ;;
  esac
done
if [[ "${CHAQIMCHI_BACKUP_MEDIA:-0}" == "1" ]]; then
  with_media=1
fi

if [[ -z "${CHAQIMCHI_BACKUP_DIR:-}" || "${CHAQIMCHI_BACKUP_DIR}" == "/" ]]; then
  echo "CHAQIMCHI_BACKUP_DIR xavfsiz, aniq katalog bo'lishi shart" >&2
  exit 1
fi
if [[ -z "${CHAQIMCHI_BACKUP_PASSWORD:-}" ]]; then
  echo "CHAQIMCHI_BACKUP_PASSWORD berilishi shart" >&2
  exit 1
fi

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
env_file="${CHAQIMCHI_ENV_FILE:-.env.production}"
compose_file="${CHAQIMCHI_COMPOSE_FILE:-docker-compose.prod.yml}"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
stage="$(mktemp -d)"
# Tozalash HECH QACHON xato bilan tugamasin: `mc mirror` konteyner ichida
# root sifatida yozadi, host user esa u fayllarni o'chira olmaydi.  EXIT
# trapdagi `rm` xatosi bash'da skriptning chiqish kodiga aylanadi — aynan
# shu sabab 2026-08-17 dagi birinchi deploy backupdan KEYIN "jimgina"
# yiqilgan edi.  Root fayllarni compose'ning o'z konteyneriga o'chirtiramiz,
# qolganini oddiy rm oladi; ikkalasi ham yiqilsa ham backup natijasiga
# ta'sir qilmaydi.
cleanup_stage() {
  docker compose --env-file "${CHAQIMCHI_ENV_FILE:-.env.production}" \
    -f "${CHAQIMCHI_COMPOSE_FILE:-docker-compose.prod.yml}" \
    run --rm --no-deps --entrypoint sh -v "$stage:/stage" minio-init \
    -c 'rm -rf /stage/minio' >/dev/null 2>&1 || true
  rm -rf -- "$stage" 2>/dev/null || true
}
trap cleanup_stage EXIT
mkdir -p -- "$CHAQIMCHI_BACKUP_DIR"
if [[ "$with_media" == "1" ]]; then
  mkdir -p -- "$stage/minio"
else
  mkdir -p -- "$stage/cloud-state"
fi

cd "$repo_dir"
compose=(docker compose --env-file "$env_file" -f "$compose_file")

# Media rejimida baza olinmaydi: u arxivga baribir kirmaydi, `pg_dump` esa
# katta bazada bekorga vaqt va disk yeb ketardi.
if [[ "$with_media" != "1" ]]; then
"${compose[@]}" exec -T postgres sh -lc \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$stage/postgres.dump"

# `cloud.db` — hisob-faktura, obuna, portal loginlari va kamera
# inventari.  Fayllarni shunchaki nusxalash YETARLI EMAS: baza WAL
# rejimida ishlaydi va `cloud.db`, `-wal`, `-shm` uch alohida nusxa
# sifatida olinsa, orasidagi yozuv yirtiq snapshot beradi.  `PRAGMA
# integrity_check` bunday faylni ham "sog'lom" deb o'tkazib yuboradi.
# SQLite'ning o'z `backup()` API'si yaxlit nusxa beradi.
#
# Natija stdout orqali oqim bilan chiqadi, `docker compose cp` bilan emas:
# konteynerning `/tmp` i tmpfs (xotirada), `docker cp` esa tmpfs'dan
# o'qiy olmaydi — "Could not find the file" deb yiqiladi.  Yuqoridagi
# `pg_dump` ham aynan shu usulda ishlaydi.
#
# Snapshot `/tmp` ga EMAS, ma'lumot volumiga yoziladi: konteynerning
# `/tmp` i 64 MB tmpfs (docker-compose'da `tmpfs: /tmp:size=64m`).
# `cloud.db` shu chegaradan oshsa backup jimgina yiqilardi va buni
# faqat tiklash kerak bo'lgan kuni bilardik.
"${compose[@]}" exec -T cloud python -c "
import os, sqlite3, sys
snapshot = '/app/data/cloud/.backup-snapshot.db'
for leftover in (snapshot, snapshot + '-wal', snapshot + '-shm'):
    if os.path.exists(leftover):
        os.remove(leftover)
try:
    src = sqlite3.connect('/app/data/cloud/cloud.db')
    dst = sqlite3.connect(snapshot)
    with dst:
        src.backup(dst)
    dst.close()
    src.close()
    with open(snapshot, 'rb') as handle:
        sys.stdout.buffer.write(handle.read())
finally:
    for leftover in (snapshot, snapshot + '-wal', snapshot + '-shm'):
        if os.path.exists(leftover):
            os.remove(leftover)
" > "$stage/cloud-state/cloud.db"
fi   # ← baza rejimi tugadi

# Media (rasm va kliplar) faqat `--media` rejimida olinadi — u o'nlab GB
# va har kecha nusxalanishi shart emas.
#
# Yuz modellari (~180 MB) ataylab olinmaydi: ular o'zgarmaydi va
# `scripts/fetch_face_models.py` bilan sha256 tekshiruvi ostida qayta
# yuklanadi.  Ularsiz arxiv 40 barobar kichik — ya'ni tiklashni mashq
# qilish ham arzon bo'ladi.
if [[ "$with_media" == "1" ]]; then
  "${compose[@]}" run --rm --no-deps --entrypoint sh \
    -v "$stage/minio:/backup" minio-init -c \
    'mc alias set src http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" && mc mirror src/"$CHAQIMCHI_S3_BUCKET" /backup'
fi

# Sirlar arxivga KIRADI.  Ularsiz tiklash yarim bo'ladi: kamera RTSP
# parollari `CHAQIMCHI_CAMERA_SECRET_KEY` bilan, MinIO'dagi har bir rasm
# va klip esa `CHAQIMCHI_SNAPSHOT_KEY` bilan shifrlangan — kalitsiz ular
# o'qib bo'lmaydigan axlat.  Arxivning o'zi AES-256 bilan yopilgan,
# backup paroli esa boshqa joyda (`/etc/chaqimchi/backup.env`) turadi va
# bu faylga KIRMAYDI, ya'ni aylanma bog'liqlik yo'q.
cp -- "$env_file" "$stage/env.production"
chmod 600 "$stage/env.production"

# Arxiv nomi rejimni AYTIB turadi: tozalash qoidalari va tiklash paytida
# qaysi fayl nima ekani nomidan ko'rinsin.
#   chaqimchi-<sana>.tar.gz.enc         — baza (har kuni, 14 kun saqlanadi)
#   chaqimchi-media-<sana>.tar.gz.enc   — media (haftada bir, 2 nusxa)
if [[ "$with_media" == "1" ]]; then
  archive="$CHAQIMCHI_BACKUP_DIR/chaqimchi-media-$stamp.tar.gz.enc"
  # Kalitlar media arxiviga ham kiradi: MinIO'dagi har bir fayl
  # `CHAQIMCHI_SNAPSHOT_KEY` bilan shifrlangan, kalitsiz ular axlat.
  contents=(minio env.production)
else
  archive="$CHAQIMCHI_BACKUP_DIR/chaqimchi-$stamp.tar.gz.enc"
  contents=(postgres.dump cloud-state env.production)
fi

tar -C "$stage" -czf - "${contents[@]}" | \
  openssl enc -aes-256-cbc -salt -pbkdf2 -pass env:CHAQIMCHI_BACKUP_PASSWORD \
  -out "$archive"
chmod 600 "$archive"

if [[ -n "${RESTIC_REPOSITORY:-}" ]]; then
  restic backup "$archive"
else
  # Server yo'qolsa zaxira ham u bilan yo'qoladi.  Bu jim qolmasin.
  echo "OGOHLANTIRISH: RESTIC_REPOSITORY sozlanmagan — zaxira faqat shu" >&2
  echo "serverda yotibdi.  Server o'lsa hisob-faktura va akkauntlar bilan" >&2
  echo "birga zaxira ham yo'qoladi (deploy/backup.env.example ga qarang)." >&2
fi

size="$(du -h -- "$archive" | cut -f1)"
echo "Backup tayyor: $archive ($size)"
