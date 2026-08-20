#!/usr/bin/env bash
#
# Zaxira nusxadan tiklash.
#
# Nega alohida skript kerak: zaxira olish yozilgan edi, tiklash esa yo'q.
# Sinalmagan zaxira — zaxira emas.  `PRAGMA integrity_check` va
# `pg_restore --list` faylning **shakli** to'g'riligini aytadi, lekin
# tiklangan ma'lumot ustida tizim ko'tariladimi degan savolga javob
# bermaydi.
#
# Ikki rejim:
#   --check    xavfsiz mashq.  Arxiv ochiladi, mazmuni tekshiriladi,
#              production'ga TEGILMAYDI.  Har chorakda shu bajarilsin.
#   --restore  haqiqiy tiklash.  Barcha joriy ma'lumot O'CHADI.
#
# Ishlatish:
#   CHAQIMCHI_BACKUP_PASSWORD=... ./scripts/restore_production.sh --check arxiv.tar.gz.enc
#
set -euo pipefail
umask 077

mode=""
archive=""
for arg in "$@"; do
  case "$arg" in
    --check) mode="check" ;;
    --restore) mode="restore" ;;
    *) archive="$arg" ;;
  esac
done

if [[ -z "$mode" || -z "$archive" ]]; then
  echo "Ishlatish: $0 --check|--restore <arxiv.tar.gz.enc>" >&2
  exit 2
fi
if [[ ! -f "$archive" ]]; then
  echo "Arxiv topilmadi: $archive" >&2
  exit 1
fi
if [[ -z "${CHAQIMCHI_BACKUP_PASSWORD:-}" ]]; then
  echo "CHAQIMCHI_BACKUP_PASSWORD berilishi shart" >&2
  exit 1
fi

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
env_file="${CHAQIMCHI_ENV_FILE:-.env.production}"
compose_file="${CHAQIMCHI_COMPOSE_FILE:-docker-compose.prod.yml}"
stage="$(mktemp -d)"
cleanup() { rm -rf -- "$stage" 2>/dev/null || true; }
trap cleanup EXIT
cd "$repo_dir"

echo "→ Arxiv ochilmoqda…"
openssl enc -d -aes-256-cbc -pbkdf2 -pass env:CHAQIMCHI_BACKUP_PASSWORD \
  -in "$archive" | tar -C "$stage" -xzf -

# Ikki xil arxiv bor (`backup_production.sh` ga qarang):
#   baza  — PostgreSQL + cloud.db + kalitlar (har kuni)
#   media — MinIO'dagi rasm/kliplar + kalitlar (haftada bir)
# Turini mazmunidan aniqlaymiz, nomidan emas: fayl qayta nomlangan
# bo'lishi mumkin.
if [[ -f "$stage/postgres.dump" ]]; then
  kind="baza"
elif [[ -d "$stage/minio" ]]; then
  kind="media"
else
  echo "✗ Arxiv tanilmadi: ichida na postgres.dump, na minio/ bor." >&2
  exit 1
fi

# ── Tekshiruv (ikkala rejimda ham) ──────────────────────────────────────
fail=0
note() { printf '  %-38s %s\n' "$1" "$2"; }

echo "→ Mazmuni tekshirilmoqda (arxiv turi: $kind):"

# `pg_restore` hostda bo'lmasligi mumkin — PostgreSQL konteynerda ishlaydi.
# Vositaning yo'qligi "dump bo'sh" degani EMAS: ikkisini aralashtirib
# yuborish yolg'on xavotir beradi, shuning uchun ular alohida aytiladi.
list_dump() {
  if command -v pg_restore >/dev/null 2>&1; then
    pg_restore --list "$1" 2>/dev/null
  else
    docker compose --env-file "$env_file" -f "$compose_file" \
      exec -T postgres pg_restore --list 2>/dev/null < "$1"
  fi
}

if [[ "$kind" == "media" ]]; then
  note "PostgreSQL dump" "bu arxivda yo'q (media arxivi)"
