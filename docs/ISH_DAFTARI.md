# Ish daftari

> Har agent ishni **shu fayldan** boshlaydi va **shu faylga** yozib
> tugatadi. Maqsad: keyingi sessiya nolla emas, shu yerdan boshlasin.
>
> Qayerda nima turishi — [ARXITEKTURA_XARITASI.md](ARXITEKTURA_XARITASI.md).

---

## HOZIRGI HOLAT · 2026-09-08

- **🧹 ESKI PANELLAR O'CHIRILDI (2026-09-08, `73cc704`).**
  `cloud/static/owner.html` (2 827 q.) va `admin.html` (2 310 q.) yo'q;
  `/owner` va `/admin` har doim React.  Eski 47 qulf
  `tests/test_panel_v2.py` ga ko'chdi (ko'chirilmaganlari va sababi —
  pastda «PANEL QOIDALARI»).  `make test` endi i18n katalogini ham
  tekshiradi (`build_i18n.py --check`).  Bundle qayta qurildi va
  commit qilindi.
  ⚠️ **React adminda eski adminning 15+ vositasi YO'Q.**  `556d33c`
  xabari «faqat Arizalar yetishmasdi» degan edi; endpoint ro'yxatini
  solishtirish boshqacha ko'rsatdi: qurilma topshiriqlari
  (`clean_chains`, `benchmark`), diagnostika, funksiya biriktirish
  (`features/draft|quote|approve` — **sotuv darvozasi**), masofaviy
  kamera/chizma (`camera-inventory`), yuz kadrlari, onboarding,
  jamoa/installer biriktirish, ogohlantirish sozlamalari va sinovi,
  biznes shablonlari, to'lov provayderlari, reliz/yangilanish
  boshqaruvi.  Ikki `xfail(strict)` test kutib turibdi
  (`test_the_admin_can_fix_a_shop_remotely`,
  `test_admin_panel_promises_the_same_interval`).  **F4 shu ro'yxatni
  yopmaguncha shox deploy qilinmaydi** — production `main` da.
  `owner.css`/`panel.css` diskda qoldi: `pay.html` hali ularni
  ishlatadi (F3 da ketadi).
- **🎨 REBRENDING: F1 (dizayn tizimi) va F2 (til yadrosi) BAJARILDI.**
  Shox: `enes-rebrend`.  Deploy qilinmagan — rebrend to'liq tayyor
  bo'lgach bir marta chiqadi.
  - **F1:** `cloud/static/tokens.css` — sayt va panel uchun yagona
    palitra; `styles.css` dagi ~130 qattiq rang tokenga ko'chdi;
    uch holatli tema (yorug'/qorong'i/tizim), tanlov `localStorage` da,
    tema birinchi chizishdan oldin qo'yiladi.
  - **F2:** `i18n/{uz,ru,en}.json` (41 kalit) + `cloud/i18n.py` +
    `cloud/errors.py` + `scripts/build_i18n.py`.  Til zanjiri:
    `?lang=` → `X-Lang` → saqlangan → Telegram → `Accept-Language` →
    `uz`.  Baza: `owner_members.language`, `portal_accounts.language`.
  - **Keyingi ish:** F3 — sayt (yangi dizayn + uch til + ENES nomi).
- **⏳ Egadan kutilmoqda:** "NS" logotipi SVG'da; `enes.uz` DNS
  boshqaruvi; Telegram bot @username; yuridik nom; Payme/Click kabineti.

- **🎨 REBRENDING BOSHLANDI: Chaqimchi AI → ENES Monitoring (enes.uz).**
  Reja tasdiqlangan: `~/.claude/plans/ok-biz-rebrending-*.md`.
  Ega qarorlari: nom **to'liq** o'zgaradi (ichki nomlar ham),
  eski domen **butunlay o'chadi** (bir kunlik cutover), sayt va'dalari
  faqat rost, **UZ/RU/EN hamma joyda** (Telegram va CSV ham),
  jonli mijoz **1 ta pilot** (qo'lda qayta o'rnatiladi), server
  idishlari nomi ham o'zgaradi (ma'lumot ko'chiriladi), eski panellar
  (`owner.html`, `admin.html`) **o'chiriladi**.  Keyingi qadam — F1:
  dizayn tizimi va dark/light tema.
- **✅ DEPLOY QILINDI VA JONLI TASDIQLANDI (2026-09-06, `6bf4e87`).**
  Excel/CSV eksporti (kunlik + oylik) va capture rate yadrosi jonli.
  Tekshirildi: `report.csv` 404 → **401** (marshrut bor), panel yangi
  to'plamni beryapti (`owner-WviT491D.js`), hamma konteyner healthy,
  deploydan keyingi 5 daqiqada **0 ta** xato.
  ⚠️ **Tuzoq takrorlandi:** manba o'zgargan, `make ui-build` esa
  qilinmagan edi — API ishlagan bo'lardi-yu, tugmalar panelda
  ko'rinmasdi.  Panel manbasiga tegilsa **bundle ham commit qilinsin**.

- **✅ DEPLOY QILINDI VA JONLI TASDIQLANDI (2026-08-31, `0a5c3e3`).**
  Zaxira olindi (760 KB), hamma konteyner healthy, deploydan keyingi
  15 daqiqada **0 ta** xato/5xx, tashqi API 200.  Jonli bazada
  `daily_sales` jadvali yaratildi, panel to'plami yangisi
  (`owner-DZcdnEeq.js`) tarqatilyapti va unda «Chek soni kiritilmagan»,
  «eshik taqsimoti saqlanmagan» matnlari bor.
- **📌 DAFTAR SHU JOYDA XATO EDI: 0.6.29 allaqachon 30-avgustda deploy
  qilingan ekan.**  Dalil: `retail_daily` yozuvlarining `updated_at` i
  `2026-08-30T11:45…19:53` — ya'ni ma'lumot yo'qolishi xavfi bir kun
  oldin yopilgan.  Bugungi deploy Bosqich 1 (ko'rinish) va bugungi
  ishni olib chiqdi.
- **🆕 BOSQICH 3 NING CLOUD QISMI BAJARILDI — eshik sanog'i va
  konversiya jonli.**  Ega qarori (2026-08-31):
  deploy bugun, keyingi bosqich — **Raqamlar**, soak ishlab turgani
  uchun **faqat cloud** qismi.  Bajarildi: (1) kirdi/chiqdi **eshik
  bo'yicha** (`line_name` bazada bor edi, hech qayerda o'qilmasdi);
  (2) **konversiya** — ega chek sonini paneldan yoki Telegramdan
  (`/chek 100`) kiritadi, kunlik hisobotda «🧾 100 chek / 200 kirgan»
  qatori; (3) **`Numbers.tsx`** — Hisobotlar sahifasida kunning yakuni
  bitta kartada.  2 034 test yashil, `make lint` va `ui-check` toza,
  `ui-build` qilingan.
