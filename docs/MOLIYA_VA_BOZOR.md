# [ARXIV] Eski moliyaviy tahlil va bozorga chiqish rejasi

> Bu taxminlar joriy mahsulot qarori emas. Faol scope va ochiq savollar:
> [DOKON_MVP.md](DOKON_MVP.md).

Sana: 2026-08-03. Raqamlar `chaqimchi_ai/licensing/plans.py` dagi haqiqiy
tariflardan olingan.

> **Taxminlar** (siz tasdiqlashingiz kerak): Mini PC 4 000 000 so‘m,
> IP kamera 900 000 so‘m, montaj 800 000 so‘m, 1 USD ≈ 12 900 so‘m,
> jamoa 2 kishi, oylik xarajat 15 000 000 so‘m. Bu raqamlar o‘zgarsa
> xulosalar ham o‘zgaradi.

---

## 1. Unit ekonomika: model ishlaydi

### Obuna — kuchli tomon

| Tarif | Oylik | Xarajat | Sof marja | % |
|-------|-------|---------|-----------|---|
| Starter | 790 000 | 180 000 | **610 000** | 77% |
| Business | 1 490 000 | 180 000 | **1 310 000** | 88% |
| Enterprise | 2 990 000 | 180 000 | **2 810 000** | 94% |

Xarajat = cloud server ulushi (~30 000) + qo‘llab-quvvatlash vaqti (~150 000).

**77–94% marja — bu juda yaxshi.** Dasturiy ta’minot biznesining butun
ma’nosi shu: bitta mijoz qo‘shilsa xarajat deyarli o‘zgarmaydi.

### O‘rnatish — kutilgandan yomonroq

| Tarif | Narx | Uskuna + ish | Marja | % |
|-------|------|--------------|-------|---|
| Starter | 6 500 000 | 5 700 000 | 800 000 | **12%** |
| Business | 9 500 000 | 7 500 000 | 2 000 000 | **21%** |
| Enterprise | 15 000 000 | 12 800 000 | 2 200 000 | **15%** |

**Xulosa: o‘rnatishdan boyimaysiz.** U faqat uskuna pulini qaytaradi. Butun
foyda obunadan keladi.

Bu strategik ma’noga ega: o‘rnatish narxini **pasaytirib** bo‘lsa ham mijoz
sonini ko‘paytirish foydali — chunki har bir mijoz keyin oyiga 1.3 mln sof
foyda beradi. Lekin uskuna puli oldindan chiqadi, shuning uchun naqd zaxira
kerak.

---

## 2. Break-even: nechta mijoz kerak

| Oylik xarajat | Faqat Starter | Faqat Business |
|---------------|---------------|----------------|
| 8 000 000 (1 kishi, ofissiz) | 14 ta | **7 ta** |
| 15 000 000 (2 kishi + server) | 25 ta | **12 ta** |
| 30 000 000 (4 kishi + ofis) | 50 ta | 23 ta |

**Maqsad: 12 ta Business mijoz.** Bu erishib bo‘ladigan son — g‘ayrioddiy
narsa emas.

### 12 oylik prognoz (oyiga 2 ta yangi mijoz, 3% churn)

| Oy | Mijoz | Oylik natija | Jamg‘arilgan naqd |
|----|-------|--------------|-------------------|
| 1 | 2 | −8 380 000 | −8 380 000 |
| 4 | 8 | −520 000 | **−17 800 000** ← eng chuqur nuqta |
| 5 | 10 | +2 100 000 | −15 700 000 |
| 8 | 16 | +9 960 000 | +6 320 000 ← naqd musbat |
| 12 | 21 | +16 510 000 | **+64 500 000** |

**Sizga kerak bo‘lgan asosiy raqam: ~18 000 000 so‘m** — 4-oygacha bo‘lgan
eng chuqur teshikni qoplash uchun. Bundan ko‘p emas.

### Naqd pulning kaliti: yillik to‘lov

Yillik = oylik × 10 (2 oy tekin). Bitta Business mijoz shartnoma imzolagan
kuni: **24 400 000 so‘m** (o‘rnatish 9.5 mln + yillik 14.9 mln).

Bu — eng kuchli moliyaviy quroli. Uskuna pulini darhol qoplaydi. **Har bir
sotuvda yillik to‘lovni taklif qiling** va chegirmani shunga bering, oylikka
emas.

