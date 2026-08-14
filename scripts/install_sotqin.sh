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

# Canonical qurilma bo'sh Ubuntu Server 24.04 bo'lishi mumkin. Python binari
# borligi `venv` moduli ham bor degani emas; installer barcha runtime
# prerequisite'larni bir marta, non-interactive usulda tayyorlaydi.
if command -v apt-get >/dev/null 2>&1; then
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y \
    ca-certificates curl ffmpeg python3 python3-venv
fi
for binary in curl ffmpeg ffprobe python3; do
  if ! command -v "$binary" >/dev/null 2>&1; then
    echo "$binary topilmadi. Sotqin R1 uchun Ubuntu Server 24.04 ishlating." >&2
    exit 2
  fi
done

id chaqimchi >/dev/null 2>&1 || useradd --system --home "$install_root" --shell /usr/sbin/nologin chaqimchi
install -d -o chaqimchi -g chaqimchi "$release" "$install_root/shared/data" "$install_root/shared/logs" "$install_root/shared/models"
install -d "$release/config" "$release/models" "$release/scripts"
cp -a "$source_dir/chaqimchi_ai" "$source_dir/webapp" "$source_dir/requirements-sotqin.txt" "$release/"
cp -a "$source_dir/config/sotqin.yaml" "$source_dir/config/rules.yaml" "$release/config/"
cp -a "$source_dir/models/retail_manifest.json" "$release/models/"
for script in \
  accept_n100_pilot.py apply_signed_update.py backup_db.py benchmark_n100.py \
  calibrate_threshold.py fetch_retail_model.py install_sotqin.sh pair_edge.py \
  pair_sotqin.py soak_n100.py verify_model_bundle.py; do
  cp -a "$source_dir/scripts/$script" "$release/scripts/"
done
ln -s "$install_root/shared/data" "$release/data"
python3 -m venv "$install_root/venv"
"$install_root/venv/bin/pip" install --upgrade pip
"$install_root/venv/bin/pip" install -r "$release/requirements-sotqin.txt"

# Retail modeli repoga binary sifatida kirmaydi. Rasmiy HTTPS manbadan olinadi
# va commit qilingan SHA-256 manifesti bilan tekshiriladi.
"$install_root/venv/bin/python" "$release/scripts/fetch_retail_model.py"
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

set_env_value() {
  local key="$1" value="$2" file="$3"
  if grep -q "^${key}=" "$file"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$file"
  else
    printf '%s=%s\n' "$key" "$value" >> "$file"
  fi
}

if grep -Eq '^CHAQIMCHI_API_KEY=(GENERATE.*|)$' /etc/chaqimchi/sotqin.env; then
  set_env_value CHAQIMCHI_API_KEY \
    "$("$install_root/venv/bin/python" -c 'import secrets; print(secrets.token_urlsafe(32))')" \
    /etc/chaqimchi/sotqin.env
fi
if grep -Eq '^CHAQIMCHI_JWT_SECRET=(GENERATE.*|)$' /etc/chaqimchi/sotqin.env; then
  set_env_value CHAQIMCHI_JWT_SECRET \
    "$("$install_root/venv/bin/python" -c 'import secrets; print(secrets.token_urlsafe(48))')" \
    /etc/chaqimchi/sotqin.env
fi
if grep -Eq '^CHAQIMCHI_EMBEDDING_KEY=(GENERATE.*|)$' /etc/chaqimchi/sotqin.env; then
  set_env_value CHAQIMCHI_EMBEDDING_KEY \
    "$("$install_root/venv/bin/python" -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" \
    /etc/chaqimchi/sotqin.env
fi
chmod 0600 /etc/chaqimchi/sotqin.env
install -m 0644 "$source_dir/deploy/chaqimchi-sotqin.service" /etc/systemd/system/chaqimchi-sotqin.service
install -m 0644 "$source_dir/deploy/chaqimchi-retail.service" /etc/systemd/system/chaqimchi-retail.service
install -m 0644 "$source_dir/deploy/chaqimchi-attendance.service" /etc/systemd/system/chaqimchi-attendance.service
systemctl daemon-reload
systemctl enable chaqimchi-sotqin.service chaqimchi-retail.service
if grep -Eq '^CHAQIMCHI_ATTENDANCE_PILOT=(1|true|yes)$' /etc/chaqimchi/sotqin.env; then
  systemctl enable chaqimchi-attendance.service
fi
echo "Sotqin R1 o'rnatildi: control va retail tayyor. Pairingdan keyin xizmatlar ishga tushadi."