elif [[ -s "$stage/postgres.dump" ]]; then
  listing="$(list_dump "$stage/postgres.dump" || true)"
  if [[ -z "$listing" ]]; then
    note "PostgreSQL dump" "TEKSHIRIB BO'LMADI (pg_restore ishga tushmadi)"
    fail=1
  else
    tables="$(printf '%s\n' "$listing" | grep -c 'TABLE DATA' || true)"
    note "PostgreSQL dump" "$tables ta jadval"
    if [[ "$tables" -eq 0 ]]; then
      note "PostgreSQL dump" "BO'SH — hodisa tarixi yo'q"
      fail=1
    fi
  fi
else
  note "PostgreSQL dump" "YO'Q"; fail=1
fi

if [[ "$kind" == "media" ]]; then
  note "cloud.db" "bu arxivda yo'q (media arxivi)"
elif [[ -s "$stage/cloud-state/cloud.db" ]]; then
  # Yaxlitlik + haqiqiy mazmun: bo'sh, lekin "sog'lom" baza ham
  # integrity_check dan o'tadi.
  summary="$(python3 - "$stage/cloud-state/cloud.db" <<'PY'
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
    print("BUZUQ"); raise SystemExit
counts = []
for table in ("sites", "invoices", "portal_accounts", "site_cameras"):
    try:
        counts.append(f"{table}={conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]}")
    except sqlite3.Error:
        counts.append(f"{table}=JADVAL YO'Q")
print(" ".join(counts))
PY
)"
  note "cloud.db" "$summary"
  # `if` bilan, `&&` bilan emas: `set -e` ostida `[[ ... ]] && fail=1`
  # shakli test YOLG'ON bo'lganda (ya'ni arxiv SOG'LOM bo'lganda) butun
  # skriptni to'xtatardi.  Natijada mashq kalitlar tekshiruvigacha
  # yetmasdan 1 kod bilan chiqardi — sog'lom zaxira "yaroqsiz" bo'lib
  # ko'rinardi.
  if [[ "$summary" == *"BUZUQ"* || "$summary" == *"JADVAL YO'Q"* ]]; then
    fail=1
  fi
else
  note "cloud.db" "YO'Q"; fail=1
fi

# `find` mavjud bo'lmagan papkada 1 qaytaradi, `set -o pipefail` esa uni
# butun quvurning kodi qilib beradi — ya'ni `set -e` skriptni JIMGINA
# to'xtatardi.  Kunlik arxivda `minio/` ataylab yo'q, shuning uchun bu
# yo'l endi odatiy holat.  (Bungacha arxivda bo'sh bo'lsa ham papka
# turardi va nuqson ko'rinmasdi.)
objects=0
if [[ -d "$stage/minio" ]]; then
  objects="$(find "$stage/minio" -type f | wc -l | tr -d ' ')"
fi
if [[ "$kind" == "media" ]]; then
  if [[ "$objects" -eq 0 ]]; then
    # Yangi tizimda (hali do'kon ulanmagan) bu NORMAL holat, xato emas:
    # aks holda haftalik unit har hafta yolg'on ogohlantirish yuborardi.
    note "MinIO obyektlari" "0 ta — hali media yo'q (yangi tizimda normal)"
  else
    note "MinIO obyektlari" "$objects ta"
  fi
else
  # Kunlik arxivda media ATAYLAB yo'q (disk 15 barobar shishmasligi uchun).
  # Rasm va kliplar alohida `chaqimchi-media-*` arxividan tiklanadi.
  note "MinIO obyektlari" "kunlik arxivda yo'q — media arxividan tiklanadi"
fi

# Eng muhim tekshiruv: kalitlarsiz tiklangan baza yaroqsiz.  Kamera
# parollari va barcha media aynan shu ikki kalit bilan shifrlangan.
if [[ -s "$stage/env.production" ]]; then
  missing=""
  for key in CHAQIMCHI_CAMERA_SECRET_KEY CHAQIMCHI_SNAPSHOT_KEY \
             CHAQIMCHI_PORTAL_JWT_SECRET CHAQIMCHI_OWNER_JWT_SECRET; do
    grep -q "^${key}=" "$stage/env.production" || missing="$missing $key"
  done
  if [[ -n "$missing" ]]; then
    note "Shifrlash kalitlari" "YETISHMAYDI:$missing"; fail=1
  else
    note "Shifrlash kalitlari" "joyida"
  fi
