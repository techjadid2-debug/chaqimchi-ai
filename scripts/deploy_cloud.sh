#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
test -f .env.production || { echo ".env.production topilmadi" >&2; exit 1; }
docker compose --env-file .env.production -f docker-compose.prod.yml config --quiet
docker compose --env-file .env.production -f docker-compose.prod.yml build cloud
docker compose --env-file .env.production -f docker-compose.prod.yml up -d
docker compose --env-file .env.production -f docker-compose.prod.yml ps
