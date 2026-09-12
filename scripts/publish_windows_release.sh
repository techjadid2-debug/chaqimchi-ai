#!/usr/bin/env bash
#
# Windows relizini serverga chiqaradi — shundan keyin do'kondagi
# qurilmalar uni 15 daqiqada o'zi oladi.
#
# Nega alohida skript kerak: `make windows-release` faqat NOUTBUKDA
# `.exe` va imzolangan `.json` yasaydi.  Ular serverdagi `releases/`
# papkasiga tushmaguncha hech bir do'kon yangilanmaydi — cloud aynan
# o'sha papkadan `enes-windows-<versiya>.exe` va `.json` juftini
# qidiradi (`cloud/main.py: latest_windows_release`).  Bu oxirgi qadam
# qo'lda `scp` edi va uni unutish "reliz chiqdi, lekin hech kimga
# yetmadi" degan jim holatga olib kelardi.
#
# Ishlatish:
#   ENES_RELEASE_HOST=deploy@169.58.198.111 \
#     scripts/publish_windows_release.sh
#
#   # CI qurgan faylni chiqarish (GitHub Releases'dan yuklab olingan):
#   ENES_RELEASE_HOST=deploy@169.58.198.111 \
#     scripts/publish_windows_release.sh --exe ~/Downloads/ENES_Setup.exe
#
# Muhitdan o'qiladi:
#   ENES_RELEASE_HOST      majburiy — `deploy@IP`
#   ENES_RELEASE_DIR       serverdagi papka (standart quyida)
#   ENES_RELEASE_SSH_KEY   SSH kaliti (standart `.deploy_keys/enes_prod`)
#   ENES_DL_URL            tashqi tekshiruv manzili (standart dl.enes.uz)
#   ENES_RELEASE_LEGACY_NAME=1  reliz ESKI nom bilan chiqadi
#                          (`chaqimchi-windows-<v>`) — pastdagi izohga qarang
#
set -euo pipefail

cd "$(dirname "$0")/.."

remote_dir="${ENES_RELEASE_DIR:-/home/deploy/enes/releases}"
ssh_key="${ENES_RELEASE_SSH_KEY:-.deploy_keys/enes_prod}"
dl_url="${ENES_DL_URL:-https://dl.enes.uz}"
py="${PY:-python3}"

source_exe=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --exe) source_exe="${2:-}"; shift 2 ;;
    *) echo "Noma'lum argument: $1 (faqat --exe <fayl>)" >&2; exit 2 ;;
  esac
done

if [[ -z "${ENES_RELEASE_HOST:-}" ]]; then
  echo "ENES_RELEASE_HOST berilishi shart (masalan deploy@169.58.198.111)" >&2
  exit 1
fi

version="$("$py" -c 'import enes; print(enes.__version__)')"

# ── Nom: yangi yoki O'TISH relizi ───────────────────────────────────────
#
# Daladagi qurilma (0.6.25) va jonli cloud REBRENDDAN OLDINGI kodda:
# qurilmaning tekshiruvchisi `product: "enes-windows"` ni "noma'lum"
# deb rad etadi (`KNOWN_PRODUCTS` o'sha versiyada faqat eski nomlarni
# biladi), cloud esa `releases/` dan faqat `chaqimchi-windows-*` ni
# qidiradi.  Ya'ni yangi nomdagi birinchi reliz hech kimga YETMAYDI.
#
# Shuning uchun brend almashuvida bitta O'TISH relizi eski nom bilan
# chiqadi.  U o'rnatilgach qurilmada yangi kod ishlaydi va u ikkala
# nomni ham taniydi — keyingi relizlar yangi nomda ketaveradi.
prefix="enes-windows"
if [[ "${ENES_RELEASE_LEGACY_NAME:-}" == "1" ]]; then
  prefix="chaqimchi-windows"
  echo "→ O'TISH RELIZI: eski nom bilan chiqadi ($prefix)"
fi
exe="releases/$prefix-$version.exe"
manifest="releases/$prefix-$version.json"
echo "→ Versiya: $version"

# CI qurgan fayl boshqa nom bilan keladi (`ENES_Setup.exe`).
# Uni versiyali nomga ko'chiramiz: cloud faqat shu nomni taniydi.
if [[ -n "$source_exe" ]]; then
  [[ -f "$source_exe" ]] || { echo "Fayl topilmadi: $source_exe" >&2; exit 1; }
  if [[ "$(cd "$(dirname "$source_exe")" && pwd)/$(basename "$source_exe")" \
        != "$(pwd)/$exe" ]]; then
    cp -- "$source_exe" "$exe"
    # Nusxa ko'chirilgan bo'lsa eski imzo endi to'g'ri kelmasligi mumkin.
    rm -f -- "$manifest"
  fi
fi

if [[ ! -f "$exe" ]]; then
  echo "Topilmadi: $exe" >&2
  echo "Avval quring:" >&2
  echo "  make windows-release CLOUD_URL=https://api.enes.uz" >&2
  echo "  (o'tish relizi uchun: LEGACY_NAME=1 make windows-release …)" >&2
  echo "yoki CI qurgan faylni bering: --exe <yuklab olingan .exe>" >&2
  exit 1
fi

# ── Imzo ────────────────────────────────────────────────────────────────
#
# Imzosiz paketni qurilma RAD ETADI (`enes/signed_update.py`) —
# ya'ni imzolanmagan relizni chiqarish shunchaki foydasiz ish bo'lardi.
if [[ ! -f "$manifest" ]]; then
  echo "→ Imzolanmoqda…"
  "$py" scripts/sign_release.py "$exe"
fi

