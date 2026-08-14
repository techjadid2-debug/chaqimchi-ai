#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
env_file="${CHAQIMCHI_ENV_FILE:-.env.production}"
compose_file="${CHAQIMCHI_COMPOSE_FILE:-docker-compose.prod.yml}"
compose=(docker compose --env-file "$env_file" -f "$compose_file")
previous_container="$("${compose[@]}" ps -q cloud 2>/dev/null || true)"
previous_image=""
previous_image_ref=""
if [[ -n "$previous_container" ]]; then
  previous_image="$(docker inspect -f '{{.Image}}' "$previous_container")"
  previous_image_ref="$(docker inspect -f '{{.Config.Image}}' "$previous_container")"
fi

rollback_cloud() {
  if [[ -z "$previous_image" || -z "$previous_image_ref" ]]; then
    echo "XATO: oldingi cloud image topilmadi; avtomatik rollback imkonsiz" >&2
    return 1
  fi
  echo "Cloud health tekshiruvi o'tmadi — oldingi image qayta yoqilmoqda" >&2
  docker image tag "$previous_image" "$previous_image_ref"
  "${compose[@]}" up -d --no-deps --force-recreate cloud
}

python3 scripts/production_preflight.py --env-file "$env_file"
"${compose[@]}" config --quiet

if [[ -n "$previous_container" ]]; then
  if [[ "${CHAQIMCHI_SKIP_DEPLOY_BACKUP:-false}" == "true" ]]; then
    echo "OGOHLANTIRISH: deploy oldi backup ataylab o'tkazib yuborildi" >&2
  else
    : "${CHAQIMCHI_BACKUP_DIR:?Mavjud production uchun CHAQIMCHI_BACKUP_DIR shart}"
    : "${CHAQIMCHI_BACKUP_PASSWORD:?Mavjud production uchun CHAQIMCHI_BACKUP_PASSWORD shart}"
    CHAQIMCHI_ENV_FILE="$env_file" CHAQIMCHI_COMPOSE_FILE="$compose_file" \
      scripts/backup_production.sh
  fi
fi

"${compose[@]}" build cloud
if ! "${compose[@]}" up -d --wait --wait-timeout 180; then
  rollback_cloud
  exit 1
fi
if ! "${compose[@]}" exec -T cloud python -c \
  "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8750/health', timeout=10)"; then
  rollback_cloud
  exit 1
fi
"${compose[@]}" ps
