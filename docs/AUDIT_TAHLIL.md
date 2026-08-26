# Audit tahlil — chaqimchi.uz va mahsulot holati

**Sana:** 2026-08-25 · **Versiya:** cloud 0.6.15, o'rnatuvchi 0.6.13
**Hukm:** nazorat ostidagi pilotga tayyor, pullik sotuvga tayyor emas
**Bog'liq hujjatlar:** [DOKON_MVP.md](DOKON_MVP.md) (mahsulot kontrakti),
[RELIZ_VA_OTA.md](RELIZ_VA_OTA.md), [INSTALLER.md](INSTALLER.md)

Bu hujjat saytdagi har bir va'dani kodga solishtirib tekshirgan auditning
natijasi va undan chiqqan reja. Bandlar bajarilgan sari shu yerda
belgilanadi — hujjat tirik qolsin, arxivga aylanmasin.

---

## Kontekst — nega bu ish qilinyapti

Chaqimchi AI sotuvga chiqish arafasida: sayt jonli (`https://chaqimchi.uz`,
HTTP 200), narxlar e'lon qilingan, "14 kun bepul" tugmasi ishlaydi va
o'rnatuvchi fayl yuklab olinadi. Ya'ni **mijoz bugun kelib pul to'lay
oladi**.

Shu sababli saytdagi har bir va'da kodga solishtirib tekshirildi. Maqsad —
mijoz topguncha biz o'zimiz topishimiz. Tekshiruv **faqat o'qish** rejimida
o'tkazildi: hech bir fayl o'zgartirilmadi, production'ga hech narsa
yuborilmadi, hujum sinovi qilinmadi.

Tekshirilgan narsalar: 9 ta jonli sahifa, HTTP sarlavhalari, DNS va server
joylashuvi, 4 ta public API (`/pricing`, `/edu-pricing`,
`/download-installer`, `/health/deep`), `cloud/`, `chaqimchi_ai/`,
`docs/` kodi va `releases/` papkasi.

### Audit davomida qabul qilingan ikki qaror (2026-08-25)

