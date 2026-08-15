#!/usr/bin/env bash
# Sotqin first-install uchun transport paketi yaratadi.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"

allow_dirty=false
args=()
for arg in "$@"; do
  case "$arg" in
    --allow-dirty) allow_dirty=true ;;
    *) args+=("$arg") ;;
  esac
done

# Commit qilinmagan o'zgarish bilan qurilgan paket qaysi kod ekanini hech kim
# ayta olmaydi — va u mijoz qurilmasiga tushadi. Diskda aynan shunday eskirgan
# tarball topilgan: nomi 0.5.0, ichi esa boshqa kod.
if [[ "$allow_dirty" != true ]] && command -v git >/dev/null 2>&1; then
  if ! git -C "$root" diff --quiet HEAD 2>/dev/null; then
    echo "XATO: worktree iflos — avval commit qiling yoki --allow-dirty bering" >&2
    git -C "$root" status --short >&2
    exit 1
  fi
fi

version="$(awk -F '"' '/^version = / { print $2; exit }' "$root/pyproject.toml")"
name="chaqimchi-sotqin-${version}"
output_dir="${args[0]:-$root/releases}"
stage="$(mktemp -d "${TMPDIR:-/tmp}/chaqimchi-release.XXXXXX")"
cleanup() { rm -rf "$stage"; }
trap cleanup EXIT

mkdir -p "$output_dir" "$stage/$name" "$stage/$name/config" "$stage/$name/models" "$stage/$name/deploy" "$stage/$name/scripts"
cp -R "$root/chaqimchi_ai" "$root/webapp" "$stage/$name/"
cp "$root/config/sotqin.yaml" "$root/config/rules.yaml" "$stage/$name/config/"
cp "$root/models/retail_manifest.json" "$stage/$name/models/"
cp \
  "$root/deploy/sotqin.env.example" \
  "$root/deploy/update-public.pem" \
  "$root/deploy/chaqimchi-sotqin.service" \
  "$root/deploy/chaqimchi-retail.service" \
  "$root/deploy/chaqimchi-attendance.service" \
  "$stage/$name/deploy/"
for script in \
  accept_n100_pilot.py apply_signed_update.py backup_db.py benchmark_n100.py \
  calibrate_threshold.py fetch_retail_model.py install_sotqin.sh \
  pair_sotqin.py soak_n100.py sotqin_preflight.py verify_model_bundle.py; do
  cp "$root/scripts/$script" "$stage/$name/scripts/"
done
# Ikkala requirements ham paketga kiradi; qaysi birini o'rnatishni
# `install_sotqin.sh` CHAQIMCHI_ATTENDANCE_PILOT bo'yicha hal qiladi.
cp "$root/requirements-sotqin.txt" "$root/requirements-attendance.txt" "$stage/$name/"
tar -C "$stage" -czf "$output_dir/${name}.tar.gz" "$name"

if command -v sha256sum >/dev/null 2>&1; then
  sha256sum "$output_dir/${name}.tar.gz"
else
  shasum -a 256 "$output_dir/${name}.tar.gz"
fi
