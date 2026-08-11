#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "root sifatida ishga tushiring" >&2
  exit 1
fi
source_dir="$(cd "$(dirname "$0")/.." && pwd)"
install_root=/opt/chaqimchi
version="$(date -u +%Y%m%dT%H%M%SZ)"
release="$install_root/releases/$version"

id chaqimchi >/dev/null 2>&1 || useradd --system --home "$install_root" --shell /usr/sbin/nologin chaqimchi
install -d -o chaqimchi -g chaqimchi "$release" "$install_root/shared/data" "$install_root/shared/models" "$install_root/shared/logs"
cp -a "$source_dir/chaqimchi_ai" "$source_dir/webapp" "$source_dir/config" "$source_dir/requirements.txt" "$release/"
ln -s "$install_root/shared/data" "$release/data"
ln -s "$install_root/shared/models" "$release/models"
python3 -m venv "$install_root/venv"
"$install_root/venv/bin/pip" install --upgrade pip
"$install_root/venv/bin/pip" install -r "$release/requirements.txt"
ln -sfn "$release" "$install_root/current"
chown -R chaqimchi:chaqimchi "$install_root"

install -d -m 0700 /etc/chaqimchi
if [[ ! -f /etc/chaqimchi/edge.env ]]; then
  install -m 0600 "$source_dir/deploy/edge.env.example" /etc/chaqimchi/edge.env
fi
install -m 0644 "$source_dir/deploy/chaqimchi-edge.service" /etc/systemd/system/chaqimchi-edge.service
systemctl daemon-reload
systemctl enable chaqimchi-edge.service
echo "O'rnatildi. /etc/chaqimchi/edge.env va licensed modellarni to'ldirib, keyin: systemctl start chaqimchi-edge"
