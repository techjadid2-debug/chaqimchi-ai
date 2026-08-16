# Chaqimchi Cloud production runbook

Bu hujjat rasmiy sayt → lead API → SQLite → Telegram, admin/owner API,
PostgreSQL va MinIO bilan ishlaydigan cloud deployi uchun canonical tartibdir.

## 1. Environment

Cloud va Sotqin env'larini aralashtirmang:

- cloud: `.env.production.example` → `.env.production`;
- Sotqin: `deploy/sotqin.env.example` → `/etc/chaqimchi/sotqin.env`.

Cloud env fayli `chmod 600 .env.production` bo‘lishi shart. Deploydan oldin:

```bash
python3 scripts/production_preflight.py --env-file .env.production
```

Birinchi login/parolli adminni interaktiv yarating. Parol shell history yoki
process listga tushmaydi:

```bash
docker compose --env-file .env.production -f docker-compose.contabo.yml exec cloud \
  python scripts/create_portal_account.py --username admin --name "Bosh admin" --role admin
```

Keyingi admin, o‘rnatuvchi va mijoz loginlari `/admin` ichidan yaratiladi.
O‘rnatuvchi public `/installer` sahifasida ro‘yxatdan o‘tsa `pending` bo‘ladi;
admin faollashtirib, faqat kerakli obyektni biriktiradi. Xarid qilgan mijoz
akkaunti obyektga bog‘lanadi va `/owner` panelida Sotqin/kamera holatini ko‘radi.

Public leadlar uchun kamida quyidagilar bo‘lsin:

```env
CHAQIMCHI_OWNER_TELEGRAM_TOKEN=BOTFATHER_TOKEN
CHAQIMCHI_TELEGRAM_BOT_USERNAME=BOT_USERNAME
CHAQIMCHI_TELEGRAM_WEBHOOK_SECRET=UZUN_RANDOM_SECRET
CHAQIMCHI_CLOUD_TELEGRAM_CHAT_ID=-1003319785064
CHAQIMCHI_TELEGRAM_LEAD_CHAT_IDS=5476913898
```

Public ro'yxatdan o'tish havolasi botni `start=register` bilan ochadi. `/start`
ichida Sotqin o'rnatuvchi va harid qilgan mijoz paneli tugmalari chiqadi.
Leadlar faqat `CHAQIMCHI_TELEGRAM_LEAD_CHAT_IDS` dagi shaxsiy ID'larga boradi.
Webhook:

```text
POST https://api.telegram.org/bot<TOKEN>/setWebhook
url=https://<DOMAIN>/api/v1/telegram/webhook
secret_token=<WEBHOOK_SECRET>
```

Secret URL'ga yozilmaydi: Telegram uni har update'da
`X-Telegram-Bot-Api-Secret-Token` headerida yuboradi, shu sabab access-logda
maxfiy qiymat ko'rinmaydi.

Token yoki secretni terminal tarixiga yozmaslik uchun real chaqiruvni vaqtinchalik,
history o‘chirilgan shell yoki secret manager orqali bajaring.

## 2. Backup va deploy

Dedicated server:

```bash
export CHAQIMCHI_BACKUP_DIR=/srv/chaqimchi-backups
export CHAQIMCHI_BACKUP_PASSWORD='UZUN_BACKUP_SECRET'
./scripts/deploy_cloud.sh
```

Bandlik/Vizora/Robosinf bilan bitta Caddy ishlatadigan test server:

```bash
export CHAQIMCHI_COMPOSE_FILE=docker-compose.contabo.yml
export CHAQIMCHI_BACKUP_DIR=/home/deploy/chaqimchi-backups
export CHAQIMCHI_BACKUP_PASSWORD='UZUN_BACKUP_SECRET'
./scripts/deploy_cloud.sh
```

Deploy mavjud cloud bo‘lsa avval PostgreSQL, SQLite cloud-state va MinIO’ni
AES-256 bilan backup qiladi. Yangi container 180 soniyada healthy bo‘lmasa,
oldingi Docker image avtomatik qayta yoqiladi.

