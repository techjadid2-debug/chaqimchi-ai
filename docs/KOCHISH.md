# Yangi serverga ko'chirish (chaqimchi.uz platformasi)

Eski VPS to'lovdan uzilgan; bu hujjat noldan yangi serverga qo'yishning
to'liq ro'yxati. Kod GitHubda tayyor — server + DNS + shu qadamlar qoladi.

## 0. Server tanlash (tavsiya)

**Tavsiya: aHOST VPS** — domen bilan bitta panelda, so'mda to'lanadi
("karta to'lovi unutildi → server o'chdi" xavfi keskin kamayadi),
O'zbekistondan ping past, Payme/Click ga yaqin.

- Minimal: **4 GB RAM / 2 vCPU / 60+ GB SSD** (Postgres + MinIO + cloud +
  yuz modellari uchun; Docker imagelar ~2 GB, modellar ~0.5 GB).
- Muqobil: Hetzner/Contabo — arzonroq spec, lekin valyuta kartasi va
  balandroq ping. Qaysi bo'lsa ham Ubuntu 22.04/24.04 + Docker.

## 1. DNS (aHOST panelida — Mening domenlarim → chaqimchi.uz → DNS)

Server IP'si ma'lum bo'lgach A yozuvlar (TTL 300):

| Yozuv | Turi | Qiymat |
|---|---|---|
| `@` (chaqimchi.uz) | A | SERVER_IP |
| `www` | A | SERVER_IP |
| `api` | A | SERVER_IP |
| `app` | A | SERVER_IP |
| `admin` | A | SERVER_IP |
| `dl` | A | SERVER_IP |
| `partner` | A | SERVER_IP |
| `docs` | A | SERVER_IP |
| `status` | CNAME | UptimeRobot bergan manzil (7-qadam) |

DNS tarqalishini tekshirish: `dig +short api.chaqimchi.uz`.

## 2. Serverni tayyorlash

```bash
apt update && apt install -y docker.io docker-compose-v2 git rsync
adduser deploy && usermod -aG docker deploy
# SSH kalitni deploy foydalanuvchiga qo'shing; parolli kirishni o'chiring.
```

