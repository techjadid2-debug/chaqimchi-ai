# Ish daftari

> Har agent ishni **shu fayldan** boshlaydi va **shu faylga** yozib
> tugatadi. Maqsad: keyingi sessiya nolla emas, shu yerdan boshlasin.
>
> Qayerda nima turishi — [ARXITEKTURA_XARITASI.md](ARXITEKTURA_XARITASI.md).

---

## HOZIRGI HOLAT · 2026-08-26

- **Cloud 0.6.17 jonli** (deploy 2026-08-26, hamma konteyner healthy).
  Sinov do'konidagi "rasm kelmayapti" nosozligining oltita sababi
  tuzatildi — tafsilot pastdagi tarixning birinchi yozuvida.
- **Windows 0.6.17 nashr qilindi va imzosi tekshirildi**
  (`dl.chaqimchi.uz`). Sinov do'koni `auto` rejimida — 15 daqiqada oladi.
- **O'lchangan natija:** snapshot 429 lari **2 618 ta/10 daqiqa → 0**;
  deploydan keyingi 2 daqiqada 86 ta rasm muvaffaqiyatli saqlandi.
- Shox: `loitering-rasmsiz`, `origin` bilan sinxron. Asosiy shox `main`.
- Audit ([AUDIT_TAHLIL.md](AUDIT_TAHLIL.md)) bo'yicha **A bosqichi
  (A0–A9) va B bosqichining katta qismi tugadi**. C boshlanmagan.
- Server: `169.58.198.111` (Contabo, Fransiya), kod
  `/home/deploy/chaqimchi-ai`, compose `docker-compose.chaqimchi.yml`.
  SSH kaliti `.deploy_keys/chaqimchi_prod`.
- **Sotuv hali ochilmagan** — pastdagi ikkita darvoza yopiq.

## KEYINGI ISH

**0.6.17 qurilmaga yetganini tasdiqlash.** Cloud va reliz chiqdi;
qurilma `auto` bo'lgani uchun o'zi oladi. Tekshirish:

```
docker compose -f docker-compose.chaqimchi.yml exec -T cloud \
  python scripts/rollout.py --holat      # 0.6.16 → 0.6.17 bo'lsin
```

Yetgach ikkita narsa o'zi hal bo'ladi: yuz kadri oqimi soatiga 40 ga
tushadi (`FACE_EMITS_PER_HOUR`) va davomat bitta kameraga qoladi
(sozlama allaqachon revision 7 da, lekin S6 tufayli u faqat yangi
versiyada kuchga kiradi).

Ko'z bilan: owner panelni toza brauzerda oching — kamera kartochkasida
"Kadr so'raldi…" chiqib, 20 soniyada rasm ko'rinsin; hodisalar soati
Toshkent vaqtida bo'lsin.

Undan keyin — **C1, haqiqiy do'konda qabul sinovi.** Ikki qismdan iborat:

1. Sig'imni o'lchash — `scripts/benchmark_n100.py`, haqiqiy RTSP manzil
   bilan (`--source` bermasangiz o'lchov yolg'on bo'ladi, skript o'zi
   ogohlantiradi).
2. 72 soatlik soak — `scripts/soak_windows.py`, natija qabul fayliga
   yoziladi va `CHAQIMCHI_N100_ACCEPTANCE_FILE` shunga ko'rsatiladi.

**Nega aynan shu birinchi:** bu tugamaguncha
`available_feature_codes()` production'da bo'sh ro'yxat qaytaradi
(`cloud/store.py:52`) — ya'ni edge AI funksiyalari rasman sotuvga
ochilmaydi. Mezonlar: [AUDIT_TAHLIL.md](AUDIT_TAHLIL.md) §3, C bosqichi.
Qabul tartibi: [DOKON_MVP.md](DOKON_MVP.md) "Qabul mezoni".

## OCHIQ MUAMMOLAR

**Sotuvni to'sib turgan ikki darvoza**

- `available_feature_codes()` → `[]`, chunki qabul fayli yo'q (yuqoriga
  qarang). `cloud/store.py:52`.
- **Oferta tayyor emas:** STIR va rekvizit bo'sh (ro'yxatdan o'tilmagan)
  + yurist ko'rigi (B2) o'tmagan. Sotuvni ochishdan oldin ikkalasi
  SHART. Yuristga beriladigan aniq savol
  [AUDIT_TAHLIL.md](AUDIT_TAHLIL.md) B bosqichida.