echo "→ Imzo tekshirilmoqda (qurilmadagi ochiq kalit bilan)…"
"$py" - "$exe" "$manifest" <<'PY'
import sys
from pathlib import Path

from enes.signed_update import verify_release_manifest

archive, manifest = Path(sys.argv[1]), Path(sys.argv[2])
data = verify_release_manifest(archive, manifest, Path("deploy/update-public.pem"))
print(f"   ✓ {data['version']} · {data.get('product', 'enes-windows')}")
PY

size_bytes="$(wc -c < "$exe" | tr -d ' ')"
echo "→ Hajmi: $((size_bytes / 1024 / 1024)) MB"

# ── Serverga ────────────────────────────────────────────────────────────
scp_opts=(-o StrictHostKeyChecking=accept-new)
if [[ -f "$ssh_key" ]]; then
  scp_opts+=(-i "$ssh_key")
fi

echo "→ Serverga yuborilmoqda: $ENES_RELEASE_HOST:$remote_dir"
scp "${scp_opts[@]}" "$exe" "$manifest" "$ENES_RELEASE_HOST:$remote_dir/"

# ── Tashqaridan tekshiruv ───────────────────────────────────────────────
#
# "Yubordim" degani "qurilma ola oladi" degani emas: papka noto'g'ri
# bo'lishi, Caddy yo'lni bermasligi yoki fayl yarim ko'chgan bo'lishi
# mumkin.  Shuning uchun aynan qurilma yuradigan manzildan tekshiramiz.
echo "→ Tashqaridan tekshirilmoqda: $dl_url/releases/"
remote_size="$(curl -fsSL -o /dev/null -w '%{size_download}' \
  "$dl_url/releases/$(basename "$exe")")"
if [[ "$remote_size" != "$size_bytes" ]]; then
  echo "XATO: serverdagi fayl hajmi mos emas ($remote_size ≠ $size_bytes)" >&2
  exit 1
fi
curl -fsS "$dl_url/releases/$(basename "$manifest")" > /dev/null

# ── Eski relizlarni tozalash ────────────────────────────────────────────
#
# `releases/` hech qachon tozalanmasdi: har nashr ~100 MB qoldirardi va
# papka serverda 19 ta eski `.exe` bilan 1,9 GB ga o'sdi.  Diskning
# to'lishi bu yerda faqat "joy tugadi" degani emas — Postgres va MinIO
# o'sha diskda turadi.
#
# Nashrdan KEYIN: yangi juftlik joyida turganda "eng yangi uchta"
# hisobi to'g'ri chiqadi.  Tozalash yiqilsa nashr BUZILMAYDI — reliz
# allaqachon jonli, tozalash esa ertaga fon vazifasida qaytadi.
#
# Ikki qadam, chunki konteynerda papka `:ro` bilan ulangan (ataylab:
# internetga qaragan ilova qurilmalar o'rnatadigan faylni o'zgartira
# olmasligi kerak).  QAROR konteynerda qabul qilinadi — u qurilmalar
# hali so'rayotgan versiyani bazadan o'qiydi, baza esa faqat docker
# tarmog'i ichidan ko'rinadi.  O'CHIRISH hostda.
prune_remote() {
  local remote_root compose env_file plan
  remote_root="$(dirname "$remote_dir")"
  compose="${ENES_COMPOSE_FILE:-docker-compose.enes.yml}"
  env_file="${ENES_ENV_FILE:-.env.production}"
  plan="$(ssh "${scp_opts[@]}" "$ENES_RELEASE_HOST" \
    "cd '$remote_root' && docker compose --env-file '$env_file' -f '$compose' \
       exec -T cloud python scripts/prune_releases.py --reja")" || return 1
  # Nomlarni QAYTA tekshiramiz: `rm` ga o'tadigan ro'yxat masofadagi
  # buyruq chiqishidan keladi, ya'ni yo'l bo'ylab chiqib ketadigan yoki
  # bo'sh joyli nom umuman o'tmasligi kerak.
  plan="$(printf '%s\n' "$plan" | grep -E '^[A-Za-z0-9._-]+\.(exe|json)$' || true)"
  if [[ -z "$plan" ]]; then
    echo "   ✓ eski reliz yo'q, tozalash kerak emas"
    return 0
  fi
  printf '%s\n' "$plan" \
    | ssh "${scp_opts[@]}" "$ENES_RELEASE_HOST" \
        "cd '$remote_dir' && xargs -r rm -f --" || return 1
  echo "   ✓ o'chirildi: $(printf '%s\n' "$plan" | wc -l | tr -d ' ') fayl"
}

echo "→ Serverdagi eski relizlar tozalanmoqda (har prefiksda 3 juftlik qoladi)…"
if ! prune_remote; then
  echo "   ⚠ tozalash bajarilmadi — nashr o'z holida, keyin qo'lda:" >&2
  echo "     docker compose exec -T cloud python scripts/prune_releases.py --reja" >&2
fi

echo
echo "✓ $version nashr qilindi."
echo
echo "Endi nima bo'ladi:"
echo "  · yangilanish siyosati 'auto' bo'lgan qurilmalar 15 daqiqada oladi;"
echo "  · o'rnatilgandan keyin 30 daqiqa ichida panel ko'tarilmasa, qurilma"
echo "    o'zi eski versiyaga qaytadi va bu versiyani bloklaydi."
echo
echo "Tarqatishni boshqarish (docs/RELIZ_VA_OTA.md):"
echo "  python3 scripts/rollout.py --holat"
echo "  python3 scripts/rollout.py --sinov <site_id>    # avval bitta do'konda"
echo "  python3 scripts/rollout.py --hammaga            # 24 soatdan keyin"
