# [ARXIV] Chaqimchi Lite — eski mahsulot kontrakti

> Bu Orange Pi/Lite hujjati faol emas. Yangi ish va sotuv uchun faqat
> [Do‘kon MVP](DOKON_MVP.md) canonical manba hisoblanadi.

## Mahsulot

**Chaqimchi Lite** — Chaqimchi AI'ning dastlabki tijoriy mahsuloti. Eski ichki
nomi `Set-1`. Komplekt markazida Orange Pi 5 Plus turadi; kamera/NVR va montaj
alohida smeta, dasturiy xizmatning **bazasi $20/oy**. Cloud-AI funksiyalari
baza ustiga, kamera bo‘yicha qo‘shiladi ($3–$10/kamera/oy) —
[TOLOV.md](TOLOV.md).

Lite obunasi hozirgi MVP'da quyidagilarni beradi:

- bitta obyekt, 8 tagacha RTSP kamera (apparat qabul testidan keyin);
- lokal person/zone/loitering/occupancy tahlili;
- faqat rozilik bergan xodimlar uchun lokal Face ID, 200 tagacha shaxs;
- internet uzilganda 7 kunlik/20 GB lokal navbat va keyin cloud replay;
- 30 kunlik event arxivi, owner panel va Telegram xabarlari;
- litsenziya, monitoring va imzolangan dastur yangilanishlari.

Oddiy mijozlar uchun “jinoyatchi”, “o‘g‘ri” yoki niyatni taxmin qilish mahsulot
vazifasiga kirmaydi. Commercial litsenziyasi tasdiqlanmagan Face ID modeli
production'da fail-closed qoladi.

## Edge va server chegarasi

```text
Kameralar/NVR
    │ RTSP substream
    ▼
Orange Pi — EDGE                         Cloud/VPS — SERVER
├─ video decode                         ├─ admin va owner panel
├─ motion/person/zone inference         ├─ mijoz, qurilma, litsenziya
├─ ixtiyoriy lokal Face ID              ├─ $20 baza invoice, Payme/Click
├─ shifrlangan lokal embedding          ├─ event metadata/snapshot
├─ offline outbox                       ├─ Telegram bot va digest
└─ health + event sync ─── HTTPS ─────► └─ update/release boshqaruvi
```

Muhim qoida: internet yoki cloud vaqtincha ishlamasa lokal kuzatuv va event
navbati davom etadi. Video oqimining o‘zi cloud'ga uzluksiz yuborilmaydi;
faqat hodisa metadata'si va siyosat ruxsat bergan snapshot yuboriladi.

## $20 billing qoidasi

Baza narxi `2000` sent va u **bitta joyda** turadi:
`chaqimchi_ai/licensing/plans.py:LITE_MONTHLY_PRICE_USD_CENTS`. Cloud katalogi
(`cloud/store.py:DEFAULT_BASE_FEE_USD_CENTS`) shuni import qiladi — ikkita
mustaqil konstanta bo‘lsa ular sekin-asta ajralib ketadi va mijoz saytdagidan
boshqa summa to‘laydi.

Payme/Click UZS qabul qilgani uchun serverdagi `CHAQIMCHI_USD_RATE_UZS`
ishlatiladi. Standart development qiymat `13000`, ya'ni namuna invoice
**260 000 so‘m/oy**.

Kurs avtomatik internetdan olinmaydi. Operator kursni yangilaydi; o‘zgarish
faqat undan keyin ochilgan invoice'larga ta'sir qiladi. Oldin ochilgan invoice
summasi `invoices.amount_uzs` da qotib qoladi — callback paytida summa almashib
ketmaydi. **Shartnoma dollar narxini muzlatadi, kursni emas**: aks holda kurs
ko‘tarilganda eski mijoz o‘z-o‘zidan arzonlashib ketardi.

Yillik to‘lovda **2 oy bepul** — barcha tarifga bir xil, `billable_months()`
da. Rasmiy sayt ham, hisob-faktura ham shu bitta qoidadan chiqadi: 12 oy =
oylik × 10, ya'ni namuna kursda **2 600 000 so‘m**.

Rasmiy sayt narxni `GET /api/v1/public/pricing` dan oladi. HTML ichida narx
yozilmaydi — katalog o‘zgarganda sayt eski narxni ko‘rsatib turmasligi kerak.
Tannarx va marja bu ochiq javobga chiqmaydi; ular faqat
`GET /api/v1/admin/features` da qoladi.

Katalogdagi funksiya sotuvga chiqishi uchun kod yozilgan bo‘lishi ham shart:
`CHAQIMCHI_AVAILABLE_FEATURES=person_count,queue_length` qo‘yilmaguncha sayt
ularni “Tez orada” deb ko‘rsatadi va sotmaydi.

## Ishga tushirish