---

## 3. Eng muhim xulosa: segmentni almashtiring

Loyiha “do‘kon xavfsizligi” deb qurilgan. Lekin raqamlar boshqa narsani
ko‘rsatadi.

### Do‘kon egasiga sotish qiyin

- ROI o‘lchanmaydi: “o‘g‘rini tutadi” — yiliga necha marta? Noma’lum.
- Byudjet yo‘q: 1.49 mln so‘m/oy kichik do‘kon uchun katta pul.
- Qaror qabul qiluvchi — egasining o‘zi, va u ehtiyotkor.

### Xodimlar davomatiga sotish oson

Bir xil kod, boshqa qadoq. Mana mijozga aytiladigan dalil:

> 100 xodim, o‘rtacha oylik 4 000 000 so‘m.
> Har biri kuniga atigi **15 daqiqa** kech kelsa —
> oyiga **12 500 000 so‘m** yo‘qotasiz.
> Tizim narxi: 1 490 000 so‘m/oy. **6 barobar qaytadi.**

Nima uchun bu yaxshiroq:

| | Do‘kon xavfsizligi | Xodimlar davomati |
|---|---|---|
| ROI | O‘lchanmaydi | So‘mda hisoblanadi |
| Xaridor | Do‘kon egasi | Direktor / HR — byudjeti bor |
| Ehtiyoj | “Balki kerak bo‘lar” | Har oy, tabel yopishda |
| Chiqib ketish xavfi | Yuqori | Past — ish jarayoniga kirib qoladi |

**Raqobat va sizning ustunligingiz.** Bozorda barmoq izi terminallari bor
(ZKTeco va shu kabilar), 2–3 mln so‘m, bir martalik. Ular arzon. Lekin:

- **Karta va barmoq izini almashtirib bo‘ladi** — do‘st do‘sti uchun bosib
  qo‘yadi. Yuzni almashtirib bo‘lmaydi. Bu sizning bitta jumlalik sotuv
  dalilingiz.
- Barmoq izi iflos/nam qo‘lda ishlamaydi (zavod, oshxona, qurilish).
- Terminal oldida navbat bo‘ladi; kamera oqim bilan ishlaydi.

### Kodga nima yetishmaydi

Deyarli hammasi tayyor — `events` jadvali allaqachon `person_id` +
`timestamp` + `camera_id` yozadi. Kerak bo‘lgani:

1. Kamera roli: “kirish” / “chiqish”
2. Kunlik tabel: kim soat nechada keldi, ketdi, necha soat ishladi
3. Oylik hisobot → Excel/CSV eksport (buxgalteriya shuni so‘raydi)
4. Kech qolganlar va kelmaganlar ro‘yxati
5. Xodim kartochkasi: bo‘lim, lavozim, ish vaqti (9:00–18:00)

Taxminan **2–3 kunlik ish**. Sotuv kuchiga nisbatan juda arzon.

---

## 4. Narx modeli mos emas

Hozirgi cheklov — **kamera soni**. Davomat uchun bu ma’nosiz: 200 xodimli
zavodga 2 ta kamera yetadi (kirish va chiqish), lekin 200 ta shaxs kerak.

Qiymat kamera sonida emas, **xodim sonida**. Narx ham shunday bo‘lsin:

| Xodim | 15 000 so‘m/xodim | 20 000 so‘m/xodim |
|-------|-------------------|-------------------|
| 30 | 450 000 | 600 000 |
| 50 | 750 000 | 1 000 000 |
| 100 | 1 500 000 | 2 000 000 |
| 200 | 3 000 000 | 4 000 000 |
| 500 | 7 500 000 | 10 000 000 |

Afzalligi: mijoz o‘ssa siz ham o‘sasiz, qayta sotuvsiz. Kichik mijoz
kirishi oson (450 000 so‘m — “yo‘q” deyish qiyin narx).

Tavsiya: **eng kam 500 000 so‘m/oy + 15 000 so‘m har xodim uchun.**

---

## 5. AI (ko‘rish agenti) — hozircha to‘xtating

| Tarif | AI‘siz marja | AI bilan |
|-------|--------------|----------|
| Starter | 77% | **44%** |
| Business | 88% | 70% |
| Enterprise | 94% | 85% |

