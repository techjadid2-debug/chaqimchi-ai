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

Public leadlar uchun kamida quyidagilar bo‘lsin:

```env
CHAQIMCHI_OWNER_TELEGRAM_TOKEN=BOTFATHER_TOKEN
CHAQIMCHI_TELEGRAM_WEBHOOK_SECRET=UZUN_RANDOM_SECRET
CHAQIMCHI_CLOUD_TELEGRAM_CHAT_ID=-1003319785064
CHAQIMCHI_TELEGRAM_LEAD_CHAT_IDS=5476913898
CHAQIMCHI_TELEGRAM_AUTO_GROUP_LEADS=true
```

Shaxsiy foydalanuvchi botga avval `/start` yuboradi. Bot ichki guruhga
qo‘shilgach guruhda `/leads` yuboriladi. Webhook:

```text
https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<DOMAIN>/api/v1/telegram/webhook/<WEBHOOK_SECRET>
```

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
