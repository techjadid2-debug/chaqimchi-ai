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

---

## 8. Ko‘rish agenti (AI)

| # | Vazifa | Holat |
|---|--------|-------|
| 8.1 | Kadrni AI ko‘rib tushuntirishi | [x] `vision.enabled`, `claude-opus-5` |
| 8.2 | Xarajat tormozlari (limit + oraliq) | [x] Diskda saqlanadi, restart aylanib o‘tmaydi |
| 8.3 | Kameraga ulash (avtomatik tahlil) | [ ] Keyingi qadam |
| 8.4 | Ogohlantirishni Telegramga yuborish | [ ] Keyingi qadam |

Yuz tanish “bu kim?” degan savolga javob beradi; ko‘rish agenti “nima
bo‘layapti?” degan savolga: kassada navbat, yiqilgan odam, tutun, ish
vaqtidan tashqari harakat.

**Bu modul pul sarflaydi** — bitta tahlil ~87 so‘m, kuniga 100 ta ≈ 262 000
so‘m/oy, ya’ni Business tarifi daromadining ~17.6% i. Tarifni qayta hisoblash
kerak; variantlar [KORISH_AGENTI.md](KORISH_AGENTI.md) da.

Ikki qavatli tormoz (ikkalasi ham majburiy): bitta kamera uchun 5 daqiqada bir
marta, va kunlik/oylik qattiq limit. Hisob `data/vision_usage.db` da — server
qayta ishga tushsa ham limit nolga qaytmaydi.

`enabled: false` (standart) bo‘lsa modul umuman qurilmaydi va bir tiyin ham
sarflanmaydi.

Batafsil, narx jadvali va chegaralari: [KORISH_AGENTI.md](KORISH_AGENTI.md)

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

## 9. Do‘kon analitikasi (Chaqimchi Retail AI)

Yuz tanish “bu kim?” degan savolga javob beradi. Do‘konga esa boshqa savol
kerak: **nechta odam kirdi, qayerda to‘xtadi, navbat qancha, kim kamerani
yopdi.** Buning uchun yuz emas, **odam** aniqlanadi — arzonroq model, kamroq
maxfiylik yuki.

| # | Vazifa | Holat |
|---|--------|-------|
| 9.1 | Inferens byudjeti va navbat (`broker`, `budget`) | [x] |
| 9.2 | Retail hodisa turlari | [x] |
| 9.3 | Deklarativ qoida dvigateli (JSON/YAML) | [x] |
| 9.4 | Chiziq kesish, dwell, navbat + harakat trackeri | [x] |
| 9.5 | OpenVINO detektor (`person-detection-retail-0013`) | [x] |
| 9.6 | Hodisa klipi uchun ring buffer (`-c copy`) | [x] |
| 9.7 | Zanjir: kadr → filtr → navbat → tahlil → qoida → harakat | [x] |
| 9.8 | Alohida xizmat (`chaqimchi-retail.service`) | [x] |
| 9.9 | Kamera buzilishi va ish vaqtidan tashqari harakat | [x] |
| 9.10 | N100 sig‘imini o‘lchash skripti | [x] skript tayyor, **o‘lchov o‘tkazilmagan** |

### Qurilmada AI — chegara o‘zgardi

Avvalgi rejada Sotqin AI umuman ishlatmaydigan gateway edi: har kadr cloudga
ketishi kerak edi. Bu ishlamadi — do‘kondan chiqadigan internet kanali ham,
cloud GPU narxi ham yetmaydi. Yangi chegara:

| Qayerda | Nima |
|---------|------|
| Qurilma (N100 iGPU) | Odam deteksiyasi (2.3 GFLOPs), tracking, sanoq, dwell, navbat, kamera buzilishi, qoidalar, klip |
| Cloud | Ko‘rish agenti (Claude), arxiv, panel, Telegram, obuna, ko‘p obyekt hisoboti |
| NVR | To‘liq video arxiv |

Sabab oddiy: 8 kamera × 5 FPS = sekundiga 40 kadr. Ularni cloudga yuborish
oyiga terabaytlab trafik va GPU hisobi degani; qurilmada esa 2.3 GFLOPs model
shu ishni bajaradi va cloudga faqat **hodisa** ketadi.

**Ochiq**: sig‘im o‘lchanmagan (`scripts/benchmark_n100.py`), kamera ro‘yxati
cloud inventari bilan ulanmagan, buzilish chegaralari kalibrlanmagan.
Batafsil: [chaqimchi_ai/retail/README.md](../chaqimchi_ai/retail/README.md),
[SOTQIN.md](SOTQIN.md).

---

**Ustuvorlik**: mahsulot barqaror → xizmat modeli → to‘lov avtomatlashtirish.

**Keyingi qadam**: N100 da benchmark o‘tkazish (9.10) — 8 kamera va’dasi shu
raqamga bog‘liq. Keyin: 8.3/8.4 ko‘rish agentini kameraga ulash, 6.7 gRPC
mikroservis (ixtiyoriy) va 6.6 anti-spoof modelini kuchaytirish
(`scripts/validate_antispoof.py`).