Kod: `git clone git@github.com:techjadid2-debug/chaqimchi-ai.git /home/deploy/chaqimchi-ai`
(yoki Mac'dan rsync — deploy skript baribir lokal build qiladi).

## 3. .env.production

`.env.production.example` dan nusxa oling va to'ldiring. Yangi/muhim:

```
CHAQIMCHI_PUBLIC_URL=https://chaqimchi.uz
CHAQIMCHI_APP_URL=https://app.chaqimchi.uz
CHAQIMCHI_API_URL=https://api.chaqimchi.uz
CHAQIMCHI_DL_URL=https://dl.chaqimchi.uz
CHAQIMCHI_PARTNER_URL=https://partner.chaqimchi.uz
CHAQIMCHI_ADMIN_URL=https://admin.chaqimchi.uz
# Face ID piloti (o'z do'koningiz uchun):
CHAQIMCHI_ATTENDANCE_PILOT=true
CHAQIMCHI_EMBEDDING_KEY=<yangi Fernet kalit>
CHAQIMCHI_FACE_RETENTION_DAYS=14
```

Barcha sirlar YANGI generatsiya qilinadi (eski serverdagi sirlar
ishlatilmaydi). Fernet kalit: `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
Tekshiruv: `python3 scripts/production_preflight.py` (xato chiqmaguncha deploy yo'q).

## 4. Deploy

```bash
cd /home/deploy/chaqimchi-ai
export CHAQIMCHI_COMPOSE_FILE=docker-compose.chaqimchi.yml   # Caddy ichida, subdomenlar bilan
export CHAQIMCHI_BACKUP_DIR=/home/deploy/chaqimchi-backups
export CHAQIMCHI_BACKUP_PASSWORD='YANGI_UZUN_SIR'            # parol menejerga yozing!
./scripts/deploy_cloud.sh
```

Birinchi ishga tushishda Caddy barcha subdomenlar uchun sertifikatlarni
o'zi oladi (DNS tarqalgan bo'lishi shart). Tekshirish:
`curl -I https://chaqimchi.uz` va `https://api.chaqimchi.uz/health`.

Caddyfile sintaksisini oldindan tekshirish (ixtiyoriy):
`docker run --rm -v $PWD/deploy/Caddyfile.chaqimchi:/etc/caddy/Caddyfile:ro caddy:2.10-alpine caddy validate --config /etc/caddy/Caddyfile`

## 5. Deploy'dan keyingi bir martalik ishlar

```bash
# Yuz modellari (Face ID pilot, ~280 MB):
docker compose --env-file .env.production -f docker-compose.chaqimchi.yml \
  exec cloud python scripts/fetch_face_models.py

# Telegram webhook (api. manziliga):
python3 scripts/set_telegram_webhook.py
python3 scripts/set_telegram_webhook.py --check

# Kunlik backup cron:
crontab -e   # → 30 3 * * * flock -n /home/deploy/chaqimchi-backup.lock /home/deploy/chaqimchi-backup-daily.sh
# (skript: deploy/chaqimchi-backup.* namunalari, runbook §2.1)
```

## 6. Windows relizini yangi manzil bilan qayta yig'ish (Mac'da)

Ichiga cloud manzili yoziladi — YANGI api manzil bilan qayta build shart:

```bash
make windows-release CLOUD_URL=https://api.chaqimchi.uz PY=.venv/bin/python
scp releases/chaqimchi-windows-0.6.6.{exe,json} deploy@SERVER_IP:/home/deploy/chaqimchi-ai/releases/
```

## 7. status.chaqimchi.uz (UptimeRobot, bepul)

1. uptimerobot.com → monitor qo'shing: `https://api.chaqimchi.uz/health` (HTTP, 5 min).
2. Status Page yarating → Custom domain: `status.chaqimchi.uz` → ko'rsatilgan CNAME'ni aHOST DNS'ga yozing.
3. Landing futeridagi "Tizim holati" havolasi keyin shu manzilga almashtiriladi.

## 8. Do'kondagi qurilmani yangi manzilga ulash

Do'kon kompyuteri eski manzilga qarab turibdi (hodisalar diskda yig'ilgan,
7 kun/20 GB gacha yo'qolmaydi):

1. Kompyuterda `http://127.0.0.1:8760` → sozlash ustasi → cloud bo'limida
   yangi kod bilan qayta ulang (admin panelda saytga yangi pairing kod
   oching). YOKI `config.yaml` da `cloud_sync.url` va `cloud.url` ni
   `https://api.chaqimchi.uz` ga almashtirib dasturni qayta ishga tushiring.
2. Ulangach yig'ilgan hodisalar o'zi yetib boradi.
3. Yangilanish siyosati `auto` bo'lsa 0.6.6 ni 15 daqiqada o'zi oladi.

## 9. Yakuniy tekshiruv ro'yxati

- [ ] https://chaqimchi.uz — landing, narx ko'rinadi
- [ ] https://app.chaqimchi.uz — panel login ekrani
- [ ] https://partner.chaqimchi.uz — montajchi portali
- [ ] https://admin.chaqimchi.uz — admin (parol so'raydi)
- [ ] https://dl.chaqimchi.uz — yuklab olish sahifasi, versiya ko'rinadi
- [ ] https://docs.chaqimchi.uz — hujjatlar
- [ ] https://api.chaqimchi.uz/health — {"ok": true}
- [ ] Botga /start — welcome, tugmalar yangi subdomenlarga
- [ ] Admin panelda sayt ochish → pairing → qurilma ulanadi
- [ ] Kechqurun kunlik hisobot keladi

## Eslatmalar

- Eski serverdagi ma'lumotlar (test davri) tiklanmaydi — yangi baza toza
  boshlanadi. Eski backuplar eski serverda edi.
- admin. hozircha parol bilan; keyin Caddyfile'dagi izohli `remote_ip`
  bloki orqali VPN/IP cheklovi qo'shiladi.
- dl. keyin CDN/object storage'ga ko'chsa — faqat DNS o'zgaradi.