Backup fayli va uning paroli bir joyda saqlanmasin. Kamida oyiga bir marta
alohida staging hostda restore drill o‘tkazing. Restore drill bajarilmaguncha
“backup bor” production tayyor degani emas.

### 2.1 Kunlik avtomatik backup (majburiy)

Deploy paytidagi backup yetarli emas: deploy bo‘lmagan har kun — backup
bo‘lmagan kun. VPS’da bir marta o‘rnatiladi:

```bash
sudo mkdir -p /etc/chaqimchi
sudo cp deploy/backup.env.example /etc/chaqimchi/backup.env
sudo nano /etc/chaqimchi/backup.env         # parol va yo'llarni kiriting
sudo chmod 600 /etc/chaqimchi/backup.env
sudo cp deploy/chaqimchi-backup.service deploy/chaqimchi-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now chaqimchi-backup.timer
sudo systemctl start chaqimchi-backup.service   # birinchi sinov darhol
systemctl list-timers chaqimchi-backup.timer    # keyingi ishga tushish vaqti
```

Har kuni 03:30 da backup olinadi, 14 kundan eskilari o‘chiriladi.
Holatni tekshirish: `journalctl -u chaqimchi-backup.service -n 20`.

### 2.2 Restore mashqi (oyiga 1 marta)

```bash
# 1. Oxirgi arxivni oching
openssl enc -d -aes-256-cbc -pbkdf2 -pass env:CHAQIMCHI_BACKUP_PASSWORD \
  -in chaqimchi-<sana>.tar.gz.enc | tar -xz -C /tmp/restore-drill

# 2. Ichida uchtasi ham borligini tekshiring:
#    postgres.dump (pg_restore --list bilan ochiladimi),
#    cloud-state/cloud.db (sqlite3 "PRAGMA integrity_check"),
#    minio/ (snapshot fayllari bor)
pg_restore --list /tmp/restore-drill/postgres.dump | head
sqlite3 /tmp/restore-drill/cloud-state/cloud.db "PRAGMA integrity_check;"

# 3. Natijani sana bilan shu faylning ostiga yozib qo'ying.
```

Restore mashqlari jurnali:

| Sana | Kim | Natija |
|---|---|---|
| _hali o‘tkazilmagan_ | | |

## 3. Deploydan keyingi tekshiruv

```bash
curl -fsS https://DOMAIN/health
curl -fsS https://DOMAIN/api/v1/public/pricing
curl -fsS https://DOMAIN/status
```

Admin readiness ichida quyidagilar tekshiriladi:

- PostgreSQL/S3/HTTPS va owner bot;
- lead Telegram recipientlari;
- N100 benchmark + 72 soatlik soak qabul fayli;
- servis alertlari va to‘lov provayderlari.

Test leadni saytdan yuboring va to‘rtta chegarani tasdiqlang:

1. UI muvaffaqiyat xabarini ko‘rsatdi;
2. `POST /api/v1/public/leads` `200` qaytardi;
3. lead admin ro‘yxati/SQLite’da paydo bo‘ldi;
4. guruh va shaxsiy chatdagi `lead_notification_deliveries` holati `sent` bo‘ldi.

Telegram vaqtincha ishlamasa delivery `failed` bo‘ladi va exponential retry
bilan qayta yuboriladi. Recipient lead yuborilgandan keyin ulansa, oxirgi 24
soatdagi hali delivery yozuvi yo‘q leadlar navbatga qaytariladi.

## 4. Sotuvga ochish darvozasi

Kod deployi apparat qabul testining o‘rnini bosmaydi. Quyidagilar tugamaguncha
AI funksiyalari katalogda “tez orada” bo‘lib qoladi:

- haqiqiy do‘kon videosida Intel GPU benchmark;
- 4 kamera bilan kamida 72 soat soak;
- kamera uptime ≥99%, kutilmagan restart 0;
- kritik event yo‘qotilishi 0;
- `scripts/accept_n100_pilot.py` yaratgan qabul fayli.

Payme/Click credentiallari bo‘lmasa onlayn checkout ochilmaydi; pilotda admin
qo‘lda invoice’ni to‘langan deb belgilashi mumkin.
