# Chaqimchi AI — umumiy reja (boshidan oxirigacha)

## Holat belgilari

- [x] Bajarilgan
- [~] Qisman
- [ ] Rejalashtirilgan (keyinroq)

---

## 1–5. Asosiy mahsulot

Barcha bandlar **[x]** — konfig, API, kamera, kalibrlash, tracking, audit, metrics, Docker, CI.

Batafsil: avvalgi versiyalar va `README.md`.

---

## 6. Kengaytirish (bajarildi)

| # | Vazifa | Holat |
|---|--------|-------|
| 6.1 | FAISS / vektor indeks | [x] `storage.vector_backend: faiss` (ixtiyoriy `faiss-cpu`) |
| 6.2 | JWT | [x] `POST /api/auth/token`, `Authorization: Bearer` |
| 6.3 | Prometheus | [x] `GET /metrics` (matn format) |
| 6.4 | ROI deteksiya | [x] `roi` konfig, `FaceEngine` preprocess |
| 6.5 | Embedding shifrlash | [x] `storage.encrypt_embeddings` + `CHAQIMCHI_EMBEDDING_KEY` |
| 6.6 | Anti-spoofing | [~] Ko‘p signalli heuristika + ONNX backend tayyor; ishonchli model topilmadi — [ANTISPOOF.md](ANTISPOOF.md) |
| 6.7 | gRPC mikroservis | [ ] |

---

## Tezkor sozlash (6-bosqich)

```yaml
storage:
  vector_backend: faiss      # pip install -r requirements-optional.txt
  encrypt_embeddings: true # CHAQIMCHI_EMBEDDING_KEY=<Fernet key>

roi:
  enabled: true
  x1: 0.2
  y1: 0.0
  x2: 0.8
  y2: 1.0

antispoof:
  enabled: true
  backend: heuristic   # heuristic | onnx (docs/ANTISPOOF.md)
  min_score: 0.5

security:
  jwt:
    enabled: true
```

```bash
# JWT
curl -H "X-API-Key: $CHAQIMCHI_API_KEY" -X POST http://127.0.0.1:8742/api/auth/token
curl -H "Authorization: Bearer <token>" ...

# Prometheus
curl http://127.0.0.1:8742/metrics
```

---

## 7. Xizmat modeli (SaaS)

| # | Vazifa | Holat |
|---|--------|-------|
| 7.1 | Tariflar (Starter / Business / Enterprise) | [x] |
| 7.2 | Cloud API (`cloud/main.py`) | [x] |
| 7.3 | Edge litsenziya + heartbeat | [x] |
| 7.4 | O‘rnatuvchi: `provision_site.py` | [x] |
| 7.5 | To‘lov integratsiyasi (Payme/Click) | [x] Hisob-faktura + avtomatik obuna — [TOLOV.md](TOLOV.md) |
| 7.6 | Admin web panel (UI) | [x] `GET /admin` (8750) — mijozlar, obuna, pairing, hisob-fakturalar |
| 7.7 | Arxiv muddati (retention) | [x] Tarifdagi 30/90/365 kun endi rostdan qo‘llanadi |
| 7.8 | Zaxira nusxa va tiklash | [x] `make backup` / `make restore`, `GET/POST /api/backup` |
| 7.9 | Aloqa nazorati | [x] Panelda qaysi mijoz tizimi ishlamayotgani ko‘rinadi |
| 7.10 | Telegram ogohlantirishi | [x] Mijoz o‘chsa cloud o‘zi xabar beradi |
| 7.11 | Kamera nazorati | [x] 3 kameradan bittasi o‘chsa ham bilinadi |

### 7.11 — Kamera nazorati

Edge har heartbeat'da `active_cameras` yuborardi, lekin cloud uni **faqat
javobda qaytarib tashlardi** — hech qayerda saqlanmasdi. Natijada 3 kamerali
Business mijozda (1 490 000 so‘m/oy) bitta kamera o‘chsa, panelda hamma narsa
yashil turardi: aloqa bor, obuna faol. Mijoz oylab bilmasligi mumkin edi.

Bu aloqa uzilishidan xavfliroq: tizim butunlay o‘chsa mijoz sezadi, bitta
kamera o‘chsa — yo‘q.

- Kamera soni endi `devices.active_cameras` da saqlanadi.
- `sites.cameras_expected` — shu obyektda ishlagani ma’lum bo‘lgan eng katta
  son. O‘rnatuvchidan alohida so‘ralmaydi: tizim bir marta 3 kamera bilan
  ishlagan bo‘lsa, keyin 2 kelishi nosozlik demakdir.
- Panelda “Kamera” ustuni: `2/3` qizil rangda.
- Telegram: “📹 Oq Saroy — 1 ta kamera ishlamayapti” + telefon raqami.
  Ahvol yomonlashsa (2 ta o‘chsa) yangi xabar ketadi; tuzatilsa ✅.
