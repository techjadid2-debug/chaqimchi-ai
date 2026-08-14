#!/usr/bin/env bash
# Sotqin first-install uchun transport paketi yaratadi.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
version="$(awk -F '"' '/^version = / { print $2; exit }' "$root/pyproject.toml")"
name="chaqimchi-sotqin-${version}"
output_dir="${1:-$root/releases}"
stage="$(mktemp -d "${TMPDIR:-/tmp}/chaqimchi-release.XXXXXX")"
cleanup() { rm -rf "$stage"; }
trap cleanup EXIT

mkdir -p "$output_dir" "$stage/$name" "$stage/$name/config" "$stage/$name/models" "$stage/$name/deploy" "$stage/$name/scripts"
cp -R "$root/chaqimchi_ai" "$root/webapp" "$stage/$name/"
cp "$root/config/sotqin.yaml" "$root/config/rules.yaml" "$stage/$name/config/"
cp "$root/models/retail_manifest.json" "$stage/$name/models/"
cp \
  "$root/deploy/sotqin.env.example" \
  "$root/deploy/chaqimchi-sotqin.service" \
  "$root/deploy/chaqimchi-retail.service" \
  "$root/deploy/chaqimchi-attendance.service" \
  "$stage/$name/deploy/"
for script in \
  accept_n100_pilot.py apply_signed_update.py backup_db.py benchmark_n100.py \
  calibrate_threshold.py fetch_retail_model.py install_sotqin.sh \
  pair_sotqin.py soak_n100.py verify_model_bundle.py; do
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