else
  note "Shifrlash kalitlari" "YO'Q — kamera parollari va media tiklanmaydi"
  fail=1
fi

if [[ "$fail" -ne 0 ]]; then
  echo "✗ Arxiv to'liq emas — bu nusxadan tiklab bo'lmaydi." >&2
  exit 1
fi
echo "✓ Arxiv butun."

if [[ "$mode" == "check" ]]; then
  echo "Mashq tugadi. Production'ga tegilmadi."
  exit 0
fi

# ── Haqiqiy tiklash ─────────────────────────────────────────────────────
echo
if [[ "$kind" == "media" ]]; then
  echo "DIQQAT: MinIO'dagi rasm va kliplar arxivdagisiga almashadi."
  echo "Baza, sozlamalar va akkauntlarga TEGILMAYDI. Compose: $compose_file"
else
  echo "DIQQAT: joriy baza, akkauntlar va sozlamalar O'CHADI va arxivdagisiga"
  echo "almashadi. Rasm/kliplar tegilmaydi — ular media arxivida."
  echo "Compose: $compose_file"
fi
read -r -p "Davom etish uchun 'TIKLASH' deb yozing: " answer
[[ "$answer" == "TIKLASH" ]] || { echo "Bekor qilindi."; exit 1; }

compose=(docker compose --env-file "$env_file" -f "$compose_file")

if [[ "$kind" == "media" ]]; then
  # Media arxivida `env.production` bor (kalitlar uchun), lekin u joriy
  # sozlamalarni ALMASHTIRMAYDI: media haftalik, sozlamalar esa undan
  # keyin o'zgargan bo'lishi mumkin.
  echo "→ MinIO tiklanmoqda…"
  "${compose[@]}" run --rm --no-deps --entrypoint sh \
    -v "$stage/minio:/backup" minio-init -c \
    'mc alias set dst http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" && mc mb --ignore-existing dst/"$CHAQIMCHI_S3_BUCKET" && mc mirror --overwrite /backup dst/"$CHAQIMCHI_S3_BUCKET"'
  echo
  echo "✓ Media tiklandi."
  exit 0
fi

echo "→ Sozlamalar tiklanmoqda ($env_file)…"
if [[ -f "$env_file" ]]; then
  cp -- "$env_file" "$env_file.bak-$(date -u +%Y%m%dT%H%M%SZ)"
fi
cp -- "$stage/env.production" "$env_file"
chmod 600 "$env_file"

echo "→ Xizmatlar to'xtatilmoqda…"
"${compose[@]}" stop cloud

echo "→ PostgreSQL tiklanmoqda…"
"${compose[@]}" exec -T postgres sh -lc \
  'dropdb -U "$POSTGRES_USER" --if-exists "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
"${compose[@]}" exec -T postgres sh -lc \
  'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner' < "$stage/postgres.dump"

echo "→ cloud.db tiklanmoqda…"
"${compose[@]}" cp "$stage/cloud-state/cloud.db" cloud:/app/data/cloud/cloud.db

echo "→ Xizmatlar ko'tarilmoqda…"
"${compose[@]}" up -d --wait --wait-timeout 180

echo
echo "✓ Tiklandi."
echo "Qolgan qo'l ishlari:"
echo "  1. Rasm va kliplar: eng yangi chaqimchi-media-*.tar.gz.enc arxivini"
echo "     shu skript bilan --restore qiling (ular kunlik arxivda yo'q)"
echo "  2. Yuz modellari: python scripts/fetch_face_models.py (arxivga kirmaydi)"
echo "  3. Telegram webhook: python scripts/set_telegram_webhook.py"
echo "  4. /health va admin panelga kirishni tekshiring"