1. **Edu kalkulyatoridan mavjud bo'lmagan modullar olib tashlanadi**
   (janjal 199 000, dars monitoringi 129 000, chuqur tahlil 249 000
   so'm/oy). Ular "Rejada — narx e'lon qilinmagan" ro'yxatiga o'tadi.
   Edu sahifasi ochiq qoladi, Face ID va qo'shimcha filial sotilaveradi.
2. **Yuz orqali davomat yopiq pilot bo'lib qoladi va kodda ham
   yopiladi.** Hozir kod uni hamma uchun ochib qo'ygan — bu sayt matniga
   zid.
3. **Saytdagi "biometrika O'zbekistonda qoladi" va'dasi olib
   tashlanadi.** Server Fransiyada (Contabo) va yaqin kelajakda shunday
   qoladi — O'zbekiston hostingiga ko'chish rejaga **kiritilmaydi**.
   Ya'ni yechim: bajarilmayotgan va'dani aytishni to'xtatish, uni
   bajarishga urinish emas. Huquqiy savol yurist ko'rigiga (B2)
   qo'yiladi.

---

## Bir qarashda: 22 ta topilma

| # | Muammo | Og'irlik | Tuzatish |
|---|---|---|---|
| K-1 | ~~Edu kalkulyatori mavjud bo'lmagan 3 ta AI modulni sotmoqda~~ | Kritik | ✅ **TUZATILDI** |
| K-2 | ~~Server Fransiyada, sayt "O'zbekistonda" deb yozgan~~ | Kritik | ✅ **TUZATILDI** |
| K-3 | Ommaviy oferta yo'q, lekin pul olinadi | Kritik | 🟡 **YOZILDI**, yurist ko'rigi qoldi |
| K-4 | ~~Biometrik rasmlar `manager` roliga ochiq~~ | Kritik | ✅ **TUZATILDI** |
| Y-0 | ~~`/health/deep` ochiq — mijozlar soni oshkor~~ | Yuqori | ✅ **TUZATILDI** |
| Y-1 | ~~"Xodim davomati" sotiladi, tarif bermaydi~~ | Yuqori | ✅ **TUZATILDI** |
| Y-2 | ~~Mijozga beriladigan o'rnatuvchi 2 versiya orqada~~ | Yuqori | ✅ **TUZATILDI** |
| Y-3 | ~~Yo'riqnoma noto'g'ri fayl nomini aytadi~~ | Yuqori | ✅ **TUZATILDI** |
| Y-4 | ~~O'rnatish vaqti 4 xil aytilgan~~ | Yuqori | ✅ **TUZATILDI** |
| Y-5 | ~~Hero "4 kamera", arzon tarifda 2 kamera~~ | Yuqori | ✅ **TUZATILDI** |
| Y-6 | AI aniqligi hech qachon o'lchanmagan | Yuqori | C bosqichi |
| Y-7 | ~~NTP yo'q — soat adashsa tungi alertlar buziladi~~ | Yuqori | ✅ **TUZATILDI** |
| Y-8 | Video/AI yo'lida birorta haqiqiy sinov yo'q | Yuqori | L |
| Y-9 | ~~Audit jurnali eng muhim amallarni yozmaydi~~ | Yuqori | ✅ **TUZATILDI** |
| Y-10 | To'lov va parollar production'da hali SQLite'da | Yuqori | L |
| Y-11 | Klip saqlash testi beqaror (mahsulot mantiqi to'g'ri, sabab noma'lum) | Yuqori | S–M |
| Y-12 | ~~Saytda klip 30 kun, kodda 7 kun~~ | Yuqori | ✅ **TUZATILDI** |
| ~~O-0~~ | ~~`config/sotqin.yaml` hali 8 kamera deydi~~ | — | ❌ **NOTO'G'RI TOPILMA** |
| O-1 | `/health` haqiqatni ko'rsatmaydi | O'rta | M |
| O-2 | CSP sarlavhasi yo'q | O'rta | M |
| O-3 | Faqat o'zbek tili — rus tili yo'q | O'rta | L |
| O-4 | Analitika yo'q — konversiya o'lchanmaydi | O'rta | S |

Qolganlari: O-5 (narx dollarga bog'langan), O-8 (token bekor qilib
bo'lmaydi), O-9 (rate limit xotirada). O-7 (JWT kaliti) serverda
tekshirildi — **muammo yo'q**, kalit qo'yilmagan.

---

## 1-QISM: TOPILGAN MUAMMOLAR

Ustuvorlik qoidasi: **Kritik** — sotishdan oldin tuzatilsin. **Yuqori** —
pilotdan keyin kengaytirishdan oldin. **O'rta** — yo'l xaritasiga.

---

### KRITIK-1 · Edu kalkulyatori mavjud bo'lmagan AI funksiyalarni sotmoqda

> ## ✅ TUZATILDI — 2026-08-25
>
> `chaqimchi_ai/licensing/edu.py`: `MODULES` da endi faqat ikkita
> sotiladigan modul (`faceid`, `branch`). Uchtasi yangi
> `PLANNED_MODULES` ga ko'chdi — **narxsiz**, sahifada tanlab
> bo'lmaydigan "rejada" holatida ko'rinadi (butunlay yashirish ham
> xato bo'lardi: mijoz baribir so'raydi, sotuvchi og'zaki va'da berib
> qo'yadi).
>
> `LOAD_WEIGHTS` dan janjal (2.5) va chuqur tahlil (2.25) olib
> tashlandi — ular o'ylab topilgan raqamlar edi va qurilma narxini
> oshirardi. Endi faqat `faceid: 1.25` qoldi va u ham "baholangan" deb
> belgilangan (`catalog()["load_note"]`).
>
> **Mijoz uchun farq** (maktab, 355 kishi, 8 kamera, "janjal + chuqur
> tahlil" so'ralgan holat):
>
> | | Ilgari | Endi |
> |---|---|---|
> | Oylik obuna | 1 000 000 so'm | **670 000 so'm** |
> | Tavsiya qilingan qurilma | Pro — 7 490 000 so'm | **Plus — 4 490 000 so'm** |
> | Yetkazib berilmaydigan modul | 3 ta sotilardi | **0** |
>
> Ya'ni maktabdan oyiga 330 000 so'm ortiqcha va qurilma uchun bir
> martalik 3 000 000 so'm ortiqcha so'ralayotgan ekan.
>
> `edu.html` da yong'in/tutun haqidagi ikkiyoqlama jumla ham tuzatildi:
> ilgari "janjal tahlili ehtimol sifatida xabar beradi" deb yozilardi,
> endi to'g'ridan-to'g'ri **"tizim yong'in, tutun yoki alangani
> aniqlamaydi"**.
>
> Testlar: `tests/test_edu_pricing.py` — uchta yangi tripwire
> (`test_only_modules_that_exist_in_code_can_be_sold`,
> `..._cannot_be_bought_even_if_asked_for`,
> `..._does_not_inflate_the_device_quote`). Sotuv namunalari
> (`SPEC_EXAMPLES`) qo'lda qayta hisoblanib, har qatorga hisob izohi
> yozildi — ular kod chiqargan raqamni emas, mustaqil arifmetikani
> tekshiradi.

**Qayerda:** `chaqimchi.uz/edu` narx kalkulyatori
**Fayl:** `chaqimchi_ai/licensing/edu.py:79-85`

Kalkulyator mijozga aniq oylik narx bilan quyidagilarni taklif qiladi:

| Modul | Kalkulyatordagi narx | Kodda bormi |
|---|---|---|
| Janjal va tajovuzni aniqlash | **199 000 so'm/oy** | **YO'Q** |
| AI dars monitoringi | **129 000 so'm/oy** | **YO'Q** |
| Chuqurlashtirilgan dars tahlili | **249 000 so'm/oy** | **YO'Q** |
| Face ID va avtomatik davomat | 129 000 so'm/oy | Bor (pilot) |

**Dalil:**
- Jonli API javobi: `GET https://chaqimchi.uz/api/v1/public/edu-pricing`
  → `modules` ro'yxatida to'rttala modul narxi bilan turibdi.
- Butun kodda janjal/tajovuz detektori **yo'q**:
  `grep -rn -iE "fight|aggress|violence|janjal|tajovuz" --include="*.py"`
  → faqat `event_models.py:61` dagi izoh matni topildi, detektor emas.
- Dars monitoringi **yo'q**: `grep -rn -iE "lesson|dars_monitor"` → bo'sh.
- Mavjud hodisa turlarining to'liq ro'yxati (`chaqimchi_ai/event_models.py`):
  `line_crossed`, `occupancy_exceeded`, `dwell_exceeded`,
  `queue_threshold_exceeded`, `loitering`, `zone_entered`,
  `after_hours_presence`, `camera_tampered`, `camera_offline`,
  `stream_frozen`, `checkout_unattended`, `checkout_second_till`,
  `shelf_empty`, `employee_seen`, `face_captured`, `ai_review`.
  Janjal ham, dars ham bu ro'yxatda yo'q.

**Eng yomoni — bir sahifaning o'zi o'zini inkor qiladi.**
`cloud/static/edu.html:152-158` matni: *"Dars monitoringi — rejada...
hozircha buni sotmaymiz."* O'sha sahifaning pastidagi kalkulyator esa uni
129 000 so'mga sotadi.

**Biznes zarari:** Maktab shartnoma imzolab, "janjal aniqlash" uchun oyiga
199 000 so'm to'laydi. Yetkazib bera olmaymiz. Ta'lim muassasasi bilan
sud/shikoyat riski, obro'ga zarar, pul qaytarish.

**Qo'shimcha zarar — qurilma narxi ham noto'g'ri.** `edu.py:96-101` dagi
`LOAD_WEIGHTS` (janjal = 2.5, chuqur tahlil = 2.25) — bu **o'lchanmagan,
o'ylab topilgan raqamlar**, chunki o'lchanadigan kod yo'q. Shu raqamlar
asosida kalkulyator mijozga 1 790 000 dan **19 490 000 so'mgacha** qurilma
tavsiya qiladi (`edu.py:109-116`).

**Tuzatish:** Kalkulyatordan `fight`, `monitoring`, `deep` modullarini
olib tashlash. Ularni "Rejada — narx e'lon qilinmagan" ro'yxatiga
ko'chirish. `LOAD_WEIGHTS` va `EDGE_CATALOG` tavsiyasini faqat o'lchangan
funksiyalar bo'yicha qayta hisoblash.
**Egasi:** Product + Backend · **Hajmi:** M · **Muddat:** 1–2 kun

**Qayta tekshirish:** `GET /api/v1/public/edu-pricing` javobidagi har bir
`modules` yozuvi uchun kodda ishlaydigan detektor ko'rsatilsin. Test:
`tests/test_edu_pricing.py` ga "har bir sotiladigan modul kodda bor"
tekshiruvi qo'shilsin.

---

### KRITIK-2 · Server Fransiyada, sayt esa "xorijga yuborilmaydi" deb yozgan

> ## ✅ TUZATILDI — 2026-08-25
>
> **Edu sahifasi** (`cloud/static/edu.html`): hudud va'dasi butunlay
> o'chirildi. O'rniga ochiq matn — *"Face ID hozir yopiq pilot
> bosqichida va uni ommaga ochmaymiz: serverimiz Yevropada
> joylashgan"*. Ya'ni sabab yashirilmadi, aksincha u pilot chegarasini
> tushuntiradi.
>
> Bir bonus topilma: o'sha ro'yxatda *"audit jurnali mavjud"* deb ham
> yozilgan ekan, holbuki biometrik rasm o'chirish audit qilinmaydi
> (YUQORI-9). U ham haqiqatga moslandi — endi rostdan ishlaydigan
> narsa aytiladi: rasmni faqat rahbar ochadi (bu A0 da kafolatlandi).
>
> **Maxfiylik sahifasi** (`cloud/static/privacy.html`): ikkita yangi
> bo'lim.
> - *«Ma'lumot qayerda saqlanadi»* — serverlar Yevropada; uzluksiz
>   video arxiv bunga **kirmaydi** va NVR'da qoladi.
> - *«Uchinchi tomon xizmatlari»* — panel AI yordamchisi kadrni
>   **Google Gemini** ga yuborishi birinchi marta oshkor qilindi.
>   Bilan birga chegara ham yozildi: yuz kadrlari va davomat rasmlari
>   u yerga **hech qachon** ketmaydi. Bu kodda tasdiqlangan
>   (`cloud/vision_agent.py:262-268` va `cloud/main.py:7820-7826`).
>
> **Qulf:** `tests/test_static_pages.py` `FORBIDDEN_CLAIMS` ga to'rtta
> ibora qo'shildi (`"xorijdagi serverga yuborilmaydi"`,
> `"hududidagi infratuzilmada qoladi"` va ikkita variant). Eski jumla
> bilan sinab ko'rildi — qulf uni ushlaydi. Hosting Fransiyada turar
> ekan, bu va'da saytga qaytib kela olmaydi.
>
> **Hosting ko'chirilmadi va bu ataylab** — qaror 2026-08-25 da qabul
> qilingan. Huquqiy savol B2 da yuristga beriladi.

**Qayerda:** `cloud/static/edu.html:285`
**Va'da matni:** *"Yuz namunalari muassasadagi qurilmada yoki O'zbekiston
hududidagi infratuzilmada qoladi; **xorijdagi serverga yuborilmaydi**."*

**Haqiqat (o'lchangan):**
```
dig +short chaqimchi.uz  →  169.58.198.111
whois 169.58.198.111     →  Contabo GmbH, Munchen, GERMANY
ipinfo.io                →  Lauterbourg, Grand Est, FRANCE (AS51167)
hostname                 →  vmi3517534.contaboserver.net
```

Ya'ni yuz embedding'lari (`cloud/faces.py`) va 14 kun saqlanadigan yuz
kadrlari **Fransiyadagi serverda** turadi. Sayt buning aksini yozgan.

**Ikkinchi ochilmagan yo'l:** Vision Agent hodisa kadrlarini Google'ga
yuboradi — `cloud/vision_agent.py:125,175` →
`https://generativelanguage.googleapis.com/...`. Bu ham xorijiy qayta
ishlovchi. `/maxfiylik` sahifasida uchinchi tomon AI provayderi **umuman
eslatilmagan**. Yuz kadrlari bundan chiqarilgan (`vision_agent.py:262-268`
— to'g'ri qilingan), lekin oddiy do'kon kadrlari ketaveradi.

**Biznes zarari:** O'zbekiston "Shaxsga doir ma'lumotlar to'g'risida"
qonuni biometrik ma'lumotni mamlakat hududida saqlashni talab qiladi.
Ta'lim muassasasida bolalar biometrikasi bilan bu — eng og'ir risk.
Yozma va'da buzilgani esa sud ishida to'g'ridan-to'g'ri dalil.

**QAROR QABUL QILINDI (2026-08-25): hudud va'dasi saytdan olib
tashlanadi. O'zbekiston hostingiga ko'chish rejaga kiritilmaydi.**

Sabab: yolg'on va'dani to'xtatish — bu bir soatlik ish va u riskning
kattasini darhol yopadi. Hosting ko'chirish esa 3–6 hafta va qo'shimcha
xarajat, holbuki davomat yopiq pilot bo'lib qolyapti (YUQORI-1 qarori) —
ya'ni ishtirokchilar soni kam va har biri yozma rozilik bergan bo'ladi.

**Bajariladigan ish:**

1. `cloud/static/edu.html:285` — butun bandni **o'chirish**:
   *"Yuz namunalari muassasadagi qurilmada yoki O'zbekiston hududidagi
   infratuzilmada qoladi; xorijdagi serverga yuborilmaydi."*
2. `cloud/static/edu.html:277` — *"mamlakat hududida saqlanishi kerak"*
   jumlasi qonun talabini tasvirlaydi; u o'z holicha to'g'ri, lekin
   yonida biz shu talabni bajaramiz degan taassurot qolmasin. Qayta
   yozilsin: talab **mavjudligi** aytilsin, biz uni bajarayotganimiz
   aytilmasin.
3. `cloud/static/privacy.html` (`/maxfiylik`) — "Davomat biometrikasi"
   bandiga **ma'lumot qayerda saqlanishi ochiq yozilsin** (yevropadagi
   serverda) va Google Gemini uchinchi tomon qayta ishlovchi sifatida
   qo'shilsin.
4. `tests/test_static_pages.py` — `FORBIDDEN_CLAIMS` ga qo'shilsin:
   `"xorijdagi serverga yuborilmaydi"`, `"O'zbekiston hududidagi
   infratuzilma"`. Shunda bu va'da kelajakda **qaytib kela olmaydi**.

**Ochiq qolayotgan savol (yurist uchun, tuzatish emas):**
O'zbekiston "Shaxsga doir ma'lumotlar to'g'risida" qonuni biometrik
ma'lumotni mamlakat hududida saqlashni talab qiladi. Biz endi buni
va'da qilmaymiz, lekin **talab baribir bizga tegishli bo'lishi mumkin**.
B bosqichidagi yurist ko'rigida (B2) aynan shu savol berilsin:
*"Yopiq pilotda, yozma rozilik bilan, Yevropadagi serverda yuz
embeddingini saqlash mumkinmi?"* Javob "yo'q" bo'lsa — o'shanda hosting
masalasi qayta ko'riladi, hozir emas.

**Egasi:** Frontend + Product · **Hajmi:** S (2 soat)

**Qayta tekshirish:** `curl https://chaqimchi.uz/edu | grep -i "xorijdagi\|hududidagi"`
→ bo'sh natija. `make test` yashil (yangi `FORBIDDEN_CLAIMS` bilan).

---

### KRITIK-3 · Ommaviy oferta yo'q, lekin pul olinadi

> ## 🟡 YOZILDI — 2026-08-25 (yopilmadi: yurist ko'rigi kerak)
>
> `cloud/static/oferta.html` yaratildi, `/oferta` marshruti, footer
> havolasi va sitemap qo'shildi. 12 bo'lim, jumladan **javobgarlik
> chegarasi** (oxirgi bir oylik to'lovdan oshmaydi) va **«Xizmat nima
> QILMAYDI»** — o'g'rilik, yong'in, xaridorni tanish va uzluksiz video
> ataylab inkor qilingan.
>
> **Qabul qilingan qarorlar** (2026-08-25):
> - Pul qaytarish: birinchi to'lovdan keyingi **14 kun** ichida to'liq,
>   keyin qaytarilmaydi.
> - SLA: **aniq raqam berilmaydi** — 72 soatlik sinov o'tkazilmagan,
>   ya'ni raqam va'da qilishga asos yo'q. C bosqichidan keyin qo'shiladi.
> - Yuridik shakl hali ro'yxatdan o'tmagan → STIR va rekvizit **bo'sh
>   joy** bo'lib qoldi.
>
> **Ofertadagi hamma raqam koddan olingan** va test bilan bog'landi
> (`test_the_offer_promises_no_more_than_the_code_delivers`): tarif
> narxlari `plans.py` dan, klip muddati `CLIP_RETENTION_DAYS_DEFAULT`
> dan, qo'shimcha muddat `GRACE_DAYS` dan. Kod o'zgarsa test yiqiladi —
> hujjat jimgina yolg'onga aylanmaydi.
>
> **Nega hali yopilmadi:** ro'yxatdan o'tmasdan rasmiy hisob-faktura
> berib bo'lmaydi va hujjat yurist ko'rigidan o'tmagan (B2). Ya'ni
> KRITIK-3 sotuvni hamon to'sib turadi — lekin endi to'sig'i "hujjat
> yo'q" emas, "hujjat tayyor, imzo kerak".

**Qayerda:** Butun sayt
**Dalil:**
- `https://chaqimchi.uz/oferta` → **404**
- Footer'da oferta havolasi yo'q (`cloud/static/site.html`)
- Repoda `oferta.html` fayli yo'q; `oferta` so'zi faqat bitta joyda —
  `STRATEGIK_AUDIT_VA_REJA.md:151`, "QO'SHILISHI SHART" ro'yxatida.

Shu bilan birga `site.html:472` mijozga aytadi: *"Hozir hisob-faktura
olinadi va to'lov operator tomonidan tasdiqlanadi."*

**Biznes zarari:** O'zbekistonda onlayn xizmatni ommaviy oferta'siz sotish
— soliq va iste'molchi huquqlari bo'yicha muammo. Bahsli holatda (mijoz
"va'da qilingani ishlamadi" desa) bizni himoya qiladigan hujjat yo'q:
xizmat doirasi, SLA, pul qaytarish tartibi, javobgarlik chegarasi —
hech biri yozilmagan.

**Tuzatish:** `/oferta` sahifasi. Ichida: xizmat tavsifi, tarif va
to'lov tartibi, bepul sinov shartlari, bekor qilish, **javobgarlik
chegarasi** ("tizim o'g'rilikni oldini olishni kafolatlamaydi"),
ma'lumot egaligi, nizolarni hal qilish. Yurist ko'rigidan o'tsin.
**Egasi:** Product + yurist · **Hajmi:** M · **Muddat:** 3–5 kun

---

### KRITIK-4 · Biometrik rasmlarga rol tekshiruvi bitta yo'lda bor, ikkitasida yo'q

> ## ✅ TUZATILDI — 2026-08-25
>
> Yechim `cloud/main.py:842` da yangi `require_biometric_access(owner)`
> funksiyasi. Yuzga tegadigan **yettala** marshrut endi shu bitta
> nomdan o'tadi (ilgari uchtasi `require_owner_role` ni qo'lda chaqirar,
> ikkitasi umuman tekshirmas edi):
>
> | Marshrut | Ilgari | Endi |
> |---|---|---|
> | `POST /owner/faces/employees/{id}/photos` | ✓ | ✓ |
> | `POST /owner/faces/employees/{id}/photos/from-event/{id}` | ✓ | ✓ |
> | `DELETE /owner/faces/photos/{id}` | ✓ | ✓ |
> | `GET /owner/faces/events/{id}/image` | **✗** | ✓ |
> | `GET /owner/faces/photos/{id}/image` | **✗** | ✓ |
> | `GET /owner/events/{id}/snapshot` | ✓ | ✓ |
> | `GET /owner/events/{id}/clip` | ✓ | ✓ |
>
> Test: `tests/test_cloud_faces.py::test_a_manager_cannot_open_any_biometric_image`
> — beshta yo'lni birdan sanaydi. Tuzatish olib qo'yilganda test
> yiqiladi (`assert 200 == 403` — menejer xodim rasmini yuklab olardi),
> qaytarilganda o'tadi. To'liq to'plam: **1724 passed**, lint toza.
>
> **Tuzatilmagan, ataylab:** `GET /owner/faces` va
> `GET /owner/faces/events` hamon menejerga ochiq. Ular rasm emas,
> ro'yxat qaytaradi (ism, rasm ID'si, sifat bali) va menejerning
> davomat ko'rish oqimi shunga tayanadi. Rasm yo'llari yopilgani uchun
> ID'ning o'zi endi hech narsa bermaydi.

Bu **kod xatosi** va tasdiqlangan.

Tizim biometrik rasmni bitta marshrutda ataylab himoya qiladi:
`cloud/main.py:7649-7657` — `GET /api/v1/owner/events/{event_id}/snapshot`
`face_captured` yoki `employee_seen` bo'lsa
`require_owner_role(owner, "owner", "service_admin")` talab qiladi.

**Lekin aynan o'sha rasmni ikkita parallel marshrut hech qanday rol
tekshiruvisiz beradi:**
- `cloud/main.py:7450-7458` — `GET /api/v1/owner/faces/events/{event_id}/image`
  → o'sha `face_captured` kadri
- `cloud/main.py:7461-7469` — `GET /api/v1/owner/faces/photos/{face_id}/image`
  → xodimning ro'yxatga olingan biometrik rasmi

Ikkalasida ham faqat `require_active_owner` bor — ya'ni **`manager` roli
yetarli**. Do'kon egasi `POST /api/v1/owner/members` orqali qo'shgan
oddiy menejer barcha xodimlarning yuz rasmlarini ko'ra oladi.

**Nega bu og'ir:** `/rozilik-shabloni` da xodimga yozma va'da beriladi —
*"Ma'lumotlarim faqat davomat maqsadida ishlatiladi va uchinchi
shaxslarga berilmaydi."* Menejer — o'sha xodimning boshlig'i, va u
ro'yxatdan tashqari kirish huquqiga ega bo'lib qolyapti.

**Tuzatish:** Har ikki marshrutga `require_owner_role(owner, "owner",
"service_admin")` qo'shish. Umumiy yordamchi funksiya yozilsin, toki
kelajakda uchinchi marshrut ochilganda ham unutilmasin.
**Egasi:** Security/Backend · **Hajmi:** S (30 daqiqa) · **Ustuvorlik: eng yuqori**

**Qayta tekshirish:** `manager` tokeni bilan uchala marshrut ham 403
qaytarsin — test yozilsin.

---

### YUQORI-1 · "Xodim davomati" Biznes tarifida sotiladi, lekin tarif uni bermaydi

> ## ✅ TUZATILDI — 2026-08-25
>
> `cloud/main.py: _attendance_enabled()` da `or` **`and`** ga
> almashtirildi. Endi ikki shart boshqa-boshqa savolga javob beradi:
>
> | Shart | Savol | Yetarlimi |
> |---|---|---|
> | `MODELS_LICENSED_FOR_COMMERCIAL_USE` | Modelni tijoratda ishlatish mumkinmi? | SHART, lekin yetarli emas |
> | `CHAQIMCHI_ATTENDANCE_PILOT` | Shu server biometrika bilan ishlashga tayyormi? | Production'da MAJBURIY |
>
> Ilgari litsenziya rost bo'lgani uchun ikkinchi shart hech qachon
> tekshirilmasdi — ya'ni davomat production'da hammaga ochiq edi,
> holbuki sayt uni "yozma rozilikli yopiq pilot" deb sotardi.
>
> `plans.py`: Biznes kartasidan "Xodim davomati — 10 xodimgacha, yuz
> orqali" bulleti olib tashlandi. Eskirgan izoh ham yangilandi — sabab
> endi `buffalo_l` litsenziyasi emas (modellar 2026-08-21 dan
> Apache-2.0), balki ikkita ochiq band: **hosting hududi** (KRITIK-2)
> va **o'lchanmagan yuz moslash aniqligi**.
>
> Ikkita yangi test: production'da pilot bayrog'isiz 403 (bayroq bilan
> 200), va litsenziya bo'lmasa pilot bayrog'i ham ochmaydi. Sotuv
> matni testi ham qayta yozildi — endi u litsenziyaga emas,
> **tarif nima berishiga** bog'langan.

**Dalil:**
- Sotuv kartasi: `chaqimchi_ai/licensing/plans.py:306-311` — Biznes
  tarifida *"Xodim davomati — 10 xodimgacha, yuz orqali."*
- Tarif funksiyalari: `plans.py:204` →
  `BIZNES_EDGE_FEATURES = ("person_count", "queue_length", "store_security")`
  — `davomat` yo'q.
- `plans.py:199-202` izohi: *"`davomat` bu ro'yxatlarda ATAYLAB yo'q."*

**Qo'shimcha chalkashlik:** Bu izoh **eskirgan**. U hali ham `buffalo_l`
tadqiqot litsenziyasini sabab qilib ko'rsatadi, lekin
`cloud/faces.py:8,101-103` bo'yicha modellar 2026-08-21 da OpenVINO
Apache-2.0 ga ko'chirilgan va `MODELS_LICENSED_FOR_COMMERCIAL_USE = True`.

**Natijada `cloud/main.py:811-830` `_attendance_enabled()` production'da
DOIM `True` qaytaradi** — chunki birinchi shart har doim bajariladi.
Ya'ni davomat aslida hamma uchun **yoqilgan**, holbuki sayt uni "yopiq
pilot, yozma rozilik bilan" deb sotadi (`site.html:217`, `edu.html:141`).

Bu KRITIK-2 bilan qo'shilganda og'irlashadi: biometrika yoqiq, serveri
Fransiyada, sayt esa "yopiq pilot" va "O'zbekistonda" deydi.

**QAROR QABUL QILINDI (2026-08-25): davomat — YOPIQ PILOT.**

Ya'ni kod ham saytga moslashadi, teskarisi emas. Bajariladigan ish:

1. `cloud/main.py:811-830` `_attendance_enabled()` dan
   `faces.MODELS_LICENSED_FOR_COMMERCIAL_USE` shartini olib tashlash —
   faqat `CHAQIMCHI_ATTENDANCE_PILOT` env bayrog'i (va development
   muhiti) ochsin. Litsenziya endi *ruxsat*, lekin *sabab* emas.
2. `chaqimchi_ai/licensing/plans.py:306-311` — Biznes kartasidan
   "Xodim davomati" bulletini olib tashlash.
3. `plans.py:199-202` izohini yangilash: `buffalo_l` yo'q, sabab endi
   litsenziya emas — **hosting hududi va qabul sinovi**.
4. Pilot obyektlarni `CHAQIMCHI_ATTENDANCE_PILOT` bilan alohida
   yoqish; yozma rozilik hujjati olinganini admin panelda belgilash.

**Bu qaror KRITIK-2 bilan birga ishlaydi:** davomat yopiq pilot bo'lgani
uchun biometrika bilan ishlaydigan obyektlar soni kam va har biri yozma
rozilik bergan bo'ladi. Shu sababli hosting hududini o'zgartirish rejaga
kiritilmadi — buning o'rniga saytdagi noto'g'ri va'da o'chiriladi va
huquqiy savol yuristga beriladi (B2).
**Egasi:** Product + Backend · **Hajmi:** M

---

### YUQORI-2 · Mijozga beriladigan o'rnatuvchi 2 versiya orqada

> ## ✅ TUZATILDI — 2026-08-26
>
> **Haqiqiy sabab audit taxmin qilganidan boshqa chiqdi.** 0.6.14 ham,
> 0.6.15 ham serverga **allaqachon chiqarilgan** edi (25-avgust), imzosi
> joyida. Muammo build'da emas — `.env.production` da:
>
> ```
> CHAQIMCHI_WINDOWS_INSTALLER_URL=...chaqimchi-windows-0.6.13.exe
> ```
>
> Qotirilgan URL 0.6.13 da qolib ketgan va ikkita reliz hech kimga
> bormagan. Kod'dagi `latest_windows_release()` aynan shu ish uchun
> yozilgan, lekin env pini uni chetlab o'tardi.
>
> **Bundan ham yomoni:** pin faqat kodsiz havolada ishlardi. Kod bilan
> kelgan mijoz (`?code=A1B2C3`) faylni to'g'ridan-to'g'ri olardi, ya'ni
> **0.6.15** ni; kodsiz kelgan esa **0.6.13** ni. Bitta sayt ikki xil
> versiya tarqatib turgan ekan.
>
> **Bajarilgani:**
> 1. Versiya **0.6.16** ga ko'tarildi va qurildi — 0.6.15 ni qayta
>    qurish ataylab qilinmadi: u imzolangan va serverda turgan edi, bir
>    xil versiya ostida boshqa baytlarni chiqarish OTA butunligini
>    buzardi.
> 2. Imzolandi (Ed25519) va nashr qilindi; imzo qurilmadagi ochiq kalit
>    bilan tekshirildi.
> 3. **Env pini olib tashlandi** — manzil endi eng yangi imzolangan
>    relizdan o'zi keladi va bu xato takrorlanmaydi.
>
> **Yon natija:** pin ketgach pairing kod fayl nomida ishlaydigan bo'ldi
> (`Chaqimchi_AI_Setup-0.6.16-A1B2C3.exe`). Ilgari redirect nomni
> yo'qotardi va mijoz 6 belgini qo'lda kiritardi.
>
> **Yon oqibat:** fayl nomi ham o'zgardi, shuning uchun A6 tuzatishi
> teskari tomonga to'g'rilandi — `install.html` endi
> `Chaqimchi_AI_Setup-<versiya>.exe` deydi va nom relizdan yasaladi.
>
> Jonli tekshiruv: yuklab olish 0.6.16 beradi, sahifadagi nom mos,
> API 0.6.16 deydi. Hozir birorta qurilma ulanmagan (4 saytdan 3 tasi
> `not_paired`, 1 tasi `offline`), ya'ni bu reliz ishlab turgan
> do'konni buzmaydi.

**Dalil (jonli o'lchangan):**
```
Repo (git 557c6f2):  pyproject.toml           → 0.6.15
Cloud (server):      GET /health/deep         → 0.6.15  ✓ yangi
Mijoz yuklab oladi:  /download-installer      → 0.6.13  ← 2 versiya orqada
                     (last-modified: 23-avgust, 102 705 431 bayt)
```
`GET /api/v1/public/download-installer` → 307 →
`https://dl.chaqimchi.uz/releases/chaqimchi-windows-0.6.13.exe`
(102 705 431 bayt, `last-modified: Sun, 23 Aug 2026`).

`releases/chaqimchi-windows-0.6.15.json` manifest fayli bor, lekin
`0.6.15.exe` build qilinmagan (papkada eng yangisi `0.6.9.exe`).

**Nima uchun muhim:** 0.6.14 dagi asosiy tuzatish — *"Demografiya
Windows'da birinchi marta ishlaydigan bo'ldi"*. Sayt esa "Mijoz portreti"
ni Biznes tarifida sotadi. Ya'ni **bugun yuklab olgan mijozda demografiya
ishlamaydi**.

**Tuzatish:** 0.6.15 ni build qilish, imzolash, `dl.` ga chiqarish.
Bosqichli tarqatish (`docs/RELIZ_VA_OTA.md`): avval o'z qurilma, 24 soat
hold.
**Egasi:** DevOps · **Hajmi:** S

---

### YUQORI-3 · O'rnatish yo'riqnomasi noto'g'ri fayl nomini aytadi

> ## ✅ TUZATILDI — 2026-08-25
>
> Fayl nomi endi **relizdan** olinadi: `install.html` dagi JS
> `/api/v1/public/windows-release` javobidan `chaqimchi-windows-<versiya>.exe`
> ni yasab qo'yadi. Qo'lda yozilgan nom boshqa qaytib kelmaydi.
>
> Tekshiruv paytida ma'lum bo'ldiki, ichki hujjatlardagi
> `Chaqimchi_AI_Setup.exe` **to'g'ri** ekan — bu build artefaktining nomi;
> `scripts/publish_windows_release.sh:55-61` uni nashr paytida
> `chaqimchi-windows-<versiya>.exe` ga qayta nomlaydi. Ya'ni xato faqat
> mijoz ko'radigan ikki sahifada edi va tuzatish aynan shu yerga
> qo'llandi.

**Dalil:**
- `cloud/static/install.html:53-54`: *"Fayl nomi `Chaqimchi_AI_Setup-`
  bilan boshlanadi... masalan `Chaqimchi_AI_Setup-0.6.8.exe`"*
- `install.html:216` yana takrorlaydi.
- Haqiqiy fayl: **`chaqimchi-windows-0.6.13.exe`**

Mijoz yuklamalar papkasini ochadi, aytilgan nomni topmaydi.
Muammolar bo'limi esa aynan shu nom bilan "to'g'ri faylni" tanishtiradi —
ya'ni yo'riqnoma o'zi chalg'itadi. Bu SmartScreen ogohlantirishi bilan
birga kelganda mijoz "virus" deb o'ylashi mumkin.

**Tuzatish:** `install.html` da fayl nomi jonli
`/api/v1/public/windows-release` javobidan olinsin (versiya ham).
**Egasi:** Frontend · **Hajmi:** S

---

### YUQORI-4 · O'rnatish vaqti to'rt xil aytilgan

> ## ✅ TUZATILDI — 2026-08-25
>
> Endi butun saytda **ikkita** raqam, va ular bir-biriga zid emas —
> chunki ular boshqa-boshqa ishni tasvirlaydi:
>
> | Kim | Qancha | Sharti |
> |---|---|---|
> | Mijoz o'zi | **30 daqiqagacha** | NVR allaqachon tarmoqda ishlab tursa |
> | Usta / montajchi | **45–90 daqiqa** | NVR, RTSP va tarmoq ham sozlanadi |
>
> Yangilangan sahifalar: `site.html` (sarlavha va FAQ), `install.html`,
> `hamkorlik.html`, `docs/index.html`, `installer-guide.html`.
>
> **Bu raqamlar hali o'lchanmagan** — ehtiyotkor baho. C bosqichida
> real o'rnatish soatga qarab o'lchansin va shu jadval o'shanga
> almashtirilsin.
>
> Yo'l-yo'lakay: `installer-guide.html` da *"Windows 11 installer
> rejalashtirilgan"* deb turgan ekan, holbuki Windows o'rnatuvchisi
> allaqachon sotilyapti. U ham tuzatildi.

| Manba | Va'da |
|---|---|
| `site.html:254` | "Uch qadam, **o'n daqiqa**" |
| `site.html:448` (FAQ) | "Butun jarayon **10 daqiqa**" |
| `install.html:29-30` | "Boshidan oxirigacha **10 daqiqa**" |
| `hamkorlik.html:13` | "odatda **30–60 daqiqa**" |
| `docs/index.html:12` | "odatda **30–60 daqiqa**" |
| `installer-guide.html:24` | "**45–90 daqiqa**" |

Farq 9 barobar. Mijoz 10 daqiqaga ishonib kechqurun boshlaydi, usta esa
90 daqiqa deb reja qiladi. Birinchi taassurot shu yerda buziladi.

**Tuzatish:** Ikkita halol raqam: **mijoz o'zi** (dastur o'rnatish +
kamera ulash) va **usta** (NVR sozlash bilan). Real pilotda
o'lchansin, keyin yozilsin. Hozircha eng yomon holat yozilsin.
**Egasi:** Product · **Hajmi:** S

---

### YUQORI-5 · Hero'da "4 kamera", arzon tarifda esa 2 kamera

> ## ✅ TUZATILDI — 2026-08-25
>
> `site.html`: hero'da **"4 kameragacha"**, faktlar blokida esa
> to'g'ridan-to'g'ri **"2–4 kamera · Tarifga qarab: Boshlang'ich 2,
> Biznes 4"**. 149 000 so'mga kelgan mijoz endi nima olishini
> sahifaning tepasidayoq ko'radi.
>
> Test `tests/test_cloud_api.py` da yangi matnga bog'landi va nega
> shunday ekani izohda yozildi.

`site.html:134,144,193` — sahifaning eng tepasida uch marta "4 kamera".
`plans.py:322` — Boshlang'ich tarifi `max_cameras=2`.

149 000 so'mga kelgan mijoz 4 kamera kutadi, 2 tasini oladi.
**Tuzatish:** Hero'da "4 kameragacha" yozilsin yoki tarif nomi bilan
bog'lansin. **Egasi:** Frontend · **Hajmi:** S

---

### YUQORI-0 · `/health/deep` ochiq va mijozlar soningizni oshkor qiladi

> ## ✅ TUZATILDI — 2026-08-25 (deploy kutilmoqda)
>
> Endpoint **butunlay yopilmadi va bu ataylab**: `Caddyfile` izohida
> yozilganidek, tashqi monitoring (UptimeRobot) aynan shu manzilga
> qaraydi. Uni admin kaliti ostiga olish monitoringni ko'r qilardi.
>
> Buning o'rniga javob **kim so'rayotganiga qarab** qisqaradi:
>
> | | Begona (monitoring) | Admin kaliti bilan |
> |---|---|---|
> | `ok` va HTTP 503 | ✓ | ✓ |
> | Qaysi tekshiruv yiqilgani (`name`) | ✓ | ✓ |
> | Javob tezligi (`ms`) | ✓ | ✓ |
> | Mijozlar soni (`sites`) | **✗** | ✓ |
> | Bucket nomi, disk hajmi, versiya | **✗** | ✓ |
> | Xato matni (`error`) | **✗** | ✓ |
>
> Xato matni ham chiqarildi, chunki uning o'zi sizdirardi:
> *"MinIO bucket topilmadi: chaqimchi-snapshots"*.
>
> Test `test_deep_health_tells_a_stranger_nothing_about_the_business`
> anonim javobda `sites`, `bucket`, `free_gb`, `used_percent`,
> `version`, `postgres` so'zlarining birortasi ham yo'qligini
> tekshiradi.

**Jonli tekshirildi:**
```
$ curl https://chaqimchi.uz/health/deep
{"ok":true,"version":"0.6.15","checks":[
  {"name":"control_db","sites":4},
  {"name":"event_db","engine":"postgres"},
  {"name":"media","engine":"minio","bucket":"chaqimchi-snapshots"},
  {"name":"disk","free_gb":85.1,"used_percent":11.1}]}
```
Autentifikatsiya yo'q, rate limit yo'q
(`cloud/main.py:1648-1669`, `deploy/Caddyfile.chaqimchi:107`).

**Biznes zarari:** Raqobatchi yoki investor bir buyruq bilan **sizda 4 ta
mijoz borligini** biladi. Sotuv suhbatida "bizda o'nlab do'kon bor"
deyishning iloji qolmaydi. Qo'shimcha: infratuzilma tafsiloti (Postgres,
MinIO bucket nomi, disk) hujumchiga tayyor xarita beradi.

**Tuzatish:** `/health/deep` ni admin kaliti ostiga olish yoki Caddy'da
faqat ichki tarmoqqa ochish. `/health` (sodda `ok`) ochiq qolaversin.
**Egasi:** DevOps · **Hajmi:** S (1 soat)

---

### YUQORI-9 · Audit jurnali eng muhim amallarni yozmaydi

> ## ✅ TUZATILDI — 2026-08-25
>
> Yetti turdagi amal endi `portal_audit_log` ga yoziladi:
>
> | Amal | Nega muhim |
> |---|---|
> | `owner.login_link.created` / `.revoked` | Havolaning o'zi parol |
> | `invoice.marked_paid` | Naqd to'lovni odam qo'lda tasdiqlaydi — tashqi provayderdan iz qolmaydi |
> | `site.subscription.extended` | Pul bilan bog'liq |
> | `site.plan.changed` | Narx va funksiya to'plami o'zgaradi |
> | `site.member.added` / `.removed` | Do'kon ma'lumotiga kirish huquqi |
> | `biometrics.photo.deleted` | Xodimga o'chirish VA'DA qilingan — isbot kerak |
>
> **Master kalit endi anonim emas.** `X-Cloud-Admin-Key` bilan qilingan
> amal ilgari `actor_id=NULL` yozardi va boshqa har qanday bo'sh
> yozuvdan farq qilmasdi. Endi `"cloud-admin-key"` — kimligini
> aytmaydi, lekin **usulini** aytadi, ya'ni qidiruv qayerdan
> boshlanishini.
>
> **Token jurnalga tushmaydi.** Kirish havolasi yozuvida faqat
> `telegram_id` va muddat bor; tokenning o'zi ataylab yozilmaydi —
> aks holda jurnalni o'qiy oladigan har kim mijoz paneliga kira
> olardi. Buni alohida test qulflaydi
> (`test_the_login_link_token_never_reaches_the_log`).
>
> Uchta yangi test.

`portal_audit_log` jadvali bor (`cloud/store.py:564-575`) va 18 ta amal
yoziladi. Lekin **eng xavflilari yozilmaydi**:

| Yozilmaydigan amal | Fayl:qator |
|---|---|
| **Kirish havolasi yaratish** (bu — parol!) | `cloud/main.py:5585-5612` |
| Hisob-fakturani "to'landi" deb belgilash | `cloud/main.py:8296` |
| Obunani uzaytirish | `cloud/main.py:4328` |
| Tarifni o'zgartirish | `cloud/main.py:3630` |
| A'zo qo'shish/o'chirish | `cloud/main.py:5569`, `:7636` |
| Biometrik rasm o'chirish | `cloud/main.py:7427`, `:7188` |
| **`X-Cloud-Admin-Key` bilan qilingan HAR QANDAY amal** | `cloud/main.py:211-222` (`actor_id=None`) |

Master admin kaliti (`X-Cloud-Admin-Key`) barcha `/api/v1/admin/*` ni
ochadi va **hech qanday iz qoldirmaydi** — rate limit ham yo'q.

**Nega muhim:** Edu sahifasi mijozga *"audit jurnali mavjud"* deb va'da
beradi (`edu.html:286`). Bugungi holatda bu va'da to'liq emas. Pul bilan
bog'liq bahsda (mijoz "men to'lamaganman" desa) kim tasdiqlaganini
ko'rsatib bo'lmaydi.

**Tuzatish:** Yuqoridagi 7 turdagi amalga `audit_portal_action()`
qo'shish. `X-Cloud-Admin-Key` uchun alohida `actor_id="cloud-admin-key"`
yozuvi + IP.
**Egasi:** Backend · **Hajmi:** M

---

### YUQORI-10 · To'lov va parol ma'lumotlari production'da hali SQLite'da

`cloud/main.py:1446-1447` production'da `DATABASE_URL` ning PostgreSQL
bo'lishini majburlaydi — va `/health/deep` buni tasdiqlaydi
(`event_db: postgres`). **Lekin bu faqat hodisalarga tegishli.**

`CloudStore` (`cloud/store.py:210-211`) va `PaymentStore`
(`cloud/payments/store.py:38-39`) **faqat SQLite** bilan ishlaydi. Ya'ni
production'da bitta SQLite faylda turadi:
- hisob-fakturalar va to'lov tranzaksiyalari
- portal akkauntlari va **parol hashlari**
- shifrlangan RTSP/NVR parollari
- audit jurnali

`docker-compose.chaqimchi.yml:35,71` ikkita servis bir xil faylga
yozadi (WAL, `timeout=30`) — yozuv raqobati xavfi bor.

**Tuzatish:** `CloudStore` va `PaymentStore` ni ham Postgres'ga ko'chirish
(`EventStore` da ikki dialekt qo'llab-quvvatlash allaqachon yozilgan —
`cloud/event_store.py:92-121` naqshini takrorlash). Ko'chirishgacha:
backup chastotasini oshirish va bitta yozuvchi jarayonni kafolatlash.
**Egasi:** Backend/DevOps · **Hajmi:** L

---

### O'RTA-7 · Tekshirilishi kerak: JWT kalitlari ajratilgani

`chaqimchi_ai/jwt_auth.py:21-26` — `resolve_jwt_secret()` avval global
`CHAQIMCHI_JWT_SECRET` ni o'qiydi va u bor bo'lsa
`CHAQIMCHI_OWNER_JWT_SECRET` / `CHAQIMCHI_PORTAL_JWT_SECRET` ni
**butunlay e'tiborsiz qoldiradi**.

Bu holatda owner va admin tokenlari bir xil kalit bilan imzolanadi
(ularni faqat `kind` claim ajratadi) va `cloud/main.py:1454-1457` dagi
"kamida 32 belgi" tekshiruvi haqiqatda ishlatilayotgan kalitni
tekshirmaydi.

**Holat: TASDIQLANMAGAN.** `CHAQIMCHI_JWT_SECRET` repoda faqat Box/Linux
profilida uchraydi (`deploy/sotqin.env.example:19`), cloud misolida
izohga olingan (`.env.example:22`). Serverdagi `.env.production` fayli
o'qilmadi.

**Qilinadigan ish:** Serverda bitta buyruq —
`grep CHAQIMCHI_JWT_SECRET .env.production`. Agar qo'yilgan bo'lsa:
o'chirish va owner/portal kalitlarini alohida yaratish.
**Egasi:** DevOps · **Hajmi:** S (10 daqiqa tekshirish)

---

### O'RTA-8 · Token `localStorage` da, server tomonda "chiqish" yo'q

Owner tokeni `localStorage["chaqimchi_owner_token"]` da, 12 soat amal
qiladi (`cloud/owner_auth.py:27`). Server tomonda blacklist yo'q —
"Chiqish" tugmasi faqat `localStorage.removeItem` qiladi
(`cloud/static/owner.html:769-772`).

Ya'ni token o'g'irlansa (XSS yoki umumiy kompyuter), uni **to'xtatib
bo'lmaydi** — a'zolikni o'chirmagunicha 12 soat ishlaydi. Do'kon
kompyuteri ko'pincha umumiy foydalanishda bo'ladi.

Ijobiy tomoni: cookie ishlatilmaydi → CSRF amalda imkonsiz.
Portal (admin/installer) tomonida esa `auth_version` mexanizmi bor va
parol o'zgarsa barcha tokenlar darhol o'ladi (`cloud/store.py:1722`) —
**owner tomonda ham shu naqsh takrorlansin**.
**Egasi:** Backend · **Hajmi:** M

---

### O'RTA-9 · Rate limit xotirada — restart bilan aylanib o'tiladi

`cloud/ratelimit.py:3-11` moduli o'zi tan oladi: *"jarayon qayta ishga
tushganda nolga qaytadi"*. Login brute-force cheklovi (8 urinish / 15
daqiqa) deploy paytida yoki ikkinchi instansiyada nolga qaytadi
(`docker-compose.chaqimchi.yml:35,71`).

