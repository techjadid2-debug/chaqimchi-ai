# Raqobat tahlili — RetailSolution.ai

Sana: 2026-09-06. Manba: ularning `retailsolution.ai/uz` sayti,
`/uz/docs` (to'liq Integration API hujjati) va mijoz paneli
(`dashboard.retailsolution.ai`, Zar Bazar akkaunti — `company_id: 55`).
API hujjati ochiq turgani uchun quyidagilar taxmin emas, tasdiqlangan
fakt.

> Bu hujjat **qaror manbai emas** — canonical kontrakt baribir
> [DOKON_MVP.md](DOKON_MVP.md). Bu yerda faqat: ular nima qiladi, biz
> qayerda ustunmiz, nimani olamiz va qanday tartibda.

---

## 1. Ular nima sotadi — bir gap bilan

**Marketing analitikasi.** "Kim kirdi, qancha sotib oldingiz, mijozingiz
kim". Bizdagi "do'koningiz xavfsizmi" tomonini **umuman** ko'rmaydi —
xavfsizlik signali, klip, ish vaqtidan tashqari trevoga ularda yo'q.

Tasdiqlangan imkoniyatlari (API modelidan):

| Narsa | Tafsil |
|---|---|
| **Avtomatik konversiya** | Tashqi kamera ko'chadan o'tganni sanaydi (`traffic_count`), ichki kamera kirganni (`visit_count`), konversiya = kirgan ÷ o'tgan. Chek so'ramaydi. |
| **Mijozni yuzidan tanish** | Har xaridor `face_id` oladi → qayta tashrif, sodiqlik, noyob tashrifchi. Eng qimmat tarif — **Loyalty AI, 1 200 000 so'm/oy**. |
| **Yosh/jins segmentatsiyasi** | Kunlik hisobotda: ayol/erkak %, yosh guruh (under_18, 18-30, 31-40, 41-54, 55+). |
| **Peak/low soat** | Har filial uchun eng gavjum va eng bo'sh soat. |
| **Integratsiya API** | JWT + `cv_live_` API kalit, scope (`analytics`/`catalog`/`visitors`), **XLSX yuklab olish**. ERP ulanadi. |
| **Ko'p filial** | Kompaniya → bino → filial → bo'lim → xodim ierarxiyasi. |
| **Turish vaqti / xizmat / xodim ishi** | Tarif jadvalida bor (dwell, wait time, staff performance). |

Marketing da'volari: **98% aniqlik, +15% daromad, 500+ obyekt, 20M
tashrif/oy, 30 kun bepul sinov.** Narx: 500k / 600k / 1 200 000 so'm/oy.

### Ularning zaif joyi (bizning foydamizga)

Ularning API'si **xaridorning yuz kadrini** (`crop_url` → S3 presigned)
va hatto **xodim parolining bcrypt hashini** (`/token`, `/user/me`
javobida) tashqariga chiqarib turibdi. Ya'ni "lokal ishlaymiz" desa ham,
amalda xaridor yuzi ularning bulutida. Bu bizning bosh va'damiz uchun
tayyor kontrast.

---

## 2. Biz nimada ULARDAN ustunmiz

1. **Video do'kondan chiqmaydi.** Faqat hodisa va ruxsat etilgan media
   bulutga boradi; xaridor yuzi qurilmada qoladi. Ular buni gapiradi,
   biz buni arxitektura bilan bajaramiz. O'zbekistonda huquqiy + ishonch
   ustunligi.
2. **Xavfsizlik butunlay bizniki.** Ish vaqtidan tashqari odam,
   taqiqlangan zona, loitering, kamera buzilishi → telefonga darhol
   Telegram + klip. Ularda bu yo'q.
3. **Mijozning O'Z Windowsi + O'Z NVR/kamerasida** (i5-4590). Ular
   alohida "ko'prik" kompyuter talab qiladi.
4. **~3-4× arzon.** Bizniki: Boshlang'ich ~148 000, Biznes ~300 000
   so'm. Ularniki 500 000 dan boshlanadi.
5. **O'zbekcha, jargonsiz + Telegram tabiiy** (OTP kirish, kunlik
   digest, `/chek`).
6. **AI yordamchi** — savol-javob, manba o'sha vaqt lentasida
   belgilanadi. Ularniki oddiy "AI tavsiya".
7. **Internet uzilsa ham ishlaydi** (offline SQLite outbox + replay),
   imzolangan avto-yangilanish (OTA).

---