- Tizim butunlay o‘chgan bo‘lsa kamera xabari **yuborilmaydi** — aloqa
  ogohlantirishi allaqachon ketgan, ikkita xabar shovqin.

Kamera ataylab olib tashlansa kutilgan sonni tushiring, aks holda tizim uni
abadiy “yo‘qolgan” deb hisoblaydi:

```bash
curl -X POST "$CLOUD/api/v1/admin/sites/SITE_ID/cameras" \
  -H "X-Cloud-Admin-Key: $CHAQIMCHI_CLOUD_ADMIN_KEY" \
  -H "Content-Type: application/json" -d '{"expected": 2}'
```

Eski bazalar avtomatik migratsiya qilinadi (yangi ustunlar qo‘shiladi,
ogohlantirish holati saqlanadi).

### 7.10 — Telegram ogohlantirishi

Panelda aloqa holati ko‘rinadi (7.9), lekin buning uchun panelni ochish kerak.
Do‘kon ertalab soat 9 da o‘chsa, panel kechqurun ochilsa — kun yo‘qoladi.
Endi cloud o‘zi Telegramga yozadi.

```bash
export CHAQIMCHI_CLOUD_TELEGRAM_TOKEN="123456:ABC..."   # @BotFather
export CHAQIMCHI_CLOUD_TELEGRAM_CHAT_ID="-1001234567890"
make run-cloud
```

Ikkalasi ham berilmasa modul jim turadi — cloud oddiy ishlaydi. Panel yuqorisida
holat ko‘rinib turadi (🔕 o‘chiq / 🔔 yoqilgan) va **“Sinov xabari”** tugmasi bor.

Qachon xabar ketadi:

| Hodisa | Xabar |
|--------|-------|
| Mijoz 24 soatdan ortiq jim | 🔴 tizim ishlamayapti + telefon raqami |
| Yangi mijoz 48 soatda juftlanmagan | ⚠️ o‘rnatish tugallanmagan |
| Aloqa tiklandi | ✅ qayta ishga tushdi |

**Shovqinga qarshi uch qoida:**

1. Xabar faqat holat **o‘zgarganda** ketadi (`alert_state` jadvali) — har 15
   daqiqada takrorlanmaydi.
2. `stale` (1–24 soat) uchun xabar yo‘q — internetning qisqa uzilishi odatiy hol.
3. Obunasi to‘xtatilgan yoki tugagan mijozlar kuzatilmaydi — ular jim turishi
   kutilgan holat.

Telegram javob bermasa holat **yozilmaydi** — xabar keyingi tekshiruvda qayta
urinib ko‘riladi, ya’ni tarmoq uzilishi tufayli ogohlantirish yo‘qolmaydi.

| Endpoint | Vazifa |
|----------|--------|
| `GET /api/v1/admin/alerts` | Sozlama va oxirgi tekshiruv |
| `POST /api/v1/admin/alerts/test` | Sinov xabari |
| `POST /api/v1/admin/alerts/check` | Darhol tekshirish |

### 7.9 — Aloqa nazorati

Edge har 30 daqiqada cloud ga xabar beradi va `last_seen` yozilardi — lekin bu
son faqat sayt tafsilotida xom matn bo‘lib turardi. Ya’ni mijozning tizimi
o‘chib qolganini bilish uchun har bir saytni qo‘lda ochib ko‘rish kerak edi.
Amalda buni hech kim qilmaydi va nosozlik mijoz qo‘ng‘iroq qilgandagina
ma’lum bo‘ladi — oyiga 790 000–2 990 000 so‘m to‘layotgan mijoz uchun yomon.

Endi har bir sayt aloqa holatiga ega:

| Holat | Ma’nosi | Panelda |
|-------|---------|---------|
| `online` | 1 soat ichida xabar bergan | yashil |
| `stale` | 1–24 soat jim — internet uzilgan yoki qayta yuklanmoqda | sariq |
| `offline` | 24 soatdan ortiq jim — **tizim ishlamayapti** | qizil |
| `not_paired` | Qurilma umuman juftlanmagan — o‘rnatish tugallanmagan | kulrang |

Panel yuqorisida **“Ishlamayapti”** qizil raqami: `offline + not_paired`.
Obunasi to‘xtatilgan yoki muddati tugagan mijozlar bu raqamga qo‘shilmaydi —
ular jim turishi kutilgan holat.

`GET /api/v1/admin/stats` → `offline`, `not_paired`, `by_connection`;
`GET /api/v1/admin/sites` → har bir saytda `connection`, `last_seen`,
`minutes_since_seen`.

### 7.8 — Zaxira nusxa

`INSTALLER.md` da “qurilma almashganda yangi pairing kod” jarayoni bor edi,
lekin bazani yangi qurilmaga ko‘chirish yo‘li yo‘q edi. Enterprise tarifda
2000 shaxs — har biri bir marta kamera oldiga kelgan; SSD ishdan chiqsa bu ish
qaytadan boshlanardi.

