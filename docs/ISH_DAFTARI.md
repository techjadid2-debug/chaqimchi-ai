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
- **YETIMLAR TOZALANDI** (2026-08-26 14:12). Beshta zanjir bir vaqtda
  ishlar edi (0.6.13 … 0.6.19) — masofaviy `clean_chains` topshirig'idan
  keyin **bitta** qoldi: `0.6.20`.  Cloud nazorati ham toza:
  `multi_version_sites: {}`.  Endi har o'lchov bitta jarayondan keladi.
- **Panel ishi boshlandi (2026-08-26 kechqurun).** Bildirishnoma
  markazi, jonli ko'rish keepalive va to'rtta yolg'on tugma tuzatildi;
  T6 biometrik teshigi yopildi. Tafsilot tarixning birinchi yozuvida.
  **Hali deploy qilinmagan.**
- Shox: `loitering-rasmsiz`, `origin` bilan sinxron. Asosiy shox `main`.
- Audit ([AUDIT_TAHLIL.md](AUDIT_TAHLIL.md)) bo'yicha **A bosqichi
  (A0–A9) va B bosqichining katta qismi tugadi**. C boshlanmagan.
- Server: `169.58.198.111` (Contabo, Fransiya), kod
  `/home/deploy/chaqimchi-ai`, compose `docker-compose.chaqimchi.yml`.
  SSH kaliti `.deploy_keys/chaqimchi_prod`.
- **Sotuv hali ochilmagan** — pastdagi ikkita darvoza yopiq.

## KEYINGI ISH

**1) Panel o'zgarishlarini deploy qilish** — kod tayyor, testlar o'tdi.
`scripts/deploy_cloud.sh` orqali (u zaxira talab qiladi). Keyin ko'z
bilan: qo'ng'iroqda haqiqiy o'qilmagan son, bosilganda ro'yxat ochiladi
va son kamayadi; "Jonli ko'rish" 5 daqiqa ochiq turganda muzlamaydi.

**2) DAVOMAT JIMGINA O'LIK — qurilma relizi kerak.** Ikki chegara
zid (batafsil: tarixning birinchi yozuvi va "Ochiq muammolar").
Kelishilgan yechim: davomat kamerasi uchun **asosiy oqim** ochiladi
(`runner.py:63-81`), chegaralar bitta formuladan chiqariladi. Narxi
i5-4590 da o'lchansin — `scripts/benchmark_n100.py` haqiqiy RTSP bilan
(`--source` bermasangiz o'lchov yolg'on).

**3) Qolgan reja** — hodisa kadrlari yon tomonda + "bu odam xodim"
tugmasi (backend tayyor: `cloud/main.py:7910`), zona muharriri
(`shelf` flagi yo'qolishi, fon kadri, o'chirish tarqalmasligi), ovoz.

---

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

**⚠ DAVOMAT JIMGINA O'LIK — ikki chegara bir-biriga zid**

Topildi 2026-08-26 kechqurun, **hali tuzatilmagan** (qurilma relizi
kerak).

| Gate | Joyi | 640×360 substreamda talab |
|---|---|---|
| `FACE_MIN_BBOX_RATIO = 0.28` | `scene_analytics.py:153`, chaqiruv `:511` | bbox balandligi ≥ **101 px** |
| `FACE_MIN_CROP_PX = 96`, crop = `0.35 × bbox` | `pipeline.py:86`, chaqiruv `:573` | bbox balandligi ≥ **274 px** (ratio 0.76) |

Analizator 101 px dan katta odam uchun `face_captured` chiqaradi,
pipeline esa 274 px dan kichigini **tashlaydi** (`return False` →
hodisa ham yuborilmaydi). Ya'ni odam kadr balandligining 76% ini
egallashi kerak — amalda faqat kameraga tegay deb turgan odam.

**Nima uchun bu muhim:** "4 606 yuz kadri → 0 ta tanish" tuzatilgandan
keyin ham davomat ishlamaydi. Ilgari mayda kadr kelardi, endi umuman
kelmaydi. Ikkalasining natijasi bir xil: nol tanish.

**Tekshirish:** qurilmada `face_crops_too_small` hisoblagichi
(`pipeline.py:180`) — u o'sib borayotgan bo'lsa tashxis tasdiqlanadi.

