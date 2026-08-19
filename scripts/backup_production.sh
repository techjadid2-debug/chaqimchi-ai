#!/usr/bin/env bash
set -euo pipefail
umask 077

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
mkdir -p -- "$CHAQIMCHI_BACKUP_DIR" "$stage/minio" "$stage/cloud-state"

cd "$repo_dir"
compose=(docker compose --env-file "$env_file" -f "$compose_file")
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
"${compose[@]}" exec -T cloud python -c "
import os, sqlite3, sys
src = sqlite3.connect('/app/data/cloud/cloud.db')
dst = sqlite3.connect('/tmp/cloud-snapshot.db')
with dst:
    src.backup(dst)
dst.close()
src.close()
with open('/tmp/cloud-snapshot.db', 'rb') as handle:
    sys.stdout.buffer.write(handle.read())
os.remove('/tmp/cloud-snapshot.db')
" > "$stage/cloud-state/cloud.db"

# Yuz modellari (~180 MB) ataylab olinmaydi: ular o'zgarmaydi va
# `scripts/fetch_face_models.py` bilan sha256 tekshiruvi ostida qayta
# yuklanadi.  Ularsiz arxiv 40 barobar kichik — ya'ni tiklashni mashq
# qilish ham arzon bo'ladi.
"${compose[@]}" run --rm --no-deps --entrypoint sh \
  -v "$stage/minio:/backup" minio-init -c \
  'mc alias set src http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" && mc mirror src/"$CHAQIMCHI_S3_BUCKET" /backup'

# Sirlar arxivga KIRADI.  Ularsiz tiklash yarim bo'ladi: kamera RTSP
# parollari `CHAQIMCHI_CAMERA_SECRET_KEY` bilan, MinIO'dagi har bir rasm
# va klip esa `CHAQIMCHI_SNAPSHOT_KEY` bilan shifrlangan — kalitsiz ular
# o'qib bo'lmaydigan axlat.  Arxivning o'zi AES-256 bilan yopilgan,
# backup paroli esa boshqa joyda (`/etc/chaqimchi/backup.env`) turadi va
# bu faylga KIRMAYDI, ya'ni aylanma bog'liqlik yo'q.
cp -- "$env_file" "$stage/env.production"
chmod 600 "$stage/env.production"

tar -C "$stage" -czf - postgres.dump cloud-state minio env.production | \
  openssl enc -aes-256-cbc -salt -pbkdf2 -pass env:CHAQIMCHI_BACKUP_PASSWORD \
  -out "$CHAQIMCHI_BACKUP_DIR/chaqimchi-$stamp.tar.gz.enc"
chmod 600 "$CHAQIMCHI_BACKUP_DIR/chaqimchi-$stamp.tar.gz.enc"

if [[ -n "${RESTIC_REPOSITORY:-}" ]]; then
  restic backup "$CHAQIMCHI_BACKUP_DIR/chaqimchi-$stamp.tar.gz.enc"
fi
echo "Backup tayyor: $CHAQIMCHI_BACKUP_DIR/chaqimchi-$stamp.tar.gz.enc"
