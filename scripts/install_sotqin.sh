#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Sotqin installer root huquqi bilan ishlashi kerak" >&2
  exit 1
fi

source_dir="$(cd "$(dirname "$0")/.." && pwd)"
install_root=/opt/chaqimchi
env_file=/etc/chaqimchi/sotqin.env
version="$(date -u +%Y%m%dT%H%M%SZ)"
release="$install_root/releases/$version"

# Canonical qurilma bo'sh Ubuntu Server 24.04 bo'lishi mumkin. Python binari
# borligi `venv` moduli ham bor degani emas; installer barcha runtime
# prerequisite'larni bir marta, non-interactive usulda tayyorlaydi.
#
# intel-opencl-icd va intel-media-va-driver — N100 ning integratsiyalangan
# grafikasi uchun. Ularsiz OpenVINO `available_devices` ichida "GPU" ni
# ko'rmaydi va detektor jimgina 4 ta CPU yadrosiga tushadi: tizim ishlayotgandek
# ko'rinadi, lekin 4-8 barobar sekin bo'ladi.
if command -v apt-get >/dev/null 2>&1; then
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y \
    ca-certificates curl ffmpeg python3 python3-venv \
    intel-opencl-icd intel-media-va-driver-non-free vainfo clinfo
fi
for binary in curl ffmpeg ffprobe python3; do
  if ! command -v "$binary" >/dev/null 2>&1; then
    echo "$binary topilmadi. Sotqin R1 uchun Ubuntu Server 24.04 ishlating." >&2
    exit 2
  fi
done

# ── iGPU tekshiruvi ───────────────────────────────────────────────────────
# Jimgina CPU'ga tushish — mahsulotni buzuq holda yetkazishning eng oson yo'li,
# chunki hech qanday xato chiqmaydi. Shuning uchun bu yerda baland ovoz bilan
# to'xtaymiz. Ishlab chiqish mashinasida CHAQIMCHI_ALLOW_CPU_ONLY=true bilan
# chetlab o'tish mumkin — lekin mijoz qurilmasida hech qachon.
allow_cpu_only="${CHAQIMCHI_ALLOW_CPU_ONLY:-false}"
gpu_ok=true
if ! clinfo -l 2>/dev/null | grep -qi intel; then
  echo "XATO: Intel iGPU OpenCL orqali ko'rinmadi (intel-opencl-icd)." >&2
  gpu_ok=false
fi
if ! vainfo --display drm >/dev/null 2>&1; then
  echo "XATO: VAAPI ishlamadi (intel-media-va-driver / /dev/dri huquqi)." >&2
  gpu_ok=false
fi
if [[ "$gpu_ok" != true ]]; then
  if [[ "$allow_cpu_only" =~ ^(1|true|yes)$ ]]; then
    echo "OGOHLANTIRISH: iGPU'siz davom etilmoqda — inferens CPU'da, ~4-8 barobar sekin." >&2
  else
    echo "Sotqin R1 iGPU'siz kafolatlangan tezlikni bermaydi. Qurilma Intel N100" >&2
    echo "ekanini va BIOS'da iGPU yoqilganini tekshiring. Ataylab CPU'da sinash" >&2
    echo "uchun: CHAQIMCHI_ALLOW_CPU_ONLY=true" >&2
    exit 3
  fi
fi

# `render` va `video` guruhlari /dev/dri/renderD128 ga kirish uchun shart —
# aks holda drayver o'rnatilgan bo'lsa ham xizmat GPU'ni ko'rmaydi.
if id chaqimchi >/dev/null 2>&1; then
  usermod -aG render,video chaqimchi || true
else
  useradd --system --home "$install_root" --shell /usr/sbin/nologin \
    --groups render,video chaqimchi
fi

# ── Muhit fayli ───────────────────────────────────────────────────────────
# Sirlar keyinroq (venv tayyor bo'lgach) yaratiladi, lekin faylning o'zi shu
# yerda kerak: davomat piloti yoqilganmi — pip o'rnatishidan oldin bilishimiz
# kerak.
install -d -m 0700 /etc/chaqimchi
if [[ ! -f "$env_file" ]]; then
  if [[ -f /etc/chaqimchi/edge.env ]]; then
    install -m 0600 /etc/chaqimchi/edge.env "$env_file"
  else
    install -m 0600 "$source_dir/deploy/sotqin.env.example" "$env_file"
  fi
fi

attendance=false
if grep -Eq '^CHAQIMCHI_ATTENDANCE_PILOT=(1|true|yes)$' "$env_file"; then
  attendance=true
fi

# ── Reliz nusxasi ─────────────────────────────────────────────────────────
install -d -o chaqimchi -g chaqimchi "$release" "$install_root/shared/data" "$install_root/shared/logs" "$install_root/shared/models"
install -d "$release/config" "$release/models" "$release/scripts"
cp -a "$source_dir/chaqimchi_ai" "$source_dir/requirements-sotqin.txt" "$release/"
# webapp — faqat davomat piloti UI'si. Do'kon analitikasi unga bog'liq emas.
if [[ "$attendance" == true ]]; then
  cp -a "$source_dir/webapp" "$source_dir/requirements-attendance.txt" "$release/"