Shuningdek `POST /api/v1/owner/auth/verify` (`cloud/main.py:5667`) da IP
bo'yicha cheklov umuman yo'q — faqat DB'dagi 5 urinish hisoblagichi.
Birovning Telegram ID'sini bilgan odam uning OTP'sini "kuydirib"
qo'yishi mumkin (hisobni buzmaydi, lekin kirishga xalaqit beradi).

**Tuzatish:** Rate limit DB'ga ko'chirilsin (vision uchun allaqachon
shunday qilingan) + `auth/verify` ga IP cheklovi.
**Egasi:** Backend · **Hajmi:** M

---

### YUQORI-6 · AI aniqligi hech qachon o'lchanmagan

Sayt "mijozlar oqimini sanaydi", "navbatni kuzatadi", "xavfsizlik
signallari" deb sotadi. Bu va'dalarni tasdiqlaydigan **birorta o'lchov
yo'q**:

- Repoda **birorta test videosi yo'q** (`.mp4/.avi/.mkv` — nol dona).
- Precision / recall / yolg'on ogohlantirish ulushi hech qayerda
  o'lchanmagan va yozilmagan.
- Yagona raqam — `chaqimchi_ai/retail/detector_ov.py:11` dagi
  **"AP 88.62%"**, bu **Intel'ning model kartochkasidan** olingan, sizning
  do'koningiz kadrlarida emas.
