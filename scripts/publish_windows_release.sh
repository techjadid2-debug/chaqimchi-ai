#!/usr/bin/env bash
#
# Windows relizini serverga chiqaradi — shundan keyin do'kondagi
# qurilmalar uni 15 daqiqada o'zi oladi.
#
# Nega alohida skript kerak: `make windows-release` faqat NOUTBUKDA
# `.exe` va imzolangan `.json` yasaydi.  Ular serverdagi `releases/`
# papkasiga tushmaguncha hech bir do'kon yangilanmaydi — cloud aynan
# o'sha papkadan `chaqimchi-windows-<versiya>.exe` va `.json` juftini
# qidiradi (`cloud/main.py: latest_windows_release`).  Bu oxirgi qadam
# qo'lda `scp` edi va uni unutish "reliz chiqdi, lekin hech kimga
# yetmadi" degan jim holatga olib kelardi.
#
# Ishlatish:
#   CHAQIMCHI_RELEASE_HOST=deploy@169.58.198.111 \
#     scripts/publish_windows_release.sh
#
#   # CI qurgan faylni chiqarish (GitHub Releases'dan yuklab olingan):
#   CHAQIMCHI_RELEASE_HOST=deploy@169.58.198.111 \
#     scripts/publish_windows_release.sh --exe ~/Downloads/Chaqimchi_AI_Setup.exe
#
# Muhitdan o'qiladi:
#   CHAQIMCHI_RELEASE_HOST      majburiy — `deploy@IP`
#   CHAQIMCHI_RELEASE_DIR       serverdagi papka (standart quyida)
#   CHAQIMCHI_RELEASE_SSH_KEY   SSH kaliti (standart `.deploy_keys/chaqimchi_prod`)
#   CHAQIMCHI_DL_URL            tashqi tekshiruv manzili (standart dl.chaqimchi.uz)
#
set -euo pipefail

cd "$(dirname "$0")/.."

remote_dir="${CHAQIMCHI_RELEASE_DIR:-/home/deploy/chaqimchi-ai/releases}"
ssh_key="${CHAQIMCHI_RELEASE_SSH_KEY:-.deploy_keys/chaqimchi_prod}"
dl_url="${CHAQIMCHI_DL_URL:-https://dl.chaqimchi.uz}"
py="${PY:-python3}"

source_exe=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --exe) source_exe="${2:-}"; shift 2 ;;
    *) echo "Noma'lum argument: $1 (faqat --exe <fayl>)" >&2; exit 2 ;;
  esac
done

if [[ -z "${CHAQIMCHI_RELEASE_HOST:-}" ]]; then
  echo "CHAQIMCHI_RELEASE_HOST berilishi shart (masalan deploy@169.58.198.111)" >&2
  exit 1
fi

version="$("$py" -c 'import chaqimchi_ai; print(chaqimchi_ai.__version__)')"
exe="releases/chaqimchi-windows-$version.exe"
manifest="releases/chaqimchi-windows-$version.json"
echo "→ Versiya: $version"

# CI qurgan fayl boshqa nom bilan keladi (`Chaqimchi_AI_Setup.exe`).
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
  echo "  make windows-release CLOUD_URL=https://api.chaqimchi.uz" >&2
  echo "yoki CI qurgan faylni bering: --exe <yuklab olingan .exe>" >&2
  exit 1
fi

# ── Imzo ────────────────────────────────────────────────────────────────
#
# Imzosiz paketni qurilma RAD ETADI (`chaqimchi_ai/signed_update.py`) —
# ya'ni imzolanmagan relizni chiqarish shunchaki foydasiz ish bo'lardi.
if [[ ! -f "$manifest" ]]; then
  echo "→ Imzolanmoqda…"
  "$py" scripts/sign_release.py "$exe"
fi

echo "→ Imzo tekshirilmoqda (qurilmadagi ochiq kalit bilan)…"
"$py" - "$exe" "$manifest" <<'PY'
import sys
from pathlib import Path

from chaqimchi_ai.signed_update import verify_release_manifest

archive, manifest = Path(sys.argv[1]), Path(sys.argv[2])
data = verify_release_manifest(archive, manifest, Path("deploy/update-public.pem"))
print(f"   ✓ {data['version']} · {data.get('product', 'chaqimchi-windows')}")
PY

size_bytes="$(wc -c < "$exe" | tr -d ' ')"
echo "→ Hajmi: $((size_bytes / 1024 / 1024)) MB"

# ── Serverga ────────────────────────────────────────────────────────────
scp_opts=(-o StrictHostKeyChecking=accept-new)
if [[ -f "$ssh_key" ]]; then
  scp_opts+=(-i "$ssh_key")
fi

echo "→ Serverga yuborilmoqda: $CHAQIMCHI_RELEASE_HOST:$remote_dir"
scp "${scp_opts[@]}" "$exe" "$manifest" "$CHAQIMCHI_RELEASE_HOST:$remote_dir/"

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