- **Deploy kaliti `.env` da.**  Standart `~/.ssh/id_ed25519` serverda
  ruxsat etilmagan; ishlaydigani — `CHAQIMCHI_DEPLOY_SSH_KEY`
  (loyihaning `.env` fayli).  `deploy` foydalanuvchisi bilan
  `docker compose` ISHLAMAYDI (`/home/deploy/chaqimchi-ai/.env` faqat
  root uchun o'qiladi) — deploy `root@` bilan, tashxis esa
  `docker inspect` / `docker exec` bilan qilinadi (deploy `docker`
  guruhida).

- **🔍 720p HALI YOQILMAGAN — jonli dalil.**  «Sig'imni o'lchash»
  tugmasi bosilmadi (u soak o'lchovini buzardi); o'rniga heartbeat
  o'qildi: demografiya `{attempts: 153, found: 3}` — **2%**, ya'ni
  oldingi 6% dan ham YOMONROQ; `face_crops {written: 0, too_small: 0}`
  — urinish umuman yo'q.  Bulutdagi kamera yozuvida
  `probe_status: pending`, `width/height: NULL` — cloud tomondan probe
  hech qachon ishlamagan, ya'ni bu manba javob bermaydi.  Xulosa:
  mijoz `camera-01` ni 1280x720 ga o'tkazmagan; xodim/davomat ishi
  shungacha kutadi.
- **🆕 BOSQICH 1 «KO'RINISH» COMMIT QILINDI, DEPLOY QILINMADI.** Ega 20
  bandlik ro'yxat berdi (reja: `~/.claude/plans/1-7-kun-demo-*.md`) va
  birinchi bosqich sifatida **ko'rinish** tanlandi.  Uchta ish bajarildi:
  (1) hodisalar **vaqt lentasi** — kun bo'ylab 24 ustun, soatga bosilsa
  kartochkalar filtrlanadi, kadr endi o'zi yuklanadi va rasm yo'q bo'lsa
  **nega yo'qligi** aytiladi (to'rt holat); (2) **AI yordamchi javobida**
  manba soatlari o'sha lentada belgilanadi; (3) **issiqlik xaritasi soat
  bo'yicha** — slayder + ijro, 24 soat bitta so'rovda va **bitta rang
  shkalasida**.  Faqat cloud + React panel — **qurilma relizi kerak
  emas, soak bilan to'qnashmaydi**.
- Yangi marshrutlar: `GET /api/v1/owner/events/timeline`,
  `GET /api/v1/owner/events?date=&hour=`,
  `GET /api/v1/owner/heatmap?by=hour`.  Dashboard endi
  `media_retention_hours` beradi, har hodisa `media_expected` beradi.
- Boy ko'rinish **Biznes tarifida** (`xavfsizlik`), oddiy ro'yxat hammaga
  ochiq qoladi — hech kim funksiya yo'qotmaydi (ega qarori).
- Jonli oqim qo'lda tekshirildi (lokal server): lenta 42 ta hodisani
  Toshkent soatlariga to'g'ri joyladi, `person_detected` chiqarib
  tashlandi, soat filtri ishladi, xarita `peak: 300` va bo'sh soat bo'sh.
- ⚠️ **Deploydan OLDIN serverda tekshiring:**
  `docker compose exec cloud printenv | grep UI_V2`.  Hammasi React
  panelga yozildi (`CHAQIMCHI_UI_V2_OWNER=1` production uchun majburiy);
  eski `owner.html` ga bir qator ham tegilmadi.
- ⚠️ **Rasm masalasi hal bo'lmasa yangi ko'rinish bo'sh ko'rinadi.**
  Jonli bazada `zone_entered` buzuq chizma sabab o'lik va kamera 360p —
  ya'ni ega kartochkada rasmni emas, «rasm nega yo'q» matnini ko'radi.
  Ega qarori: chizma va 720p ishi **shu bosqich bilan parallel** (0b).

- **🔴 MA'LUMOT YO'QOLISHI OLDI OLINDI (0.6.29).** Panelning HAMMA
  raqami (`retail_report`, `traffic_trend`) xom `production_events` dan
  qayta hisoblanardi, xom hodisalar esa tarif muddatida (lite = 30 kun)
  o'chadi.  Ya'ni **~20-sentabrda** 21-avgust kunining kirish soni,
  soatlik grafigi, navbati va xavfsizlik sanog'i butunlay yo'qolishi
  kerak edi — va buni hech narsa aytmasdi.  Endi `retail_daily` va
  `retail_hourly` bor (3 yil), hisobot tugagan kunni o'shandan o'qiydi,
  purge esa yig'indisi yozilmagan kunga TEGMAYDI.
- **Media 48 soat (ega qarori).** Rasm, yuz kadri va klip bir xil
  muddatda ketadi (`purge_media_older_than`).  Hodisa qatorining o'zi
  tarif muddatigacha qoladi — narx sahifasidagi «Arxiv 30 kun» va'dasi
  buzilmadi.  Oferta, maxfiylik siyosati va rozilik shabloni yangi
  muddatga moslandi (yuz kadri: 14 kun → 48 soat).
- **Panel nega bo'sh ko'rinardi — javob:** (1) 29-avgust rostdan 0 ta
  kirish (tuzatilgan uzilish); (2) rasm umuman olinmaydi —
  `SECURITY_MEDIA_EVENTS` faqat uch tur va kun davomida ishlaydigan
  yagonasi (`zone_entered`) 29x20 pikselli buzuq chizma sabab o'lik;
  (3) klip hech qachon yozilmagan.

- **🔴 TUZATILDI VA JONLI TASDIQLANDI (0.6.27): do'kon besh kun hodisa
  yubormagan edi.** 29-avgust ertalabidan 30-avgust 13:14 gacha
  "Do'kon (5070)" ning HAMMA biznes hodisasi qurilmada tashlangan —
  kuniga ~7 600 ta.  Mijoz 29 va 30-avgust uchun **nol raqamli** kunlik
  hisobot oldi.  Sabab: bulut qurilmaga bo'sh funksiya ro'yxati
  yuborardi, `retail_event_filter` esa bo'sh ro'yxatni ko'rib har bir
  hodisani rad etardi.  Deploydan keyin: tashlash **100% → 74%** ga
  tushdi (qolgani normal — `person_detected` va sovutishlar) va
  30-avgust 13:14 da birinchi `line_crossed` bulutga yetdi.
- **Qabul darvozasi (`available_feature_codes()`) UCH joydan olindi**
  (ega qarori, 2026-08-30): qurilma konfigi, admin biriktirish va
  mijozning O'Z paneli.  Sotuv sahifasida QOLDI.  Sabab: darvoza
  obunasi tugagan saytga umuman yetib bormaydi (u yuqorida bo'sh
  ro'yxat oladi), ya'ni u faqat PUL TO'LAYOTGAN mijozni to'sardi.
- **Jimlikka signalizatsiya qo'shildi** — `config_health.feature_problems()`.
  Ikki tekshiruv: obuna faol-u ro'yxat bo'sh (sabab) va
  `plan_filtered == events` (natija).  Admin sayt kartochkasida qizil
  qator bo'lib chiqadi.
- **Zaxiraning tashqi nusxasi endi bor** — Telegram yo'li yoqildi va
  jonli sinaldi (1,1 MB arxiv ketdi).  ⚠️ `CHAQIMCHI_BACKUP_PASSWORD`
  hali FAQAT serverda — parol menejeriga ko'chirilmaguncha bu nusxa
  server o'lganda ochilmaydi.
- **Kamera rollari KODDA TAYYOR (0.6.26, nashr qilinmagan):** rol endi
  saqlanadi va zanjirni boshqaradi — sehrgar → `config.yaml` →
  bulut (`site_cameras.role`) → edge config → `CameraPlan.role`.
  Tizim rol TAKLIF qiladi (kanal nomi + oqim o'lchami), odam
  tasdiqlaydi; «kirish» roli kamerani davomat ro'yxatiga avto-qo'shadi
  (faqat o'tishda, maks. 2); 4 tadan ko'p topilsa eng yaxshi 4 belgilanadi.
  Yagona manba: `chaqimchi_ai/camera_roles.py`. **Soak muzlatishi
  sabab Windows nashr QILINMAYDI** — soak tugagach chiqadi.
- **Cloud deploy QILINDI (2026-08-30):** 🚻 tuzatishi + kamera rollari
  serverga chiqdi (`25a2882`, `af08057`). Tekshirildi: konteynerlar
  healthy, `site_cameras.role` migratsiyasi jonli bazada ishladi,
  tashqi API 200, deploydan keyingi loglarda xato yo'q. Bugungi 21:00
  hisobotida 🚻 qatori son-formatda chiqishini Telegramda tekshiring.
- **QA sessiyasi (29-avg kunduzi):** 🚻 ayol/erkak qatori kunlik
  hisobotga QAYTARILDI — «aqlli format»: o'lchov vakillik qilsa foiz,
  kam bo'lsa faqat SON (ega qarori — qatorni butunlay yashirish xato
  bo'lgan). Uch haftalik beqaror test (`test_clip_retention_is_
  configurable`) ildizi topilib tuzatildi. Cloud deploy 30-avg da
  qilindi. Ega qarori bilan: kameralarga hozircha TEGILMAYDI
  (720p, camera-02, chizmalar keyinga), maqsad — avval pilotni
  barqarorlashtirish (72 soatlik soak + soak paytida reliz muzlatish).
- **Jonli tekshiruv o'tkazildi** (PostgreSQL, `device_metrics`, konteyner
  loglari, 3 kunlik telemetriya). 27-avgust tuzatishlari **ishlagani
  tasdiqlandi**:
  - vaqt mintaqasi tuzalgan — `device_tz_offset_min: 300`,
    `clock_skew_sec: -0.7`;
  - ertalabki yolg'on trevoga **26 tadan 0 ga** tushdi;
  - yetim zanjirlar o'lgan — `stale_chains: {}`, bitta versiya `0.6.21`;
  - panel qo'ng'irog'i — 24 soatlik logda **0 ta** 5xx;
  - `outbox_poisoned` **o'smayapti** (4 401 → 2 752), `pending: 0`;
  - zanjir sog'lom: `analyzed` 52 835, fps 17.4, latency 47 ms,
    `analysis_errors: 0`, CPU atigi **8.8%**.
- **Cloud deploy qilindi va JONLI TASDIQLANDI** (`ed23cc7`): hamma
  konteyner healthy, deploydan keyin **0 ta** 5xx, heartbeat 0.6.21
  qurilmasidan muammosiz kelyapti (yangi maydonlar standart qiymatli).
  Admin panelda sinov do'koni kartochkasida ikkita yaroqsiz chizma
  ro'yxatga chiqdi (4 px chiziq, 29x20 px zona) va `device_jobs`
  CHECK ro'yxatida `benchmark` bor — migratsiya jonli bazada ishladi.
- **Windows 0.6.25 NASHR QILINDI** — o'lchov endi kameraning
  HAQIQIY o'lchamini aytadi (`native_size`). Usiz 720p ga o'tish
  ishlaganini faqat 24 soatdan keyin bilib bo'lardi.
- 0.6.24 (kamera manzili zaxirasi). Oldingi: (0.6.22 dagi o'lchov xatosi
  tuzatilgan holda). Oldingi holat: (imzo tekshirildi, tashqaridan
  ochiladi: `dl.chaqimchi.uz/releases/chaqimchi-windows-0.6.22.exe`,
  sha256 `145e240f…`). Cloud uni beryapti
  (`/api/v1/public/windows-release` → `0.6.22`).
  **Dalada bitta qurilma bor** — Do'kon (5070), siyosat `auto`, ya'ni
  15 daqiqada oladi. Bosqichma-bosqich tarqatish shart bo'lmadi.
- Shox: `loitering-rasmsiz`. Server: `169.58.198.111`.
- **Sotuv hali ochilmagan** — pastdagi ikkita darvoza yopiq.

- **SIG'IM O'LCHANDI** (2026-08-28, loyihada birinchi marta —
  ilgari raqam taxmin edi):

  | Nima | O'lchov |
  |---|---|
  | Detektor | 33,7 inferens/s, p95 **36 ms**, p99 49 ms |
  | Byudjet qabul qiladigan tezlik | **22,1 fps** |
  | 4 kamera uchun kerak | 8 fps |
  | Ko'taradigan kamera | **11 ta** · zaxira **176%** |
  | Barqarorlik | 9,8% sekinlashish (chegara 15%) — qizish yo'q |
  | Dekodlash | 1,19 ms/kadr, oqim 15,9 fps |
  | Kadr yuki | motion 1,8 ms + tamper 1,1 ms = 2,9 ms |
  | Xulosa | `ok: true`, ogohlantirishsiz |

  **Ikkinchi o'lchov (29-avg 04:11, do'kon bo'sh):** 36,1 inferens/s,
  p95 33,4 ms, byudjet 24,0 fps, zaxira 200%, sekinlashish 10,1%.
  Xulosa bir xil — **11 kamera**. Ikki mustaqil o'lchov mos keldi,
  ya'ni raqamga ishonsa bo'ladi. Kechagisi ish paytiga yaqinroq va
  shuning uchun ehtiyotkorroq.

  **720p ko'tariladi.** Detektor narxi oqim o'lchamiga BOG'LIQ EMAS
  (model kirishi qat'iy 320×544), ya'ni 22,1 fps o'zgarmaydi.
  O'zgaradigani faqat dekodlash: 1,19 ms → taxminan 4,8 ms, kadr yuki
  esa 0,08 yadrodan ~0,15 yadroga chiqadi. Bu ahamiyatsiz.

- **Kamera manzillari bulutda** (0.6.24 dan) va ular darhol javob berdi:

  | | camera-01 | camera-02 |
  |---|---|---|
  | IP | 192.168.1.64 | 192.168.1.170 |
  | Brend | **Hikvision** | eski/generik |
  | Tahlil oqimi | `/Streaming/Channels/102` | `/mpeg4cif` — ya'ni **352×288** |
  | Klip oqimi | `/Streaming/Channels/101` | **yo'q** |

## KEYINGI ISH

**REBREND (2026-09-08).** To'liq holat + xatolar + tartib:
`~/.claude/plans/loyiha-bo-yicha-nimalar-qilishimiz-*.md`.  Navbat:
**F3 sayt** (avval `scripts/build_site.py` qarori — bitta shablon +
katalog → `cloud/static/site/{uz,ru,en}/`, keyin dizayn; aks holda 15+7
sahifa ikki marta yoziladi) → **F4 panellar** (namunadagi ko'rinish +
matn ajratish + yuqoridagi admin vositalari ro'yxati; ikki `xfail`
belgisi olinadi; `owner.css`/`panel.css` o'chadi) → F5 Telegram/CSV →
F6 ichki nomlar → F7 cutover (egadan: DNS, bot @username, yuridik nom,
Payme/Click) → F8 qurilma relizi (soakdan keyin) → F9 tozalash.
Rebrendga bog'liq bo'lmagan kichik xatolar parallel, cloud-only:
`/health` halol (O-1), CSP (O-2), server tomonda chiqish (O-8), rate
limit (O-9), `geometry-panel.js` da `shelf` yo'q, CI'ga `make ui-check`.

**RAQOBAT (2026-09-06).** Tahlil va reja:
[docs/RAQOBAT_RETAILSOLUTION.md](RAQOBAT_RETAILSOLUTION.md) §7 (holat jadvali).
- ✅ **C bajarildi** — Excel/CSV yuklash (`/api/v1/owner/report.csv` +
  panel tugmasi). Faqat cloud+panel, deploy qilinsa bo'ladi.
- ⏸ **A1 (capture rate)** — qurilma sanash logikasi soakka to'qnashadi,
  **soak tugagach** relizga qo'shiladi. Ochiq sub-qaror: A1 (qo'shimcha
  kamerasiz, tavsiya) yoki A2 (tashqi kamera) — hujjat §5.A.
- ⏸ **D (sodiqlik, lokal/rasmsiz)** — huquqiy hujjatlar (oferta/
  maxfiylik/rozilik) yangilangach + qurilma relizi (§5.D).
- ℹ️ **B (720p)** mijoz kamerasiga bog'liq; **E** tarmoq mijozi kelganda.

**A) ✅ BAJARILDI — deploy qilindi va tasdiqlandi (2026-08-31).**
Qolgani — **ega ko'zi bilan tekshirish**: Hodisalar → kun tanlash →
soatga bosish kartochkalarni o'zgartiradimi; AI yordamchi javobi ostida
lenta chiqadimi; Issiqlik xaritasi → «Soat bo'yicha» → slayder so'rov
yubormasligi; **Hisobotlar → eshik bo'yicha qator va chek kiritish
formasi**; Telegramda `/chek 100` (javobda konversiya darhol ko'rinishi
kerak) va bugun 21:00 hisobotida `🧾` qatori.

⚠️ **Bugungi (31-avg) kun eshik taqsimotini KO'RSATADI, oldingi kunlar
yo'q.**  30-avgustgacha yozilgan `retail_daily` yozuvlarida `by_door`
kaliti umuman yo'q — panel «saqlanmagan» deb aytadi.  Bu kutilgan
xulq, xato emas.

**A2) ⚠️ MIJOZ BILAN — 720p hali yoqilmagan (tekshirildi).**
Demografiya `{attempts: 153, found: 3}` = 2%, `face_crops` da urinish
yo'q.  `camera-01` substream'ini **1280x720** ga o'tkazish kerak
(o'lchov ruxsat bergan: 11 kamera, zaxira 176–200%).  Shundan keyin
24 soat ichida `face_crops.written > 0` bo'lishi kutiladi.

**B) Bosqich 3 ning QOLGAN qismi (qurilma relizi kerak, soak tugagach):**
`exit` kamera roli (3.2), ish zonasi va faol ish vaqti (3.4), xodim/
davomat (3.3 — 720p tasdiqlangandan keyin).  Bajarilgani: 3.1 (eshik
bo'yicha), 3.5 (konversiya), 3.6 (birlashgan ko'rinish).

**B2) Keyingi bosqichlar (reja faylida to'liq):** Bosqich 2 — pul
(7 kunlik demo saytdan o'zi ochiladi, «Tarmoq» → «Moslashtirilgan»
kalkulyator, Payme/Click merchant shartnomasi va avtomatik yechish,
tannarx `cloud/finance.py` ga chiqariladi).  Bosqich 3 — raqamlar
(kirdi/chiqdi eshik bo'yicha, `exit` kamera roli, xodim Face ID orqali,
konversiya «200 kirdi → 100 chek», ish zonasi va faol ish vaqti).
Bosqich 4 — sotuv (partnyor komissiyasi va tasdiqlash, kamera qo'yish
standartlari).  Keyinga: ovoz funksiyalari, video darslar, jonli kamerani
takomillashtirish.

**0) ⚠️ EGA QILADI — zaxira parolini ko'chiring.**
`CHAQIMCHI_BACKUP_PASSWORD` faqat serverda (`/etc/chaqimchi/backup.env`).
Telegramdagi kunlik nusxa shu parolsiz ochilmaydi — ya'ni server o'lsa
zaxira ham foydasiz.  Parol menejeriga ko'chiring.

**0b) Mijoz bilan: chizmalar va 720p.**
`camera-02` da 4 pikselli «kirish» chizig'i va 29x20 pikselli
«Taqiqlangan zona» hali ham yaroqsiz — admin panelda ro'yxatda turibdi.
`camera-01` ni 1280x720 ga o'tkazish (o'lchov ruxsat bergan) — usiz
demografiya va davomat ishlamaydi.

**1) ✅ BAJARILDI — cloud deploy qilindi va tasdiqlandi** (2026-08-28).

Bugun kechqurun 16:00 UTC (21:00 Toshkent) birinchi kunlik hisobot
yangi kod bilan ketadi — Telegramda tekshiring: `🚻` qatori
CHIQMASLIGI kerak (bugun demografiya qamrovi 30% dan past) va
`⚠️` qatorida «N marta kassada hech kim yo'q» paydo bo'lishi kerak.

**2) ✅ BAJARILDI — 0.6.22 nashr qilindi** (2026-08-28).

Qurilma 15 daqiqada oladi. Yetganini shundan tekshiring:

```sql
select payload_json::jsonb->>'app_version', received_at from device_health;
```

Yangi versiyada ko'rilsin: `clips` ichida `no_segments` va
`cut_failed` alohida, `cameras_configured` bor, `snapshots{}` bor,
`device_diagnostics` jadvali endi **bo'sh emas**.

**3) ✅ BAJARILDI — sig'im o'lchandi** (yuqoridagi jadval). Eski matn: — admin panelda «Sig'imni o'lchash» tugmasi
(0.6.22 kerak). Natija `device_diagnostics` da ko'rinadi. Hozirgi
zaxira katta ko'rinadi (CPU 8.8%, RAM 40%, 2 kamera), lekin
**o'lchovsiz 720p ga o'tilmaydi**.

**4) ✅ BAJARILDI — cloud deploy qilindi (2026-08-30)** — 🚻 qaytishi,
beqaror test tuzatishi va kamera rollari bilan. Deploydan keyingi
21:00 hisobotida 🚻 qatori son-formatda chiqqanini tekshiring.

**5) 72 soatlik soak — pilotni barqarorlashtirish o'lchovi.**
`scripts/soak_windows.py` ni do'kon kompyuteriga qo'lda ko'chiring
(payloadda `scripts/` yo'q — tuzoqlarga qarang) va:
`python soak_windows.py --hours 72 --cameras 2 --output
soak-windows.json --samples-file soak-samples.jsonl`.
DIQQAT: `--cameras 2` bilan bu C1 qabul uchun YARAMAYDI (C1 ≥4 kamera
talab qiladi) — bu faqat barqarorlik o'lchovi. **Soak davomida reliz
chiqarmang** — avto-yangilanish zanjirni qayta ishga tushirib o'lchovni
buzadi.

**6) Soak tugagach — 0.6.26 nashri (kamera rollari).** Kod tayyor,
versiya ko'tarilgan. Nashrdan keyin tekshirish: sehrgarda kanal skan →
takliflar chiqadimi; rol «kirish» qilinganda `attendance_camera_ids`
ga tushadimi (maks. 2); `site_cameras.role` to'ldimi. Keyinga
qoldirilgan: harakat namunasi tugmasi (30–60 s/kamera) va `role_suggest`
qurilma job'i — dvigatel (`camera_roles.py`) buni allaqachon qabul
qiladi, faqat UI/transport yo'q.

**KEYINGA QOLDIRILGAN (ega qarori, 2026-08-29 — kameralarga tegilmaydi):**

- Mijoz kamerasida substream 1280x720 (o'lchov ruxsat berdi: 11 kamera,
  zaxira 176–200%). Shundan keyin 24 soatda `face_crops.written > 0`.
- Chizmalarni mijoz bilan tuzatish («Taqiqlangan zona» 29x20 px,
  camera-02 dagi 4 px chiziq).
- `camera-02` `record_url` — SABAB TOPILDI (2026-08-29): uning
  `/mpeg4cif` yo'li `MAIN_STREAM_REWRITES` dagi 6 brend naqshining hech
  biriga tushmaydi (`camera_probe.py:392`), shuning uchun
  `suggest_record_url()` `None` qaytaradi. Yechim: naqsh qo'shish yoki
  manzilni qo'lda kiritish — kamera almashtirish qarori bilan birga.
- C1 rasmiy qabul (4 kamera sharti pilotda bajarib bo'lmaydi) va sotuv
  darvozalari (`CHAQIMCHI_AVAILABLE_FEATURES` +
  `CHAQIMCHI_N100_ACCEPTANCE_FILE`, oferta STIR/yurist).

## OCHIQ MUAMMOLAR

**✅ YOPILDI (2026-08-30) — hodisalar mijozgacha yetmasdi**

Qabul darvozasi to'lovchi mijozning funksiyalarini nolga tushirardi.
Uch joydan olindi, jonli tasdiqlandi.  Tafsilot: Tarix, 2026-08-30.

**✅ YOPILDI (tekshirildi 2026-08-31) — `suppressed` heartbeatda BOR**

Jonli heartbeatda `suppressed: 0` keladi (qurilma 0.6.25).  Quyidagi
eski yozuv tarix uchun qoldirildi.

~~Zanjir `suppressed` (qoidalar tashlagan hodisa) ni sanaydi
(`pipeline.py:401`), lekin u heartbeatga CHIQMAYDI.~~  30-avgustdagi
tekshiruvda aynan shu raqam yetishmadi: "hodisa filtrdan o'tdi, lekin
bulutga kelmadi" savoliga masofadan javob berib bo'lmadi va sabab
faqat kutish orqali aniqlandi.  Qo'shilsa keyingi tashxis daqiqalar
emas, soniyalar oladi.

**✅ YOPILDI — vaqt mintaqasi**

`device_tz_offset_min: 300` (Toshkent UTC+5), `clock_skew_sec: -0.7`.
Ertalabki yolg'on trevoga 27-avg **26 ta** → 28-avg **0 ta**.

**✅ YOPILDI — yetim zanjirlar**

`stale_chains: {}`, bitta versiya, `chain_restarts: 2`.

**✅ YOPILDI (kodda) — davomat chegaralari zid edi**

Jonli dalil: `face_crops {written: 0, too_small: 93}` — 93 urinishdan
**0 tasi** o'tgan. Sabab matematik: `0.35 x bbox >= 96 px` uchun
`bbox >= 275 px` kerak, `FACE_MIN_BBOX_RATIO = 0.28` esa 640x360 da
atigi 101 px kafolatlardi. Endi ikkala chegara `limits.py` dagi bitta
formuladan (`face_min_bbox_px`, `face_min_bbox_ratio`).
**Lekin 720p ga o'tmaguncha davomat baribir ishlamaydi** — 360p da
formula halol javob beradi: 0.76, ya'ni amalda imkonsiz.

**⚠ KLIP YOZILMAYDI — SABAB ANIQLANDI (2026-08-31): recorder segment
yozmaydi**

Jonli heartbeat: `clips {written: 0, missing: 6, no_segments: 6,
cut_failed: 0}` va `clips_last_error: "buferda segment yo'q"`.  Ya'ni
ffmpeg kesa olmagani emas — **kesish uchun material yo'q**.  Keyingi
qadam qurilma tomonda: recorder nega buferga yozmayotgani
(`camera-01` da `record_url_set: true`).

Eski tashxis (0.6.22 gacha) — «manzil berilmagan» — noto'g'ri edi:
`clips {written: 0, missing: 2}`, camera-01 da `record_url_set: true`.
Ilgari tashxis "manzil berilmagan" edi va u **noto'g'ri**. 0.6.22 dan
boshlab `missing` ikkiga bo'linadi: `no_segments` (recorder umuman
yozmayapti) va `cut_failed` (ffmpeg kesa olmadi) + `clips_last_error`.
Reliz yetgach javob bitta heartbeat masofasida bo'ladi.

**⚠ DEMOGRAFIYA 6%**

`{attempts: 95, found: 6}`; kunlik: 207 kirishdan 9 tasi (4.3%).
Bir ildizdan — 640x360 oqim. 720p buni ikki barobar yaxshilashi kerak.
Kunlik hisobotda bu holat endi foizsiz, SON ko'rinishida chiqadi
(«O'lchangani 9 kishi: …» — 2026-08-29 qarori).

**⚠ `zone_entered` nol — sabab TOPILDI**

Chizmaning o'zi yaroqsiz: «Taqiqlangan zona» polygoni x∈[0.340, 0.385],
y∈[0.046, 0.102] — 640x360 da **29x20 piksel**, kadr tepasida.
`scene_analytics.py:544` zonani bbox **markazi** bo'yicha tekshiradi va
markaz u yerga tushmaydi. 57 ta eski hodisa yetim zanjirlardan kelgan
va tozalash daqiqasida (26-avg 13:37) to'xtagan.
Xuddi shunday: camera-02 da «kirish» chizig'i **4 piksel** uzunlikda.
Endi admin panelda ro'yxat chiqadi (`cloud/config_health.py`), lekin
**chizmani mijoz bilan qayta chizish kerak**.

**⚠ camera-02 — eng band kamera eng past sifatli oqimda**

Uch kunda 571 ta `line_crossed` (camera-01 da 44 ta), ya'ni do'konning
asosiy sanog'i shu kameradan keladi. Oqimi esa **MPEG-4 CIF (352×288)**
va unda `record_url` yo'q — klip printsipial yozilmaydi. 720p ni
ko'tarmasligi ehtimoli yuqori; almashtirish kerak bo'lishi mumkin.

**⚠ camera-02 paroli `123456`**

Manzilda MD5 ko'rinishida (`e10adc3949ba59abbe56e057f20f883e`).
Mijozning kamerasi va uning qarori, lekin 0.6.24 dan boshlab bu parol
bizning bulutimizda ham turadi (shifrlangan). Mijozga almashtirishni
taklif qilish kerak.

**Sotuvni to'sib turgan ikki darvoza**

- `available_feature_codes()` → `[]`.  **Sabab aniqlashtirildi
  (2026-08-31): `CHAQIMCHI_AVAILABLE_FEATURES` serverda QO'YILGAN**
  (`person_count,queue_length,store_security` — uchalasi ham haqiqiy
  kod).  To'sib turgani — ikkinchi shart: production'da
  `pilot_acceptance_status()["ok"]` bo'lishi kerak, N100 qabul fayli
  esa yo'q.  Deploy preflight buni har safar aytadi: «N100 qabul fayli
  yo'q: public AI funksiyalari sotuvga ochilmaydi».  `cloud/store.py:52`.
- **Oferta tayyor emas:** STIR va rekvizit bo'sh + yurist ko'rigi (B2)
  o'tmagan. Sotuvni ochishdan oldin ikkalasi SHART.

**Texnik**

- **✅ YOPILDI (2026-08-29) — beqaror test:**
  `test_clip_retention_is_configurable`. Ildiz: TestClient ochilishi
  bilan `_maintenance_loop` fon oqimida darhol purge boshlab, testdagi
  `CHAQIMCHI_CLIP_RETENTION_DAYS=60` o'rnatilishidan OLDIN standart
  7 kunni muzlatib olardi; to'liq to'plamda oqim kechikib test saytiga
  yetib borib klipni o'chirardi. Fixture endi fon halqalarini no-op
  qiladi (testlar purge'ni sinxron o'zi chaqiradi).
- **`cloud/store.py` faqat SQLite** — litsenziya, to'lov va portal
  parollari production'da ham SQLite'da (audit YUQORI-10). Shu sabab
  `Dockerfile.cloud` da `--workers 1`. (Raqamli qator o'qish naqshi
  2026-08-28 da profilaktika tariqasida tozalandi.)
- **Rate limit xotirada** (`cloud/ratelimit.py`) — restart bilan
  aylanib o'tiladi (audit O'RTA-9).
- **CSP sarlavhasi yo'q** (audit O'RTA-2).
- **Token `localStorage` da**, server tomonda "chiqish" yo'q (O'RTA-8).
- **AI aniqligi hech qachon o'lchanmagan** (YUQORI-6) — endi asbob bor
  (masofaviy `benchmark` topshirig'i), o'lchov hali olinmagan.
- **Haqiqiy video/model bilan test yo'q** (YUQORI-8) — chegaralar
  kontrakti (`test_face_crop_contract.py`) yopildi, model yo'li esa yo'q.
- **Faqat o'zbek tili** — rus tili yo'q (O'RTA-3).
- **Vision agent (Gemini) deyarli ishlatilmagan** — `vision_observations`
  0 ta. Saytda va'da qilinmagan, lekin funksiya sifatida o'lik.
- **`releases/` da ~1.9 GB eski `.exe`** — 19 ta fayl.

## TUZOQLAR — bir marta yeb bo'lingan

- **Commit xabari «faqat X yetishmaydi» desa ham endpoint ro'yxatini
  SOLISHTIRING.**  `556d33c` eski adminni o'chirishga tayyorlashda
  «Arizalar bo'limi yo'q edi, qo'shildi» deb yozgan;
  `grep -o '/api/v1/admin/[^"]*'` eski va yangi faylda **15 dan ortiq**
  farq ko'rsatdi (qurilma topshiriqlari, diagnostika, funksiya
  biriktirish, masofaviy chizma, reliz boshqaruvi…).  Bir sahifani
  boshqasi bilan almashtirishdan oldin ikkala faylning endpoint
  to'plamini ayirib ko'ring — ikki daqiqalik ish, xato esa bir
  deploydan keyin ko'rinardi.

- **Yozilgan-u hech qachon O'QILMAGAN ustun bo'lishi mumkin.**
  `production_events.line_name` qurilmadan kelib bazaga yozilardi va
  butun kodda bironta ham `SELECT` uni so'ramasdi — ya'ni «qaysi
  eshikdan» savoli oylab javobsiz qolgan, ma'lumot esa joyida turgan.
  Yangi ko'rsatkich so'ralganda avval `grep -rn` bilan **bor narsani
  qidiring**: hisob-kitobning yarmi allaqachon yig'ilgan bo'lishi mumkin.

- **Nom bir saqlagichda, raqam boshqasida.** `site_cameras.label`
  `cloud/store.py` da (SQLite), `production_events` esa
  `cloud/event_store.py` da (production'da PostgreSQL).  Ularni SQL
  bilan biriktirib bo'lmaydi — birlashtirish javob yig'ilayotgan
  qatlamda bajariladi (`_name_doors`).  Bu «bitta so'rov bilan
  hal qilaman» degan urinishni oldindan to'xtatadi.

- **Uzoq yashaydigan snapshotga NOM yozmang.**  `retail_daily` uch yil
  turadi; kamera qayta nomlansa arxiv eski nom bilan qotib qolardi.
  Snapshotda ID, nom esa ko'rsatish paytida.  Xuddi shu sabab bilan
  **chek soni ham** snapshotga yozilmaydi: ega uni ertasi kuni
  kiritadi, snapshot esa kun tugashi bilan muzlaydi.

- **BO'SH va NOL — ikki boshqa javob.**  Kiritilmagan chek soni `null`
  qaytadi («ma'lumot yo'q»), `0` esa «hech kim sotib olmadi».  Panelda
  ham, hisobotda ham ular boshqacha ko'rinadi.  Xuddi shu qoida eski
  kunlardagi `by_door` kalitiga tegishli: kalit yo'q — «saqlanmagan»,
  bo'sh ro'yxat — «o'tish bo'lmagan».

- **Kunlik xabarga qo'shilgan har qator uni O'QILMAYDIGAN qiladi.**
  Chek eslatmasi birinchi variantda har kuni chiqardi va
  `test_a_calm_day_message_stays_short` darhol qulab tushdi.  Yechim:
  eslatma haftada bir marta (dushanba — `_quiet_reason` bilan bir xil
  kun) va faqat 20 dan ko'p odam kirgan kunda.

- **Ro'yxatni RUXSAT emas, TAQIQ qilib yozing.** `REPORT_EVENT_TYPES`
  ruxsat ro'yxati bo'lgani uchun `checkout_unattended` unga tushmay
  qolgan va ega uni oylab hech qayerda ko'rmagan.  Vaqt lentasi shuning
  uchun `TIMELINE_HIDDEN_TYPES` (uch tur) bilan ishlaydi — yangi hodisa
  turi lentaga O'ZI chiqadi.  Qulf:
  `test_a_new_event_type_appears_without_touching_the_list`.
- **Har javob o'z cho'qqisini hisoblasa grafik YOLG'ON bo'ladi.**
  Issiqlik xaritasida soatlarni alohida-alohida so'rash 09:00 dagi uch
  kishini 18:00 dagi uch yuz kishi bilan bir xil qizil qilardi.  Shuning
  uchun `heatmap_by_hour` 24 soatni bitta so'rovda va bitta `peak` bilan
  qaytaradi.  Bu «kichik namunadan foiz chiqarmang» tuzog'ining
  xaritadagi ko'rinishi.
- **«Kadr yo'q» va «kadrga huquq yo'q» — ikki BOSHQA javob.**
  `media_expected` shu ikkisini ajratadi; muddat esa serverdan keladi
  (`dashboard.media_retention_hours`), `.tsx` ga «48» yozilmaydi.
  Ro'yxat ikki joyda (`pipeline.SECURITY_MEDIA_EVENTS` va
  `notify.MEDIA_EVENT_TYPES`) — `cloud` `cv2` tortadigan modulni import
  qila olmaydi; tenglikni `tests/test_media_policy_contract.py` qulflaydi.

- **Hisobotdan hosila bo'lgan raqam hisobot bilan BIRGA o'ladi.**
  Yig'indi jadvali bo'lmasa, xom hodisani o'chirish jimgina statistikani
  ham o'chiradi.  Yangi ko'rsatkich qo'shsangiz o'zingizga savol bering:
  «xom hodisa 30 kundan keyin o'chganda bu raqam qayerdan keladi?»
- **Yig'ish funksiyasi XOM manbadan o'qisin.**  `retail_report` endi
  tugagan kunni yig'indidan qaytaradi; yig'ish uni chaqirsa, o'zi yozgan
  yozuvni qayta ko'chirardi va xato abadiy muzlab qolardi.  Shuning uchun
  `rollup_retail` va `rollup_demography` `_retail_report_from_events` ni
  chaqiradi.
- **Holat faylidagi yangi kalit supervisor'dan ham o'tishi SHART.**
  `tests/test_status_chain.py` buni qulflaydi: `suppressed` qo'shilganda
  aynan shu test ushladi.

- **Bitta darvoza UCH joyda turardi.**  `available_feature_codes()`
  qurilma konfigida, admin biriktirishda (`store.py: feature_quote`) va
  mijoz panelida — uchtasi ham alohida yozilgan edi.  30-avgustda
  birinchisi topilib "zaxira yo'l bor" deb o'ylandi, biriktirish esa
  aynan shu darvoza bilan **422** qaytardi.  Yangi cheklov qo'shsangiz
  `grep -rn` bilan HAMMA chaqiruv joyini sanang.
- **Funksiya ro'yxati o'zgarsa `revision` ni OSHIRING.**  Qurilma
  konfigni faqat revision o'zgarganda qayta o'qiydi
  (`cloud_config.py:925`).  Bulutdagi ro'yxat to'g'rilangani bilan
  qurilma eski keshda qolaveradi — `approve_feature_draft` shu sababdan
  `cloud_feature_revision` ni oshiradi.
- **Biznes hodisasi soatiga 20-30 ta, daqiqasiga emas.**  Tuzatishdan
  keyin 12 daqiqa kutib "ishlamadi" degan xulosa chiqarilayozdi.
  Zanjir daqiqasiga ~100 xom hodisa yasaydi, ularning ko'pi
  `person_detected` va sovutishlarda qoladi.  Tasdiqlash uchun
  **kamida 30-60 daqiqa** kuting yoki `plan_filtered` nisbatiga qarang.

- **`save_camera` yozuvni TO'LIQ qayta quradi** (`config_store.py`):
  chaqiruvchi bermagan maydon JIMGINA o'chadi.  Yangi per-kamera maydon
  qo'shsangiz BARCHA chaqiruvchilarni tekshiring — `_backfill_record_urls`
  rolni aynan shu yo'l bilan o'chirib yuborayozdi.  Qulf:
  `test_the_record_url_backfill_preserves_the_role`.

- **Kamera rolida uch holat bor va ular teng emas:** `""` — eski
  qurilma, rolni BILMAYDI (bulut tegmaydi); `"none"` — ochiq
  "tanlanmagan" (bulut NULL ga tozalaydi); qiymat — o'rnatiladi.
  Yangi kod rolni olib tashlaganda `"none"` yuborishi SHART, aks holda
  o'chirish bulutga hech qachon yetib bormaydi
  (`cloud_config.py:publish_cameras` izohi).

- **`record_url_set` heartbeatda LOKAL konfigdan hisoblanadi**
  (`cloud_config.py:332`), `merge_cameras()` bergan yakuniy rejadan
  emas. Bulut zaxirasidan record manzili ishlayotgan bo'lsa ham panel
  `false` ko'rsatishi mumkin — tashxis qo'yishda ikkalasini ham qarang.

- **`CHAQIMCHI_AVAILABLE_FEATURES` dagi xato kod JIMGINA yutiladi.**
  `available_feature_codes()` noma'lum kodlarni filtrda tashlab
  yuboradi (`cloud/store.py:52`) — `person_counts` deb yozsangiz xato
  chiqmaydi, funksiya shunchaki ochilmaydi. Env qo'ygandan keyin
  natijani API dan tekshiring.

- **Generik kamera `suggest_record_url()` dan o'tmaydi.**
  `MAIN_STREAM_REWRITES` (`camera_probe.py:383`) faqat 6 brend
  naqshini biladi; camera-02 ning `/mpeg4cif` yo'li hech biriga
  tushmaydi → `record_url` avtomatik berilmaydi va bu «usta buzilgan»
  degani emas. Yangi brend uchun naqsh qo'shing yoki manzilni qo'lda
  kiriting.

- **TestClient ochilishi bilan fon halqalari DARHOL ishga tushadi.**
  `_maintenance_loop` birinchi iteratsiyada uyqusiz purge qiladi va
  test env'ini o'rnatilishidan OLDIN o'qib muzlatib oladi — uch
  haftalik beqaror test shundan edi. Cloud testida fon halqasiga
  bog'liq bo'lmagan tekshiruv yozayotgan bo'lsangiz halqalarni no-op
  qiling (`tests/test_cloud_load.py` fixture'i naqsh).

- **`frame_size` kamera sozlamasi haqida hech narsa aytmaydi.**
  Tahlil kadrni doim 640x360 ga keltiradi (`frames_from_source`), ya'ni
  o'lchov natijasidagi `frame_size` har doim shu son. "Kamerani 720p ga
  o'tkazdim" degandan keyin o'zgarish ishlaganini tekshirish uchun
  `native_size` kerak (0.6.25 dan) — u kadrning O'ZIDAN olinadi,
  `CAP_PROP` dan emas (RTSP'da property'lar yolg'on qaytarishi mumkin).

- **Soxta funksiya imzoni TEKSHIRMASA, xatoni yashiradi.**
  `capacity_verdict` faqat nomli argument oladi, chaqiruv esa pozitsion
  edi. Test uni `lambda *a, **k` bilan almashtirgan va bunday soxta har
  qanday chaqiruvni qabul qiladi — natijada o'lchov jonli do'konda 95%
  da yiqildi. Arzon va sof funksiyani (arifmetika) soxtalashtirmang:
  uni HAQIQIY holda chaqiring, qimmat qismini (model, RTSP) esa
  almashtiring. Bu sessiyada shu sinf xato **ikki marta** chiqdi.

- **Kamera manzili qaroriga tegishli.** 0.6.24 dan boshlab qurilma
  RTSP manzilini (parol bilan) bulutga yuboradi va u Fernet bilan
  shifrlanadi. Ilgari teskarisi edi va `test_camera_list_goes_up_to_
  the_cloud` uni qulflab turardi. Qaror sabablari commit `5ef77b6` da.
  **Eski qurilma bo'sh manzil yuboradi va u mavjudini O'CHIRMASLIGI
  shart** — aks holda yangilanish paytidagi bir necha daqiqa do'konning
  sozlamasini yo'q qilardi (`test_an_old_device_does_not_wipe_the_only_copy`).

- **Soxta ma'lumot koddagi xatoni TAKRORLASA, test uni tasdiqlaydi.**
  `benchmark` topshirig'i kamera ro'yxatini ildizdagi `cameras` dan
  o'qirdi, haqiqiysi esa `retail.cameras[].stream_url` da. Test ham
  aynan shu noto'g'ri shakldagi soxta sozlama bergani uchun **yashil**
  edi — xato faqat jonli o'lchovda ko'rindi ("Kamera manzili yo'q",
  holbuki ikkala kamera sozlangan). Soxta ma'lumot HAQIQIY sxemadan
  olinsin: `settings.py` dagi model yoki jonli bazadagi yozuv.

- **Sozlamada `cameras` IKKI joyda bor.** Ildizda
  (`AppSettings.cameras` — veb-kamera uchun eski yo'l, do'kon
  kompyuterida doim bo'sh) va `RetailSettings.cameras` (haqiqiy
  ro'yxat). Ikkinchisida manzil `stream_url`, `url` emas.

- **Tugma qo'yish yetarli emas — natijani ko'rsatish ham kerak.**
  «Sig'imni o'lchash» o'lchovni boshlardi, natija esa
  `device_jobs.result_enc` da qolib ketardi va panelda unga yo'l yo'q
  edi; xabar matni esa "«Diagnostika» da ko'rinadi" deb yolg'on
  aytardi. Yangi amal qo'shsangiz: foydalanuvchi javobni QAYERDAN
  ko'radi?

- **`created_at` bir soniya aniqligida.** Bir kunda ikki marta
  o'lchansa `ORDER BY created_at DESC` tartibi tasodifiy bo'ladi va
  admin eski natijani yangisi deb o'qishi mumkin. `rowid` qo'shilsin.

- **Ikkita JONLI o'lchovni `==` bilan solishtirmang.**
  `test_the_panel_and_the_alert_watch_the_same_disk` disk bandligini
  ikki marta o'lchab tenglikni talab qilardi; to'liq to'plam ishlaganda
  vaqtinchalik fayllar tufayli farq chiqib, test tasodifan yiqilardi
  (`37.07083227 != 37.07083268`). Savol "bir xil YO'L kuzatilyaptimi"
  edi — endi `pytest.approx(..., abs=0.5)`.

- **Ikki fayldagi ikki son bir-birini INKOR QILISHI mumkin va buni
  hech qaysi test ko'rmaydi.** `scene_analytics.FACE_MIN_BBOX_RATIO`
  ramka uchun 0.28 ga ruxsat berardi, `pipeline.FACE_MIN_CROP_PX` esa
  kesma uchun 96 px talab qilardi. 640x360 da birinchisi 101 px beradi,
  ikkinchisi 275 px talab qiladi — ya'ni chegara **hech qachon**
  o'tolmasdi. Har modul alohida to'g'ri edi, 1 835 test o'tardi,
  davomat esa oylab ishlamadi. Ikki modul o'rtasidagi kelishuvni
  tekshiradigan test kerak — `tests/test_face_crop_contract.py`.

- **`int()` yaxlitlashi chegarani bir piksel bilan buzadi.**
  `96 / 0.35 = 274.3`, lekin `int(274 * 0.35) = 95` — 274 px ramka
  baribir rad etilardi. `limits.face_min_bbox_px()` natijani taxmin
  qilmaydi, TEKSHIRADI (`while` bilan).

- **"Kalit so'ralyaptimi" testi kalit UNUTILGANINI ko'rmaydi.**
  `test_status_chain.py` uch marta takrorlangan xatoni to'xtata olmasdi,
  chunki u faqat "so'ralgan kalit bormi" ni tekshirardi: kalit
  unutilganda uni hech kim so'ramaydi va test ham jim qoladi. Endi
  **teskari yo'nalish** ham qulflangan — ishlab chiqarilgan har kalit
  yo ketishi, yoki sababli ro'yxatga yozilishi shart.

- **Kod to'g'ri bo'lishi yetarli emas — u CHAQIRILISHI ham kerak.**
  Diagnostika paketi to'liq yozilgan edi (yig'uvchi, endpoint, jadval,
  14 kunlik retention, admin ko'rinishi) va `device_diagnostics`
  jadvalida **0 qator** turardi: yuborishning yagona yo'li do'kondagi
  paneldagi tugma edi. Yangi funksiya qo'shsangiz: uni kim va qachon
  chaqiradi?

- **`scripts/` do'kon kompyuterida YO'Q.** Windows payload'iga faqat
  `chaqimchi_ai` ko'chiriladi (`build_windows_payload.py: CODE_DIRS`).
  Shu sabab "avval `benchmark_n100.py` bilan o'lchang" degan tavsiya
  bajarib bo'lmaydigan edi — o'lchov ma'noli bo'ladigan yagona mashinada
  skript yo'q. Qurilmada ishlashi kerak bo'lgan kod `chaqimchi_ai`
  ichida bo'lsin.

- **Har yangi `device_jobs.kind` uchun ALOHIDA migratsiya kerak.**
  Mavjud migratsiya `clean_chains` ni tekshiradi, ya'ni undan keyin
  qurilgan bazani o'tkazib yuboradi. `benchmark` uchun alohida blok
  yozildi va `test_an_old_database_learns_the_new_job_kind` uni
  qulfladi (eski sxema qo'lda yasab sinaladi).

- **Chizilgan zona/chiziq YAROQSIZ bo'lishi mumkin va tizim jim
  turadi.** 4 pikselli chiziq va 29x20 pikselli zona saqlandi, revision
  o'sdi, qurilma qabul qildi — faqat hodisa yo'q edi. Nosozlik "xato"
  ko'rinishida emas, JIMLIK ko'rinishida keladi.
  `cloud/config_health.py` endi buni admin uchun ko'rsatadi.

- **Hisobot kichik namunadan foiz chiqarmasin.** Kunlik xabar 207
  kirishdan 9 tasi o'lchanganda "11% ayol · 89% erkak" deb FAKT
  sifatida yozardi. Ikki xato birga: n=9 da bitta odam foizni 11
  punktga siljitadi, va 4% qamrovda o'lchanganlar tasodifiy tanlanmagan
  (kameraga eng yaqin o'tganlar) — natija shovqinli emas, **OG'GAN**.
  `trust_score.py` bu intizomni allaqachon to'g'ri bajaradi; hisobot
  ham endi shunday.

- **SQLite testda o'tadi, PostgreSQL production'da yiqiladi.**
  `cloud/event_store.py` da `fetchone()[0]` yozmang. `sqlite3.Row`
  raqamli indeksni qo'llaydi, psycopg `dict_row` esa **yo'q** —
  `KeyError: 0`. 1 800+ test o'tib turgan holda marshrut jonli serverda
  48 soat davomida har safar 500 bergan. `SELECT COUNT(*) AS nom` qilib
  `self._dict(row)["nom"]` o'qing. `test_owner_notifications.py` endi
  naqshning O'ZINI qulflaydi. (`cloud/store.py` da bu naqsh to'g'ri —
  u faqat SQLite.)

- **Soat to'g'ri, mintaqa noto'g'ri — `clock_skew_sec` buni KO'RMAYDI.**
  Do'kon 5070 kompyuteri UTC ni 0,8 soniya aniqlikda bilardi va
  mintaqasi UTC+3 edi (Toshkent UTC+5). Natijada tungi nazorat ikki
  soat surilgan: ertalab 08:30–10:30 orasida yolg'on kritik trevoga,
  kechqurun 22:00–00:00 orasida esa — o'g'rilik uchun eng ehtimolli
  ikki soat — nazorat UMUMAN yo'q. Endi zanjir `limits.store_now()` dan
  o'qiydi va mashina zonasiga qaramaydi; heartbeat esa
  `device_tz_offset_min` yuboradi.

- **Windows'da vaqt mintaqasini o'zgartirish ishlab turgan jarayonga
  ta'sir qilmaydi.** Dastur mintaqani START paytida o'qiydi. Mijoz
  soatni to'g'rilagach zanjir **qayta ishga tushirilishi** shart —
  aks holda hech narsa o'zgarmaydi va buni tashqaridan sezib
  bo'lmaydi. Masofadan: admin paneldagi `clean_chains` tugmasi
  (supervisor darhol yangisini ko'taradi).

- **Hisoblagich qo'shsangiz — ZANJIRNI ham tekshiring.** Raqam cloudga
  yetguncha to'rtta qo'ldan o'tadi: `pipeline._stats()` →
  `service.write_status()` → `supervisor.status()` →
  `cloud_config.send_heartbeat()`. Bittasini unutish qiymatni JIMGINA
  nolga aylantiradi — hisoblagich bor, so'rov bor, javob bor, faqat
  doim nol. Bu **uch marta** sodir bo'lgan (`analyzed`/`errors`,
  `fps`/`pressure`, `face_crops`/`demography`). Oxirgisi uch kun
  davomida "davomat o'chiq" degan noto'g'ri tashxis berdi.
  `tests/test_status_chain.py` endi zanjirni qulflaydi.

- **`loitering` uchun rasm ATAYLAB olinmaydi.** `SECURITY_MEDIA_EVENTS`
  ga uni qaytarmang. 2026-08-21 o'lchovi: 7,4 soatda 321 hodisadan 300
  tasi loitering edi va 29 MB rasmning 28,9 MB'i (99,6%) shundan
  chiqqan — kunlik 500 talik snapshot chegarasining 302 tasi kechgacha
  yeb bo'lingan, ya'ni haqiqiy o'g'rilik hodisasiga rasm ilinmay
  qolardi. Sabab `pipeline.py:66-77` da yozilgan.

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

## PANEL QOIDALARI — eski testlardan ko'chirilmaganlari

`tests/test_panel_v2.py` eski `owner.html`/`admin.html` uchun yozilgan
47 qulfning davomi.  Ko'chirilganlari o'sha faylda; quyidagilar
ko'chirilmadi va har birining sababi bor.  F4 da bu ro'yxat qayta
ko'riladi: «hali tekshirilmagan» guruhi yo qulflanadi, yo sababi bilan
o'chiriladi.

**React'da tuzilma boshqacha — qoida ma'nosini yo'qotgan:**
- `test_owner_panel_logs_in_from_the_link`, `test_stored_session_wins_over_the_link`
  — `loginFromLink()`/`showApp()` funksiyalari yo'q; token yo'li
  `api.ts` da, qulf `test_link_login_uses_the_token_endpoint`.
- `test_owner_panel_has_one_operational_screen_without_tabs`,
  `test_owner_tabs_fail_independently` — React panelda bo'limlar `NAV`
  orqali va har sahifa o'z so'rovini o'zi qiladi.
- `test_admin_panel_has_a_left_sidebar_with_six_sections`,
  `test_every_admin_section_can_actually_load_its_data` — `NAV[].deps ⊆
  LOADERS ⊆ S` zanjiri faqat eski adminda edi.
- `test_admin_panel_translates_raw_api_codes` — F2 dan server xatoni
  matn + kod qilib qaytaradi (`cloud/errors.py: ApiError`).
- `test_the_attendance_camera_can_be_chosen_in_the_panel` — davomat
  kamerasi endi «kirish» ROLIDAN keladi (`af08057`), alohida tanlagich
  yo'q; qulf `test_the_camera_role_is_offered_but_never_forced`.
- `test_owner_panel_does_not_break_binary_uploads` — `api.ts` shu
  qoidani bajaradi; qulf `test_employee_photos_survive_an_iphone` ichida.
- `test_owner_panel_is_light_branded_not_admin_dark`,
  `test_admin_panel_is_light_and_reuses_the_customer_design_system` —
  ikkala panel bitta `styles.css` dan; qulf
  `test_both_panels_share_one_design_system`.

**Hali tekshirilmagan — F4 da ko'chiriladi** (React'da bor-yo'qligi
tekshirilmagan yoki YO'Q):
- `test_owner_staff_tab_disappears_when_the_feature_is_off` — «Xodimlar»
  bo'limi funksiya yopiq saytda ham `NAV` da turadi (`owner.tsx:28`);
  eski qoida: 403 o'rniga tugmaning o'zi chizilmasin.
- `test_admin_panel_has_no_native_dialogs` — React adminda
  `window.confirm` QAYTGAN (`admin.tsx:139`, hisobni to'langan deb
  tasdiqlash).  Eski sabab `prompt()` haqida edi (matn kiritishda
  bitta harf xato — amal bajarilmasdi); `confirm` uchun sabab
  yengilroq, F4 da qaror.
- `test_admin_customer_page_is_deep_linkable` — `router.ts` faqat bo'lim
  ID'sini o'qiydi, `customers/{id}` yo'q; «diqqat talab qiladi»
  ro'yxatidan mijozga to'g'ridan-to'g'ri o'tib bo'lmaydi.
- `test_admin_panel_promises_the_same_interval` — reliz boshqaruvi React
  adminda yo'q; `tests/test_windows_installer.py` da `xfail(strict)`.
- `test_owner_panel_shows_camera_previews_and_refreshes`,
  `test_owner_can_ask_for_a_fresh_camera_frame` — React'da `/preview`
  va `requestFrame` bor, qulf yozilmagan.
- `test_owner_drag_does_not_storm_the_server` — `GeometryEditor.tsx`
  sudrashda so'rov yubormasligi tekshirilmagan (eski panelda har
  `pointermove` da issiqlik xaritasi qayta so'ralardi).
- `test_owner_uses_the_shop_day_not_utc` — `api.ts` da `tashkentDay`
  bor, «Kecha» tugmasi uni ishlatishi qulflanmagan (eski xato: yarim
  tundan 05:00 gacha ikki kun oldingi hisobot so'ralardi).
- `test_owner_settings_explain_what_each_number_does` («navbat zonasisiz
  ishlamaydi» izohi), `test_owner_shows_the_data_it_already_fetches`,
  `test_owner_hourly_chart_can_show_occupancy` — tekshirilmagan.

**Eski adminning React adminga ko'chirilmagan vositalari** (endpoint
bo'yicha, `556d33c` dan keyin o'lchandi):
`sites/{id}` tafsilot sahifasi (config_health: `geometry_problems`,
`feature_problems`, `role_problems`), `sites/{id}/camera-inventory`
(masofaviy kamera va chizma — 2026-08-21 qarori),
`sites/{id}/jobs/clean-chains` va `jobs/benchmark`,
`sites/{id}/diagnostics`, `sites/{id}/features/draft|quote|approve`
(**sotuv darvozasi**), `sites/{id}/faces`, `sites/{id}/onboarding`,
`accounts/{id}` va `installer-assignments` (Jamoa), `alerts` +
`alerts/test`, `business-templates`, `payments/providers`,
`updates-paused`, `windows-releases`.  Qulf:
`test_the_admin_can_fix_a_shop_remotely` (`xfail(strict)`).

**Ega panelida eski `owner.html` ga nisbatan yo'q** (React owner 08-24
dan production'da — yo'qotish yangi emas, lekin F4 da qaror kerak):
`announcements`/`speak` (do'kon gapiradi — bot tugmalari orqali
ishlaydi), `attendance.csv`, `shifts`/`shifts.csv`, `faces/events`
(hodisadan yuz qo'shish), `faces/photos/{id}` (rasmni o'chirish),
`digest`, `revenue`, `trust-score`, `trend`, `subscription`, `health`,
`features` — oxirgi oltitasi `dashboard` ichiga yig'ilgan bo'lishi
mumkin, tekshirilmagan.

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

### 2026-09-08 — Eski panellar o'chirildi, qoidalar React manbasiga ko'chdi (`73cc704`)

Nima: `cloud/static/owner.html` va `admin.html` repodan ketdi; `/owner`
va `/admin` faqat React.  Eski panel uchun yozilgan 47 qulf
`tests/test_panel_v2.py` ga, uchtasi (`test_plans`, `test_zone_editor`,
`test_windows_installer`) React manbasiga qaratildi.  `make test` endi
`build_i18n.py --check` ni ham yuritadi.  Yo'l-yo'lakay: iPhone HEIC →
JPEG (`api.ts: toJpeg`) eski paneldan ko'chirilmay qolgan edi —
qaytarildi; sidebar'da aloqa raqami (`SUPPORT_PHONE`, sayt bilan bir
xil — test qulflaydi).

Nega: ikki avlod har o'zgarishni ikki joyda talab qilardi
(ARXITEKTURA §10.7).

Qayerda: `tests/test_panel_v2.py`, `tests/test_plans.py`,
`tests/test_zone_editor.py`, `tests/test_windows_installer.py`,
`Makefile`, `docs/PRODUCTION_RUNBOOK.md` §5,
`docs/ARXITEKTURA_XARITASI.md` §9/§10.7,
`frontend/src/{api.ts,components.tsx,owner.tsx,styles.css}`,
`cloud/static/v2/` (bundle).

Test: `test_panel_v2.py` (47 ta, shundan bittasi `xfail`), ikki
`xfail(strict)`: `test_the_admin_can_fix_a_shop_remotely`,
`test_admin_panel_promises_the_same_interval` — vosita ko'chirilgach
«kutilmagan o'tish» beradi va belgi olinadi.

Diqqat: **React adminda eski adminning 15+ vositasi yo'q** — `556d33c`
xabari «faqat Arizalar» degan edi.  Ro'yxat «PANEL QOIDALARI» da; F4
yopmaguncha shox deploy qilinmaydi.  `owner.css`/`panel.css` diskda
qoldi — `pay.html` hali ularni ishlatadi (F3 da ketadi).

### 2026-09-07 — F1 dizayn tizimi va F2 til yadrosi (`0fca9e2`, `8a1c1cf`, `ed5b777`)

**F1 — tokenlar va tema.**  Palitra to'rt faylda takrorlangan edi
(`frontend/src/styles.css`, `site.css`, `owner.css`, `panel.css`);
endi `cloud/static/tokens.css` — yagona manba, sayt uni `@import` bilan,
panel esa Vite orqali oladi.  `styles.css` dagi **~130 ta** qattiq
yozilgan rang tokenga ko'chirildi — ularsiz dark rejim ishlamasdi.
Tema uch holatli (yorug'/qorong'i/tizim) va **birinchi chizishdan
oldin** qo'yiladi.

**F2 — til yadrosi.**  Uch qatlamli yechim: yopiq ro'yxatdan kelib
chiqadigan matn (hodisa nomlari) panelda **koddan** chiziladi; kanal
serverniki bo'lgan matn (Telegram, CSV) serverda; xato esa
**matn + kod** bo'lib qaytadi.

Ikkita tuzoq oldindan yopildi:
1. `HTTPException(detail=dict)` ishlamaydi — FastAPI lug'atni javob
   ildiziga qo'yadi va `api.ts` dagi `body.detail` obyektga aylanib
   mijoz `[object Object]` ko'rardi.  Shuning uchun `ApiError`.
2. `BackgroundTasks` so'rov kontekstini meros oladi — fon rejimidagi
   Telegram xabari noto'g'ri tilda ketardi.  Telegram/CSV tomonida til
   **majburiy argument** (`tg(lang, key)`), ya'ni bu xatoni yozib
   bo'lmaydi.

**Yo'l-yo'lakay tuzatilgan xatolar:**
- `api.ts` xato matnini `body.detail` dan olardi, `RequestValidationError`
  esa uni ro'yxat qilib qaytaradi → `[object Object]`.
- `?v=` kesh tokeni 13 sahifada eskirgan edi (test faqat `site.html` ni
  qaraardi).  Endi hamma sahifa tekshiriladi.
- `list_members` ustunlarni aniq sanaydi — `language` unga ham
  qo'shildi, aks holda digest jimgina `None` olardi.

### 2026-09-06 — Rebrending rejasi tasdiqlandi va kutib turgan ish deploy qilindi (`b1d13a5`, `6bf4e87`)

**Rebrending.** Mahsulot **ENES Monitoring** ga, domen **enes.uz** ga
o'tadi; sayt va ikkala panel yangi dark-first dizaynga, hammasi
UZ/RU/EN va dark/light bilan.  To'liq reja va o'lchovlar:
`~/.claude/plans/ok-biz-rebrending-qilmoqchimiz-ancient-wilkes.md`.

Tekshiruvda chiqqan asosiy sonlar: `chaqimchi` so'zi **316 faylda**,
`chaqimchi.uz` **168 marta**, **132 ta** `CHAQIMCHI_*` sozlama;
tarjima qilinadigan matn **~2 000 kalit** (~4 000 tarjima);
mehnat **~25-33 ish kuni**.  `enes.uz` ro'yxatdan o'tgan, lekin
ahost.uz parkovkasida (`185.196.212.52`) — DNS Contabo'ga ko'chiriladi.

**Deploy.** 6-sentabrgacha uchta commit deploy qilinmasdan turgan edi.
Chiqarildi va jonli tasdiqlandi (yuqoridagi HOZIRGI HOLAT).

**Yo'l-yo'lakay topilgan xato:** `test_energy_is_computed_from_measured_uptime`
sentabrda qulab tushdi.  `_add_uptime` bucketlarni **UTC** oy boshidan
yozardi, `/admin/finance` esa oyni **Toshkent** chegarasi bilan kesadi —
oxirgi 5 soat oynadan chiqib ketardi (720 o'rniga 715).  Avgustda
(31 kun) oyna 744 soat bo'lgani uchun farq yashirin qolgan; 30 kunlik
oy boshlanishi bilan ko'rindi.  Mahsulot kodi to'g'ri, test moslandi.

### 2026-09-06 — Avtomatik konversiya (capture rate) — algoritmik yadro (`commit qilinmagan`)

Ega qarori: **moslashuvchan (A1+A2)** va **hozir yozib qo'yish** (reliz
soak tugagach). Sof, testlangan yadro qo'shildi (qurilma pipeline'iga
HALI ulanmagan — soak):

- `chaqimchi_ai/retail/conversion.py: SeenCounter` — bir kamerada oynada
  ko'ringan noyob odam soni (capture rate maxraji). Bir kadrlik xato
  deteksiya odam deb sanalmaydi (`min_frames`, standart 2); bir track
  oynada bir marta; oynadan keyin qaytsa yangi tashrif (line_crossed
  re-entry mantiqi).
- `cloud/value.py: capture_rate` + `capture_rate_line` — «yaqinlashdi →
  kirdi (foiz)». Chekli konversiya bilan bir xil intizom: `passed` yo'q →
  javob yo'q, kichik namunada foiz yo'q, «100% dan ortiq» chiqmaydi.
- `cloud/value.py: select_passed` — adaptiv maxraj: tashqi kamera (A2)
  ustun, bo'lmasa kirish (A1).

**Qoladi (keyingi qadam):** (1) qurilma — SeenCounter'ni
`scene_analytics.py` treklariga ulash va per-kamera `seen` ni cloudga
yuborish (reliz, soak tugagach); (2) cloud — `seen` ni per-kun saqlash,
`retail_report` ga `capture` bloki + digest qatori + panel. Transport
qarori ochiq: aggregat event yoki heartbeat maydoni.

### 2026-09-06 — Davriy (oylik) hisobot eksporti qo'shildi (`commit qilinmagan`, faqat cloud+panel)

`GET /api/v1/owner/report.csv` endi `?start=&end=` ni ham oladi (≤31 kun,
raqobatchining branch-summary'idek): kuniga bitta qator + **Jami**.
Ustunlar — sana, kirdi/chiqdi, chek, konversiya %, ayol/erkak %, yosh
guruhlari, gavjum soat, xavfsizlik. Jami qatoridagi konversiya foizi
**yig'indidan** qayta hisoblanadi (kunlik foizlar o'rtachasi emas — kam
kirgan kun ko'p kirgan kun bilan teng vaznlansa yolg'on chiqardi).
Panelda «Oylik (Excel)» tugmasi (oxirgi 30 kun). Testlar: HTTP (oraliq,
422 teskari/uzun) + builder (jami yig'indidan). `make lint`, TS toza.

### 2026-09-06 — Kunlik hisobotni Excelda (CSV) yuklash (`commit qilinmagan`, faqat cloud+panel)

Raqobatchida bor, bizda yo'q edi: hisobotni Excel qilib yuklash
(RetailSolution «branch-summary export»). Qo'shildi — **faqat cloud +
panel, soakka to'qnashmaydi**:

- `GET /api/v1/owner/report.csv?date=` — kunlik yakun: kirdi/chiqdi,
  ichkarida, gavjum soat, chek+konversiya, mijoz portreti (tarif ochiq
  bo'lsa) va **xavfsizlik** (ularda yo'q) + soat/eshik bo'yicha bo'limlar.
- Panel bilan bir manba: `_owner_report_dict()` — endpoint ham, CSV ham
  shundan oladi (demografiya darvozasi va konversiya bir joyda).
- **Yangi bog'liqliksiz:** `.xlsx` emas, BOM'li UTF-8 CSV — Windows
  Excelda o'zbekcha bilan to'g'ri ochiladi (smena/attendance eksporti
  ham shu yo'l). `openpyxl` cloudda yo'q, soak/deploy davrida qo'shilmadi.
- Panel: Hisobotlar sahifasida «Kunlik hisobot (Excel)» tugmasi
  (`downloadDailyReportCsv`, `mediaObjectUrl` orqali — `<a download>`
  Bearer yubora olmaydi). Eski 14-kunlik CSV «14 kunlik CSV» bo'lib qoldi.
- Testlar: `test_cloud_events_owner.py` (HTTP: 200, content-type, BOM,
  fayl nomi, raqamlar, auth 401) va `test_owner_report.py` (builder:
  konversiya, bo'sh portret chiqmaydi, xavfsizlik). `make lint` toza,
  TS typecheck toza.

Bu **A bosqich (avtomatik konversiya)** ning cloud «plumbing»i ham:
hisobotda konversiya bor. A1 ning qurilma sanash logikasi — **soak
tugagach**, qurilma relizi bilan. Batafsil:
[RAQOBAT_RETAILSOLUTION.md](RAQOBAT_RETAILSOLUTION.md) §7.

### 2026-09-06 — Raqobat tahlili: RetailSolution.ai (`commit qilinmagan`, faqat hujjat)

Raqobatchi to'liq ko'rildi: sayt, `/uz/docs` (Integration API — ochiq
hujjat) va mijoz paneli (Zar Bazar akkaunti). Tahlil va reja:
[docs/RAQOBAT_RETAILSOLUTION.md](RAQOBAT_RETAILSOLUTION.md).

**Ular:** faqat marketing analitikasi — avtomatik konversiya (tashqi
trafik ÷ kirgan), mijozni yuzidan tanish (sodiqlik, 1.2M so'm tarif),
yosh/jins, ko'p filial, XLSX + integratsiya API. Xavfsizlik ularda YO'Q.
Zaifligi: xaridor yuz kadri va xodim parol hashi ularning API'sidan
tashqariga chiqadi ("lokal" desa ham).

**Biz ustun:** video do'kondan chiqmaydi, xavfsizlik signali+klip,
mijoz O'Z Windows/NVR'ida, ~3-4× arzon, o'zbekcha+Telegram, offline
outbox, AI yordamchi.

**Ega qarorlari (2026-09-06):** (1) birinchi ish — avtomatik konversiya;
(2) mijozni yuzidan tanish — QILAMIZ, lekin **lokal, rasmsiz** (yuz
bulutga ketmaydi); bu `DOKON_MVP.md` "mijoz Face ID yo'q" bandini
o'zgartiradi va huquqiy hujjatlar (oferta/maxfiylik/rozilik) yangilanishi
kerak; (3) maqsad — yakka do'kon + arxitekturani tarmoqqa tayyorlash.

**Keyingi qadam:** avtomatik konversiya. Ega A1 (qo'shimcha kamerasiz,
capture rate — tavsiya) yoki A2 (tashqi kamera) ni tanlaydi — batafsil
hujjatning §5.A da.

### 2026-08-31 — Eshik bo'yicha sanoq va konversiya: «200 kirdi → 100 chek» (`0a5c3e3`, deploy qilindi)

Nima: ega endi (1) qaysi eshikdan necha kishi kirganini, (2) nechta
tashrif xaridga aylanganini ko'radi.  Chek sonini o'zi kiritadi —
paneldan yoki Telegramdan bitta xabar bilan (`/chek 100`, kecha uchun
`/chek 100 kecha`).  Kunlik hisobotda yangi qator: «🧾 100 chek / 200
kirgan — har 2-mijoz sotib oldi».

Nega: eshik nomi (`line_name`) qurilmadan kelib bazaga yozilardi-yu
butun kodda HECH QAYERDA o'qilmasdi — ko'p eshikli do'kon bitta
yig'indi ko'rardi va yon eshik kunlab yopiq turganini bilmasdi.
Konversiya esa umuman yo'q edi: kirish sanog'i bizda, chek soni faqat
egada (kassa integratsiyasi yo'q va yaqin rejada ham yo'q).

Qayerda: `cloud/event_store.py` (`_retail_report_from_events` → `by_door`,
`daily_sales` jadvali + `save_daily_sales`/`daily_sales`, purge
yig'indi bilan bir muddatda), `cloud/value.py` (`conversion`,
`conversion_line`, `MIN_VISITORS_FOR_CONVERSION`), `cloud/main.py`
(`_name_doors`, `_with_sales`, `_owner_day`, `GET/PUT /api/v1/owner/sales`,
`/chek` bot buyrug'i, `MAX_DAILY_RECEIPTS`), `cloud/digest.py`
(konversiya qatori + dushanbadagi eslatma), `frontend/src/Numbers.tsx`
(yangi), `owner.tsx` (Hisobotlar sahifasiga ulandi), `types.ts`,
`styles.css`.

Test: `tests/test_daily_sales.py` (13 ta, yangi),
`tests/test_owner_report.py` (+4 eshik testi),
`tests/test_retail_rollup.py` (+2 — eng muhimi
`test_the_door_split_survives_into_the_daily_rollup`: xom hodisa
o'chgandan keyin ham taqsimot qoladi), `tests/test_cloud_events_owner.py`
(+9 API va bot testi), `tests/test_events_ui.py` (+7 struktura testi).
Jami **2 034 test** yashil.

Diqqat: kamera NOMI hisobotning o'ziga (`retail_daily.report_json`)
yozilmaydi — yig'indi uch yil yashaydi, kamera esa qayta nomlanishi
mumkin.  Snapshotda ID, nom esa har javobda `site_cameras.label` dan
qo'shiladi (`_name_doors`).  Ikkalasi ikki BOSHQA saqlagichda, ya'ni
SQL bilan biriktirib bo'lmaydi.

Diqqat: chek soni ham hisobotning o'ziga yozilmaydi — ega uni ko'pincha
ERTASI kuni kiritadi, yig'indi esa kun tugashi bilan muzlab qoladi.
`_with_sales` uni har javobda qo'shadi.

Diqqat: deploydan oldingi kunlarda `by_door` kaliti umuman YO'Q.  Panel
buni «saqlanmagan» deb aytadi — nol ko'rsatish «o'sha eshikdan hech kim
kirmadi» degan yolg'on bo'lardi.

### 2026-08-31 — Hodisalar vaqt lentasi, agent javobida grafik, xarita soat bo'yicha (`6ffdbbd`, `2f04bbf`, `c3c79b6`)

Nima: ega endi kun bo'ylab NIMA bo'lganini bir qarashda ko'radi.  Uchta
ekran: (1) Hodisalar — 24 ustunli vaqt lentasi + kadrli kartochkalar,
soatga bosilsa ro'yxat o'sha soatdan; (2) AI yordamchi javobi ostida
o'sha lenta, manba soatlari belgilangan; (3) Issiqlik xaritasida «Soat
bo'yicha» rejimi — slayder, ijro/to'xtatish va butun kun uchun bitta
rang shkalasi.

Nega: hodisalar ro'yxati «kichik matn qatori + Rasm tugmasi» edi va
tugma amalda hech qachon chiqmasdi (eski panelda `_decode_event(public)`
kalitlarni olib tashlaydi).  Issiqlik xaritasi uchun soatlik ma'lumot
2026-08 dan beri yig'ilib turardi (`heatmap_hourly`), lekin uni ko'radigan
UI yo'q edi.  Ega qarori (2026-08-31): birinchi bosqich — ko'rinish.

Qayerda: `cloud/event_store.py` (`TIMELINE_HIDDEN_TYPES`,
`events_timeline`, `list_events(since,until)`, `heatmap_by_hour`),
`cloud/main.py` (`/owner/events/timeline`, `_tashkent_window`,
`owner_events?date&hour`, `owner_heatmap?by=hour`,
`dashboard.media_retention_hours`, `owner_events.media_expected`),
`cloud/notify.py: MEDIA_EVENT_TYPES`, `cloud/vision_agent.py:_answer`
(manbaga `event_type`), `frontend/src/charts.tsx: Timeline`,
`frontend/src/EventTimeline.tsx` (yangi), `EventEvidence.tsx` (qayta
qurildi), `VisionAgent.tsx`, `Heatmap.tsx` (yangi — `owner.tsx` dan
ko'chirildi), `api.ts` (`tashkentHour/tashkentDay/tashkentToday/hoursSince`),
`types.ts`, `styles.css`.

Test: `tests/test_events_timeline.py` (15 ta) — eng muhimi
`test_the_timeline_covers_the_whole_day_not_the_last_500_events`: 600 ta
hodisadan ertalabki 03:00 dagisi ko'rinishi qulflangan, ya'ni
`limit=500` yo'liga qaytib bo'lmaydi.
`tests/test_media_policy_contract.py` (4 ta) qurilma va panel bitta
ro'yxatni bilishini qulflaydi.  `tests/test_heatmap.py` ga 6 ta
(`test_every_hour_is_coloured_against_the_same_peak` — cho'qqi butun
kundan).  `tests/test_events_ui.py` (20 ta struktura testi).
Jami 1 996 test yashil.

Diqqat: hammasi FAQAT React panelga yozildi — `cloud/static/owner.html`
ga tegilmadi.  Deploydan oldin serverda `CHAQIMCHI_UI_V2_OWNER` ni
tekshiring («env pini kodni yengadi»).  Qurilma relizi kerak emas, ya'ni
soak muzlatishi buzilmaydi.

Diqqat: `test_connect_ui.py:test_a_locked_heatmap_looks_like_an_offer_not_a_breakage`
endi `Heatmap.tsx` ni o'qiydi (ekran `owner.tsx` dan ko'chdi) — kafolat
o'zgarmadi.

### 2026-08-30 — Kunlik raqamlar endi xom hodisalardan alohida yashaydi (0.6.29)

Nima: `retail_daily` va `retail_hourly` jadvallari paydo bo'ldi; hisobot
tugagan kunni o'shandan o'qiydi, bugungi kunni esa avvalgidek jonli.
Media (rasm, yuz kadri, klip) endi 48 soat yashaydi.

Nega: panelning har bir raqami xom `production_events` dan qayta
hisoblanardi va xom hodisalar tarif muddatida o'chadi.  Eng eski hodisa
21-avgust, lite tarifi 30 kun — ya'ni **20-sentabrda** o'sha kunlarning
raqamlari ham hodisalar bilan birga ketishi kerak edi.  Demografiya
uchun bu allaqachon hal qilingan edi (`demography_daily`), qolgan
raqamlar uchun yo'q.  Yo'qotish hali BOSHLANMAGAN — uch hafta oldin
ushlandi.

Qayerda: `cloud/event_store.py` (`retail_daily`/`retail_hourly` DDL,
`rollup_retail`, `rollup_pending_retail`, `purge_retail_rollups`,
`retail_rollup`, `_retail_report_from_events`, `_stored_entered_by_day`,
`purge_media_older_than`), `cloud/main.py` (`_rollup_site_history`,
`MEDIA_RETENTION_HOURS_DEFAULT`, `_media_retention_hours`),
`cloud/config_health.py` (kunlik jimlik tekshiruvi),
`cloud/static/oferta.html`, `privacy.html`, `rozilik-shabloni.html`.

Test: `tests/test_retail_rollup.py` (8 ta) — eng muhimi
`test_the_rollup_matches_the_live_report`: yig'indi va hisobot AYNAN bir
xil javob berishi qulflangan, aks holda mijoz qaysi raqamga ishonishni
bilmasdi.  `test_a_finished_day_survives_the_purge` xom hodisa
o'chirilgandan keyin ham raqam qolishini tekshiradi.
`test_media_dies_in_48_hours_but_the_event_stays` hodisa qatori
o'chmasligini qulflaydi.

Diqqat: media bayrog'i KALITDAN mustaqil tozalanadi.  Qurilma hodisani
«rasmim bor» deb yuborib rasmni keyin yuklaydi; yuklash yiqilsa bayroq
qoladi-yu kalit kelmaydi.  Jonli bazada shunday **39 ta** qator bor edi
va panel ular uchun 404 beradigan tugma ko'rsatardi (0.6.29 da yopildi).

Diqqat: `purge_clips_older_than` va `purge_face_media` OLIB TASHLANDI —
ularning o'rniga bitta `purge_media_older_than`.  Uchta alohida muddat
(klip 7 kun, yuz 14 kun, rasm 30 kun) bir joyda ko'rinmasdi va
uzoqlashib ketardi.  `CHAQIMCHI_CLIP_RETENTION_DAYS` va
`CHAQIMCHI_FACE_RETENTION_DAYS` o'rniga
`CHAQIMCHI_MEDIA_RETENTION_HOURS` (standart 48).

### 2026-08-30 — Do'kon besh kun hodisa yubormagan edi (`commit qilinmagan`, 0.6.27)

Nima: mijozning hodisalari qaytdi — 29-avgustdan beri birinchi
`line_crossed` 30-avgust 13:14 da bulutga yetdi.  Qurilmada tashlanish
**100% dan 74% ga** tushdi (qolgani normal).

Nega: bulut qurilmaga bo'sh funksiya ro'yxati yuborardi va
`retail_event_filter` bo'sh ro'yxatni ko'rib HAR BIR biznes hodisasini
rad etardi — kuniga ~7 600 ta.  Ildizi: `available_feature_codes()`
qabul darvozasi.  U 2026-08-24 da qo'yilib 08-28 deployi bilan jonli
chiqqan, qurilma esa 0.6.24 ga yangilanib qayta ishga tushgach yangi
(bo'sh) sozlamani olgan.  Darvoza tuzilishi bo'yicha noto'g'ri joyda
edi: obunasi tugagan sayt unga yetib bormaydi (yuqorida bo'sh ro'yxat
oladi), ya'ni u faqat **pul to'layotgan** mijozni to'sardi.  Ega qarori
bilan uch joydan olindi; sotuv sahifasida qoldi.

Qayerda: `cloud/main.py` (`site_cloud_features()` — yangi yagona manba,
`/api/v1/edge/config` va `/api/v1/owner/dashboard`),
`cloud/store.py: feature_quote`, `cloud/config_health.py:
feature_problems()`, `cloud/static/admin.html`,
`cloud/event_store.py: requeue_failed_vision_jobs()`,
`chaqimchi_ai/outbox.py: failure_reason(), requeue_dead_letters()`,
`chaqimchi_ai/cloud_sync.py`, `scripts/dead_letters.py` (yangi).

Test: `test_a_paying_site_keeps_plan_features_without_acceptance`
(`test_cloud_events_owner.py`), `test_config_health.py` dagi yettita
`feature_problems` testi, `test_vision_agent.py` dagi uchta qayta
urinish testi, `test_outbox.py` dagi beshta sabab/qaytarish testi.
Obunasi tugagan sayt hali ham bo'sh ro'yxat oladi — buni eski
`test_an_expired_subscription_stops_the_features_but_not_the_camera_alarm`
qulflaydi.

Diqqat: nosozlik BESH KUN ko'rinmadi — na log, na panel, na
ogohlantirish.  `plan_filtered` raqami heartbeatda shu davr ichida
turgan, lekin uni hech kim o'qimagan.  Shu sababdan tuzatish bilan
birga signalizatsiya qo'shildi.  Yonaki ish: zaxiraning tashqi nusxasi
yoqildi (Telegram, jonli sinaldi) — lekin shifr paroli hali faqat
serverda.

### 2026-08-30 — Kamera rollari: tizim taklif qiladi, odam tasdiqlaydi (`af08057`)

Nima: sehrgarda tanlangan rol (kirish/kassa/zal/ombor) endi SAQLANADI
va tizimni boshqaradi: «kirish» roli kamerani davomat (Face ID)
ro'yxatiga avto-qo'shadi (maks. 2, faqat rol O'TISHIDA — ega olib
tashlasa qayta urilmaydi), rol prioritet standartini beradi, skanerdan
keyin tizim rol taklif qiladi (kanal nomi uz/ru/en + oqim o'lchami;
ishonchli belgi bo'lmasa taklif YO'Q), 4 tadan ko'p kanal topilsa eng
yaxshi 4 tasi belgilanadi, rol berilgan-u geometriya chizilmagani
BALAND aytiladi (`feature_status` + admin `role_problems`).

Nega: o'rnatishda hamma kamera chiqardi-yu, qaysi biri nimaga
ishlatilishi hech qayerda hal bo'lmasdi (ega qarori, 2026-08-30).
2026-08-22 da o'chirilgan `camera_roles` xatosi takrorlanmasligi uchun
rol per-kamera maydon (sayt-konfig dict emas), bo'sh variant har UI da
bor, va rol haqiqatan O'QILADI.

Qayerda: `chaqimchi_ai/camera_roles.py` (yangi — konstantalar + taklif
dvigateli), `settings.py:RetailCameraSettings.role`,
`local/config_store.py:save_camera`, `local/app.py` (`CameraSaveBody.role`,
`POST /api/setup/role-suggestions`), `local/static/setup.js` (kanal-skan
UI, 1-kanal «Kirish eshigi» jim prefilli O'CHIRILDI),
`local/cloud_config.py:publish_cameras` (role doim ochiq, `"none"`),
`cloud/store.py` (`site_cameras.role` + no-wipe CASE),
`cloud/main.py` (`EdgeCameraItem.role`, `_sync_attendance_with_roles`,
`_attach_role_suggestions`, `ATTENDANCE_MAX_CAMERAS`),
`cloud/config_health.py:role_problems`, `retail/inventory.py`
(`CameraPlan.role`, prioritet roldan hosila),
`frontend/src/SetupCameras.tsx` (rol tugmalari + «Rolsiz»).

Test: `tests/test_camera_roles.py` (27 ta: taklif jimligi, no-wipe,
avto-yozuv o'tishi, backfill regressiyasi, rol-geometriya ogohlantirishi).
Qulflangan testlar (`test_zone_editor.py:207`,
`test_static_pages.py:436`) O'ZGARMADI — rol tahriri owner.html ga
kirmaydi (sehrgar/installer + React onboarding'da).

Diqqat: versiya 0.6.26 ga ko'tarildi, lekin **soak paytida Windows
nashr taqiqlangan** — reliz soak tugagach. Harakat namunasi bo'yicha
taklif (`traffic_per_min`) dvigatelda bor, lekin UI tugmasi va
`role_suggest` qurilma job'i KEYINGA qoldirildi.

### 2026-08-29 — QA tahlili: 🚻 qaytdi, beqaror test yopildi (`25a2882`)

Nima: ega kunlik hisobotda ayol/erkak qatorini sog'inganini aytdi —
qator «aqlli format»da qaytarildi: o'lchov vakillik qilsa (n≥20 va
qamrov≥30%) avvalgidek foiz, kam bo'lsa `🚻 O'lchangani 9 kishi:
1 ayol · 8 erkak`. Bu T1 (28-avg) qarorini QISMAN bekor qilish:
qatorni butunlay yashirish halollikni saqladi-yu, egadan foydali
ma'lumotni ham olib qo'ydi. Halollik endi FORMAT bilan saqlanadi —
kichik namunadan foiz baribir chiqarilmaydi (sonlar tayyor
`jins_soni` dan olinadi, qurilma relizi kerak emas).

Yo'l-yo'lakay: uch haftalik beqaror test ildizi topildi — TestClient
lifespan'i `_maintenance_loop` ni yaratishi bilan u fon oqimida darhol
purge boshlab, test env'i (`CHAQIMCHI_CLIP_RETENTION_DAYS=60`)
o'rnatilishidan OLDIN standart 7 kunni muzlatib olardi; to'liq
to'plamda oqim kechikib test saytining klipini o'chirardi. Fixture
endi `_maintenance_loop` va `_demography_rollup_loop` ni no-op qiladi.

QA tahlilining boshqa topilmalari: camera-02 `record_url` sababi
(`/mpeg4cif` rewrite naqshlarda yo'q), `record_url_set` lokal konfigdan
hisoblanishi, feature-env xatosi jimgina yutilishi — tuzoqlarga yozildi.
Ega qarorlari: kameralarga tegilmaydi, avval pilot barqarorlashtiriladi.

Qayerda: `cloud/digest.py:134-160`, `tests/test_owner_report.py`
(ikkita test yangi xulqqa moslandi va kuchaytirildi),
`tests/test_cloud_load.py` (fixture).
Test: `test_a_handful_of_measurements_is_shown_as_counts_not_percent`,
`test_low_coverage_shows_counts_even_with_enough_samples`;
`test_cloud_load.py` 20 marta ketma-ket yashil.

Diqqat: bu cloud-tomon o'zgarish — deploy qilinmaguncha jonli hisobot
eski xulqda qoladi.

### 2026-08-29 — 0.6.25: kamera ROSTDAN qaysi o'lchamda berayotgani ko'rinadi (`a440a6f`)

Nima: benchmark natijasiga `native_size` qo'shildi — birinchi
muvaffaqiyatli kadrning O'ZIDAN o'lchanadi (`CAP_PROP` emas: RTSP'da
property yolg'on qaytarishi mumkin). 720p ga o'tishdan keyin o'zgarish
ishlaganini shu ko'rsatadi; usiz buni faqat 24 soatlik bilvosita
statistikadan bilib bo'lardi. Ertalab 04:11 da ikkinchi sig'im o'lchovi
ham olindi (36,1 inf/s, xulosa o'zgarmadi — 11 kamera).

Qayerda: `chaqimchi_ai/local/benchmark.py`,
`chaqimchi_ai/local/cloud_jobs.py:338`, `cloud/static/admin.html:1621`.
Test: `test_benchmark_n100.py` (+3), `test_local_jobs.py` (+2).

Diqqat: `native_size` heartbeatga CHIQMAYDI — faqat admin paneldagi
«Sig'imni o'lchash» topshirig'i natijasida. 720p tasdiqlash uchun
tugmani qo'lda bosish kerak. (Bu yozuv reliz kuni yozilmay qolgan
edi — 29-avg QA sessiyasida retroaktiv qo'shildi.)

### 2026-08-28 — Kamera manzili endi bulutda zaxiralanadi (0.6.24)

Nima: mijoz talabi bo'yicha qurilma kamera RTSP manzilini (IP va parol
bilan) bulutga yuboradigan bo'ldi. Ilgari faqat ID va nom ketardi.

**Bu ONGLI qarorni bekor qilish edi** — `publish_cameras()` izohida va
`register_device_cameras()` docstringida "parol do'konda qolsin" deb
yozilgan, test ham qulflab turardi. Bekor qilish sababi uchta jonli
holat: do'kon kompyuteri o'lsa sozlama butunlay yo'qolardi; camera-02
dagi `record_url` yo'qligini masofadan tuzatib bo'lmasdi; oqim
sifatini bulutdan tekshirib bo'lmasdi.

Tekshirildi: saytda ham, README da ham bunday va'da **yo'q** —
izohdagi "README va'dasi" muallifning ichki prinsipi ekan. Admin oynasi
esa allaqachon "parol shifrlangan holda saqlanadi" deb yozadi.

Ikkala oqim saqlanadi: `rtsp_ciphertext` (tahlil) va yangi
`record_ciphertext` (klip), migratsiya bilan. Zaxira ROSTDAN
ishlatiladi — `merge_cameras` klip manzilini lokal sozlama → bulut
zaxirasi → substream tartibida oladi; ikkinchisisiz zaxira "bor, lekin
foydasiz" bo'lardi.

Eng xavfli holat alohida qulflandi: eski qurilma bo'sh manzil yuboradi
va u bulutdagi yagona nusxani o'chirmasligi shart.

Yo'l-yo'lakay: sig'im o'lchovi IKKINCHI marta yiqildi —
`capacity_verdict` faqat nomli argument oladi. Test buni ushlamadi,
chunki funksiyani `lambda *a, **k` bilan almashtirgan edi. Endi test
haqiqiy funksiyani chaqiradi. Admin paneldagi kalit nomlari ham
tuzatildi (`per_second` mavjud emas edi).

Qayerda: `cloud/store.py` (migratsiya, `register_device_cameras`,
`list_cameras`), `cloud/main.py` (`EdgeCameraItem`),
`chaqimchi_ai/local/cloud_config.py` (`publish_cameras`),
`chaqimchi_ai/retail/inventory.py` (`InventoryCamera.record_url`,
`merge_cameras`), `chaqimchi_ai/local/cloud_jobs.py`.
Test: `test_camera_credentials.py` (11 ta, yangi),
`test_device_telemetry.py` (qaror o'zgarishi),
`test_local_jobs.py` (haqiqiy `capacity_verdict`).
Jami **1 889 test** o'tdi.

Diqqat: qurilma 0.6.24 ni olgach `cameras_source` `auto` ga o'tadi
(bulutda endi manzil bor) va zanjir bir marta qayta ishga tushadi.
Lokal sozlama o'chmaydi — `merge_cameras` uni ustun deb oladi.

### 2026-08-28 — Sig'im o'lchovi ishlamasdi: uchta xato (0.6.23)

Nima: 0.6.22 dagi «Sig'imni o'lchash» tugmasi jonli do'konda birinchi
urinishdayoq yiqildi — «Kamera manzili yo'q», holbuki ikkala kamera
sozlangan edi. Uchta xato topildi va uchalasi ham o'sha kungi ishda
kiritilgan edi.

**1 · Kamera ro'yxati noto'g'ri joydan.** Sozlamada IKKI joyda
`cameras` bor: ildizda (`AppSettings.cameras` — veb-kamera uchun eski
yo'l, do'kon kompyuterida doim bo'sh) va `RetailSettings.cameras`
(haqiqiy ro'yxat, manzil `stream_url` da). Kod ildizdagisini o'qirdi.

**Testning o'zi ham xato edi** — u koddagi xuddi shu noto'g'ri shakldagi
soxta sozlama bergani uchun yashil turardi. Ya'ni test xatoni ushlamadi,
TASDIQLADI. Endi soxta ma'lumot haqiqiy sxemadan va tuzatish mutatsiya
bilan tekshirildi.

**2 · Admin natijani ko'ra olmasdi.** Tugma o'lchovni boshlardi, natija
`device_jobs.result_enc` da qolardi va panelda unga yo'l yo'q edi;
xabar matni esa "«Diagnostika» da ko'rinadi" deb yolg'on aytardi. Endi
`latest_job_of_kind()` orqali diagnostika javobida keladi va oynada
odam o'qiydigan qilib chiqadi (nechta kamera, inferens/s, p95).

**3 · Oxirgi o'lchov tartibi noaniq edi.** `created_at` bir soniya
aniqligida — bir kunda ikki marta o'lchansa admin eskisini yangisi deb
o'qishi mumkin edi. `rowid` qo'shildi.

Yo'l-yo'lakay: `test_the_panel_and_the_alert_watch_the_same_disk`
ikkita jonli disk o'lchovini `==` bilan solishtirardi va to'liq
to'plamda tasodifan yiqilardi. Endi `pytest.approx(abs=0.5)`.

Yana bir topilma (hali tuzatilmagan): **`origin: device` kameralar hech
qachon probe qilinmaydi** — bulutda `probe_status` abadiy `pending`,
`width`/`height`/`codec` esa `null`. Sinov do'konining ikkala kamerasi
shunday, ya'ni oqim o'lchamini bulutdan bilib bo'lmaydi.

Qayerda: `chaqimchi_ai/local/cloud_jobs.py`, `cloud/store.py`
(`latest_job_of_kind`), `cloud/main.py`, `cloud/static/admin.html`.
Test: `test_local_jobs.py` (+1 va ikkitasi tuzatildi),
`test_device_jobs.py` (+3), `test_config_health.py` (+1),
`test_server_health.py` (beqarorlik tuzatildi).
Jami **1 878 test** o'tdi, lint va TS toza.

Diqqat: cloud tuzatishi (2 va 3) darhol ta'sir qiladi, 1-band esa
qurilma 0.6.23 ni olmaguncha ishlamaydi.

### 2026-08-28 — Jonli tekshiruv: nima ishlaydi, nima yolg'on gapiradi (0.6.22)

Nima: bulut va Do'kon 5070 jonli ma'lumotdan tekshirildi. 27-avgust
tuzatishlari **ishlagani tasdiqlandi**, lekin AI tomonda uchta funksiya
nol ko'rsatayotgani va kunlik hisobot **yolg'on raqam** yozayotgani
aniqlandi. Sakkizta tuzatish kiritildi.

**Tasdiqlangan (jonli dalil bilan):** `device_tz_offset_min: 300`
(mintaqa tuzalgan), ertalabki yolg'on trevoga 26 → **0**,
`stale_chains: {}` (yetimlar o'lgan), 24 soatlik logda **0 ta** 5xx,
`outbox_poisoned` 4 401 → 2 752 (o'smayapti), `analyzed` 52 835,
CPU atigi **8.8%**.

**T1 · Kunlik hisobot YOLG'ON foiz yozardi.** 27-avgust: 207 kirishdan
9 tasida jins bor edi, xabar esa "11% ayol · 89% erkak" deb fakt
sifatida chiqardi. Endi `🚻` qatori faqat namuna vakillik qilganda
chiqadi (`>= 20` o'lchov **va** `>= 30%` qamrov). **Xabar shakli
o'zgarmadi** — qator shunchaki chiqmaydi.

**T2 · `checkout_unattended` egaga HECH QAYERDA ko'rinmasdi.**
Uch kunda 35 ta hodisa: `REPORT_EVENT_TYPES` da yo'q edi (hisobotdan
filtrlanardi) va `warning` bo'lgani uchun Telegramga ham bormasdi.
Endi mavjud `⚠️` qatoriga qo'shiladi.

**T3 · Davomat chegaralari bir-birini inkor qilardi.** Jonli dalil:
`face_crops {written: 0, too_small: 93}` — 93 urinishdan 0 tasi.
`0.35 x bbox >= 96` uchun `bbox >= 275 px` kerak, `FACE_MIN_BBOX_RATIO
= 0.28` esa 360p da 101 px kafolatlardi. Endi ikkalasi `limits.py`
dagi bitta formuladan va u kadr balandligiga moslashadi
(360p → 0.76, 720p → 0.38, 1080p → 0.25).

**T4 · Klip: `record_url` BOR, klip YO'Q.** Oldingi tashxis
("manzil berilmagan") **noto'g'ri** edi. `missing` endi ikkiga
bo'linadi — `no_segments` va `cut_failed` — va ffmpeg xatosi
`clips_last_error` da saqlanadi.

**T5 · `zone_entered` nolining sababi topildi — chizmaning O'ZI
yaroqsiz.** «Taqiqlangan zona» 640x360 da **29x20 piksel**, kadr
tepasida; camera-02 dagi «kirish» chizig'i **4 piksel**. Zona bbox
markazi bo'yicha tekshiriladi va markaz u yerga tushmaydi. 57 ta eski
hodisa yetim zanjirlardan kelgan. Yangi `cloud/config_health.py` buni
admin panelida ko'rsatadi (egaga tegilmaydi — sizning qaroringiz).

**T6 · Diagnostika paketi hech qachon yuborilmagan.**
`device_diagnostics` jadvalida **0 qator**: kod to'liq yozilgan edi,
lekin uni faqat do'kondagi paneldagi tugma yuborardi. Endi sutkada bir
marta o'zi ketadi.

**T7 · Status zanjirining 3→4 bo'g'inida 7 maydon yo'qolardi.**
`cameras_configured`, `pressure`, `status_stale`, `events`,
`plan_filtered` + yangi `snapshots{}` va klip sabablari qo'shildi.
`test_status_chain.py` endi **teskari yo'nalishni** ham qulflaydi.

**T8 · Sig'imni masofadan o'lchash mumkin bo'ldi.** O'lchov yadrosi
`scripts/benchmark_n100.py` dan `chaqimchi_ai/local/benchmark.py` ga
ko'chdi (payload'da `scripts/` yo'q edi, ya'ni tavsiya bajarib
bo'lmasdi) va admin panelda «Sig'imni o'lchash» tugmasi paydo bo'ldi.

Profilaktika: `cloud/store.py` dagi 8 ta raqamli qator o'qish nomli
aliasga o'tkazildi va naqsh uchala baza moduli uchun testda qulflandi.

Qayerda: `cloud/digest.py`, `cloud/event_store.py`,
`cloud/config_health.py` (yangi), `cloud/main.py`, `cloud/store.py`,
`cloud/static/admin.html`, `cloud/static/owner.html`,
`chaqimchi_ai/limits.py`, `chaqimchi_ai/scene_analytics.py`,
`chaqimchi_ai/retail/pipeline.py`, `chaqimchi_ai/retail/ringbuffer.py`,
`chaqimchi_ai/retail/service.py`, `chaqimchi_ai/local/benchmark.py`
(yangi), `chaqimchi_ai/local/cloud_config.py`,
`chaqimchi_ai/local/cloud_jobs.py`, `chaqimchi_ai/local/supervisor.py`,
`chaqimchi_ai/local/app.py`.

Test: `test_config_health.py` (8 ta, yangi — jonli revision 11
konfiguratsiyasi kirish sifatida), `test_face_crop_contract.py` (8 ta,
yangi), `test_device_diagnostics.py` (6 ta, yangi),
`test_status_chain.py` (+5, teskari yo'nalish),
`test_owner_report.py` (+4), `test_retail_pipeline.py` (+2),
`test_local_jobs.py` (+2), `test_device_jobs.py` (+2, eski sxema
migratsiyasi), `test_owner_notifications.py` (naqsh uchala modulga).
Jami **1 873 test** o'tdi (avval 1 835), lint va TS typecheck toza.

Diqqat — uchta narsa:

* **720p ga o'tmaguncha davomat baribir ishlamaydi.** Formula endi
  halol javob beradi (360p da 0.76 — amalda imkonsiz), lekin bu
  nosozlikni KO'RSATADI, tuzatmaydi. Avval sig'imni o'lchang.
* **Chizmani mijoz bilan qayta chizish kerak.** Admin paneldagi ro'yxat
  faqat ko'rsatadi; 29x20 pikselli zona o'zidan tuzalmaydi.
* Ikkita mutatsiya sinovi o'tkazildi (kalitni va migratsiyani ataylab
  o'chirib): ikkala yangi qulf ham **rostdan ushlaydi**.

### 2026-08-27 — Jonli serverdan to'liq tekshiruv: oltita nosozlik (0.6.21)
Nima: bulut va Do'kon 5070 jonli ma'lumotdan tekshirildi (PostgreSQL,
konteyner loglari, 3 kunlik `device_metrics` — 1 515 daqiqalik o'lchov).
Oltita nosozlik topildi; ikkitasi mijozga o'sha kuni zarar yetkazayotgan
edi va **ikkitasi ilgari yozilgan tashxisni bekor qildi**.

**K1 · Panel qo'ng'irog'i production'da 100% yiqilardi.**
`cloud/event_store.py:991` da `.fetchone()[0]`. PostgreSQL ulanishi
`dict_row` bilan ochiladi va `row[0]` → `KeyError: 0`; SQLite'da esa
`sqlite3.Row` raqamli indeksni qo'llaydi. Ya'ni **1 800+ test o'tardi,
production yiqilardi**: 48 soatda 49 marta 500, `notification_reads`
jadvalida 0 qator — hech kim hech qachon "o'qildi" qila olmagan. Bu
kechagi (`e05ac3a`) ishning asosiy funksiyasi edi.
Deploydan keyin egasining o'z brauzeridan (83.222.7.214) **200 OK**.

**K2 · Do'kon kompyuterining vaqt mintaqasi UTC+3 edi (Toshkent UTC+5).**
Dalil `after_hours_presence` metadatasidan: `occurred_at` 03:34 UTC,
`local_time` **06:34** (Toshkentda 08:34). UTC to'g'ri edi
(`clock_skew_sec` −0,8 s) — shuning uchun 26-avgustda qo'yilgan soat
nazorati buni **ko'rmadi**. Oqibati ikki tomonlama va ikkalasi ham
qimmat: har ertalab 08:30–10:30 orasida do'kon OCHIQ bo'la turib kritik
Telegram trevogasi ketardi (o'sha kuni 26 ta), kechqurun 22:00–00:00
orasida esa nazorat UMUMAN jim edi. Bu saytdagi to'rtta va'dadan
uchinchisini ("Do'kon yopiq payt kimdir kirsa") buzardi.

**K3 · Davomat/demografiya diagnostikasi YOLG'ON nol ko'rsatardi.**
26-avgustda qo'shilgan `face_crops` va `demography` hisoblagichlari
heartbeatga hech qachon yetib bormagan: `write_status()` ularni holat
fayliga yozmasdi, `supervisor.status()` ham o'tkazmasdi. Uch kunlik
1 515 o'lchovda hammasi nol. Bu xatoning **uchinchi marta** takrorlanishi.

**K4 · Demografiya "o'chiq" emas — 0.8% da ishlaydi.** Bazadan: 257 ta
"kirish" kesishmasidan **2 tasida** `jins` bor. Model yuklangan; yuz
topilmayapti. Ilgari yozilgan "funksiya o'chiq" tashxisi K3 tufayli
noto'g'ri chiqqan.

**K5 · "camera-02 yuz kadri to'xtamayapti" — YOPILDI.** Sabab yetim
zanjirlar bo'lgan: tozalashdan keyin 27-avgust kuni camera-02 dan
**0 ta** `face_captured` (oldingi kuni 2 383 ta).

**K6 · 3 375 ta hodisa butunlay yo'qolgan.** `outbox_poisoned` 4 401
gacha chiqqan; do'kon jami 7 227 hodisa yuborgan, ya'ni ~uchdan biri.
Eng ko'p sabab — "All connection attempts failed", ya'ni **vaqtinchalik**
xato. Har muvaffaqiyatsizlik `MAX_ATTEMPTS = 20` ni yeb borardi va 20
urinish backoff bilan ~3 soat: yarim kunlik uzilish navbatni o'ldirardi.

Tuzatishlar:

1. `event_store.py` — `SELECT COUNT(*) AS unread` + `_dict()`.
2. `limits.py` — `STORE_TZ` / `store_now()`. `zoneinfo` EMAS: Windows'da
   tz bazasi yo'q va `tzdata` paketi ham yo'q; O'zbekistonda yozgi vaqt
   bo'lmagani uchun qat'iy UTC+5 to'liq to'g'ri javob beradi.
   `pipeline.py` va `local/app.py` shundan o'qiydi.
3. Heartbeat: `device_tz_offset_min`, `config_revision`, kamera bo'yicha
   `record_url_set`; `alerts.py` da mintaqa va `outbox_poisoned`
   ogohlantirishlari.
4. `write_status()` + `supervisor.status()` — `face_crops`/`demography`.
5. `outbox.fail(permanent=...)` — tarmoq va 5xx endi urinishlar hisobini
   yemaydi; yoshi o'tgan yuborilmagan yozuv esa jimgina o'chirilmay
   `dead_letter` ga ko'chadi (aks holda uzoq uzilish ko'rinmay qolardi).
   Bo'sh sabab ham to'ldiriladi ("602× sabab yozilmagan" shundan edi).

Qayerda: `cloud/event_store.py`, `cloud/alerts.py`, `cloud/main.py`,
`chaqimchi_ai/limits.py`, `chaqimchi_ai/retail/pipeline.py`,
`chaqimchi_ai/retail/service.py`, `chaqimchi_ai/local/supervisor.py`,
`chaqimchi_ai/local/cloud_config.py`, `chaqimchi_ai/local/app.py`,
`chaqimchi_ai/outbox.py`, `chaqimchi_ai/cloud_sync.py`.

Test: `test_status_chain.py` (yangi, 4 ta — zanjirni qulflaydi),
`test_owner_notifications.py` (+3, `dict_row` va naqsh qulfi),
`test_device_health_alerts.py` (+5), `test_outbox.py` (+4),
`test_cloud_sync.py` (+2). Jami **1 834 test** o'tdi, lint va TS toza.

Diqqat — uchta narsa:

* **Windows'da mintaqani o'zgartirish ishlab turgan jarayonga ta'sir
  qilmaydi.** Mijoz soatni to'g'rilagach zanjir 25 soat eski qiymatda
  ishlab turdi; masofadan `clean_chains` bilan qayta ishga tushirildi
  (`restarts` 1→2, `analyzed` 53 616→88).
* **`loitering` uchun rasmni qaytarmang** — 2026-08-21 o'lchovi bilan
  ataylab olib tashlangan (tuzoqlar bo'limiga qarang). Dastlabki rejada
  buni qaytarish bor edi va u **noto'g'ri** bo'lardi.
* Mintaqa tuzatilganini tasdiqlash **bugun kechqurun 17:05 UTC** da
  mumkin — "Keyingi ish" ning 1-bandi.

### 2026-08-26 — Panel: qo'ng'iroq rostdan ishlaydi, jonli ko'rish muzlamaydi (`e05ac3a`, deploy qilingan)
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
