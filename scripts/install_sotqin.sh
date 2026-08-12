#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Sotqin installer root huquqi bilan ishlashi kerak" >&2
  exit 1
fi

source_dir="$(cd "$(dirname "$0")/.." && pwd)"
install_root=/opt/chaqimchi
version="$(date -u +%Y%m%dT%H%M%SZ)"
release="$install_root/releases/$version"

id chaqimchi >/dev/null 2>&1 || useradd --system --home "$install_root" --shell /usr/sbin/nologin chaqimchi
install -d -o chaqimchi -g chaqimchi "$release" "$install_root/shared/data" "$install_root/shared/logs"
cp -a "$source_dir/chaqimchi_ai" "$source_dir/config" "$source_dir/scripts" "$source_dir/requirements-sotqin.txt" "$release/"
ln -s "$install_root/shared/data" "$release/data"
python3 -m venv "$install_root/venv"
"$install_root/venv/bin/pip" install --upgrade pip
"$install_root/venv/bin/pip" install -r "$release/requirements-sotqin.txt"
ln -sfn "$release" "$install_root/current"
chown -R chaqimchi:chaqimchi "$install_root"

install -d -m 0700 /etc/chaqimchi
if [[ ! -f /etc/chaqimchi/sotqin.env ]]; then
  if [[ -f /etc/chaqimchi/edge.env ]]; then
    install -m 0600 /etc/chaqimchi/edge.env /etc/chaqimchi/sotqin.env
  else
    install -m 0600 "$source_dir/deploy/sotqin.env.example" /etc/chaqimchi/sotqin.env
  fi
fi
install -m 0644 "$source_dir/deploy/chaqimchi-sotqin.service" /etc/systemd/system/chaqimchi-sotqin.service
systemctl daemon-reload
systemctl enable chaqimchi-sotqin.service
echo "Sotqin R1 o'rnatildi. pair_sotqin.py bilan ulang, keyin: systemctl start chaqimchi-sotqin"