**Texnik**

- **Beqaror test:**
  `tests/test_cloud_load.py::test_clip_retention_is_configurable` —
  to'liq to'plamda ~50% yiqiladi, yolg'iz o'tadi. Klip saqlash mantiqi
  tekshirildi va **to'g'ri**; sabab hali topilmagan. Inkor qilingan
  gumonlar ro'yxati: [AUDIT_TAHLIL.md](AUDIT_TAHLIL.md) YUQORI-11.
  Yiqilsa — o'zingizdan deb o'ylamang, avval yolg'iz ishlatib ko'ring.
- **`cloud/store.py` faqat SQLite** — litsenziya, to'lov va portal
  parollari production'da ham SQLite'da (audit YUQORI-10). Shu sabab
  `Dockerfile.cloud` da `--workers 1`. Yechim rejasi:
  [ARXITEKTURA_XARITASI.md](ARXITEKTURA_XARITASI.md) "Kengayishga
  tayyorlik" §2.
- **Rate limit xotirada** (`cloud/ratelimit.py`) — restart bilan
  aylanib o'tiladi (audit O'RTA-9). Bitta VPS uchun yetadi, ikkinchi
  instansiya qo'shilsa yaramaydi.
- **CSP sarlavhasi yo'q** (audit O'RTA-2).
- **Token `localStorage` da**, server tomonda "chiqish" yo'q (O'RTA-8).
- **AI aniqligi hech qachon o'lchanmagan** (YUQORI-6) — C bosqichida.
- **Video va AI yo'lida haqiqiy sinov yo'q** (YUQORI-8) — testlar
  kamerasiz ishlaydi, bu ataylab, lekin uchidan-uchiga sinov ham kerak.