Nusxa — bitta ZIP: `manifest.json` (versiya, sana, sha256) + `metadata.json` +
vektorlar. Tiklash **avval to‘liq tekshiradi** (versiya, checksum, o‘lcham,
soni), shundan keyingina bazaga yozadi — buzuq fayl bazani buzmaydi.

```bash
make backup OUT=/Volumes/USB          # o'rnatishdan keyin va har oy
python scripts/backup_db.py info n.zip
make restore FILE=n.zip                # yoki --merge: birlashtirish
```

Baza shifrlangan bo‘lsa nusxa ham shifrlanadi; tiklashda o‘sha
`CHAQIMCHI_EMBEDDING_KEY` kerak. Ikkala marshrut ham API kalit talab qiladi va
audit jurnaliga yoziladi.

### 7.7 — Arxiv muddati

Bungacha tarif jadvalidagi “voqea arxivi 30/90/365 kun” faqat yozuv edi:
voqealar va yuz rasmlari cheksiz to‘planardi. Kuniga 500 voqea ≈ 15 MB, ya’ni
bir yilda ~5 GB va Mini PC diski hech qachon bo‘shamasdi.

Endi fon vazifasi 6 soatda bir marta muddati o‘tgan voqealarni va ularning
snapshot fayllarini o‘chiradi (yetim qolgan eski rasmlar ham supuriladi).

Muddat ikki manbadan: **tarif** (litsenziya) va `config.yaml`. Ikkalasi ham
bo‘lsa qisqarog‘i ishlaydi — mijoz kamroq saqlashi mumkin, tarifdan ko‘p emas.
Litsenziya o‘chiq bo‘lsa (dev) faqat konfig ishlaydi; `0` — tozalash o‘chiq.

```yaml
events:
  retention_days: 0          # 0 = tarif belgilaydi
  retention_interval_sec: 21600
```

| Endpoint | Vazifa |
|----------|--------|
| `GET /api/retention` | Muddat, arxiv hajmi, oxirgi tozalash |
| `POST /api/retention/purge` | Darhol tozalash (API kalit) |

Metrika: `chaqimchi_purged_events_total`, `chaqimchi_purged_files_total`.
Obuna to‘xtatilganda ham ishlaydi — biometrik kadr muddatidan ortiq qolmasligi kerak.

### 7.6 — Admin panel

```bash
export CHAQIMCHI_CLOUD_ADMIN_KEY="maxfiy-kalit"
make run-cloud
# brauzer: http://127.0.0.1:8750/admin
```

Panel imkoniyatlari: umumiy ko‘rsatkichlar (mijozlar, faol, 7 kunda tugaydiganlar,
qurilmalar, oylik daromad), yangi mijoz ochish + pairing kod, obunani uzaytirish,
to‘lov kechikkanda to‘xtatish/qayta yoqish, qurilma almashganda yangi pairing kod.

Yangi admin endpointlar:

| Endpoint | Vazifa |
|----------|--------|
| `GET /api/v1/admin/stats` | Umumiy ko‘rsatkichlar |
| `GET /api/v1/admin/sites/{id}` | Sayt tafsiloti + qurilmalar |
| `POST /api/v1/admin/sites/{id}/status` | `active` / `suspended` |
| `POST /api/v1/admin/sites/{id}/pairing` | Yangi juftlash kodi |

### 7.5 — To‘lov (Payme / Click)

Hisob-faktura ochiladi → mijozga `/(pay)/{id}` havolasi yuboriladi → to‘lov
tushgach obuna **avtomatik** uzayadi. Naqd/bank to‘lovi ham shu yo‘ldan o‘tadi.

```bash
export CHAQIMCHI_PUBLIC_URL="https://cloud.chaqimchi.uz"
export CHAQIMCHI_PAYME_MERCHANT_ID=... CHAQIMCHI_PAYME_KEY=...
export CHAQIMCHI_CLICK_SERVICE_ID=... CHAQIMCHI_CLICK_MERCHANT_ID=... CHAQIMCHI_CLICK_SECRET=...
```

| Endpoint | Vazifa |
|----------|--------|
| `POST /api/v1/admin/sites/{id}/invoices` | Hisob-faktura ochish |
| `GET /api/v1/admin/invoices` | Hisoblar ro‘yxati |
| `POST /api/v1/admin/invoices/{id}/paid` | Naqd/bank to‘lovi |
| `POST /api/v1/payments/payme` | Payme Merchant API |
| `POST /api/v1/payments/click/{prepare,complete}` | Click SHOP-API |

Batafsil: [TOLOV.md](TOLOV.md)

---

**Ustuvorlik**: mahsulot barqaror → xizmat modeli → to‘lov avtomatlashtirish.

**Keyingi qadam**: 6.7 gRPC mikroservis (ixtiyoriy, GPU serverga chiqarishda kerak
bo‘ladi) va 6.6 anti-spoof modelini kuchaytirish (o‘z hujum suratlaringiz kerak —
`scripts/validate_antispoof.py`).