- `scripts/benchmark_n100.py` faqat **tezlikni** o'lchaydi (p50/p95/p99),
  aniqlikni umuman o'lchamaydi. Natija fayli repoda yo'q.
- Jamoa buni o'zi tan olgan: `docs/DOKON_MVP.md:45` — "real do'konlarda
  line/queue/tamper/loitering **aniqlik kalibratsiyasi**" bajarilmagan;
  `chaqimchi_ai/retail/README.md:305-319` — "Benchmark hali ishlatilmagan",
  "Sig'im hali haqiqiy qurilmada o'lchanmagan".

**Yolg'on ogohlantirish haqida bor bo'lgan yagona dalillar — nosozlik
izohlari, metrika emas:**
- `chaqimchi_ai/settings.py:128-136` — *"6×12 pikselli dog' 'odam' bo'lib,
  bir kechada **48 ta yolg'on hodisa**"*
- `chaqimchi_ai/retail/pipeline.py:67-72` — *"**321 hodisadan 300 tasi
  loitering (93%)**, 29 MB rasmning 28.9 MB'i shundan"*
- `scene_analytics.py:552-557` — *"bitta track bir joyda 6354 soniya
  turgan"*

**Nima qilish kerak:** C bosqichida (72 soatlik sinov) aniqlik ham
o'lchansin — pastdagi jadval bo'yicha.
**Egasi:** ML-CV · **Hajmi:** L