**Kelishilgan yechim:** davomat kamerasi uchun **asosiy oqim** ochiladi
(naqsh bor: klip uchun main stream `ringbuffer.py:103-133` da shunday
ochiladi), va ikki chegara bitta formuladan chiqariladi. Narxi
o'lchansin — i5-4590 da qo'shimcha 1080p dekod, 4 kamera kafolatiga
tegishi mumkin.

**Yon eslatma:** pastdagi "camera-02 yuz kadri to'xtamayapti" muammosi
shu bilan bog'liq bo'lishi mumkin — beshta yetim zanjir tozalangandan
keyin qayta o'lchanmagan.

**⚠ camera-02 yuz kadri to'xtamayapti (yetimlar tozalangach qayta o'lchanmagan)**

0.6.17 chiqqandan keyin ham sinov do'konining `camera-02` kamerasi
daqiqasiga ~11 ta `face_captured` yuborishda davom etyapti.  Ikkala
himoya ham ishlamayapti va sabab **hali topilmagan**.

Nima tekshirilgan va INKOR qilingan:

| Gumon | Natija |
|---|---|
| Qurilma eski versiyada | ✗ heartbeat `app_version: 0.6.17` |
| Shift kodi relizga tushmagan | ✗ `build/payload/.../scene_analytics.py` da `FACE_EMITS_PER_HOUR` bor |
| Sozlama cloudda o'zgarmagan | ✗ revision 8, `attendance_camera_ids: ["camera-01"]` |
| Qurilma sozlamani olmagan | ✗ `config/ack` keldi |
| Zanjir qayta ishga tushmagan | ✗ `analyzed` 16622 → 3917 (hisoblagich nolga tushdi) |
| `now` noto'g'ri birlikda | ✗ `runner.py:135` — `time.monotonic` |
| Analizator har ulanishda qayta yaratiladi | ✗ faqat `build_runner` da, bir marta |

Ya'ni: yangi kod, yangi sozlama, qayta ishga tushgan zanjir — va
baribir eski xatti-harakat.  Keyingi qadam **qurilmaning o'z logini
ko'rish** (`%PROGRAMDATA%\Chaqimchi\logs`): `build_runner` qaysi
`attendance_cameras` to'plami bilan qurilayotgani va
`face_emits_suppressed` o'syaptimi.  Masofadan aniqlab bo'lmadi.

**Zarari cheklangan:** T2 tufayli bu oqim do'kon hodisalarining rasm
byudjetiga tegmaydi — `/health/deep` da `rate_limited` faqat
`face-snapshots` ni ko'rsatadi, `snapshots` toza.

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

### 2026-08-26 — Panel: qo'ng'iroq rostdan ishlaydi, jonli ko'rish muzlamaydi (commit qilinmagan)
Nima: mijoz panelidagi to'rtta yolg'on gapiradigan tugma tuzatildi va
bildirishnoma markazi qurildi.

