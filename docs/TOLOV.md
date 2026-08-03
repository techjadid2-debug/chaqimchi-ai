# To'lov integratsiyasi — Payme va Click

Maqsad: **to'lov tushdi → obuna avtomatik uzaydi**. Admin qo'lda hech narsa
bosmaydi; naqd to'lov ham shu bitta yo'ldan o'tadi.

## Oqim

1. Admin panelda mijoz qatoridagi **“Hisob”** tugmasi → necha oy → hisob-faktura ochiladi.
   Summa tarifdan olinadi, admin qo'lda kiritmaydi.
2. Panel to'lov havolasini beradi: `https://<sizning-domen>/pay/<hisob-id>`.
   Shu havola mijozga (Telegram/SMS) yuboriladi.
3. Mijoz sahifada **Payme** yoki **Click** tugmasini bosadi.
4. Provayder serverimizga callback yuboradi → hisob “to'langan” bo'ladi →
   `subscription_until` shuncha oyga suriladi → edge qurilma keyingi heartbeat da
   yangi muddatni oladi.

Naqd yoki bank o'tkazmasi bo'lsa: hisob qatoridagi **“To'landi”** tugmasi —
natija bir xil, obuna o'sha zahoti uzayadi.

## Narx qoidasi

Summa = tarif oylik narxi × to'lanadigan oy. **Har to'liq yil uchun 2 oy tekin**
(yillik = oylik × 10) — `billable_months()` da, bitta joyda.

| Tarif | 1 oy | 12 oy |
|-------|------|-------|
| Starter | 790 000 | 7 900 000 |
| Business | 1 490 000 | 14 900 000 |
| Enterprise | 2 990 000 | 29 900 000 |

## Sozlash

`.env` (kalitlar konfig faylda emas — ular maxfiy):

```bash
CHAQIMCHI_CLOUD_ADMIN_KEY=maxfiy-admin-kalit
# To'lov havolalari tashqaridan ochilishi uchun — HTTPS domen
CHAQIMCHI_PUBLIC_URL=https://cloud.chaqimchi.uz

# Payme (merchant kabinetidan)
CHAQIMCHI_PAYME_MERCHANT_ID=xxxxxxxxxxxxxxxxxxxxxxxx
CHAQIMCHI_PAYME_KEY=xxxxxxxxxxxxxxxxxxxxxxxx

# Click (SHOP-API)
CHAQIMCHI_CLICK_SERVICE_ID=12345
CHAQIMCHI_CLICK_MERCHANT_ID=54321
CHAQIMCHI_CLICK_SECRET=xxxxxxxxxxxxxxxx
```

Sozlanmagan provayder shunchaki ko'rinmaydi — server baribir ishlayveradi.
Panelda “Onlayn to'lov: Payme · Click” yozuvi qaysi biri ulanganini ko'rsatadi.

### Payme kabinetida ko'rsatiladigan ma'lumot

| Maydon | Qiymat |
|--------|--------|
| Endpoint | `https://<domen>/api/v1/payments/payme` |
| Hisob maydoni (`account`) | `invoice_id` |

Payme Merchant API to'liq qo'llab-quvvatlanadi: `CheckPerformTransaction`,
`CreateTransaction`, `PerformTransaction`, `CancelTransaction`,
`CheckTransaction`, `GetStatement`. Tranzaksiya 12 soatdan keyin avtomatik
bekor bo'ladi.

### Click kabinetida ko'rsatiladigan ma'lumot

| Maydon | Qiymat |
|--------|--------|
| Prepare URL | `https://<domen>/api/v1/payments/click/prepare` |
| Complete URL | `https://<domen>/api/v1/payments/click/complete` |

Imzo (`sign_string`) Click hujjatidagi tartibda tekshiriladi; noto'g'ri imzo → `-1`.

## API

| Endpoint | Kim uchun | Vazifa |
|----------|-----------|--------|
| `POST /api/v1/admin/sites/{id}/invoices` | admin | Hisob-faktura ochish |
| `GET /api/v1/admin/invoices` | admin | Ro'yxat (`?site_id=`, `?limit=`) |
| `POST /api/v1/admin/invoices/{id}/paid` | admin | Naqd/bank to'lovi |
| `POST /api/v1/admin/invoices/{id}/cancel` | admin | Bekor qilish |
| `GET /api/v1/admin/payments/providers` | admin | Qaysi provayder ulangan |
| `GET /pay/{id}` | mijoz | To'lov sahifasi |
| `GET /api/v1/invoices/{id}` | mijoz | Hisob ma'lumoti (JSON) |
| `POST /api/v1/payments/payme` | Payme | Merchant API (JSON-RPC) |
| `POST /api/v1/payments/click/prepare` | Click | Prepare |
| `POST /api/v1/payments/click/complete` | Click | Complete |

Misol:

```bash
# Hisob ochish
curl -X POST https://cloud.chaqimchi.uz/api/v1/admin/sites/<site-id>/invoices \
  -H "X-Cloud-Admin-Key: $CHAQIMCHI_CLOUD_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"months": 12}'
# → {"id": "a1b2c3...", "amount_uzs": 14900000, "pay_url": "...", "payme_url": "...", "click_url": "..."}
```

## To'lov qaytarilsa (refund)

Payme `CancelTransaction` ni bajarilgan tranzaksiyaga yuborsa, hisob bekor
bo'ladi **va obuna o'sha oylarga qisqaradi** — ya'ni pul qaytgani hisobga olinadi.
Bu ataylab shunday: aks holda pul qaytarilgan mijoz tekinga ishlab yurardi.

## Xavfsizlik

- Callback endpointlari **HTTPS** ostida bo'lishi shart — imzo va kalitlar ochiq
  kanaldan o'tmasin.
- `CHAQIMCHI_PAYME_KEY` va `CHAQIMCHI_CLICK_SECRET` faqat serverda; git ga tushmasin.
- Summa har doim serverda hisoblanadi — provayder yuborgan summa faqat
  **tekshiriladi**, ishonchli manba sifatida qabul qilinmaydi.
- Takroriy callback (retry) xavfsiz: bir hisob ikki marta to'langan deb
  belgilanmaydi va obuna ikki marta uzaymaydi.

## Test

```bash
make test          # tests/test_payments_store.py, tests/test_payments_api.py
```

Testlar Payme JSON-RPC oqimini (yaratish → bajarish → bekor qilish) va Click
Prepare/Complete imzosini haqiqiy HTTP so'rovlar orqali tekshiradi.