### Cloud

```bash
cp .env.production.example .env.production
# domen, DB/S3, admin/JWT, BotFather va payment secretlarini kiriting
docker compose --env-file .env.production -f docker-compose.prod.yml config --quiet
./scripts/deploy_cloud.sh
curl https://YOUR_DOMAIN/health
```

Telegram webhook:

```text
POST https://api.telegram.org/bot<TOKEN>/setWebhook
url=https://<DOMAIN>/api/v1/telegram/webhook
secret_token=<WEBHOOK_SECRET>
```

Admin: `https://<DOMAIN>/admin`; mijoz: `https://<DOMAIN>/owner`.
Rasmiy sayt: `https://<DOMAIN>/`; Orange Pi ulash: `https://<DOMAIN>/connect`;
ochiq holat: `https://<DOMAIN>/status`.

Rasmiy saytdagi pilot ariza `leads` bazasiga tushadi. Admin uni `new →
contacted → qualified` bosqichlarida yuritadi va “Lite mijoz ochish” orqali
obyekt, pairing kod va onboarding ro‘yxatini bir amalda yaratadi.

### Yangi Lite obyekti

```bash
export CHAQIMCHI_CLOUD_ADMIN_KEY='...'
export CHAQIMCHI_CLOUD_URL='https://YOUR_DOMAIN'
python scripts/provision_site.py "Mijoz nomi" --plan lite --months 1
```

Pairing natijasidagi `site_id`, `device_id` va `device_token` Orange Pi'dagi
`/etc/chaqimchi/edge.env` ga yoziladi.

### Orange Pi

Minimal profil: Orange Pi 5 Plus, 16 GB RAM, 256/512 GB NVMe, aktiv sovutish
va UPS. microSD production data diski sifatida ishlatilmaydi.

```bash
sudo ./scripts/install_edge.sh
sudoedit /etc/chaqimchi/edge.env
sudo /opt/chaqimchi/venv/bin/python /opt/chaqimchi/current/scripts/pair_edge.py \
  --cloud https://YOUR_DOMAIN --code ABC123
sudo systemctl start chaqimchi-edge
curl http://127.0.0.1:8742/health
```

Hozir installer **control-only agent**ni o‘rnatadi: pairing, heartbeat, disk/
harorat holati, remote config va imzolangan update ishlaydi; InsightFace,
ONNX Runtime va video model dependency'lari Orange Pi'ga o‘rnatilmaydi.
`/health` javobidagi `ai_model: deferred` shu holatni ochiq ko‘rsatadi.

Video relizi tayyor bo‘lgach alohida staging o‘rnatishda to‘liq dependency va
`config/lite.yaml` bilan quyidagi qabul testi ishlatiladi:

```bash
make benchmark-lite
```

8 kamera sotuv va'dasidan oldin 72 soat soak test, har kamera kamida 2 AI FPS
va harorat 80°C dan past bo‘lishi shart. Orange Pi bu gate'dan o‘tmasa kamera
soni tushiriladi yoki x86/NVIDIA edge ishlatiladi.

## Yangilanish kontrakti

- release arxivi va manifest Ed25519 bilan imzolanadi;
- Lite manifest v2 ichida `product=chaqimchi-lite` va Orange Pi uchun
  `target_arch=aarch64` ham imzolanadi (`deploy/release-manifest.example.json`);
- qurilmada faqat public key saqlanadi;
- SHA-256 yoki imzo noto‘g‘ri bo‘lsa update qo‘llanmaydi;
- yangi release alohida katalogka yoziladi, `current` symlink atomik almashadi;
- health-check muvaffaqiyatsiz bo‘lsa oldingi release qayta yoqiladi;
- `data/` va `models/` release'dan tashqarida saqlanadi, update ularni
  o‘chirib yubormaydi.

Hozirgi update yo‘li app/model patchlari uchun tayyor. Python/system dependency
o‘zgaradigan reliz avval staging Orange Pi'da tekshiriladi va maintenance
release sifatida installer orqali beriladi; avtomatik dependency upgrade hali
production gate'dan o‘tmagan.

## Ish navbati

1. Cloud domen, PostgreSQL/MinIO, Telegram va admin panelni stagingda ko‘tarish.
2. Rasmiy saytdan test ariza → admin konvertatsiya → Orange Pi pairing oqimini yakunlash.
3. Control-only agent heartbeat va imzolangan update/rollbackni real Orange Pi'da sinash.
4. Payme/Click sandboxda $30→UZS invoice va refund oqimini tekshirish.
5. Keyingi AI sprintida 1 → 4 → 8 kamera benchmark va 72 soat soak testini o‘tkazish.
6. Birinchi pilot obyektni 30 kun kuzatib, cloud va support xarajatidan keyin
   $30 narxning marjasini tasdiqlash.
