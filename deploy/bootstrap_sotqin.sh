#!/usr/bin/env bash
# Chaqimchi AI rasmiy saytidan birinchi Sotqin o'rnatishi uchun bootstrap.
# Release SHA-256 cloud tomonidan beriladi; keyingi relizlar signed updater bilan o'tadi.
set -euo pipefail

release_url="__RELEASE_URL__"
release_sha256="__RELEASE_SHA256__"
cloud_url="__CLOUD_URL__"
pairing_code=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --cloud) cloud_url="$2"; shift 2 ;;
    --code) pairing_code="$2"; shift 2 ;;
    *) echo "Noma'lum parametr: $1" >&2; exit 2 ;;
  esac
done

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Installer sudo/root bilan ishga tushishi kerak" >&2
  exit 1
fi
if [[ ! "$pairing_code" =~ ^[A-Fa-f0-9]{6}$ ]]; then
  echo "--code bilan 6 xonali pairing kod bering" >&2
  exit 2
fi
if [[ "$release_url" == __* || "$release_sha256" == __* ]]; then
  echo "Sotqin release hali admin tomonidan nashr qilinmagan" >&2
  exit 3
fi

workdir="$(mktemp -d /tmp/chaqimchi-sotqin.XXXXXX)"
cleanup() { rm -rf "$workdir"; }
trap cleanup EXIT
archive="$workdir/release.tar.gz"
curl --fail --location --proto '=https' --tlsv1.2 "$release_url" -o "$archive"
echo "$release_sha256  $archive" | sha256sum --check --status
mkdir -p "$workdir/release"
tar -xzf "$archive" -C "$workdir/release"
installer="$(find "$workdir/release" -path '*/scripts/install_sotqin.sh' -type f -print -quit)"
if [[ -z "$installer" ]]; then
  echo "Release ichida Sotqin installer topilmadi" >&2
  exit 4
fi
bash "$installer"
/opt/chaqimchi/venv/bin/python /opt/chaqimchi/current/scripts/pair_sotqin.py \
  --cloud "$cloud_url" --code "${pairing_code^^}"
systemctl restart chaqimchi-sotqin
systemctl restart chaqimchi-retail
if systemctl is-enabled --quiet chaqimchi-attendance.service; then
  systemctl restart chaqimchi-attendance
fi
systemctl --no-pager --full status chaqimchi-sotqin chaqimchi-retail >/dev/null
echo "Sotqin o'rnatildi: cloud control va do'kon analitikasi ishga tushdi."
