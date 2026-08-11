#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${CHAQIMCHI_BACKUP_DIR:-}" || "${CHAQIMCHI_BACKUP_DIR}" == "/" ]]; then
  echo "CHAQIMCHI_BACKUP_DIR xavfsiz, aniq katalog bo'lishi shart" >&2
  exit 1
fi
if [[ -z "${CHAQIMCHI_BACKUP_PASSWORD:-}" ]]; then
  echo "CHAQIMCHI_BACKUP_PASSWORD berilishi shart" >&2
  exit 1
fi

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
stage="$(mktemp -d)"
trap 'rm -rf -- "$stage"' EXIT
mkdir -p -- "$CHAQIMCHI_BACKUP_DIR" "$stage/minio" "$stage/cloud-state"

cd "$repo_dir"
docker compose --env-file .env.production -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc > "$stage/postgres.dump"
docker compose --env-file .env.production -f docker-compose.prod.yml cp \
  cloud:/app/data/cloud/. "$stage/cloud-state"
docker run --rm --network chaqimchi_backend \
  --env-file .env.production -v "$stage/minio:/backup" \
  minio/mc:RELEASE.2025-07-21T05-28-08Z sh -c \
  'mc alias set src http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" && mc mirror src/"$CHAQIMCHI_S3_BUCKET" /backup'

tar -C "$stage" -czf - postgres.dump cloud-state minio | \
  openssl enc -aes-256-cbc -salt -pbkdf2 -pass env:CHAQIMCHI_BACKUP_PASSWORD \
  -out "$CHAQIMCHI_BACKUP_DIR/chaqimchi-$stamp.tar.gz.enc"

if [[ -n "${RESTIC_REPOSITORY:-}" ]]; then
  restic backup "$CHAQIMCHI_BACKUP_DIR/chaqimchi-$stamp.tar.gz.enc"
fi
echo "Backup tayyor: $CHAQIMCHI_BACKUP_DIR/chaqimchi-$stamp.tar.gz.enc"