AI marjaning uchdan birini yeydi va **sotuvni osonlashtirmaydi** — mijoz
“nima bo‘layapti” tahlilini so‘ramaydi, u tabel so‘raydi.

Qaror: kodda tayyor tursin (`enabled: false`), lekin **alohida qo‘shimcha**
sifatida soting: “AI kuzatuv +490 000 so‘m/oy”. Kim xohlasa — o‘zi to‘laydi.

---

## 6. Nomdagi muammo

**“Chaqimchi”** = xabarchi, sotqin. Direktorga kulgili tuyuladi. Lekin:

- Xodim uchun bu ochiq signal: “bu narsa meni sotadi”.
- HR sotib olishda ichki qarshilikka duch keladi.
- Katta korxona bilan shartnomada nom hujjatda turadi.

Davomat bozoriga chiqsangiz, neytral nom kerak (masalan “Davomat AI”,
“Yuz+”, kompaniya nomi). Bu shoshilinch emas, lekin birinchi katta mijozdan
oldin hal qilinsin.

---

## 7. Nimadan boshlash — aniq ketma-ketlik

### 1-oy: pilot (pul emas, ma’lumot)

Bitta korxona toping — 50–150 xodimli. Tanish orqali bo‘lsa yaxshi.
**Tekin yoki faqat uskuna puliga** o‘rnating, 2 oy.

Maqsad: pul emas. Sizga kerak bo‘lgani:
- Nima ishlamaydi (yorug‘lik, burchak, niqob, qish kiyimi)
- Mijoz nimani so‘raydi (siz o‘ylamagan narsa bo‘ladi)
- **Referens va raqam**: “X korxonada kechikish 22% kamaydi”

Bittasiz ikkinchi mijozni sotib bo‘lmaydi.

### 2-oy: tabel hisoboti

Yuqoridagi 5 ta narsa (2–3 kunlik ish). Pilot mijoz aynan shuni so‘raydi.

### 3-oy: narxni qayta qo‘ying

Xodim boshiga model. Eski tariflar ham qolsin (do‘kon uchun).

### 4–6-oy: 10 ta mijoz

Bitta yaxshi sotuvchi. Har sotuvda **yillik to‘lov** taklif qiling.
Hisob: har mijoz shartnoma kuni ~24 mln so‘m naqd beradi.

### Nimani hozir qilmang

- AI ni yoqmang (marja yeydi)
- Yangi funksiya yozmang (tabeldan boshqa)
- Ofis olmang, xodim yollamang — 12 ta mijozdan keyin
- Reklamaga pul sarflamang — birinchi 10 ta mijoz tanish va sovuq qo‘ng‘iroq
  orqali keladi

---

## 8. Xavflar

| Xavf | Ta’siri | Nima qilish |
|------|---------|-------------|
| **Yuridik** — biometrik ma’lumot | Sotuv to‘xtaydi | Xodimdan yozma rozilik shakli tayyorlang. Bu birinchi savol bo‘ladi. |
| **Churn** — 3-oyda chiqib ketish | LTV yarmiga tushadi | Oylik hisobot yuboring: mijoz nima uchun to‘layotganini ko‘rsin |
| **Uskuna narxi oshishi** | O‘rnatish zararga chiqadi | Narxni dollarga bog‘lang yoki 3 oyda qayta ko‘ring |
| **Bitta katta mijozga bog‘lanish** | U ketsa biznes qulaydi | 5 ta mijozdan keyin hech biri daromadning 30% idan oshmasin |
| **Aniqlik past chiqishi** | Ishonch yo‘qoladi | Pilotda o‘lchang: `make calibrate` |

---

## 9. Siz javob berishingiz kerak bo‘lgan savollar

Bu raqamlar aniqlashsa, tahlil aniqroq bo‘ladi:

1. Hozir nechta to‘lovchi mijoz bor?
2. Mini PC + kamera **haqiqiy** narxi qancha? (men 4 mln + 900 ming deb oldim)
3. Jamoada necha kishi, oylik xarajat qancha?
4. Qancha naqd zaxira bor? (18 mln kerak bo‘ladi)
5. Sotuvni kim qiladi — o‘zingizmi?