- **Faqat o'zbek tili** — rus tili yo'q (O'RTA-3).

## TUZOQLAR — bir marta yeb bo'lingan

- **`PYTHONPATH="$PWD"` reliz build'ida SHART.** Usiz
  `build_windows_payload.py` oxirgi qadamda yiqiladi.
- **`Caddyfile` o'zgarsa konteynerni QAYTA YARATISH kerak** — oddiy
  restart eski faylni saqlab qoladi. Tasdiqlashda **host** faylini emas,
  **konteyner ichidagi** faylni o'qing.
  [DEPLOY_TARIFLAR.md](DEPLOY_TARIFLAR.md) §3.
- **`admin.html` da yangi sahifa:** `NAV[].deps ⊆ LOADERS ⊆ S` zanjiri
  buzilmasin. Moliya paneli aynan shundan ochilmagan edi — `S` obyektida
  `finance` kaliti yo'q edi, `need()` esa faqat `=== null` ni yuklaydi,
  ya'ni so'rov **umuman yuborilmasdi**. Struktura testi endi bor.
- **`vision-worker` `frontend` tarmog'ida bo'lishi shart.** `backend`
  `internal: true` — faqat unda qolsa konteynerda gateway bo'lmaydi va
  HAR BIR Gemini chaqiruvi tarmoq xatosi bilan yiqiladi.
- **`releases/` bind mount compose'da qolsin.** `.dockerignore` da
  `releases/` bor va shunday qolishi kerak; qator olib tashlansa
  `/releases/*.tar.gz` va `/downloads/sotqin-installer.sh` 404 beradi.
- **Env pini kodni yengadi.** Mijoz nega eski versiya olayotgani
  build'da emas, serverdagi `.env.production` da qotirilgan URL'da edi.
  Muammo topilmasa — **serverdagi env'ni ham qarang**, faqat kodni emas.
- **Modul ichidagi kodni o'qish yetarli emas.** Audit ikki marta shu
  sababdan xato topilma yozdi (`notify.py` dagi standart qiymatni o'qib,
  production `store.py: alert_throttle_allow` ni uzatishini ko'rmadi).

## YOZUV SHABLONI

Tarix bo'limining **tepasiga** qo'shing:

```markdown
### YYYY-MM-DD — sarlavha (commit yoki "commit qilinmagan")
Nima: bir jumla, natija tilida ("egasi endi X ni ko'radi")
Nega: qanday muammo hal bo'ldi
Qayerda: fayl:qator, fayl:qator
Test: qaysi test buni qulflaydi
Diqqat: keyingi agent bilishi kerak bo'lgan narsa (bo'lsa)
```

3 oydan eski yozuvlar `docs/archive/` ga ko'chiriladi.

---

# Tarix

### 2026-08-26 — Rasm hech qayerda ko'rinmasdi: oltita sabab
Nima: sinov do'konida hodisa kelayotgan edi-yu rasm panelda ham,
Telegramda ham yo'q edi.  **Oltita** mustaqil sabab topildi va tuzatildi.
Nega: har biri alohida "kichik" edi, birga esa mahsulotning ko'zini
o'chirgan.

**Dalillar** (serverdagi log va baza):
3 soatda **6 315 ta** snapshot yuklash 429 oldi (200 OK — atigi 204 ta);
6 soatda **0 ta** `live-frame`; panel **33 ta GET → hammasi 404**, POST
umuman yo'q; 45 daqiqada **399 ta** `face_captured` (9 ta tashrifchidan);
`line_crossed` 26 ta — rasmli 0; **ERROR darajasidagi log 0 ta**.

**S1 · 429 o'lim halqasi** (asosiy).  `face_captured` toshqini kunlik
snapshot byudjetini (500) yedi, keyin HAR bir rasm 429 oldi, va
`cloud_sync.py` uni **hodisa xatosi** deb butun hodisani qayta
navbatga qo'ydi → cheksiz halqa.
Qayerda: `chaqimchi_ai/cloud_sync.py:_upload_media` (4xx endi hodisani
o'ldirmaydi, 5xx esa avvalgidek qayta urinadi);
`cloud/main.py:upload_event_snapshot` (yuz kadri endi FAQAT o'z
chegarasini sarflaydi, umumiy byudjetga tegmaydi);
`chaqimchi_ai/scene_analytics.py` (`FACE_EMITS_PER_HOUR = 40` — track
almashuvidan mustaqil shift; tuzatishsiz 200 track = 200 kadr edi).

**S2 · Panel kadrni hech qachon SO'RAMASDI.**  `CameraImage` faqat GET
qilardi; kadr so'raydigan POST endpoint bor edi, lekin v2 panel uni
chaqirmasdi — "Kadr hozircha kelmadi" boshi berk ko'cha edi.
Qayerda: `frontend/src/owner.tsx` (404 da bir marta POST, keyin uch
marta qayta o'qish; yozuv "Kadr so'raldi…").

**S3 · Telegramga faqat `critical` borardi** va bu hech qayerda
aytilmagan edi: 449 hodisadan 9 tasi ketdi.  Endi ega o'zi tanlaydi
(`telegram_min_severity`: faqat muhimi / +ogohlantirish / hammasi),
standart o'zgarmadi.
Qayerda: `cloud/notify.py`, `cloud/main.py:SiteConfigBody`,
owner "Sozlamalar".

**S4 · Owner panel vaqtni UTC ko'rsatardi** — `slice(11,16)` xom ISO
dan kesardi.  Skrinshotda sarlavha "14:47", hodisalar "09:47" edi.
Qayerda: `frontend/src/api.ts:formatTimeUz` (Toshkent qat'iy, `Intl`siz
— ba'zi WebView'da ICU yo'q), `OwnerHome.tsx`, `AdminHome.tsx`.

**S6 · Sozlama qurilmaga YETMASDI** (tuzatish paytida topildi).
Davomatni bitta kameraga tushirdim, admin panel "saqlandi" dedi
(revision 6 → 7), lekin camera-02 **12 daqiqadan keyin ham** yuz kadri
yuborardi.  Sabab: `cloud_config.apply()` davomat o'zgarishini `changed`
ga yozmasdi, ya'ni zanjir qayta ishga tushmasdi — u esa davomat
ro'yxatini faqat startda o'qiydi.  **Bu xato ikkinchi marta:** aynan shu
tuzoq ilgari "ish vaqti" bilan bo'lgan va kodda izohi ham bor edi.
Qayerda: `chaqimchi_ai/local/cloud_config.py:_attendance_signature`,
`chaqimchi_ai/local/app.py` (restart sharti + yangi sozlama qo'shganda
nima tekshirish kerakligi yozib qo'yildi).

**S5 · Bunday nosozlik hech kimga bildirilmasdi** — eng qimmat topilma.
Endi: rad etishlar sanaladi (`cloud/ratelimit.py:rejections`), admin
panel va `/health/deep` da ko'rinadi, platforma adminiga kuniga bir
marta Telegram xabar, egaga panelda halol yozuv.

Test: `test_cloud_sync.py` (429 → hodisa saqlanadi, 503 → qayta urinish),
`test_cloud_faces.py::test_face_flood_does_not_starve_store_event_snapshots`,
`test_scene_analytics.py` (track churn + shift oynasi + issiqlik xaritasi
to'xtamasligi), `test_notify.py` (uch daraja), `test_ratelimit.py`,
`test_cloud_api.py::test_rate_limited_site_notifies_the_platform_admin`,
`test_remote_config.py` (davomat o'zgarishi zanjirga yetadi, tartib
o'zgarishi esa bekorga restart bermaydi).
Jami **1782 test** o'tdi (avval 1755), lint va TS typecheck toza.

Diqqat: T2 va T8 **serverda darhol** ta'sir qiladi; T1, T3 va S6
tuzatishi esa qurilma 0.6.17 ni olmaguncha ishlamaydi — ya'ni reliz tarqalmaguncha
429 halqasi eski qurilmalarda davom etadi.
**Sinov do'koni sozlamasi allaqachon o'zgartirildi** (revision 7):
`attendance_camera_ids` ikkitadan bittaga tushdi — lekin S6 tufayli u
**qurilma 0.6.17 ni olgandan keyin** kuchga kiradi.

### 2026-08-26 — Agent uchun kirish hujjati (`0133865`)
Nima: yangi agent endi loyihani qaytadan o'rganmaydi — `CLAUDE.md` ni
o'qib qayerdan boshlashni biladi.
Nega: har sessiya boshida 8 720 qatorli `cloud/main.py` va 101 ta test
fayli qaytadan o'rganilardi; avvalgi sessiya nima qilgani esa faqat
commit xabarlarida qolardi.
Qayerda: `CLAUDE.md` (ildizda, Claude Code o'zi o'qiydi),
`docs/ISH_DAFTARI.md` (shu fayl), `docs/ARXITEKTURA_XARITASI.md`
(9 ta chizma + §10 kengayishga tayyorlik).
Test: kod tegilmadi — lint toza, 1755 test o'tdi.
Diqqat: §10 da yettita kengayish chegarasi tartiblangan. Eng birinchi
va eng arzoni — `main.py` ni `cloud/api/` ga bo'lish, lekin **avval**
`app.routes` ni qulflaydigan testni yozing: marshrutlar faylda aralash
yotibdi va bitta unutilgan dekorator jimgina 404 beradi.

### 2026-08-26 — Elektr mijozning xarajati, bizniki emas (`6ac4784`)
Nima: foyda hisobida elektr endi bizning tannarxdan chiqarildi.
Nega: Windows yo'lida dastur **mijozning o'z kompyuterida** ishlaydi —
tokni u to'laydi. `total_cost_uzs` = Gemini + infra (elektrsiz); elektr
alohida `energy_*` maydonlarida va `customer_total_uzs` (obuna + tok) da
qoladi, sotuv argumenti uchun.
Qayerda: `cloud/main.py` moliya endpointi, `cloud/static/admin.html`.
Test: `test_energy_does_not_shrink_our_profit` — elektri 70 barobar
farq qiladigan ikki do'konning foydasi bir xil chiqishi kerak.

### 2026-08-26 — Moliya paneli umuman ochilmasdi (`fd3ff8c`)
Nima: "Ma'lumot kelmadi" o'rniga sahifa ishlaydi; elektr, tannarx va
foyda qo'shildi.
Nega: `admin.html` dagi `S` obyektida `finance` kaliti yo'q edi.
Qayerda: `cloud/static/admin.html`.
Test: `test_finance_api.py` + struktura testi (`NAV[].deps ⊆ LOADERS ⊆ S`).
Diqqat: elektr `device_metrics` daqiqalik bucketlaridan **o'lchangan**
ish vaqti × qurilma vatti bo'yicha hisoblanadi. `uptime_sec` ataylab
ishlatilmadi — restartda nolga tushadi. "O'lchov yo'q" va "nol"
ajratilgan; `device_metrics` 30 kun saqlanadi. Env:
`CHAQIMCHI_COST_KWH_UZS=1000`, `CHAQIMCHI_COST_SERVER_MONTHLY_USD=8`
(ikkalasi serverda qo'yilgan), vatt — Windows 65, Box 12.

### 2026-08-26 — 0.6.16 va yuklab olish pinidan qutulish (`503f98a`, `925e63b`)
Nima: mijoz endi eng yangi imzolangan relizni oladi; kompyuter soati
nazorati mijozgacha yetdi.
Nega: `CHAQIMCHI_WINDOWS_INSTALLER_URL` serverda qotirilgan edi va
0.6.14/0.6.15 nashr qilingani holda mijozlar 0.6.13 olib turardi.
Qayerda: server `.env.production` (pin olib tashlandi),
`latest_windows_release()`, `cloud/static/install.html`.
Diqqat: **bu pinni qayta qo'ymang.** Yon natija — fayl nomi endi
`Chaqimchi_AI_Setup-<versiya>.exe` (redirect emas, to'g'ridan-to'g'ri
berish) va pairing kod nomda ishlaydi.

### 2026-08-26 — B6/B7: soat nazorati va audit jurnali (`13ae521`)
Nima: kompyuter soati noto'g'ri bo'lsa ega tushunarli Telegram xabar
oladi; audit jurnaliga 7 turdagi amal yozila boshladi (kirish havolasi,
hisob-faktura to'lovi, obuna, tarif, a'zo, biometrik rasm).
Nega: noto'g'ri soat tungi ogohlantirishlarni buzadi (YUQORI-7); audit
jurnali eng muhim amallarni yozmasdi (YUQORI-9).
Qayerda: o'rnatuvchida `w32time`, heartbeat'da `device_clock`.
Test: `test_device_clock.py`.
Diqqat: master kalit endi anonim emas — `actor_id="cloud-admin-key"`.

### 2026-08-25 — B bosqichi: oferta va davomat pilotga qaytdi (`5dae793`)
Nima: `/oferta` sahifasi yozildi (12 bo'lim, javobgarlik chegarasi,
14 kunlik pul qaytarish); yuz orqali davomat yopiq pilotga qaytarildi;
klip saqlash muddati to'g'rilandi (sayt 30 kun derdi, kod 7 kun).
Nega: pul olinardi-yu ommaviy oferta yo'q edi (KRITIK-3); sayt "yopiq
pilot" deydi-yu `_attendance_enabled()` production'da doim `True`
qaytarardi.
Qayerda: `cloud/static/oferta.html`, `cloud/main.py:834`
(`_attendance_enabled` — `or` → `and`).
Diqqat: SLA raqami oferta'da **ataylab yo'q**. STIR va rekvizit hali
bo'sh — yuqoridagi "Ochiq muammolar" ga qarang.

### 2026-08-25 — A0–A9: audit tuzatishlari (`615a5f2`, `d20bcf5`)
Nima: biometrik rasmlar yopildi; sotilmaydigan Edu modullari olib
tashlandi; bajarilmayotgan va'dalar saytdan o'chdi.
Nega: audit 22 topilma berdi, 4 tasi kritik.
Qayerda: `cloud/main.py:877` (`require_biometric_access` — yuzga
tegadigan **yettala** marshrut endi bitta nomdan o'tadi, ikkitasi
umuman tekshirmasdi); `chaqimchi_ai/licensing/edu.py` (`MODULES` endi
faqat `faceid` + `branch`, qolgani `PLANNED_MODULES` da narxsiz);
`/maxfiylik` ga ikkita yangi bo'lim; `/health/deep` javobi rolga qarab
qisqaradi.
Test: `tests/test_cloud_faces.py::test_a_manager_cannot_open_any_biometric_image`,
`tests/test_static_pages.py` (`FORBIDDEN_CLAIMS` — 4 ta ibora
qulflandi, qaytib kela olmaydi).
Diqqat: `/health/deep` **butunlay yopilmadi** — UptimeRobot aynan shu
manzilga qaraydi; begona faqat `ok`/`name`/`ms` ni ko'radi.
Serverda `CHAQIMCHI_JWT_SECRET` **qo'yilmagan** (A9 tekshirildi) —
owner/portal kalit ajratilishi buzilmagan, O'RTA-7 yopildi.

### 2026-08-25 — Audit hujjati (`1daf474`)
Nima: [AUDIT_TAHLIL.md](AUDIT_TAHLIL.md) — chaqimchi.uz va mahsulot
holati bo'yicha 22 topilma, tuzatish holati va A/B/C/D reja.
Diqqat: audit **ikki marta xato qildi** va ikkalasi bekor qilindi —
O-0 (`config/sotqin.yaml` da 4 va 8 ikkalasi ham to'g'ri: SLA va
apparat shifti) va O-6 (chidamli Telegram tormozi allaqachon bor).
Saboq "Tuzoqlar" bo'limiga yozilgan.
