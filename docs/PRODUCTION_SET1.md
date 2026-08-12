# Chaqimchi Lite production qo‘llanmasi

> `Set-1` — mahsulotning eski ichki nomi. 2026-08 dan Orange Pi asosidagi
> ushbu mahsulot **Chaqimchi Lite** deb ataladi. Yangi canonical konfiguratsiya
> `config/lite.yaml`; `config/production.yaml` eski o‘rnatishlar uchun saqlanadi.

## Reliz tarkibi

`v0.4.0` bitta obyekt va sakkizta kamera uchun quyidagilarni beradi:

- motion-gated person detection;
- person, zona, loitering va occupancy eventlari;
- faqat rozilik bergan xodimlar Face ID’i;
- 7 kun/20 GB edge outbox va idempotent cloud replay;
- PostgreSQL event/owner bazasi va private MinIO snapshotlari;
- Telegram OTP, owner/manager rollari, tezkor alert va 21:00 digest;
- HTTPS, backup, monitoring heartbeat va imzolangan rollback update.

Oddiy mijozlarga doimiy Face ID berilmaydi. Tizim “niyat”, “o‘g‘rilik” yoki jinoyatni taxmin qilmaydi. V1 faqat konfiguratsiya qilingan ko‘rinadigan hodisalarni qayd etadi.

## Chaqimchi Lite apparat nomzodlari

Hikvision testi:

- DS-7608NXI-K2/8P NVR;
- 8 × DS-2CD2646G2-IZS, 4 MP varifocal WDR;
- 8 TB surveillance HDD.

Dahua testi:

- NVR4108HS-8P-EI NVR;
- 8 × IPC-HDBW3441R-ZAS-S2, 4 MP varifocal WDR;
- 8 TB surveillance HDD.

Edge: Orange Pi 5 Plus, 16 GB RAM, 256/512 GB NVMe, aktiv sovutish va UPS. NVR main stream’ni H.265 ~2 Mbps yozadi; AI NVR’dan 720p H.264 10 FPS substream oladi. Kamera VLAN’ida internet, vendor P2P va UPnP o‘chiriladi.

## Cloud o‘rnatish

Talablar: Ubuntu VPS, domen DNS’i, Docker Engine va Compose plugin.

```bash
cp .env.production.example .env.production
chmod 600 .env.production
# barcha GENERATE/FROM qiymatlarini almashtiring
./scripts/deploy_cloud.sh
curl https://YOUR_DOMAIN/health
```

Cloud quyidagilarni tashqi portga chiqarmaydi: PostgreSQL, MinIO va legacy subscription state. Internetga faqat Caddy 80/443 ochiladi.

Sayt va qurilma yaratish:

```bash
python scripts/provision_site.py "Lite do‘kon" --plan lite --months 1
```

Pairing javobidagi `site_id`, `device_id` va `device_token` edge env fayliga xavfsiz ko‘chiriladi. Owner Telegram ID’i admin API’dagi `POST /api/v1/admin/sites/{site_id}/members` orqali `owner` roli bilan qo‘shiladi.

Telegram webhook:

```text
https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<DOMAIN>/api/v1/telegram/webhook/<WEBHOOK_SECRET>
```

## Edge o‘rnatish

Hozirgi `v0.4.0` installer AI modelini emas, **Chaqimchi Lite control-only**
agentini o‘rnatadi. Quyidagi model tekshiruvi AI sprinti ochilgunga qadar
production onboarding uchun talab qilinmaydi.

```bash
sudo ./scripts/install_edge.sh
sudo /opt/chaqimchi/venv/bin/python /opt/chaqimchi/current/scripts/pair_edge.py \
  --cloud https://YOUR_DOMAIN --code ABC123
sudo systemctl start chaqimchi-edge
curl http://127.0.0.1:8742/health
```

AI sprinti ochilgach commercial model paketi repository’ga kiritilmaydi.
O‘sha bosqichda `python scripts/verify_model_bundle.py
/opt/chaqimchi/shared/models/manifest.json` ishlatiladi. `licensed_for_commercial_use`,
license reference va barcha SHA-256 qiymatlari tasdiqlanmaguncha
`CHAQIMCHI_FACE_MODEL_LICENSED=true` qilish taqiqlanadi.

Har bir do‘konda `scene.zones` normalized polygonlar bilan site survey asosida to‘ldiriladi. Face threshold real xodimlar va real yorug‘likdagi calibration dataset bilan belgilanadi.

## Qabul testi

```bash
python scripts/benchmark_streams.py \
  --config config/lite.yaml \
  --duration 300 \
  --output benchmark-lite.json
```

Qabul mezoni:

- aynan 8 faol RTSP stream;
- har kanal kamida 2 AI FPS, motion paytida 5 FPS maqsad;
- qurilma harorati 80°C dan past;
- online alert 10 soniyadan tez;
- 72 soatlik real apparat soak test;
- 30 kunlik NVR hajmi real bitrate bilan tasdiqlanishi;
- xodim Face ID recall ≥95%, false accept <0.1% bo‘yicha site calibration hisoboti.

Orange Pi mezondan o‘tmasa, fallback — 32 GB RAM, 512 GB NVMe va kamida 8 GB NVIDIA GPU’li x86 mini-PC.

## Backup, restore va update

Cloud backup:

```bash
export CHAQIMCHI_BACKUP_DIR=/srv/chaqimchi-backups
export CHAQIMCHI_BACKUP_PASSWORD='LONG_RANDOM_SECRET'
./scripts/backup_production.sh
```

Natija PostgreSQL, MinIO snapshotlari va legacy subscription/payment state’ning AES-256 shifrlangan arxividir. `RESTIC_REPOSITORY` berilsa arxiv offsite restic repository’ga ham yuboriladi. Restore har relizdan oldin staging VPS’da sinovdan o‘tkaziladi.

Edge embedding bazasi cloudga yuborilmaydi. `scripts/backup_db.py` orqali har kuni shifrlangan USB/NAS nusxa olinadi.

Update paketi Ed25519 bilan imzolanadi. Qurilmada faqat public key saqlanadi:

```bash
sudo python scripts/apply_signed_update.py release.tar.gz release.json
```

SHA-256 yoki imzo mos kelmasa paket o‘rnatilmaydi. Service health-check’dan o‘tmasa `current` symlink oldingi release’ga avtomatik qaytadi.

## Hali tashqi gate bo‘lib qoladigan ishlar

- InsightFace yoki boshqa tanlangan Face ID modeli uchun commercial litsenziya olish;
- Hikvision va Dahua komplektlarini sotib olib real benchmark qilish;
- Orange Pi uchun RKNN modelni vendor toolkit bilan quantize qilib, aniqlik regressiyasini tekshirish;
- xodim roziligi, obyekt ogohlantiruvchi belgisi va yurist tasdig‘i;
- VPS/domen credentiallari va offsite backup manzilini production secret store’ga joylash.