---

### YUQORI-7 · Soat noto'g'ri bo'lsa tungi ogohlantirishlar buziladi

> ## ✅ TUZATILDI — 2026-08-25
>
> Uch qatlam, chunki bittasi yetmaydi:
>
> 1. **Oldini olish** — o'rnatuvchida yangi «Kompyuter soatini
>    to'g'rilash» bo'limi: `w32time` avtomatik ishga tushiriladi va
>    `pool.ntp.org` ga ulanadi. Muvaffaqiyatsizlik o'rnatishni
>    **to'xtatmaydi** — domenga ulangan kompyuterda vaqt siyosatini
>    administrator boshqaradi va uni buzmaslik kerak.
> 2. **O'lchash** — qurilma har heartbeat'da o'z soatini yuboradi
>    (`device_clock`), cloud farqni hisoblaydi (`_clock_skew_seconds`).
>    Ishora saqlanadi: **orqada** — o'lgan CMOS batareyasi, **oldinda** —
>    odatda noto'g'ri timezone. Ustaga qaysi biri ekani kerak.
>    Maydonni yubormagan eski qurilma `None` beradi — «bilmayman»
>    nolga aylantirilmaydi, aks holda adashgan soat hech qachon
>    ko'rinmasdi.
> 3. **Aytish** — 5 daqiqadan oshsa egaga Telegram xabari. Matn
>    texnik atamasiz: nima buzilishini tushuntiradi («kunduzi bekorga
>    xabar kelishi yoki kechasi umuman kelmasligi mumkin») va uchta
>    aniq qadam beradi, oxirgisi — «batareyka o'lgan, ustaga
>    ko'rsating».
>
> Ustuvorlik ham to'g'rilandi: soat tekshiruvi tahlil xatosidan
> **oldin** turadi, chunki adashgan soat hech qanday hisoblagichni
> o'stirmaydi — qurilma «sog'lom» bo'lib turaveradi. Lekin hodisa
> yo'qolayotgan bo'lsa (`queue`) u baribir birinchi qoladi: bitta
> xabar — bitta muammo.
>
> Yo'l-yo'lakay: egaga xabar berish `if state == "temp"` shartlari
> bilan ikki joyda yozilgan ekan; lug'atga (`_OWNER_ALERT_TEXT`)
> ko'chirildi, aks holda har yangi holat uchun ikkala joyni tuzatish
> kerak bo'lardi.
>
> 11 ta yangi test.

**Dalil:** NTP hech qayerda sozlanmaydi — `w32tm`, `timedatectl`,
`chrony` butun kodda chaqirilmaydi. Muammo jamoa tomonidan tan olingan:
`cloud/event_store.py:497-501` — *"do'kon kompyuteri 2014-yilgi, CMOS
batareyasi o'lishi odatiy hol, **NTP hech qayerda majburiy emas**"*.

Cloud himoyasi bor, **lekin u yetarli emas**: `_normalise_occurred_at()`
(`event_store.py:483-535`) faqat hodisaning *yozilgan vaqtini* tuzatadi.
Qurilma **qarorlari** esa OS soatiga ishonadi:
`chaqimchi_ai/retail/pipeline.py:219-221` → `datetime.now().time()`.

**Real oqibat:** Do'kon kompyuterining soati 6 soatga adashsa,
`after_hours_presence` **kunduzi** ishlaydi — har mijoz "ish vaqtidan
tashqari odam" bo'lib Telegramga tushadi. Yoki teskarisi: tunda o'g'ri
kirsa, tizim uni "ish vaqti" deb hisoblab **jim turadi**.

Bu memory'dagi mijoz kompyuteri (i5-4590, 2014-yil, Haswell) uchun aynan
mos xavf — o'sha yoshdagi mashinada CMOS batareyasi odatda o'lgan bo'ladi.

**Tuzatish:**
1. O'rnatuvchida Windows vaqt xizmatini yoqish
   (`w32tm /config /syncfromflags:manual /manualpeerlist:pool.ntp.org`
   + `/resync`).
2. Har heartbeat'da qurilma soati bilan server soati farqini yuborish;
   5 daqiqadan oshsa — panelda qizil ogohlantirish va Telegram xabari.