## 3. Ular ustun / bizda kamchilik

| # | Ularda | Bizda holat |
|---|---|---|
| 1 | Avtomatik konversiya (tashqi ÷ kirgan) | Faqat **qo'lda chek** (`/chek 100`, `cloud/value.py`). Tashqi/o'tgan sanog'i yo'q. |
| 2 | Yosh/jins hisobotda | Kod **bor** (`chaqimchi_ai/retail/demography.py`), lekin jonli kamera 360p → topilish **2%**. Feature bor, ishlamayapti. |
| 3 | Excel (XLSX) yuklash | CSV bor (`cloud/main.py`), XLSX yo'q. |
| 4 | Integratsiya API (kalit + scope) | Yo'q. |
| 5 | Ko'p filial/tarmoq | Yo'q — bitta do'kon, 4 kamera (`limits.py`). |
| 6 | Sodiqlik / qayta tashrif (mijoz yuzidan) | Yo'q — hozirgacha ataylab. **Qaror o'zgardi (§5).** |
| 7 | Sayt pishiqligi (narx jadvali, onboarding, dalil) | Ataylab minimal. |

---

## 4. Qarorlar (ega, 2026-09-06)

1. **Birinchi ish — avtomatik konversiya** (tashqi trafik / capture rate).
2. **Mijozni yuzidan tanish — QILAMIZ** (sodiqlik/qayta tashrif). Bu
   `DOKON_MVP.md` dagi "mijoz Face ID — MVP'da yo'q" bandini
   **o'zgartiradi**. Amalga oshirish **lokal, rasmsiz** bo'lishi shart
   (§5) — aks holda 1-ustunligimizni yo'qotamiz.
3. **Maqsad mijoz — ikkalasi**: hozir yakka do'kon bilan sotamiz,
   arxitekturani tarmoqqa (ko'p filial) tayyorlab boramiz.

---

## 5. Reja — tartib bilan

### A. Avtomatik konversiya  ⭐ birinchi

**Maqsad:** chek so'ramay konversiya ko'rsatish.

Ikki yo'l bor, ega tanlaydi:

- **A1 — qo'shimcha kamerasiz (tavsiya, yakka do'kon uchun):** kirish
  kamerasida "eshik oldida ko'ringan odam" (yaqinlashgan) ni "chiziqni
  kesib kirgan" (`retail/lines.py`) bilan solishtirish → *capture rate*:
  "eshik oldidan 500 o'tdi, 350 kirdi = 70%". 4 kamera chegarasini
  (`SHOP_MAX_CAMERAS`) yemaydi.
- **A2 — tashqi kamera (ulardek):** vitrinaga/ko'chaga qaragan alohida
  kamera ko'cha oqimini sanaydi. Aniqroq, lekin bitta kamera "sarflaydi"
  va do'konda 4 tadan ko'p kamera bo'lishini talab qiladi.

**Qadamlar (A1):**
1. `chaqimchi_ai/camera_roles.py` — kirish roliga "yaqinlashish
   zonasi"ni qo'shish (chiziqning tashqi tomoni). Yangi rol shart emas.
2. `chaqimchi_ai/retail/` — zona ichida ko'ringan noyob trekni sanash
   (kirmaganini ham). Klip/rasm **yozilmaydi** — faqat son.
3. `cloud/value.py` — `conversion()` ni `receipts` yoniga
   `passed`/`entered` variantini oladigan qilish; chek yo'q bo'lsa
   capture rate ko'rsatiladi. `MIN_VISITORS_FOR_CONVERSION=20` intizomi
   saqlanadi.
4. `cloud/digest.py` — kunlik hisobotga "🚶 500 o'tdi → 350 kirdi (70%)"
   qatori. `/chek` qatori chek kiritilganda konversiya (savdo) uchun
   qoladi — ikkalasi boshqa savolga javob beradi.
5. `FORBIDDEN_CLAIMS` (`tests/test_static_pages.py`) — saytga faqat
   yetkazib bera oladigan narsani qo'shamiz.

### B. Demografiyani ishga tushirish

Kod bor, muammo **kamera 360p**. `camera-01` 1280×720 ga o'tsa
`demography` ishlaydi (ISH_DAFTARI: hozir topilish 2%). Bu mijoz
kamerasiga bog'liq — kodda emas. O'tgach: yosh guruh % + ayol/erkak %
kunlik hisobotga chiqadi, ularning asosiy "sotuv gapi" yopiladi.

