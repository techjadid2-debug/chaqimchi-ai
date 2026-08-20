#!/usr/bin/env bash
#
# Kunlik backup yiqilganda Telegramga xabar beradi.
#
# Nega kerak: `chaqimchi-backup.service` — `Type=oneshot` va unda
# `OnFailure=` yo'q edi.  Skript yiqilsa (masalan compose fayl nomi
# noto'g'ri bo'lsa) systemd shunchaki xatoni jurnalga yozardi va boshqa
# hech narsa bo'lmasdi.  Har kecha jimgina takrorlanadigan bunday xato
# faqat server yo'qolganda — ya'ni juda kech — bilinardi.
#
# `ExecStartPost` dagi eskirgan arxivlarni o'chirish ham o'tkazib
# yuboriladi, ya'ni papkada eski nusxa turadi va hammasi joyidaday
# ko'rinadi.
#
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
env_file="$repo_dir/${CHAQIMCHI_ENV_FILE:-.env.production}"
[[ -f "$env_file" ]] || exit 0

value_of() {
  # `KEY=value` — tirnoqlarsiz, birinchi mos qator.
  sed -n "s/^$1=//p" "$env_file" | head -n 1 | tr -d "\"'" | tr -d '\r'
}

token="$(value_of CHAQIMCHI_SALES_TELEGRAM_TOKEN)"
[[ -n "$token" ]] || token="$(value_of CHAQIMCHI_CLOUD_TELEGRAM_TOKEN)"
[[ -n "$token" ]] || token="$(value_of CHAQIMCHI_OWNER_TELEGRAM_TOKEN)"
chat="$(value_of CHAQIMCHI_CLOUD_TELEGRAM_CHAT_ID)"
[[ -n "$chat" ]] || chat="$(value_of CHAQIMCHI_TELEGRAM_LEAD_CHAT_IDS | cut -d, -f1)"

if [[ -z "$token" || -z "$chat" ]]; then
  echo "Telegram sozlanmagan — backup xatosi haqida xabar yuborilmadi" >&2
  exit 0
fi

host="$(hostname)"
text="⚠️ Chaqimchi: kunlik zaxira nusxa OLINMADI ($host).
Sabab: journalctl -u chaqimchi-backup.service -n 30
Tuzatilmaguncha yangi zaxira yo'q."

curl -fsS --max-time 20 \
  "https://api.telegram.org/bot${token}/sendMessage" \
  --data-urlencode "chat_id=${chat}" \
  --data-urlencode "text=${text}" >/dev/null || {
    echo "Telegram xabari yuborilmadi" >&2
    exit 0
  }
