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

mkdir -p "$output_dir" "$stage/$name"
cp -R "$root/chaqimchi_ai" "$root/config" "$root/deploy" "$root/scripts" "$stage/$name/"
cp "$root/requirements-sotqin.txt" "$stage/$name/"
tar -C "$stage" -czf "$output_dir/${name}.tar.gz" "$name"

if command -v sha256sum >/dev/null 2>&1; then
  sha256sum "$output_dir/${name}.tar.gz"
else
  shasum -a 256 "$output_dir/${name}.tar.gz"
fi