3. Farq 30 daqiqadan oshsa jadvalga bog'liq qoidalarni **to'xtatish**
   (`rules.py:206-211` allaqachon "vaqt noma'lum bo'lsa ishlamaydi"
   mantiqiga ega — shu yo'lni ishlatish).

**Egasi:** Backend + Installer · **Hajmi:** M

---

### YUQORI-8 · Video va AI yo'lida birorta haqiqiy sinov yo'q

1639 ta test funksiyasi bor (101 fayl, ~31 300 qator) — bu yaxshi. Lekin
**video/AI qismi 100% soxta bog'liqlik bilan ishlaydi**:

- Hech bir testda haqiqiy RTSP oqim, haqiqiy `cv2.VideoCapture` yoki
  haqiqiy OpenVINO modeli yuklanmaydi. Kamera — `FakeCapture`
  (`tests/test_retail_runner.py:30-53`), detektor — `FakeDetector` /
  `ScriptedDetector`.
- 862 ta mock/monkeypatch, 22 ta `class Fake*`.
- `pytest.mark.skipif` / `importorskip` **umuman yo'q** — ya'ni "apparat
  bo'lsa ishlaydigan" bitta ham test yo'q.
- Model fayllari repoda yo'q: `models/retail/` papkasi **bo'sh**.

Ya'ni `make test` yashil bo'lishi "video zanjiri ishlaydi" degani emas —
faqat "mantiq to'g'ri yozilgan" degani.

**Tuzatish:** 2–3 ta qisqa haqiqiy video (kunduzi, kechasi, gavjum) repoga
yoki alohida yuklanadigan paketga qo'shilsin; ular ustida haqiqiy model
bilan ishlaydigan, qo'lda belgilangan javob bilan solishtiruvchi test
yozilsin (`@pytest.mark.slow`, CI'da ixtiyoriy).
**Egasi:** ML-CV · **Hajmi:** L

---

### YUQORI-12 · Saytda klip 30 kun deb va'da qilingan, kod 7 kunda o'chiradi

**Qachon topildi:** B1 (oferta) yozilayotganda — saqlash muddatlarini
koddan tekshirayotib.

**Dalil:**
- `cloud/static/docs/xavfsizlik.html` jadvali: *"Hodisa kadrlari va
  qisqa **kliplar** — 30 kun"*
- `cloud/main.py:1296` — `CLIP_RETENTION_DAYS_DEFAULT = 7`
- `cloud/event_store.py:3360` izohi buni ataylab shunday qilgan:
  *"Klip hodisani tekshirish uchun kerak — bir haftadan keyin deyarli
  hech kim ochmaydi"*

Ya'ni mijoz 30 kun deb o'ylab, 8-kuni klipni izlasa topmaydi. Rasm
(snapshot) rostdan 30 kun turadi — jadval ikkalasini bitta qatorga
qo'shib yuborgani uchun qisqarog'i ko'rinmay qolgan.

Qiziq tomoni: koddagi izoh *"Sayt ham aniq kun sonini va'da qilmaydi"*
deb yozilgan — muallif shunday deb o'ylagan, lekin hujjatlar sahifasi
aniq raqam berib turgan ekan.

**✅ TUZATILDI:** jadval ikkita alohida qatorga bo'lindi — rasm 30 kun,
klip 7 kun. Oferta ham shu raqamlar bilan yozildi va test bilan
`CLIP_RETENTION_DAYS_DEFAULT` ga bog'landi.

**Egasi:** Product · **Hajmi:** S

---

### YUQORI-11 · Klip saqlash testi beqaror — jimgina o'chib ketayotgan bo'lishi mumkin

**Qachon topildi:** A1 ishidan keyin to'liq to'plam ishlatilganda
(2026-08-25). Auditning o'zida emas — tuzatishlar davomida chiqdi.

**Dalil:**
```
tests/test_cloud_load.py::test_clip_retention_is_configurable
  to'liq to'plamda:   FAILED  (assert False == 1)
  yolg'iz:            PASSED
  faqat o'sha fayl:   PASSED (3/3 urinish)
  to'liq to'plam #2:  PASSED
```

Test 60 kunlik saqlash muddati qo'yib, **20 kunlik** klip qolishini
tekshiradi. Yiqilganda `has_clip` **0** bo'lgan — ya'ni klip
muddatidan ancha oldin o'chirilgan.

**Nega jiddiy:** Agar bu faqat testlar orasidagi ifloslanish bo'lsa —
kichik muammo. Agar `_purge_expired_events()`
(`cloud/main.py:1356`) `_clip_retention_days()` ni ba'zi holatda
noto'g'ri o'qisa — bu **mijozning hodisa klipini muddatidan oldin
o'chirish** demakdir. Klip esa xavfsizlik hodisasining yagona dalili.

Bu KRITIK-3 (oferta) bilan bog'lanadi: mijoz "menda 60 kunlik arxiv
bor edi" desa, biz nima va'da qilganimizni ko'rsatadigan hujjat ham
yo'q.

**Nima TEKSHIRILDI va inkor qilindi** (keyingi kishi qaytarmasin):

| Gumon | Natija |
|---|---|
| Klip saqlash SQL'i noto'g'ri | ❌ **To'g'ri.** `event_store.py:3374` — `occurred_at < now − 60 kun`; 20 kunlik klip omon qolishi shart |
| `_clip_retention_days()` keshlangan | ❌ Yo'q, `main.py:1287` env'ni har chaqiruvda o'qiydi |
| Media kvotasi klipni o'chiryapti | ❌ Standart kvota **10 GB** (`main.py:1272`), klip esa 1 KB |
| Kvotani boshqa test kichraytirib qoldirgan | ❌ `test_cloud_events_owner.py:130` to'g'ri `monkeypatch` ishlatadi |
| Tasodifiy test tartibi plagini | ❌ O'rnatilmagan (faqat `pytest-asyncio`) |
| Vaqt funksiyasi (`_now`) almashtirilib qolgan | ❌ Testlarda hech kim uni patch qilmaydi |
| Oldingi fayllar ifloslantiryapti | ❌ Birinchi 15 fayl birga ishlatilganda **o'tadi** |

**Ya'ni mahsulot mantiqi to'g'ri** — bu production'da klip erta
o'chishini ko'rsatmaydi. Qolgan yagona tushuntirish: to'liq to'plamda
paydo bo'ladigan, hali aniqlanmagan holat sizishi. Yiqilish chastotasi
~50%.

**Keyingi qadam:** yiqilgan lahzada `_purge_expired_events()` ichida
qaysi purge kalitni qaytarganini loglash (uchta nomzod:
`purge_site`, `purge_clips_older_than`, `purge_site_media_over_quota`)
va `CHAQIMCHI_SITE_MEDIA_MAX_BYTES` qiymatini o'sha yerda chop etish.
Bir marta ushlansa sabab darhol ko'rinadi.

**Egasi:** Backend · **Hajmi:** S–M · **Ustuvorlik:** C bosqichidan
oldin — 72 soatlik soakda "hodisa klipi cloudga yetib borishi" mezon
sifatida tekshiriladi va yashirin flake o'sha natijani buzadi.

---

### O'RTA-0 · ❌ NOTO'G'RI TOPILMA — bekor qilindi (2026-08-25)

**Audit xato qilgan.** Tuzatishga kirishganda ma'lum bo'ldiki
`config/sotqin.yaml` da **ikkala** qiymat bor va ular kodga aynan mos:

```yaml
guaranteed_cameras: 4    # sotiladigan SLA
max_cameras: 8           # apparat imkoniyati
```
`chaqimchi_ai/sotqin_profile.py:19-20` — `GUARANTEED_CAMERAS =
SHOP_MAX_CAMERAS` (4) va `MAX_CAMERAS = 8`. Validatsiya
(`sotqin_agent.py:272`) apparat shiftiga qaraydi, va bu to'g'ri:
u konfig qurilmani ko'tarolmaydigan yukka sozlab qo'yishini
to'xtatadi, sotuv va'dasini emas.

Ya'ni 4 va 8 bir-biriga zid emas — ular boshqa savolga javob beradi.
**Hech narsa o'zgartirilmadi.**

Bu yozuv ataylab o'chirilmadi: audit ham xato qilishi mumkinligi va
qaysi joyda qilgani ko'rinib tursin.

---

### O'RTA-6 · ❌ NOTO'G'RI TOPILMA — bekor qilindi (2026-08-25)

**Audit yana xato qilgan.** Tuzatishga kirishganda ma'lum bo'ldiki
chidamli tormoz **allaqachon bor**:

- `cloud/store.py:2648` — `alert_throttle_allow()`, `alert_state`
  jadvalida saqlanadi;
- `cloud/main.py:1095` — `_DurableAlertThrottle` uni o'raydi;
- `cloud/main.py:4725` — production yo'li aynan shuni uzatadi
  (`select_alert_events(..., throttle_service=_durable_throttle)`);
- `tests/test_cloud_events_owner.py:726` —
  `test_alert_throttle_survives_a_restart` buni allaqachon isbotlaydi.

`cloud/notify.py` dagi xotiradagi `AlertThrottle` — faqat **standart
qiymat** (test va mustaqil ishlatish uchun). Audit uni o'qib,
production nima uzatishini tekshirmagan.

**Saboq:** "modul ichida shunday yozilgan" — bu "production shunday
ishlaydi" degani emas. Chaqiruv joyini ham ko'rish kerak.

**Hech narsa o'zgartirilmadi.**

---

### O'RTA-1 · `/health` haqiqatni ko'rsatmaydi

`https://chaqimchi.uz/health` → `{"ok":true,"service":"chaqimchi-cloud"}`

Bu faqat "web-server javob beryapti" degani. Baza, MinIO, Telegram,
Gemini va navbat tekshirilmaydi. `/status` sahifasi
(`cloud/static/status.html:12`) aynan shuni o'qiydi va **baza o'lgan
holatda ham "Cloud ishlayapti"** deb yozadi.

**Tuzatish:** `/health` ichiga DB `SELECT 1`, MinIO ping, outbox navbat
uzunligi va oxirgi heartbeat vaqti qo'shilsin; `/status` komponent
bo'yicha ko'rsatsin. **Egasi:** Backend/DevOps · **Hajmi:** M

---

### O'RTA-2 · CSP sarlavhasi yo'q

Jonli javobda: HSTS ✓, `X-Frame-Options: DENY` ✓, `nosniff` ✓,
`Referrer-Policy` ✓, `Permissions-Policy` ✓ — lekin
**`Content-Security-Policy` yo'q** (`deploy/Caddyfile.chaqimchi:11-24`).

Panel (`app.`) XSS bo'lsa himoya qatlami yetishmaydi.
**Tuzatish:** Avval `Content-Security-Policy-Report-Only` bilan
boshlash, keyin majburlash. **Egasi:** DevOps · **Hajmi:** M

---

### O'RTA-3 · Faqat o'zbek tili — rus tili yo'q

23 ta HTML'ning hammasi `lang="uz"`. Rus tili, `hreflang`, til
almashtirish tugmasi — yo'q.

Toshkent va yirik shaharlardagi do'kon egalari va NVR ustalarining katta
qismi rus tilida ishlaydi. Bu sotuv hajmiga bevosita ta'sir qiladi.
**Tuzatish:** Kamida landing + narx + o'rnatish sahifasi rus tilida.
**Egasi:** Product/Sales · **Hajmi:** L

---

### O'RTA-4 · Hech qanday analitika yo'q — konversiyani o'lchay olmaymiz

Google Analytics, Yandex Metrika, Plausible — hech biri yo'q.
Ariza qoldirgan har bir odam ko'rinadi, lekin **necha kishi sahifani
ochib, ariza qoldirmagani** noma'lum.

Sotuvni yo'lga qo'yayotgan mahsulot uchun bu ko'r-ko'rona harakat.
**Tuzatish:** Maxfiylikka mos yengil analitika (Plausible / o'z-o'zini
hostlaydigan Umami) + `/maxfiylik` ga bir qator.
**Egasi:** Product · **Hajmi:** S

---

### O'RTA-5 · Narx dollarga bog'langan — kurs oshsa mijoz to'lovi jimgina oshadi

`plans.py:49-50` narxni **sentda** saqlaydi (1140¢ va 2300¢),
`plans.py:66-93` uni `CHAQIMCHI_USD_RATE_UZS` (default 13 000) bilan
so'mga o'giradi. Hozir mos: 149 000 va 299 000 so'm.

Lekin sayt yozadi: *"Yashirin qo'shimcha to'lovlar yo'q"* (`site.html:366`).
Kurs 14 000 ga chiqsa, narx avtomatik 160 000 va 322 000 bo'ladi.
Do'kon egasi buni "yashirin qo'shimcha to'lov" deb qabul qiladi.

**Tuzatish:** Yoki so'mda qat'iy narx (kurs riskini o'zimiz ko'taramiz),
yoki saytda halol yozish: "Narx dollarga bog'langan, kurs o'zgarsa
o'zgaradi". Birinchisi sotuvga yaxshiroq.
**Egasi:** Product/Sales · **Hajmi:** S

---

## 2-QISM: TO'G'RI ISHLANGAN NARSALAR (buzib qo'ymaslik uchun)

Audit davomida tasdiqlangan kuchli tomonlar — bularni saqlash kerak:

- **Yolg'on va'dalar testda qulflangan.** `tests/test_static_pages.py:65-72`
  `FORBIDDEN_CLAIMS` — "o'g'rini aniqlaydi", "100% aniqlik", "har qanday
  kamera" saytga tushishi mumkin emas. Kam jamoada bu juda kuchli qaror.
- **Huquqiy sahifalar sifatli.** `/rozilik-shabloni` (xodim biometrik
  roziligi) va `/kuzatuv-eslatmasi` (eshikka osiladigan) — tayyor, chop
  etiladigan, tushunarli hujjatlar. Ko'p raqobatchida bu yo'q.
- **Maxfiylik sahifasi aniq chegara qo'yadi:** demografiyada yuz rasmi
  saqlanmaydi, embedding olinmaydi, ikkinchi tashrif birinchisi bilan
  bog'lanmaydi (`privacy.html:13`).
- **Edu sahifasi funksiya statusini halol yozadi** — "hozir ishlaydi" /
  "pilot" / "rejada" (matn qismida; kalkulyator esa buni buzadi — KRITIK-1).
- **Formalarda 3 qatlam spam himoyasi:** honeypot (`site.html:428-431`),
  IP bo'yicha soatiga 5 ta cheklov (`main.py:2503-2509`), majburiy rozilik.
  IP saqlanmaydi — faqat SHA-256 xeshi (`main.py:2517-2518`).
- **Narx bitta manbadan:** sayt, panel va hisob-faktura `plans.py` dagi
  bitta funksiyani chaqiradi — ikki joyda ikki xil narx chiqmaydi.
- **Vision Agent yuz kadrlarini Google'ga yubormaydi**
  (`vision_agent.py:262-268`) va prompt'da "yuz, yosh, jins taxmin
  qilmang" cheklovi bor (`vision_agent.py:44-50`).
- **Xavfsizlik sarlavhalari** (CSP'dan boshqa hammasi) va rasm/kesh
  optimizatsiyasi testda majburlangan.
- **Obuna tugaganda kamera sog'ligi hodisalari to'xtamaydi**
  (`main.py:5335-5340`) — do'kon "kamerangiz o'chdi" xabarini yo'qotmaydi.

**Xavfsizlik tomonida kuchli qarorlar** (KRITIK-4 dan boshqasi):

- **Do'konlar bir-birini ko'rmaydi.** `site_id` **hech qachon** so'rov
  tanasidan olinmaydi — doim sessiyadan (`cloud/main.py:676-709`).
  `X-Owner-Site-Id` header qabul qilinadi, lekin darhol a'zolik bilan
  tekshiriladi. Aniq IDOR topilmadi.
- **Parollar scrypt bilan** (N=2^14, 16 baytli salt) —
  `cloud/portal_auth.py:28-30, 58-86`. Parol o'zgarsa `auth_version` +1
  bo'lib **barcha eski tokenlar darhol o'ladi** (`cloud/store.py:1722`).
- **NVR parollari hech qachon ochiq yotmaydi.** Ustun nomi
  `rtsp_ciphertext` (`cloud/store.py:360`), Fernet bilan shifrlangan,
  panelga chiqishda `pop` qilinadi (`cloud/store.py:622`). Brauzer xom
  RTSP yubora olmaydi — faqat indeks (`cloud/main.py:6581-6614, 6682-6686`).
- **SQL injection yo'q** — foydalanuvchi kiritmasi hamma joyda `?`
  parametr orqali.
- **JWT'dagi rolga ishonilmaydi** — rol har so'rovda DB'dan qayta
  o'qiladi (`cloud/main.py:694-709`).
- **OTP kodi bazada saqlanmaydi** — faqat HMAC-SHA256
  (`cloud/event_store.py:3097-3099`), 5 daqiqa, 5 urinish.
- **To'lov summasi doim serverda hisoblanadi** — mijozdan faqat oy soni
  olinadi (`cloud/payments/store.py:108-123`). Payme Basic auth va Click
  imzosi `compare_digest` bilan tekshiriladi.
- **Cookie umuman ishlatilmaydi** → CSRF amalda imkonsiz.
- **Production preflight** xavfli sozlamalar bilan serverni ataylab
  yoqmaydi (`cloud/main.py:1444-1490`) — `CHAQIMCHI_OTP_BYPASS_IDS` va
  `CHAQIMCHI_OTP_TEST_CODE` qolib ketsa deploy to'xtaydi.
- **Backup infratuzilmasi tayyor:** kunlik shifrlangan zaxira, systemd
  timer, muvaffaqiyatsizlikda Telegram xabari
  (`scripts/backup_production.sh`, `deploy/chaqimchi-backup*.service`).
- **Kodda birorta hardcode qilingan sir topilmadi**; `.env` git'da yo'q.
- **OTA imzosi jiddiy:** Ed25519 + sha256, imzodan o'tmagan fayl
  o'chiriladi, rollback nishoni **qayta imzo tekshiruvidan o'tadi**,
  buzuq versiya `blocked_version` bo'lib qoladi
  (`chaqimchi_ai/local/updater.py:170-178, 200-240, 306-343`).
- **Yolg'on ogohlantirishga qarshi ishlangan:** loitering Telegramga
  umuman bormaydi va media qabul qilinmaydi
  (`cloud/main.py:1149`), Telegramga faqat `critical` o'tadi
  (`cloud/notify.py:38`), 600 soniyalik throttle va bitta batch → bitta
  xabar (`cloud/notify.py:100-190`).

---

## 3-QISM: KEYINGI REJA

### 0-qadam — shu hujjatni loyihaga saqlash · ✅ BAJARILDI (2026-08-25)

Audit `docs/AUDIT_TAHLIL.md` fayliga yozildi.

**Holat (2026-08-25):** A0–A8 va B1, B3, B5, B6, B7 bajarildi.

Yopilgan topilmalar: **K-1, K-2, K-4** (kritiklardan uchtasi),
**Y-0, Y-1, Y-3, Y-4, Y-5, Y-7, Y-9, Y-12**.
Bekor qilinganlar (audit xatosi): **O-0, O-6**.
**K-3** yozildi, lekin yurist ko'rigi va rekvizit kutilmoqda.

Qolgan yagona A ishi — **A9**: serverda
`grep CHAQIMCHI_JWT_SECRET .env.production`. Buni faqat server
egasi bajara oladi (10 daqiqa).

**DEPLOY QILINDI (2026-08-26).** Cloud 0.6.15 jonli, hamma konteyner
healthy. Jonli tekshiruv o'tdi: `/oferta` 200, hudud va'dasi yo'q,
Edu'da faqat ikkita modul sotiladi, `/health/deep` begonaga raqam
bermaydi, o'rnatish vaqti bir xil.

**Qolgan yagona deploy ishi — B4:** mijoz hamon 0.6.13 yuklab oladi
(cloud esa 0.6.15). Build va imzo kaliti kerak.

Ochiq qolgan yagona kritik — **K-3 (ommaviy oferta)**, u B1 da.

---

### A bosqichi — 3 kun: sotuvni to'xtatadigan yolg'onlarni o'chirish

Bu ishlar tugamaguncha Edu yo'nalishi bo'yicha **hech kimga taklif
yuborilmasin**.

| # | Ish | Fayl | Kim | Vaqt |
|---|---|---|---|---|
| ~~A1~~ | ✅ **BAJARILDI** — `fight`, `monitoring`, `deep` `PLANNED_MODULES` ga ko'chdi | `chaqimchi_ai/licensing/edu.py` | Backend | — |
| ~~A2~~ | ✅ **BAJARILDI** — `LOAD_WEIGHTS` faqat `faceid`, qurilma tavsiyasi qayta hisoblandi | `edu.py` | Backend | — |
| ~~A3~~ | ✅ **BAJARILDI** — hudud va'dasi o'chirildi, 4 ta ibora `FORBIDDEN_CLAIMS` da qulflandi | `cloud/static/edu.html`, `tests/test_static_pages.py` | Frontend | — |
| ~~A4~~ | ✅ **BAJARILDI** — ikkita yangi bo'lim: «Ma'lumot qayerda saqlanadi» va «Uchinchi tomon xizmatlari» | `cloud/static/privacy.html` | Product | — |
| ~~A5~~ | ✅ **BAJARILDI** — hero va faktlar bloki tarifga mos qilindi | `cloud/static/site.html` | Frontend | — |
| ~~A6~~ | ✅ **BAJARILDI** — fayl nomi relizdan olinadi, eski noto'g'ri nom hamma sahifadan ketdi | `cloud/static/install.html`, `installer-guide.html` | Frontend | — |
| ~~A7~~ | ✅ **BAJARILDI** — ikkita halol raqam: mijoz 30 daqiqagacha, usta 45–90 daqiqa | 5 ta sahifa | Product | — |
| ~~**A0**~~ | ✅ **BAJARILDI** — biometrik marshrutlarga rol tekshiruvi (KRITIK-4) | `cloud/main.py:842` + 7 ta marshrut | Security | — |
| ~~A8~~ | ✅ **BAJARILDI va DEPLOY QILINDI** — raqamlar admin kaliti ostida, monitoring uchun 503 ochiq qoldi | `cloud/main.py` | DevOps | — |
| ~~A9~~ | ✅ **TEKSHIRILDI** — `CHAQIMCHI_JWT_SECRET` serverda qo'yilmagan, kalit ajratilishi buzilmagan | server | DevOps | — |

**A0 birinchi bajarilsin** — u eng arzon (30 daqiqa) va eng qimmat
xatoni yopadi: biometrik ma'lumot xodimga berilgan yozma va'da
doirasidan chiqib ketmaydi.

**Yangi testlar (A bilan birga):**
- `tests/test_edu_pricing.py`: har bir sotiladigan modul uchun kodda
  ishlaydigan detektor bo'lishi shart.
- `tests/test_static_pages.py`: `FORBIDDEN_CLAIMS` ga qo'shish —
  "xorijdagi serverga yuborilmaydi", "O'zbekiston hududidagi
  infratuzilma". Bu doimiy qulf: hosting Fransiyada turar ekan, bu
  va'da saytga qaytib kela olmaydi.
- O'rnatish vaqti raqami barcha sahifada bir xil ekanini tekshiruvchi test.

**Tugallanish mezoni:** `make test` yashil; `GET /api/v1/public/edu-pricing`
javobidagi har bir modul kod bilan asoslangan.

---

### B bosqichi — 7 kun: yuridik va reliz

| # | Ish | Kim | Vaqt |
|---|---|---|---|
| ~~B1~~ | 🟡 **YOZILDI** — `/oferta` jonli, footer va sitemapda; STIR/rekvizit bo'sh, yurist ko'rigi kutilmoqda | Product + yurist | B2 da |
| B2 | Yurist ko'rigi: oferta, `/maxfiylik`, `/rozilik-shabloni` **+ bitta aniq savol** (pastda) | Yurist | 2 kun |
| ~~B3~~ | ✅ **BAJARILDI** — `_attendance_enabled()` da `or` → `and`; Biznes kartasidan bullet olindi | Product + Backend | — |
| ~~B4~~ | ✅ **BAJARILDI** — 0.6.16 qurildi, imzolandi, nashr qilindi; env pini olib tashlandi | DevOps | — |
| ~~B5~~ | ✅ **BAJARILDI** — izoh yangilandi: sabab litsenziya emas, hosting hududi va o'lchanmagan aniqlik | Backend | — |
| ~~B6~~ | ✅ **BAJARILDI** — 7 turdagi amal yoziladi, master kalit endi anonim emas | Backend | — |
| ~~B7~~ | ✅ **BAJARILDI** — o'rnatuvchida `w32time`, heartbeat'da soat farqi, egaga tushunarli ogohlantirish | Backend + Installer | — |
| ~~B8~~ | ❌ **BEKOR** — O'RTA-6 noto'g'ri topilma, chidamli tormoz allaqachon bor | — | — |
| ~~B9~~ | ❌ **BEKOR** — O'RTA-0 noto'g'ri topilma bo'lib chiqdi, o'zgartirish kerak emas | — | — |

**B2 uchun yuristga beriladigan aniq savol** (umumiy "tekshirib bering"
emas — shu savol yozma javob bilan qaytsin):

> Yopiq pilotda, har bir xodimdan yozma rozilik olingan holda, yuz
> embeddingi (256 o'lchamli, shifrlangan) va yuz kadri (14 kun) **Yevropa
> Ittifoqi hududidagi serverda** saqlanishi O'zbekiston "Shaxsga doir
> ma'lumotlar to'g'risida" qonuniga mos keladimi? Agar yo'q bo'lsa —
> pilotni davom ettirish uchun minimal shart nima?

Javob "mos emas" bo'lsa, o'shanda va faqat o'shanda hosting masalasi
qayta ochiladi. Hozir bu reja ichida yo'q.

**Tugallanish mezoni:** `/oferta` 200 qaytaradi; mijoz yuklaydigan fayl
versiyasi = deploy qilingan cloud versiyasi; yuristdan yozma javob
olingan.

---

### C bosqichi — 14 kun: haqiqiy do'konda qabul sinovi

Bu **eng muhim** bosqich va uni hech narsa almashtira olmaydi.
`docs/DOKON_MVP.md:106-137` allaqachon mezonni belgilagan:

1. `scripts/benchmark_n100.py --device CPU --source rtsp://... --cameras 4`
   — real i5-4590 da sig'imni o'lchash.
   (`hardware.py` dagi `INFERENCES_PER_CORE=8.0` hozir **taxmin**.)
2. `scripts/soak_windows.py --hours 72 --cameras 4` — 72 soat uzluksiz:
   kutilmagan restart 0, yo'qolgan critical event 0, kamera uptime ≥ 99%.
3. Qo'lda sanash bilan solishtirish — kunlik kirish soni ±10% ichida.
4. `scripts/accept_n100_pilot.py` → `acceptance-windows.json` →
   `CHAQIMCHI_N100_ACCEPTANCE_FILE`.

**Nega bu shart:** `cloud/store.py:52-68` `available_feature_codes()`
production'da qabul fayli bo'lmasa bo'sh to'plam qaytaradi. Ya'ni bu
qadamsiz AI funksiyalari rasman ochilmaydi — sayt "AI funksiyalari hozir
birinchi do'konlarda sinovdan o'tmoqda" deb yozadi (`site.js:235-238`).

**Shu bosqichda o'lchanadigan raqamlar** (hozir hech biri o'lchanmagan —
YUQORI-6). Bu jadval to'ldirilmaguncha aniqlik haqida hech narsa
va'da qilinmasin:

| O'lchov | Qanday | Maqsad |
|---|---|---|
| Kirish sanog'i aniqligi | Qo'lda sanash bilan, kuniga 3 marta ×20 daqiqa | ±10% |
| Yolg'on ogohlantirish ulushi | Har alert turini qo'lda ko'rib chiqish | < 20% |
| Ogohlantirish kechikishi | Hodisadan Telegram xabarigacha | < 30 s |
| Kechasi vs kunduzi | Bir xil o'lchov, tungi soatlarda alohida | farq yozilsin |
| Gavjum payt (18:00–20:00) | Alohida | farq yozilsin |
| CPU / RAM / disk o'sishi | 4 kamerada, `soak_windows.py` | CPU < 80% |
| Soat farqi | Qurilma soati vs server soati | < 1 daqiqa |

**Tugallanish mezoni:** `acceptance-windows.json` mavjud va uchala maydon
odam tomonidan tasdiqlangan; yuqoridagi jadval raqam bilan to'ldirilgan.

---

### D bosqichi — 30 kun: sotuvni ochish

- D1 · Landing skrinshotlarini **real pilot ma'lumoti** bilan qayta olish
  (`scripts/make_panel_screenshots.py`). Hozir "raqamlar namunaviy".
- D2 · `/health` ni chuqurlashtirish + `/status` komponent bo'yicha
  (O'RTA-1).
- D3 · CSP `Report-Only` → majburiy (O'RTA-2).
- D4 · Yengil analitika + konversiya o'lchovi (O'RTA-4).
- D5 · Narx valyutasi bo'yicha qaror (O'RTA-5).
- D6 · Rus tili: landing + narx + o'rnatish (O'RTA-3).
- D7 · Har bir AI funksiya uchun **o'lchangan chegara jadvali**: nimani
  ishonchli aniqlaydi, nimani yo'q. Bu jadval saytga chiqsin — raqobatchi
  buni qila olmaydi, mijoz esa ishonadi.
- D8 · Owner tokeni uchun `auth_version` naqshi (O'RTA-8) — portal
  tomonda allaqachon bor, owner tomonga ko'chirilsin.
- D9 · Rate limit DB'ga + `auth/verify` ga IP cheklovi (O'RTA-9).
- D10 · Haqiqiy video bilan ishlaydigan sinov to'plami (YUQORI-8).

### 90 kun — yetuklik

- `CloudStore` va `PaymentStore` ni Postgres'ga ko'chirish (YUQORI-10) —
  gorizontal masshtablash shusiz imkonsiz.
- `main.py` ni bo'lish (8398 qator), zone-editor'ning uch nusxasini
  birlashtirish, `package.json` dagi `latest` pinlari.

---

## 4-QISM: HUKM

**Ready for controlled pilot** — nazorat ostidagi pilotga tayyor.
**Paid launch uchun tayyor emas.**

**Nega pilotga tayyor:** Do'kon yo'nalishida kod real: 16 ta hodisa turi,
offline outbox, imzolangan OTA, tarif→funksiya bog'lanishi, shifrlangan
RTSP inventari, huquqiy hujjatlar. Testlar yolg'on va'dani saytga
qo'ymaydi. Bu bir kishilik jamoa uchun kuchli natija.

**Nega pullik sotuvga tayyor emas — to'rtta dalil:**
1. Edu kalkulyatori kodda **umuman mavjud bo'lmagan** uchta AI modulini
   oyiga 199 000 / 129 000 / 249 000 so'mga sotmoqda (KRITIK-1).
2. Sayt biometrikani "O'zbekistonda" deb yozadi, server esa Fransiyada —
   `whois` va `ipinfo` bilan tasdiqlangan (KRITIK-2). Yechim: va'dani
   o'chirish (2 soat), hosting o'zgarmaydi.
3. Ommaviy oferta yo'q, lekin hisob-faktura beriladi (KRITIK-3).
4. Biometrik rasmlar `manager` roliga ochiq — bir marshrutda himoyalangan,
   ikkitasida esa yo'q (KRITIK-4).

Birinchi uchtasi **kod muammosi emas** — va'da bilan haqiqat orasidagi
farq, va shuning uchun A bosqichi 3 kunda tugaydi. To'rtinchisi haqiqiy
kod xatosi, lekin uni tuzatish 30 daqiqa oladi.

**Eng katta o'lchanmagan noma'lum:** 72 soatlik soak va aniqlik
kalibratsiyasi hali o'tkazilmagan. Sotilayotgan AI aniqligi uchun yagona
raqam — Intel'ning model kartochkasidagi "AP 88.62%"
(`detector_ov.py:11`), sizning kadrlaringizda emas. Ya'ni "4 kamera 24/7
ishlaydi va odamlarni to'g'ri sanaydi" degan asosiy va'dani hozir hech
kim tasdiqlay olmaydi — jamoa buni `DOKON_MVP.md:40-51` va
`retail/README.md:305-319` da o'zi ham tan olgan.

**Muhimi:** Bu hukm mahsulot yomon degani emas. Kod sifati bir kishilik
jamoa uchun kutilganidan ancha yuqori — tenant izolyatsiyasi, imzolangan
OTA, shifrlangan NVR parollari, offline outbox va yolg'on va'dani
bloklaydigan testlar buni ko'rsatadi. Muammo — **sayt kodadan oldinga
ketib qolgan**. A va B bosqichlari aynan shu masofani yopadi.

---

## Tekshirish usuli (bu reja bajarilgach)

```bash
# 1. Barcha testlar
make lint && make test

# 2. Edu kalkulyatori — har bir modul kodda bormi
curl -sS https://chaqimchi.uz/api/v1/public/edu-pricing | python3 -m json.tool

# 3. Hudud va'dasi saytdan butunlay ketganmi (bo'sh natija kutiladi)
curl -sS https://chaqimchi.uz/edu | grep -i "xorijdagi\|hududidagi infratuzilma"

# 4. Yuridik sahifalar javob beradimi
for p in oferta maxfiylik rozilik-shabloni kuzatuv-eslatmasi; do
  curl -sS -o /dev/null -w "%{http_code} /$p\n" https://chaqimchi.uz/$p
done

# 5. Mijozga beriladigan versiya = deploy qilingan versiya
curl -sS -o /dev/null -D - https://chaqimchi.uz/api/v1/public/download-installer | grep -i location

# 6. Sog'liq tekshiruvi chuqurmi
curl -sS https://chaqimchi.uz/health | python3 -m json.tool

# 7. /health/deep endi yopiqmi (401/403 kutiladi)
curl -sS -o /dev/null -w "%{http_code}\n" https://chaqimchi.uz/health/deep

# 8. Biometrik marshrutlar: manager tokeni bilan uchalasi ham 403 bo'lsin
#    (test bilan qulflansin, qo'lda emas)
pytest tests/ -k "face and role"
```

**Qo'lda tekshiriladigan narsalar** (buyruq bilan bo'lmaydi):

- Edu sahifasini ochib, kalkulyatorda tanlanadigan har bir modul uchun
  "buni bugun yetkazib bera olamizmi?" savoliga **ha** deb javob bering.
- `/oferta` matnini yurist o'qib chiqqanini tasdiqlang.
- Yangi Windows kompyuterda o'rnatuvchini boshidan oxirigacha o'tkazing
  va **soatga qarab** vaqtni yozing — saytdagi raqam shundan chiqsin.

---

## Eslatma

Bu audit **faqat o'qish** rejimida bajarildi: birorta fayl
o'zgartirilmadi, production'ga hech narsa yuborilmadi, hujum sinovi
qilinmadi. Yuqoridagi barcha jonli tekshiruvlar — oddiy `GET`
so'rovlari va ochiq `whois`/`dig` ma'lumotlari.

Tekshirilmagan va shu sababli **noma'lum** bo'lib qolgan narsalar:
- Serverdagi `.env.production` mazmuni (o'qishga ruxsat yo'q edi) —
  shuning uchun O'RTA-7 "tasdiqlanmagan" holatida qoldi.
- Owner va admin panelining ichki oqimlari (login talab qiladi).
- Haqiqiy kamera bilan video zanjirining ishlashi.
- Telegram bot oqimi va to'lov provayderlari bilan real integratsiya.