fi
cp -a "$source_dir/config/sotqin.yaml" "$source_dir/config/rules.yaml" "$release/config/"
cp -a "$source_dir/models/retail_manifest.json" "$release/models/"
for script in \
  accept_n100_pilot.py apply_signed_update.py backup_db.py benchmark_n100.py \
  calibrate_threshold.py fetch_retail_model.py install_sotqin.sh \
  pair_sotqin.py soak_n100.py sotqin_preflight.py verify_model_bundle.py; do
  cp -a "$source_dir/scripts/$script" "$release/scripts/"
done
ln -s "$install_root/shared/data" "$release/data"

python3 -m venv "$install_root/venv"
"$install_root/venv/bin/pip" install --upgrade pip
if [[ "$attendance" == true ]]; then
  # requirements-attendance.txt asosiy faylni `-r` orqali o'z ichiga oladi.
  "$install_root/venv/bin/pip" install -r "$release/requirements-attendance.txt"
else
  "$install_root/venv/bin/pip" install -r "$release/requirements-sotqin.txt"
fi

# Retail modeli repoga binary sifatida kirmaydi. Rasmiy HTTPS manbadan olinadi
# va commit qilingan SHA-256 manifesti bilan tekshiriladi.
"$install_root/venv/bin/python" "$release/scripts/fetch_retail_model.py"
ln -sfn "$release" "$install_root/current"
chown -R chaqimchi:chaqimchi "$install_root"

set_env_value() {
  local key="$1" value="$2" file="$3"
  if grep -q "^${key}=" "$file"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$file"
  else
    printf '%s=%s\n' "$key" "$value" >> "$file"
  fi
}

if grep -Eq '^CHAQIMCHI_API_KEY=(GENERATE.*|)$' "$env_file"; then
  set_env_value CHAQIMCHI_API_KEY \
    "$("$install_root/venv/bin/python" -c 'import secrets; print(secrets.token_urlsafe(32))')" \
    "$env_file"
fi
if grep -Eq '^CHAQIMCHI_JWT_SECRET=(GENERATE.*|)$' "$env_file"; then
  set_env_value CHAQIMCHI_JWT_SECRET \
    "$("$install_root/venv/bin/python" -c 'import secrets; print(secrets.token_urlsafe(48))')" \
    "$env_file"
fi
if grep -Eq '^CHAQIMCHI_EMBEDDING_KEY=(GENERATE.*|)$' "$env_file"; then
  set_env_value CHAQIMCHI_EMBEDDING_KEY \
    "$("$install_root/venv/bin/python" -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" \
    "$env_file"
fi
chmod 0600 "$env_file"

# ── OTA ishonch langari ───────────────────────────────────────────────────
# Ochiq kalit shu yerda bir marta qotiriladi va **almashtirilmaydi**.
#
# Birinchi o'rnatishda ishonch baribir cloudga tayanadi: arxiv HTTPS bilan
# olinadi va SHA-256 tekshiriladi.  Lekin kalit qotirilgach, keyinchalik
# cloud buzilsa ham hujumchi imzo yasay olmaydi va qurilma eski kodda
# qolaveradi.  Agar bu yerda har o'rnatishda ustiga yozilsa, zararli paket
# o'z kalitini qo'yib qo'ya olardi va butun imzo qatlami ma'nosiz bo'lardi.
update_key=/etc/chaqimchi/update-public.pem
new_key="$source_dir/deploy/update-public.pem"
if [[ -f "$new_key" ]]; then
  if [[ ! -f "$update_key" ]]; then
    install -m 0644 "$new_key" "$update_key"
    echo "OTA ochiq kaliti o'rnatildi: $update_key"
  elif ! cmp -s "$new_key" "$update_key"; then
    if [[ "${CHAQIMCHI_ROTATE_UPDATE_KEY:-false}" =~ ^(1|true|yes)$ ]]; then
      install -m 0644 "$new_key" "$update_key"
      echo "OGOHLANTIRISH: OTA kaliti ataylab almashtirildi" >&2
    else
      echo "OGOHLANTIRISH: paketdagi OTA kaliti qurilmadagidan farq qiladi." >&2
      echo "Mavjud kalit saqlab qolindi. Ataylab almashtirish uchun:" >&2
      echo "  CHAQIMCHI_ROTATE_UPDATE_KEY=true" >&2
    fi
  fi
else
  echo "OGOHLANTIRISH: paketda OTA ochiq kaliti yo'q — bu qurilma masofadan yangilanmaydi" >&2
fi

install -m 0644 "$source_dir/deploy/chaqimchi-sotqin.service" /etc/systemd/system/chaqimchi-sotqin.service
install -m 0644 "$source_dir/deploy/chaqimchi-retail.service" /etc/systemd/system/chaqimchi-retail.service
systemctl daemon-reload
systemctl enable chaqimchi-sotqin.service chaqimchi-retail.service
if [[ "$attendance" == true ]]; then
  install -m 0644 "$source_dir/deploy/chaqimchi-attendance.service" /etc/systemd/system/chaqimchi-attendance.service
  systemctl daemon-reload
  systemctl enable chaqimchi-attendance.service
fi
echo "Sotqin R1 o'rnatildi: control va retail tayyor. Pairingdan keyin xizmatlar ishga tushadi."