**Eng muhim topilma — davomat JIMGINA O'LIK.** Ikki chegara bir-biriga
zid: `scene_analytics.py:153` (`FACE_MIN_BBOX_RATIO = 0.28`) hodisa
chiqarish uchun odam kadr balandligining 28% ini egallashini talab
qiladi; `pipeline.py:86` (`FACE_MIN_CROP_PX = 96`, crop `0.35×bbox`) esa
kesmani saqlash uchun 274 px, ya'ni **76%** ni talab qiladi. 640×360
substreamda odam kadrning uchdan ikkisidan ko'pini egallashi kerak —
amalda faqat kameraga tegay deb turgan odam. Shuning uchun "4 606 yuz
kadri → 0 ta tanish" tuzatilgandan keyin ham davomat ishlamaydi: ilgari
mayda kadr kelardi, endi umuman kelmaydi. **Hali tuzatilmagan** —
qurilma relizi kerak (reja: davomat kamerasi asosiy oqimdan o'qiydi).

Tuzatilganlar:

1. **Bildirishnoma markazi** — `notification_reads` jadvali,
   `GET/POST /api/v1/owner/notifications`. Qo'ng'iroqdagi son ilgari
   `data.events.length` edi (panel olgan oxirgi 12 ta hodisa) va hech
   qachon kamaymasdi. Endi son serverda hisoblanadi, "o'qildi" belgisi
   har a'zoda alohida (`member_id`), qo'ng'iroq ro'yxat ochadi.

   **Test loyiha xatosini topdi:** dastlab `occurred_at` bo'yicha
   solishtirgan edim. Internet uzilib qayta ulangan qurilma ESKI sanali
   hodisalarni yuboradi — ular "o'qilgan" bo'lib jimgina yo'qolardi,
   ya'ni aynan uzilish paytidagi eng muhim hodisalar. Endi solishtirish
   `created_at` (bulut qachon bilgani) bo'yicha.

2. **Jonli ko'rish 90 soniyada muzlardi.** `store.request_live` izohi
   "panel har 60 soniyada qayta chaqiradi" deb va'da qilgan, panel esa
   HECH QACHON chaqirmagan. Ustiga panel `new Date()` bilan o'z soatini
   ko'rsatardi — muzlagan rasm ustida soat tikillab turardi. Endi:
   keepalive har 60 s, `X-Frame-At` sarlavhasi (kadrning O'Z sanasi),
   25 soniyadan eski kadrda qizil "yangilanmayapti", va panel yopilganda
   `{stop:true}` bilan oqim to'xtatiladi (kunlik byudjet tejaladi).

3. **"AI ramkani ko'rsatish"** jonli rejimsiz faqat yorliq qo'yardi —
   ramka qurilmada, faqat jonli kadrga chiziladi. Endi tugma jonli
   rejimni o'zi yoqadi.

4. **"Nusxalash"** `navigator.clipboard?.` edi — HTTP, eski WebView va
   Telegram Mini App'da jimgina hech narsa qilmasdi. `copyText()`
   zaxira yo'l bilan va `CopyButton` natijani ko'rsatadi.

5. **"Dalilni ochish"** `event_id` ni umuman ishlatmasdi. Endi aynan
   o'sha hodisa ochiladi va ekranga suriladi.

6. **T6 — menejer xodim ismini ko'rardi.** `/owner/faces/events`
   `require_biometric_access()` dan o'tmasdi (yonidagi `/image` o'tardi)
   va javobda `person_name`, `person_id`, `snapshot_key` bor edi. Bu
   audit KRITIK-4 yopgan sinfning aynan o'zi. Endi tekshiruv bor,
   `snapshot_key` javobdan olindi (`has_image` qoldi), admin biometrik
   media ochgani audit jurnaliga yoziladi.

7. **Ovoz uchun tayyorgarlik** — `camera_probe.audio_track()` RTSP
   `DESCRIBE` javobidan (u allaqachon olinadi, faqat status kodi
   ishlatilardi) audio yo'lagini o'qiydi. Sozlash ustasi endi
   "kamerada mikrofon bormi" degan savolga javob beradi.

Qayerda: `cloud/event_store.py` (`notification_reads`,
`NOTIFICATION_SEVERITIES`, `notifications()`), `cloud/main.py`
(bildirishnoma endpointlari, `X-Frame-At`, `_audit_biometric_view`),
`cloud/store.py` (`stop_live`, `camera_frame_at`),
`frontend/src/owner.tsx` (`NotificationBell`, keepalive),
`frontend/src/components.tsx` (`CopyButton`), `frontend/src/api.ts`
(`copyText`), `chaqimchi_ai/local/camera_probe.py` (`audio_track`).

Test: 4 ta yangi fayl/bo'lim — `test_owner_notifications.py` (6 ta),
`test_camera_audio_track.py` (5 ta), `test_owner_cameras.py` (jonli
ko'rish 2 ta), `test_cloud_faces.py` (biometrik audit 1 ta).

Diqqat — ikkita narsa:

* **Repodagi `cloud/static/v2/` bundle 25-avgustdan eskirgan edi** va
  26-avgust tuzatishlari (Telegram darajasi, preview POST) unda yo'q
  edi. **Lekin production'ga ta'sir qilmagan:** `Dockerfile.cloud:25`
  panelni har build'da qaytadan quradi. Tekshirildi — jonli saytdagi
  `owner-Op4c4Sdx.js` da hammasi bor. Bundle endi yangilandi, ya'ni
  `make run-cloud` lokalda ham to'g'ri panelni beradi.
* **Admin `snapshot`/`clip` marshrutlarida biometrik tekshiruv yo'qligi
  NOSOZLIK EMAS** — `require_admin` platforma adminini bildiradi, u esa
  `require_biometric_access` ruxsat beradigan `service_admin`. Kamchilik
  jurnal edi va u qo'shildi. (Bu — auditning uchinchi marta shu sinfda
  xato topilma yozishi bo'lardi.)


### 2026-08-26 — Yetimlar tozalandi, o'lchov endi ishonchli
Nima: masofaviy `clean_chains` topshirig'i yuborildi va beshta
zanjirdan **bittasi** qoldi.

| | Oldin | Keyin |
|---|---|---|
| Ishlayotgan versiyalar | 0.6.13, 0.6.16, 0.6.17, 0.6.18, 0.6.19 | **faqat 0.6.20** |
| `multi_version_sites` | 4 ta versiya | `{}` |

Yo'lda bitta xato chiqdi va tuzatildi: `clean_chains`
`JOB_DEADLINE_SEC` ga qo'shilgan, lekin `device_jobs.kind` dagi CHECK
ro'yxatiga qo'shilmagan edi — birinchi chaqiruv jonli serverda 500
berdi.  Ikki ro'yxat ajralib ketgan va buni ushlaydigan test yo'q edi.
Endi `test_every_known_job_kind_can_actually_be_created` har turni
bazaga rostdan yozib ko'radi; mavjud bazalar uchun migratsiya ham
qo'shildi va eski sxemada sinovdan o'tkazildi.

**Nima uchun bu muhim:** bugungacha davomat, mijoz portreti va yuz
kadri bo'yicha har o'lchov beshta jarayonning ARALASHMASI edi.  Endi
o'lchov bitta jarayondan keladi va unga ishonish mumkin.

Test: 1809 ta o'tdi.

### 2026-08-26 — Nega eski jarayonlar o'chmadi: javob va yechim
Nima: o'rnatuvchida eski zanjirni o'ldiradigan **uchta** qatlam bor va
uchalasi to'g'ri yozilgan.  Muammo mantiqda emas — **natija hech qayerda
tekshirilmasdi**: `nsExec::ExecToLog` javob kodi o'qilmaydi,
`Stop-Process -ErrorAction SilentlyContinue` xatoni yutadi, uchinchi
qatlam esa windowsiz jarayonni printsipial topa olmaydi.  O'ldirish
yiqilsa yangilanish baribir davom etardi va ortda tirik zombi qolardi.

**Bu uchinchi marta takrorlandi** — `windows_installer.nsi` ning o'zida
0.6.9 dagi xuddi shu holat haqida izoh bor.  Har safar mantiq
kuchaytirildi, tekshiruv esa qo'shilmadi.

Beshta ish:

1. **`chaqimchi_ai/local/chain_processes.py`** (yangi) —
   `find_chains()` / `kill_chains()`.  Mantiq NSIS ichidagi PowerShell
   satrlaridan modulga ko'chdi: endi u testlanadi va uchta joyga xizmat
   qiladi (supervisor, masofaviy topshiriq, heartbeat).  `kill_chains()`
   **hammasini** o'ldiradi — ilgari holat faylidagi bitta PID edi va
   beshta yetimda har restartda bittadan kamayardi.
2. **O'rnatuvchi natijani tekshiradi** — qolgan jarayonlar sanalib
   `update-warning.json` ga yoziladi.  Yangilanish ataylab
   to'xtatilmaydi (foydalanuvchi qarori): xavfsizlik tuzatishi yetib
   borishi muhimroq, lekin holat endi ko'rinadi.
3. **Heartbeat `stale_chains` yuboradi** — admin panelda qizil qator:
   "N ta zanjir bir vaqtda ishlayapti".
4. **Masofadan tozalash** — `clean_chains` topshirig'i va admin
   panelda tugma.  Muhim nuqta: topshiriqni **dastur** bajaradi, ya'ni
   eski yetimlar hech narsani tushunishi shart emas.
5. **Cloud o'zi sezadi** (eng qimmatlisi, relizsiz):
   `multi_version_sites()` — bitta obyektdan bir nechta `edge_version`
   kelsa admin Telegramiga kuniga bir marta xabar va `/health/deep` da
   `multi_version_sites`.  Bu nosozlikni oylar oldin ushlagan bo'lardi.

Fayllar bo'yicha esa hammasi joyida edi: `updater.run_once()` yangi
paket va rollback nishonini qoldirib, qolganini o'chiradi.  Endi bu
testga bog'landi (`test_windows_update.py`).

Qayerda: `chaqimchi_ai/local/chain_processes.py` (yangi),
`local/supervisor.py`, `local/cloud_jobs.py`, `local/cloud_config.py`,
`scripts/windows_installer.nsi`, `cloud/event_store.py`
(`active_edge_versions`), `cloud/main.py`, `cloud/store.py`,
`cloud/static/admin.html`.
Test: 1805 ta o'tdi (avval 1799).

Diqqat: yagona yiqilgan test — ma'lum beqaror
`test_cloud_load.py::test_clip_retention_is_configurable` (yolg'iz
o'tadi, "Ochiq muammolar" da qayd etilgan).

### 2026-08-26 — Do'kon kompyuterida TO'RTTA zanjir ishlayotgan ekan
Nima: bir necha relizdan beri "tuzatish ishlamayapti" degan holat bor
edi.  Sabab topildi va u kutilganidan jiddiyroq.

**Dalil.** Hodisalardagi `edge_version` bir vaqtda to'rtta qiymat
ko'rsatdi va to'rttasi ham o'sha daqiqada hodisa yuborardi:

| edge_version | hodisa | oxirgisi |
|---|---|---|
| 0.6.13 | 528 | 13:12 |
| 0.6.16 | 505 | 13:12 |
| 0.6.17 | 71 | 13:06 |
| 0.6.18 | 4 | 13:12 |

**Sabab.** `RetailSupervisor` faqat O'Z bolasini biladi
(`self._process`).  Dastur yangilanganda eski nusxa o'ladi, uning bolasi
esa **yetim qolib ishlashda davom etadi** — uni hech kim to'xtatmaydi.
Har yangilanish bitta zombi qoldirgan.

**Nima uchun bu hamma narsani buzdi.** Har chegara jarayonlar soniga
ko'payib ketardi: yuz kadri soatlik shifti (40 emas, 160), davomat
kamerasi ro'yxati (eski jarayonlarda eski ro'yxat), kamera byudjeti.
Shuning uchun:

* 0.6.17 dagi `FACE_EMITS_PER_HOUR` "ushlab turmagandek" ko'rindi;
* davomatni bitta kameraga tushirish "yetmagandek" ko'rindi;
* 0.6.18 dagi 96 px chegarasi umuman ta'sir qilmadi.

Uchalasi ham aslida ISHLAYOTGAN edi — faqat eski jarayonlar ham yonma-yon
ishlayotgan edi.

**Ikki himoya qo'shildi** (bir-birini to'ldiradi):

1. `supervisor._kill_orphan_chain()` — yangi zanjirni ko'tarishdan
   oldin holat faylidagi PID bo'yicha eskisini to'xtatadi.  PID qayta
   ishlatilishidan himoya: holat fayli 120 soniyadan yangi bo'lsagina
   o'ldiriladi.
2. `service.claim_ownership()` / `_still_the_owner()` — yangi zanjir
   egalik faylini qayta yozadi, eski jarayon buni ko'rib **o'zi**
   chiqadi.  Supervisor yetimlarni ko'rmaydi, shuning uchun ikkinchi
   himoya ichkaridan ishlaydi.  Fayl buzilsa `True` qaytadi: ishlab
   turgan zanjirni to'xtatish nazoratsiz qolishdan yomonroq.

Qayerda: `chaqimchi_ai/local/supervisor.py`,
`chaqimchi_ai/retail/service.py` (`write_status` ga `pid` qo'shildi).
Test: `test_supervisor_recovery.py` (4 ta), `test_retail_service.py`
(3 ta) — jami 1799 test o'tdi.

**DIQQAT — bir martalik qo'l ishi.** Hozirgi to'rtta yetim ESKI kodda
ishlayapti va ularda egalik tekshiruvi yo'q.  0.6.19 o'rnatilgach
supervisor bittasini o'ldiradi, qolganlari esa **do'kon kompyuteri
qayta yuklanmaguncha** ishlashda davom etadi.  Eng ishonchli yo'l:
mijozdan kompyuterni bir marta qayta yuklashni so'rash.

Tekshirish: `SELECT edge_version, count(*) FROM production_events
WHERE occurred_at > '<qayta yuklashdan keyin>' GROUP BY 1;` — faqat
bitta versiya qolishi kerak.

### 2026-08-26 — Sayt, SEO va sotilayotgan funksiyalarni tekshirish
Nima: footer tuzatildi, Google uchun razmetka qo'shildi, admin
sozlamalaridan ichki narx jadvali olindi va sotuv sahifasi faqat
ISHLAYDIGAN funksiyalarni va'da qiladigan bo'ldi.

**Eng muhimi — o'lchov.** Saytda va'da qilingan 4 funksiyadan
**ikkitasi umuman ishlamayotgani** aniqlandi:

| Sayt va'dasi | Haqiqat |
|---|---|
| Mijozlar oqimi | ✅ 28 kirdi / 32 chiqdi, yo'nalish to'g'ri |
| Issiqlik xaritasi | ✅ 13 696 kadr, joriy soat |
| Jonli ogohlantirish | ✅ tungi 12, tamper 8, zona 44 |
| Xodimlar davomati | ❌ **4 606 yuz kadri → 0 ta tanish** |
| Mijoz portreti | ❌ `demography_daily` butunlay 0 |

**Ikkalasining sababi BITTA:** yuz kadrlari o'rtacha **727 bayt**
(~40×40 px), ro'yxatdagi xodim rasmi esa 329 KB.  Zanjir kesmani
tahlil substreamidan oladi va chegara 16 px edi — u "bo'sh kesma
bo'lmasin" degan himoya, yuzning O'QILISHI haqida emas.  Xuddi shu
sabab demografiyani ham o'ldiradi: yuz detektori o'sha kadrdan yuz
topa olmaydi va `_estimate_demography()` **jimgina `None`** qaytaradi.

Qayerda: `retail/pipeline.py` (`FACE_MIN_CROP_PX = 96`, mayda kesmali
hodisa endi UMUMAN yuborilmaydi — uning yagona qiymati rasmda edi);
`retail/demography.py` (`LAST_OFF_REASON` — nega o'chiq);
`scene_analytics.py` (`demography_attempts` / `demography_found`);
`local/cloud_config.py` + `cloud/main.py` (heartbeat);
`cloud/static/admin.html` (qurilma kartochkasida ko'rinadi).

**Yana bir topilma:** `scripts/calibrate_face_threshold.py` — Face ID
ni sozlaydigan YAGONA asbob — hech qachon ishlamagan.  U
`employee_face()` dan embedding kutardi, o'sha metod esa faqat panel
maydonlarini qaytaradi.  Jonli bazada birinchi qatordayoq
`KeyError: 'embedding_b64'`.  Tuzatildi (`face_embeddings()` ga
o'tkazildi) va shartnoma test bilan qulflandi.

Sayt: sarlavhalar endi funksiya nomi emas, mijozning savoli
("Qaysi javon oldida odam to'planadi").  Davomat va mijoz portreti
sotuv sahifasidan **olib tashlandi** — ishlagani o'lchangach
qaytariladi; `test_landing_does_not_sell_attendance_or_demography`
buni qulflaydi.

SEO: canonical, JSON-LD (Organization + SoftwareApplication +
FAQPage), sitemap'da `lastmod` (fayl sanasidan), sarlavhada
qidiriladigan so'zlar.  Sizdan kutiladigan ikki qadam —
[SEO.md](SEO.md).

Test: 1792 ta o'tdi (avval 1782), lint va TS typecheck toza.

Diqqat: `FACE_MIN_CROP_PX` va demografiya hisoblagichlari QURILMA
tomonida — ular yangi reliz talab qiladi.  Chegarani o'lchash (4c)
esa **hali bajarilmagan**: skript endi ishlaydi, lekin unga har
xodimdan kamida 2 ta rasm va yangi relizdan keyingi haqiqiy kesmalar
kerak.

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