### C. Excel yuklash + hisobotni ular formatiga yaqinlashtirish

Kam mehnat, katta ta'sir: peak/low soat, yosh %, jins % — hammasi bizda
bor, bitta chiroyli hisobotga + XLSX ga yig'ish.

### D. Mijoz sodiqligi / qayta tashrif — LOKAL, RASMSIZ

**Muhim:** buni ularning yo'li bilan (yuzni bulutga yuborib) qilsak,
1-ustunligimizni (§2.1) o'ldiramiz. Shuning uchun:

- Embedding **faqat qurilmada** hisoblanadi va **faqat qurilmada**
  saqlanadi; bulutga **hech qanday yuz kadri ketmaydi** — faqat
  "yangi mijoz / qayta kelgan mijoz" degan **anonim signal**.
- Embedding Fernet bilan shifrlanadi, qisqa muddat (masalan 30 kun)
  yashaydi, xaridor rasmi umuman saqlanmaydi.
- Mijozga ko'rinadigan natija ular bilan bir xil: qayta tashrif %,
  noyob mijoz, "doimiy mijozlar" — lekin bizniki maxfiylikni
  buzmaydi va shu bizning **sotuv gapimiz** bo'ladi.

**Kodni yozishdan OLDIN (ega imzosi kerak):**
- `DOKON_MVP.md` "MVP'da yo'q → mijoz Face ID" bandini yangilash;
- maxfiylik siyosati + oferta + rozilik shabloni (do'kon xaridorlarni
  ogohlantirishi kerak — huquqiy);
- `require_biometric_access()` (`cloud/main.py`) qamrovini tekshirish;
- narx/tarif: bu Loyalty tarifimi yoki Biznesga qo'shiladimi.

### E. Integratsiya API + ko'p filial

**Tarmoq mijozi kelganda.** Hozir yakka do'kon fokusda, lekin
arxitekturani tarmoqqa tayyorlab boramiz (ega qarori §4.3):
- ma'lumot modelida "site" allaqachon bor — uni "filial"ga
  umumlashtirish yo'lini yopib qo'ymaslik;
- API kalit + scope (ulardagidek) — ERP integratsiyasi uchun.

---

## 6. Nimani ATAYLAB olmaymiz

- **98% / +15%** kabi da'volar — `FORBIDDEN_CLAIMS` taqiqlaydi, to'g'ri
  qiladi. Biz faqat yetkazib bera oladiganini va'da qilamiz.
- **Xaridor yuzini bulutga yuborish** — bu ularning yo'li; biz sodiqlikni
  lokal qilamiz (§5.D).

---

## 7. Bajarilish holati

**Muhim cheklov:** 72 soatlik soak ishlab turibdi — soak tugamaguncha
**qurilma relizi chiqmaydi** (ISH_DAFTARI). A1 (capture rate) qurilmada
yangi signal talab qiladi ("eshik oldiga kelib kirmagan odam"), ya'ni
uning **qurilma qismi soakka to'qnashadi**. Shuning uchun bosqichlar
to'qnashmaydigan tartibda olib boriladi:

| Bosqich | Holat |
|---|---|
| **C — Excel/CSV yuklash** | ✅ **Bajarildi (2026-09-06, faqat cloud+panel).** `GET /api/v1/owner/report.csv` — **kunlik** (`?date=`) va **davriy** (`?start=&end=`, ≤31 kun, kuniga qator + Jami — raqobatchining branch-summary'idek). Ustunlar: kirdi/chiqdi, gavjum soat, konversiya, mijoz portreti, **xavfsizlik** (ularda yo'q). Panelda «Kunlik hisobot», «Oylik» va «14 kunlik CSV» tugmalari. BOM'li CSV, yangi bog'liqliksiz. |
| **A — avtomatik konversiya** | Cloud «plumbing»i C bilan tayyor bo'ldi (hisobotda konversiya bor). A1 sanash logikasi — **qurilma relizi, soak tugagach**. |
| **B — demografiya 720p** | Mijoz kamerasiga bog'liq (kod bor). |
| **D — sodiqlik (lokal)** | Huquqiy hujjatlar + qurilma relizi kerak. |
| **E — API + ko'p filial** | Tarmoq mijozi kelganda. |

**Keyingi qadam:** soak tugagach A1 qurilma logikasi; parallel — C ni
haqiqiy `.xlsx` ga ko'tarish (`openpyxl` ni ataylab qo'shib) agar ega
formatlangan Excel xohlasa.
