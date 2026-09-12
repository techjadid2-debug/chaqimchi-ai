# Ish daftari

> Har agent ishni **shu fayldan** boshlaydi va **shu faylga** yozib
> tugatadi. Maqsad: keyingi sessiya nolla emas, shu yerdan boshlasin.
>
> Qayerda nima turishi — [ARXITEKTURA_XARITASI.md](ARXITEKTURA_XARITASI.md).

---

## HOZIRGI HOLAT · 2026-09-12

- **🔧 BOSQICH E — USTA PANELI REACT'DA (2026-09-12, commit qilinmagan,
  shox `worktree-agent-aee520e409d4d0c84`).**  `cloud/static/installer.html`
  — **oxirgi eski statik panel** — o'chdi; o'rniga `frontend/installer.html`
  + `frontend/src/installer.tsx`, `InstallerJobs.tsx`, `InstallerCamera.tsx`.
  Usta endi ega va admin bilan BITTA dizayn tizimida: uch til, qora tema,
  telefon (390 px), `ErrorStrip` + «Qayta urinish», fokus tuzog'i,
  brauzer oynalari o'rniga modal.  Obyekt endi modal emas, MANZIL:
  `/installer/jobs/<site_id>/<tab>` (steps · cameras · zones) — havola
  qilinadi va «orqaga» ishlaydi.
  - **Teginish tuzatildi:** muharrirda zonani yakunlash `dblclick` ga,
    o'chirish esa sichqonchaning O'NG tugmasiga bog'langan edi — ya'ni
    usta telefonda nuqtalarni qo'yib, zonani UMUMAN yopa olmasdi.
    `finishDraft`/`cancelDraft` muharrirda 2026-08-17 dan bor edi,
    faqat hech kim chaqirmagan (tipda ham e'lon qilinmagan).  Endi
    tugma bor; har shakl yonida «×» (o'chirish).
  - **Face ID belgisi** kamera ro'yxatida — qaror SERVERDA
    (`camera_roles.face_id_state`, `list_cameras` javobida), panel
    faqat matn tanlaydi.
  - ⚠️ **Qobiq qurilmagan:** `cloud/static/v2/installer.html` — build
    artefakti va u `npm run build` dan keyin paydo bo'ladi.  Shu
    sababdan LOKAL `/installer` hozir 404 beradi va ikki test buni FAYL
    BORLIGIGA qarab kutadi (`test_platform_hosts.py: _panel_code`).
    Jonli deployda xavf YO'Q: `Dockerfile.cloud` bundle'ni o'zi quradi
    (`frontend-builder` bosqichi).  Lekin repodagi nusxa ham
    yangilansin — lokal ishga tushirish va testlar o'shanga qaraydi.
  - **Holat:** `2360 passed, 12 skipped`, `ruff` toza, `tsc --noEmit`
    toza, i18n va sayt `--check` toza.

- **📷 KAMERA JOYLASHUVI + FACE ID DARVOZASI — KODDA TAYYOR, DEPLOY
  KUTADI (2026-09-12, shox `reja-2026-09-12`: `2a6ece3`, `b11381e`,
  `3200772`).**  Ega uchta yangi ish so'radi (kamera o'rnatish
  yo'riqnomasi, o'rnatishni maksimal qulay qilish, demo 7/14 kun +
  kartadan oylik yechish) va to'liq reja
  `~/.claude/plans/md-file-ichii-o-qi-linear-tulip.md` da; bajarilgani
  quyidagi commitlar.

  **HOLAT (2026-09-12 kechqurun): A, B, C, D, E, F, G, I — TUGADI.
  Qolgan yagona blok — H (admin i18n).**  To'plam `2449 passed,
  13 skipped`, `ruff` toza, i18n va sayt `--check` toza, bundle manba
  bilan bitta commitda.

  Lokal jonli tekshiruv o'tdi: 8 marshrut 200 (`/owner`, `/admin`,
  `/installer`, `/installer-guide`, `/install`, `/`, `/status`,
  `/oferta`); forma xatosi uch tilda MATN qaytardi va qurilma API
  strukturali `detail` ni saqladi; `capabilities.agent.ready` false va
  sababli; yaroqsiz chiziq saqlanganda «Chiziq juda qisqa: 3 piksel»;
  `trial_days: 7`; karta API provayder kalitisiz 503 va tushunarli
  matn; usta paneli React bundle'ini beryapti; loglarda 0 xato.

  **Qo'shimcha bloklar (yuqoridagi uchtadan tashqari):**
  - **B — sayt xatolari** (`ac30722`, `921572a`, `34acb91`)
  - **C — panel xatolari** (`dbda134`, `5cce2eb`, `1bb740c`)
  - **E — usta paneli React'da** (`9828021`, `d7e57c4`)
  - **F — karta va demo 7/14 kun** (`6c0d1bb`, `3d01088`, `c8eb1f0`)
  - **G — avtomatik konversiya** (`3434619`)
  - **I — CSP va `releases/`** (`e4200fd`, `6647341`, `5a111d8`)
  - **Bosqich A (`2a6ece3`):** ikkita oylik qizil test yashil — `night`
    statistikasi zanjirning to'rt bo'g'inidan o'tkazildi, CI testi
    eskirgan domenni kutardi.  `/chek` bot menyusiga qo'shildi (yordam
    matnida bor edi, menyuda yo'q — ya'ni konversiyani kiritishning
    yagona yo'lini faqat yordamni o'qigan ega topardi); yangi
    `tests/test_bot_commands.py` menyu bilan `bot.help` ni uch tilda
    qulflaydi.  Box ko'prigi (`enes/paths.py`) `exists()` dan
    `_has_installation()` ga o'tdi.  `docs/DOKON_MVP.md` dagi «yuz
    kadri 14 kun» → 48 soat.
  - **Bosqich D1 (`b11381e`):** kamera kadrining HAQIQIY o'lchami endi
    cloudda — `runner` → holat fayli → heartbeat `cameras[]` →
    `site_cameras.width/height`.  Bungacha Windows yo'lida bu son
    printsipial yo'q edi (pastdagi TUZOQLARga qarang).
  - **Bosqich D2–D6 (`3200772`):** `docs/KAMERA_JOYLASHUVI.md` (usta va
    jamoa uchun texnik manba, har son koddan va testga qulflangan);
    `/installer-guide` Windows yo'liga o'tkazildi + «Kamerani qayerga
    qo'yish» bo'limi; `/install` da mijoz uchun qisqa versiya; panelda
    Face ID belgisi (`face_id_state` — qaror serverda, matn panelda uch
    tilda); yaroqsiz chiziq/zona haqida CHIZGAN ODAMGA aytiladi (uchala
    config PUT javobida, strukturaviy qulf bilan).
  - **Bosqich C (`dbda134`, `5cce2eb`, `1bb740c`):** panel xatolari —
    zona nomlash `window.prompt` dan o'z oynasiga (Telegram WebView'da
    u jim o'lardi), admin 6 sahifadagi abadiy skelet, CSV yuklash
    Safari'da, yoqilmagan bo'lim darvozasi (`capabilities.agent` va
    `capabilities.attendance`), fokus tuzog'i, telefonda qidiruv,
    bitta KPI komponenti.  Tafsilot Tarixda.
  - **Bosqich I (`e4200fd`, `afbfe3c`):** CSP majburiy rejimda (faqat
    sarlavha nomi — mazmun va hash o'sha holda); `releases/` o'zini
    tozalaydi (`prune_windows_releases(keep=3)`), qurilmalar hali
    so'rayotgan va `pin` bilan qotirilgan versiya o'chmaydi.
    **Deployda diqqat:** Caddy `--force-recreate`, serverdagi 1,9 GB
    esa ikki qadamda tozalanadi (konteynerda `:ro`).  Tafsilot Tarixda.
  - **Holat:** `2387 passed, 13 skipped`, `ruff` toza, i18n va sayt
    `--check` toza, bundle manba bilan bitta commitda.  Lokal jonli
    tekshiruv: `/owner`, `/admin`, `/installer`, `/installer-guide`,
    `/install` 200; bundle fayllari 200; `capabilities.agent.ready`
    false va sababli; yaroqsiz chiziq saqlanganda javobda
    «Chiziq juda qisqa: 3 piksel» keldi; loglarda 0 xato.
  - ⏳ **Deploy qilinmagan.**  Cloud qismi (D1 qabul qilish, D5 javob,
    D6 tekshiruv) deploy talab qiladi; qurilma qismi (D1 yuborish)
    keyingi Windows relizi bilan chiqadi — **tartib: AVVAL cloud**.


- **🎨 UI/UX QA + DIZAYN-3 — KODDA TAYYOR, DEPLOY KUTADI (2026-09-11,
  `3c19d63`…`28b73cd`, 9 commit).**  Ega «xatolar ko'p» dedi; jonli sayt
  va panel Playwright bilan (telefon emulyatsiyasi 390, desktop 1280,
  ikki tema) QA qilindi — topilmalar va reja
  `~/.claude/plans/ui-ux-bo-yicha-tahlil-qil-eventual-cat.md`.
  Qarorlar: sayt + panel; mockupdagi rost bo'lmagan va'dalar
  («Shubhali harakat», «Shaxs aniqlandi… ro'yxatda yo'q», Face ID,
  1000+/99.9%/24/7, App Store, ENES Box) OLINMADI — dizayn olindi, matn
  rost; panel standart temasi QORA.
  **Tuzatildi (panel):** API yiqilganda xato + abadiy skelet (Dalillar,
  AI yordamchi, Tarif, Telegram) → `ErrorStrip` + «Qayta urinish»; xom
  FastAPI matni yashirildi; telefonda `.page-actions` yashirilmaydi
  (kamera Jonli/AI, Rasm/Klip, Xodim qo'shish, hisobot tugmalari qaytdi);
  do'kon tanlagich «Nam⌄» → til/tema «Yana» menyusida; tablar so'nuvchi
  chet + strelkalar; «Excel» yorlig'i → CSV; ish vaqti badge'i sozlama
  kelgach; bitta do'konda Filiallar bo'sh emas; KPI kartasi bitta
  komponent; IR belgisi o'z rangi.  **Dizayn-3 (panel):** standart qora
  tema (CSP hash ikkala Caddyfile'da yangilandi — **deployda Caddy
  konteyneri qayta yaratilsin**); bosh sahifa 5 doimiy KPI, hodisa
  rasmchasi (`has_snapshot`), «So'nggi hodisalar», topbar do'kon chipi;
  **alohida kamera sahifasi** `/owner/cameras/camera-NN/{live|analytics|alerts}`
  (`Cameras.tsx`, `CameraDetail.tsx`, router 3-segment).  **Sayt:** hero
  ega bergan lobby fotosi + rost hodisa kartasi «Kassada navbat uzun»,
  2 ta CTA; telefon menyusi (`<details>`, «Mijoz kirishi» ichida);
  brendli 404 (apex, HTML so'rov); rasmlar `hero-lobby-v1.webp`,
  `shop-corridor-v1.webp` (< 200 KB).  **Vositalar:**
  `scripts/ui_qa_screenshots.py` (toshish / xom kalit / konsol / abadiy
  skelet / tugma soni; `--fail-api`, `--site`),
  `scripts/bump_asset_tokens.py` (kesh tokenlari).  Yakuniy matritsa
  (19 marshrut × 3 til × 2 tema × 2 kenglik, 228 surat) RU/EN da 10 ta
  gorizontal toshish topdi — o'zbekchada ko'rinmasdi (yorliqlar qisqa):
  karta `min-width:auto`, `.segmented`, `.bottom-nav` (`c8f3400`);
  qayta yurgizilganda 0 nuqson, `--fail-api` 0 skelet, sayt 0.
  ✅ **DEPLOY QILINDI (2026-09-11 ~08:00 UTC):** rsync (85 fayl) →
  `deploy_cloud.sh` (zaxira, image, cloud+worker healthy) → Caddy
  `--force-recreate` (bind-mount inode; CSP sarlavhasida yangi hash
  tasdiqlandi).  Jonli: 8 host 200/301, `enes.uz/narxlar` brendli 404,
  `/api/*` JSON, hero `hero-lobby-v1.webp`, telefon menyusi ochiladi va
  «Mijoz kirishi» bor, `app.enes.uz/owner` qora ochiladi, loglarda 0 xato.
  ⚠️ **Ikkita test HEAD da allaqachon yiqilardi** (menga
  aloqasi yo'q, tuzatilmadi): `test_status_chain.py::…silently_dropped`
  (`night` stat holat fayliga yozilmaydi — 10-sentabr tungi ishi) va
  `test_windows_installer.py::test_ci_gives_the_build_a_cloud_address`
  (workflow'da `ENES_DEFAULT_CLOUD_URL:` yo'q).

- **🚀 F7 CUTOVER BAJARILDI — SERVER YANGI KODDA, DEPLOY TAQIQI OLINDI
  (2026-09-11, `ea7c7cd`, `7b5686c`).**  Jonli server endi `enes` loyihasi:
  `/home/deploy/enes` (`chaqimchi-ai` → symlink), `/etc/enes`
  (`/etc/chaqimchi` → symlink), `.env.production` va `backup.env` da
  `ENES_*` (nusxalar `*.bak-f7` va `/home/deploy/env-backups/`),
  volume'lar `enes_*` ga NUSXALANDI (eski `chaqimchi_*` rollback uchun
  turibdi, ~310 MB), backup timer'lari `enes-backup*`, kod **0.6.33** —
  ya'ni 10-sentabrdagi 6 commit (tungi nazorat cloud qismi, dizayn-3
  paneli, rasmli hisobot) ham jonli.  Hodisa soni ko'chirishdan oldin va
  keyin **5 894**, `/health/deep` ok, loglarda 0 xato, hamma konteyner
  healthy.  Eski domen hostlari 200 (`api.chaqimchi.uz` proxy — pilot
  shu yerda qoladi), canonical/sitemap `enes.uz`.
  **Yangi bot `@enes_monitoring_bot`** — webhook hozircha
  `https://api.chaqimchi.uz/api/v1/telegram/webhook` (yangi token bilan;
  `api.enes.uz` DNS'siz).  ⚠️ **Eski a'zolarga yangi bot yoza olmaydi** —
  pilot egasi yangi botda `/start` bosishi kerak (admin paneldan yangi
  taklif havolasi).  Ops/lead boti (`ENES_CLOUD_TELEGRAM_TOKEN`,
  `ENES_SALES_*`) eski bot — tegilmadi.
  **✅ DNS QO'YILDI (ega, 2026-09-11 02:10):** `@`, `www`(CNAME), `app`,
  `api`, `dl`, `docs`, `partner`, `admin` → 169.58.198.111; `mail`/`ftp`
  o'chirildi (nspos'da FTP/SMTP yo'q, tekshirildi); MX/DKIM/SPF/DMARC
  qoldi; `tizim.enes.uz` (ERP nspos, 169.58.216.246) TEGILMADI va
  ishlayapti.  aHost paneli TTL 300 ni qabul qilmadi — hammasi 14400.
  Caddy 8 ta sertifikatni oldi (`certificate obtained successfully` ×8),
  har host `--resolve` bilan 200 va haqiqiy TLS; webhook
  `https://api.enes.uz/api/v1/telegram/webhook` ga ko'chirildi (pending 0);
  `/api/v1/public/urls` → `enes.uz`.  **✅ Apex tarqaldi (jonli
  tekshiruv 2026-09-11 02:37 +05):** `enes.uz`/`www` 1.1.1.1, 8.8.8.8,
  9.9.9.9, OpenDNS — hammasida 169.58.198.111; serverda apex sertifikati
  Let's Encrypt `CN=enes.uz` (Dec 9 gacha), 8 host ham olingan, Caddy ACME
  urinishlari DNS'dan keyin (20:59 UTC) to'xtagan, 0 xato.  Faqat
  **mahalliy kesh** (masalan, agent Mac'ining mDNSResponder'i) hali eski
  185.196.212.52 ni beradi — brauzerda `*.ahost.uz` sertifikat xatosi
  chiqsa, sabab shu; TTL 14400 tugashi bilan o'tadi.
  Deploy oldi `tests` bilan tutilmagan xato: Docker frontend bosqichi
  `tokens.css` ni nusxalamasdi (F1 dan beri birinchi Docker qurilishi) —
  sayt ~8 daqiqa o'chiq turdi, tuzatildi va qulflandi.

- **🌙📊 TUNGI NAZORAT + YANGI PANEL (dizayn-3) + RASMLI HISOBOT — KODDA
  TAYYOR, 5 commit (2026-09-10, `ec34ccb`…`b7a1e02`).**  Ega uchta ish
  so'radi; hammasi kodda, testda va bundle'da.  **Cloud qismi 11-sentabr
  cutoveri bilan deploy qilindi** (yuqoriga qarang); qurilma qismi 0.6.33
  relizini kutadi.
  Ikki yo'lga bo'linadi:
  - **Cloud + panel (cutover deployi bilan chiqadi):** yon menyu 14 → 8
    bo'lim (bo'lim ichida tab, eski manzillar `LEGACY_ROUTES` orqali o'z
    joyiga); bosh sahifa mockup tartibida (davr tanlagich Bugun/7/30,
    KPI rost raqamlar, issiqlik xaritasi kichik ko'rinishi, hodisalar
    donut, rangli belgili AI hodisalari); yangi **«Tahlil»** sahifasi —
    4 grafik (`GET /api/v1/owner/overview?days=`, `retail_daily` dan);
    Sozlamalar → **ish vaqti** maydoni (`open_from/open_to` — bungacha
    ega panelida YO'Q edi, ya'ni tungi nazorat pilotda o'chiq bo'lishi
    mumkin; dashboard `night_watch` + bosh sahifada banner); Telegram:
    kunlik/haftalik hisobot va `/hisobot` avval **grafik rasm** + qisqa
    izoh, keyin matn (`cloud/chartimg.py`, Pillow, DejaVu shrifti repoda —
    kirill uchun); tungi hodisa kadri ustiga vaqt/kamera; xabarda 🌙,
    hisobotda «Tunda: N».  **Yangi bog'liqlik `Pillow`** — Docker image
    qayta quriladi (deploy skripti buni o'zi qiladi).
  - **Qurilma (0.6.33, F8 relizi bilan, pilot tirilgach):**
    `enes/retail/nightmode.py` — IR o'tishini sezish (to'yinganlik < 8),
    `dark` (yorug'lik < 25) → tamper `relearn()` + MOG2 `reset()`,
    `dark` da detektorga CLAHE nusxa va ramka 1.5×; yangi hodisa
    **`night_motion`** (yopiq do'konda 3% harakat 3 s; odam tanilganda
    jim); har tungi hodisaga `metadata.night`; `rules.yaml` da tungi
    qoidalar BIRINCHI.  ⚠️ **Deploy tartibi: AVVAL cloud, KEYIN reliz** —
    eski cloud `night_motion` ni tanimaydi va batchni rad etadi
    (`outbox_poisoned`), tuzoqlarga qarang.
  - **Kalibrlanmagan chegaralar** (haqiqiy IR kamerada sinalmagan):
    `CHROMA_MAX_IR=8`, `DARK_BRIGHTNESS=25`, `NIGHT_MOTION_RATIO=0.03`,
    `NIGHT_MOTION_SEC=3`.  Pilotda kechqurun heartbeatda
    `cameras[].night_mode: ir` ko'rinishi va `tamper_alerts` o'smasligi
    — birinchi tekshiruv.

- **🔴 PILOT HAMON O'LIK — 44 SOAT (jonli tekshiruv, 2026-09-10 21:39 UTC,
  cutoverdan keyin).**  Oxirgi heartbeat `2026-09-09T01:51:09Z`,
  `app_version 0.6.25` — ya'ni ma'lumot papkasi do'kon kompyuterida HALI
  nusxalanmagan.  `pending_devices` da `DESKTOP-GVOE93B` (`ENES Windows`,
  `0.6.30`, `verify_code AB4B70`) turibdi va qator `21:11:22 UTC` da
  yangilangan, ya'ni **0.6.30 jarayoni tirik va hamon `device-handover`
  so'rayapti** — cutover unga ta'sir qilmadi (`api.chaqimchi.uz` proxy
  ishlayapti).  Do'kon xuddi shu muddat davomida ko'r.  Serverdan
  so'rash: `docker compose exec -T cloud python -` + `sqlite3`
  `/app/data/cloud/cloud.db` (boshqaruv DB Postgresda EMAS — `devices`,
  `pending_devices` u yerda yo'q).

- **🔴 KOD BILAN TASDIQLANDI: PILOT O'ZI YANGILANA OLMAYDI.**  Ilgari
  daftar «papkani nusxalash» va «0.6.32 ni chiqarish» ni ikki mustaqil
  ish deb yozardi — ular aslida qat'iy tartibda.  Zanjir:
  `enes/local/updater.py:79` `_cloud()` → `config_store.read_raw()` →
  `enes/local/paths.py: config_path()` → bo'sh `%PROGRAMDATA%\ENES` →
  `config.yaml` yo'q → `device_token` yo'q →
  `UpdateError("Cloudga ulanmagan — yangilanish tekshirilmaydi")`.
  **Yangilagichning O'ZI o'lgan**, ya'ni nosozlikni masofadan tuzatib
  bo'lmaydi: reliz qancha chiqarilmasin, do'kon kompyuteriga tushmaydi.
  ⏳ **Do'kon kompyuterida (yagona yo'l):** «ENES Monitoring» vazifasini
  to'xtatish → `C:\ProgramData\Chaqimchi` ni `C:\ProgramData\ENES` ga
  NUSXA (ko'chirish emas) → vazifani qayta ishga tushirish.  Shundan
  keyin qurilma 0.6.30 da tirilib, 15 daqiqada 0.6.32 ni o'zi oladi.
  ⚠️ **Panelda ulanish kodini TASDIQLAMANG.**  U yangi papkaga
  `config.yaml` yozadi va shundan keyin 0.6.32 ko'prigi (`_pick()`
  belgisi aynan `config.yaml`) eski papkani hech qachon tanlamaydi —
  outbox navbati va bufer abadiy yetim qoladi.

- **✅ BIOMETRIK QO'RIQCHI TO'RT MARSHRUTDA HAM YOPILDI (2026-09-10,
  `1d70c43`).**  `GET /owner/faces`, `/owner/employees`,
  `/owner/attendance{,.csv}` va `/owner/events?event_type=employee_seen`
  faqat `require_attendance()` bilan turgan edi — u esa qo'riqchi emas,
  RUBILNIK: rolga umuman qaramaydi.  Auditning KRITIK-4 sinfi, boshqa
  URL orqali.  **`/owner/events` ga marshrut darajasida qo'riqchi
  QO'YILMADI** va bu ataylab: u «Dalillar» sahifasining yagona manbai,
  ya'ni menejerning asosiy ish quroli o'lardi — qo'riqchi TURGA
  qo'yildi.  Yon kanal ham yopildi: oylik smena hisoboti Telegramda
  barcha a'zolarga ketardi.  ⏳ **Faqat cloud — cutover deployi bilan
  chiqadi.**

- **🎬 KLIP TUZATILDI — ildiz sabab ORTIQCHA BITTA `%` edi (2026-09-09,
  `188a7c5`, 0.6.31).**  Recorder aslida hamma vaqt yozib turgan ekan.
  `record_command()` ffmpegga `camera-01-%%Y%m%d-%H%M%S.mp4` uzatardi
  (`SEGMENT_TIME_FORMAT` ning o'zida `%` bor, oldiga yana bittasi
  qo'yilgan edi); `-strftime 1` da `%%` literal `%` bo'ladi va disk
  fayli `camera-01-%Y0909-041347.mp4` deb yozilardi — `SEGMENT_PATTERN`
  uni tanimasdi.  Ya'ni `scan()` **doim bo'sh**: har hodisada "buferda
  segment yo'q" va `prune()` ham hech narsani o'chirmagan (retention
  ham, 40 GB kvota ham amalda ishlamagan — bufer mijoz diskida
  cheksiz o'sgan).  Xato funksiya tug'ilgan commitdan beri bor
  (`7bfa07c`, 13-avgust): klip **hech qachon** ishlamagan.
  **Ikkinchi, ustma-ust xato:** ffmpeg `-strftime` da MAHALLIY vaqt
  yozadi, kod esa nomni UTC deb o'qirdi (`pipeline.py` izohi shu
  noto'g'ri farazni yozib ham qo'ygan edi) — UTC+5 da har segment besh
  soat "kelajakda" ko'rinardi.  Birinchisi yolg'iz tuzatilsa klip
  baribir chiqmasdi.  **Ikkalasi ham lokal ffmpeg 8.1.1 bilan qayta
  ko'rsatildi**, keyin testga aylantirildi.
  Yo'l-yo'lakay: xom segment oynasi tayyor klip muddatidan ajratildi
  (`segment_retention_sec` = 10 daqiqa; ilgari ikkalasi 3 kun edi va
  tuzatishdan keyin har 30 soniyada ~60 000 fayl `stat()` qilinardi),
  eski nomli fayllarni `prune()` endi o'zi tozalaydi.
  ⏳ **Pilotda tasdiqlanadi** (0.6.31 yetgach): `clips.written > 0`,
  `no_segments` o'smaydi, `disk_free_bytes` o'sib ketadi.

- **🚀 0.6.30 NASHR QILINDI — «O'TISH RELIZI» (2026-09-09, `f6cb8fc`).**
  Fayl ataylab ESKI nom bilan: `chaqimchi-windows-0.6.30.exe`,
  `product: "chaqimchi-windows"`.  **Sabab — rebrend avto-yangilanish
  zanjirini uzgan edi** va buni hech narsa aytmasdi: pilotdagi 0.6.25
  ning `KNOWN_PRODUCTS` ro'yxati faqat eski nomlarni biladi, jonli
  cloud esa `releases/` dan faqat `chaqimchi-windows-*` juftini
  qidiradi — ya'ni yangi nomdagi reliz **hech kimga yetmasdi**.
  Tekshirildi: manifest 0.6.25 KODINING O'ZI bilan (git'dan olib)
  ochib ko'rildi — qabul qiladi.  Cloud `0.6.30` beryapti, `dl.` dan
  fayl ochiladi.  ⚠️ **To'g'rilandi (09-sen):** "keyingi relizlar yangi
  nomda ketaveradi" degan xulosa ERTA edi.  Qurilma tomoni ochiq
  (0.6.30 ning `KNOWN_PRODUCTS` da `enes-windows` bor), lekin JONLI
  cloud hali `c0c8cbb` gacha bo'lgan kodda va `releases/` dan faqat
  `chaqimchi-windows-*` ni qidiradi.  Ya'ni birinchi `enes-windows-*`
  reliz faqat **cloud deploy qilingandan keyin** (F7) chiqadi;
  undagacha har reliz `LEGACY_NAME=1` bilan.
  ⏳ **Pilotda tekshirilsin** (kodda bor, Windows'da sinalmagan): eski
  `Software\ChaqimchiAI` o'rnatishi olib tashlandimi; «Chaqimchi AI»
  vazifalari o'chib «ENES Monitoring» BITTA nusxada yaratildimi;
  `ProgramData\Chaqimchi` papkasi (juftlik) saqlanganmi; heartbeatda
  `app_version: 0.6.30` va `stale_chains: {}`.

- **🐘 5B TUGADI — `--workers 2+` yo'li ochiq (2026-09-09, `9e80352`,
  `6f474bc`, `b847b30`).**  Uchta to'siq ham yopildi:
  1. **Tezlik cheklovi umumiy bazada** (`rate_limit_windows`, hodisa
     bazasida — u production'da allaqachon PostgreSQL).  Ilgari hisob
     xotirada edi va har worker o'zinikini yuritardi, ya'ni chegara
     worker soniga KO'PAYARDI.  Baza javob bermasa so'rov o'tadi.
  2. **Fon vazifalari faqat YETAKCHIDA** (`cloud/leader.py`,
     `cloud_leases`).  `lifespan` har worker'da OLTITA fon vazifasini
     ochardi — ikki worker bilan mijoz kunlik hisobotni ikki marta
     olardi.  Kunlik hisobotda belgi endi yuborishdan OLDIN qo'yiladi.
  3. **Worker soni env'dan** (`ENES_CLOUD_WORKERS`, standart 1) va
     shartlar bajarilmasa server umuman ko'tarilmaydi
     (`multi_worker_problems`): boshqaruv bazasi + hodisa bazasi
     PostgreSQL, `ENES_RATELIMIT_SHARED` o'chirilmagan.
  **Qoldi:** jonli bazani ko'chirish (`scripts/migrate_control_db.py`,
  zaxira bilan) va shundan keyin `ENES_CLOUD_WORKERS=2` — ikkalasi ham
  deploy kuni.  Tartib: `docs/PRODUCTION_RUNBOOK.md` §1.1 va §1.2.

- **✅ SOAK TUGADI — jonli dalil bilan (2026-09-09, o'qish tekshiruvi).**
  Qurilma **9,1 kun** uzluksiz (`uptime_sec: 787 992`), `stale_chains: {}`,
  `analysis_errors: 0`, `chain_restarts: 2`, fps 17,0, latency 47 ms,
  CPU 8,2%, RAM 48%, `outbox_pending/poisoned/queue_errors: 0`.
  Cloud: hamma konteyner healthy (13 kun), 24 soatda **0 ta** 5xx va
  **0 ta** ERROR, disk 14%.  Kunlik raqamlar yozilyapti (08-sen:
  169 kirdi / 155 chiqdi; eshik taqsimoti uch chiziq bo'yicha) va
  kunlik hisobot har kuni 16:00 UTC da ketyapti.
  **🎉 720p YOQILGAN KO'RINADI:** `face_crops {written: 25, too_small: 4}`
  — ilgari `{0, 93}` edi, ya'ni yuz kadri endi **rostdan olinyapti**
  (3 kunda 7 ta `face_captured` hodisasi).  Demografiya esa hali 3,1%
  (`40/1288`) — o'rtachani `camera-02` (352×288) tushiryapti.
  **Ochiqligicha qolgani:** klip yozilmaydi (`clips {written: 0,
  no_segments: 36}`, `clips_last_error: "buferda segment yo'q"`) va
  bulutdagi kamera probe'i hech qachon ishlamagan
  (`site_cameras.width/height` NULL, `probe_status: pending`).

- **🚫 DEPLOY TAQIQI — `main` cutover kunigacha SERVERGA CHIQMAYDI.**
  Jonli server hali eski kodda.  Compose fayldagi `${ENES_*}`
  almashtirishlari serverdagi env yangilanmaguncha BO'SH qoladi va
  `enes/envcompat.py` ko'prigi bunga yordam bermaydi — u faqat Python
  ichida ishlaydi, compose'ning o'zi Python'dan o'tmaydi.  Tartib:
  F7 §2 (serverda `mv` + `sed`) → keyin deploy.

- **✅ SHOX `main` GA QO'YILDI (2026-09-09).**  `enes-rebrend` → `main`
  fast-forward (148 commit, `101befd` → `a807983`), `origin/main`
  yangilandi.  Shox tarix uchun QOLDIRILDI, keyingi ish `main` da.

- **🐘 5B — BOSHQARUV BAZASI PostgreSQL'DA HAM ISHLAYDI (2026-09-09,
  `0045f4a`, `2e2a5c0`, `2e3db31`, `7a30b77`).**  `cloud/store.py` va
  `cloud/payments/store.py` ikki dialektli; yoqish IXTIYORIY —
  `ENES_CONTROL_DATABASE_URL` bo'sh bo'lsa hammasi avvalgidek
  SQLite'da.  **`DATABASE_URL` ATAYLAB ishlatilmadi**: u hodisalar
  uchun allaqachon qo'yilgan va `CloudStore` ham o'shani o'qiganda
  deploy litsenziya/to'lovlarni bo'sh sxemaga yo'naltirardi.
  Ko'chirish: `scripts/migrate_control_db.py` (hech narsa
  o'chirmaydi, qatorlarni sanab solishtiradi, mos kelmasa to'xtaydi).
  Tartib va qaytish yo'li: `docs/PRODUCTION_RUNBOOK.md` §1.1.
  **Naqsh farqi:** `event_store` har so'rovni `_sql()` bilan o'raydi,
  bu yerda esa ULANISHNING O'ZI o'ralgan (`_PostgresConnection`) —
  200+ so'rovda bitta unutilgan `_sql()` faqat productionda
  ko'rinardi.
  **⚠️ `--workers` HALI KO'TARILMAYDI:** `cloud/ratelimit.py` xotirada
  va har worker o'z hisobini yuritadi, ya'ni chegara worker soniga
  ko'payadi.
  **Qoldi:** rate limitni bazaga ko'chirish, keyin `--workers 2+`;
  jonli serverda ko'chirish (zaxira bilan).

- **🧮 «TARMOQ» KALKULYATORI (2026-09-09, `cbe7599`).**  Karta
  «so'rov bo'yicha» derdi va tugma to'g'ridan-to'g'ri arizaga olib
  borardi — mijoz kattalik haqida tasavvursiz ketardi.  Endi tugma
  kalkulyatorni ochadi: do'kon soni × funksiya × kamera → taxminiy
  oylik va yillik summa, ariza shu hisob bilan boradi.  Summani
  **server** hisoblaydi (`POST /api/v1/public/quote`, `feature_quote`
  ustida) — saytda qo'shish yo'q.  **Tannarx va marja javobga
  chiqmaydi**, maydonlar ro'yxati aniq sanaladi.  Chegara 1–100
  do'kon (forma chegarasi, mahsulot chegarasi emas).  Matn uch tilda:
  HTML `site.calc.*`, JS `site.js.calc_*`.

- **💳 5A BOSHLANDI — obuna eslatmasi to'lov sahifasiga ulandi
  (2026-09-09, `e713a7d`).**  Eslatma «To'lovni panelda ochasiz» deb
  tugardi va zanjir shu yerda uzilardi.  Endi xabarda to'lov
  sahifasining o'zi (uch tilda, yangi kalit `digest.renewal.pay_link`);
  to'langach obuna `mark_paid` → `extend_subscription` orqali o'zi
  uzayadi.  Hisob DAVR bo'yicha ochiladi (bosqich bo'yicha emas):
  bitta davr uchun uchta eslatma ketadi va uchalasi AYNAN bir hisobga
  ishora qiladi; admin qo'lda ochgani ham chetlab o'tilmaydi.
  `DailyDigestService` to'lov qatlamini import qilmaydi — chaqiruv
  orqali oladi (`renewal_invoice`), aks holda aylanma bog'liqlik
  chiqardi.  `ENES_PUBLIC_URL` yo'q bo'lsa havola ham, hisob ham
  ochilmaydi.  **Qoldi (5A):** Payme/Click merchant kalitlari (egadan), karta
  tokeni bilan avto-yechish (shartnomada recurring ruxsati kerak),
  demo 7 kunmi/14 mi degan qaror (`quick-trial` hozir 14).

- **🔒 CSP MAJBURIY REJIMGA TAYYOR (2026-09-09, `e068cf9`, `701ec62`).**
  Sahifalarda ijro etiladigan inline `<script>` ham, `onclick="…"`
  atributi ham QOLMADI: sakkiz sahifadan 691 qator JS
  `cloud/static/*.js` ga chiqdi, server va katalog qo'yadigan
  qiymatlar esa `application/json` bloklariga (`#page-text`,
  `#page-links`, `#site-data`, `#bot-url` — ular ijro etilmaydi,
  ya'ni `script-src` ularga tegmaydi).  10 ta inline ishlov beruvchi
  `data-act` + delegatsiyaga o'tdi.  Yagona istisno — panel
  qobig'idagi tema bootstrap'i (birinchi chizishdan oldin ishlashi
  SHART), u CSP hashiga olindi.  Siyosat o'sha paytda `-Report-Only`
  edi; **2026-09-12 da majburiy qilindi** (I bloki).
  Frontend versiyalari ham qotirildi (`latest` → `^19.2.8` va h.k.).
  To'liq: **2 157 passed, 1 skipped**; lokal serverda 7 sahifa va
  8 JS fayl 200, uch tilli data blok tekshirildi.

- **🔧 QADAM 3 — CUTOVERGACHA CLOUD TUZATISHLARI TUGADI (2026-09-09,
  `39352a8`, `e58a974`, `a889175`, `1e027f1`, `83c055c`, `a466e06`).**
  Beshtasi ham cutoverga bog'liq emas, hammasi cutover kuni bitta
  deployda chiqadi.  To'liq to'plam: **2 153 passed, 1 skipped**.
  - **CI to'liq** — ish endi `make lint` va `make test` chaqiradi
    (`setup-node` + `npm ci`).  Ilgari faqat `ruff` va `pytest` edi,
    ya'ni `i18n/*.json` yoki `cloud/site/*` qayta qurilmagan commit
    CI'da yashil bo'lardi.  Qulf: `tests/test_ci_workflow.py`.
  - **🔴 `shelf` bayrog'i SAQLANMAS EKAN** — `zone-editor.js:serialise()`
    `restricted` va `queue` ni yozardi, `shelf` ni esa tashlab
    yuborardi.  Ya'ni «javon» andozasi saqlangach belgisini yo'qotardi
    va serverdagi mavjud sozlama ham kimdir chizmani qayta saqlagan
    zahoti jimgina o'chardi — `enes/retail/shelf.py` (`shelf_empty`)
    amalda hech qachon yoqilmagan bo'lishi mumkin.  Ikkinchi yarmi:
    `cloud/static/geometry-panel.js` da «javon» checkboxi yo'q edi,
    ya'ni usta zonani javon deb belgilay olmasdi.  Kesh tokeni ikkala
    chaqiruvchida `v=4` ga tenglashtirildi.
  - **Server tomonda chiqish (O-8)** — `owner_members.auth_version`
    (`portal_accounts` naqshi), `POST /api/v1/owner/auth/logout` va
    `POST /api/v1/auth/logout`, panelda `api.ts: logout()`.  Versiya
    **tokenni bergan** a'zolik qatoriga nisbatan tekshiriladi (ko'p
    filialli egada tanlangan filial boshqa qator).
  - **CSP (O-2)** — ikkala Caddyfile'da; o'sha paytda `-Report-Only`
    edi, **2026-09-12 da majburiy** bo'ldi.  Qulf:
    `tests/test_security_headers.py` (ikki fayldagi siyosat TENG,
    siyosat bo'shab ketmasin, kuzatuv rejimi qaytmasin).
  - **`/health/deep` resurs ogohlantirishi (O-1)** — `server` va
    `warnings` maydonlari, **503 qilmasdan**; chegaralar Telegram
    ogohlantirishi bilan bitta manbadan (`alerts.server_health_warnings`).
    Raqamlar admin kaliti bilan.
  - Yetim `cloud/static/chaqimchi-logo-blue.svg` o'chirildi.

- **🏷 F6 + F9 — ICHKI NOMLAR VA TOZALASH TUGADI (2026-09-08, `b8883d8`,
  `ef558cd`, `c0c8cbb` + hujjat commiti).**  Paket `chaqimchi_ai` →
  `enes` (184 fayl); 134 ta `CHAQIMCHI_*` → `ENES_*`; reliz
  `enes-windows-<v>.exe` / `ENES_Setup.exe`; xizmatlar `enes-*.service`;
  yo'llar `/opt/enes`, `/etc/enes`, `/home/deploy/enes`,
  `ProgramData\ENES`; Docker `enes-cloud`, `docker-compose.enes.yml`,
  `Caddyfile.enes`; `product_name` «ENES Windows»; brauzer kalitlari
  `enes_owner_token`/`enes_admin_token`; JWT `kind` yangi (hamma
  qaytadan kiradi).  **Ko'priklar** (ataylab, `tests/test_brand.py`
  ro'yxatida): `chaqimchi_ai/__init__.py` (eski paket nomi — pilot
  kompyuteridagi `-m chaqimchi_ai.local.updater` vazifasi uchun,
  payloadga kiradi), `enes/envcompat.py` (eski env nomlari yangisiga
  ko'chiriladi), cloud eski `chaqimchi-windows-*` relizlarni ham
  tarqatadi, `paths.py` eski ma'lumot papkasini ishlatadi (2026-09-09
  gacha bu FAQAT `enes/paths.py` da rost edi — `enes/local/paths.py` da
  ko'prik yo'q edi va pilot shu sababdan to'xtadi), `autostart`
  va NSI eski vazifa/registrni topib o'chiradi, `sign_release` eski kalit
  yo'lini ham ko'radi.  Hujjatlar (CLAUDE.md, docs/*, README) yangi
  nomda; ISH_DAFTARI/AUDIT_TAHLIL/STRATEGIK tarix sifatida eski nomni
  saqlaydi.  `og-enes.png` (PIL bilan yasalgan vaqtinchalik OG rasm —
  egadan NS SVG kelgach almashtiriladi), `og-v3.png` va
  `chaqimchi-logo-new.png` o'chdi.  `releases/` 2.2 GB → 294 MB (0.6.24,
  0.6.25 va `Chaqimchi_AI_Setup.exe` qoldi).  **Qolgani egadan (F7):**
  domen `chaqimchi.uz` va `@chaqimchi_ai_bot` kodda shu turadi.
- **🌐 F5 — TELEGRAM, HISOBOT, CSV, TARIF UCH TILDA (2026-09-08, `28e2c8b`).**
  Server chizadigan matn katalogga o'tdi va til ANIQ uzatiladi
  (`tg(lang, key)`).  `digest.py` builder'lari `lang` oladi; `_deliver`
  matnni a'zoning `owner_members.language` ustuniga qarab bir marta
  yasab keshlaydi — bitta do'konda o'zbek ega va ruscha menejer har biri
  o'z tilida oladi.  `alerts.py`: egaga boradigan matn `OwnerMessage`
  (til bo'yicha yasovchi), `_notify_site_members` uni har a'zo uchun
  ochadi; ichki ops ogohlantirishlari ataylab o'zbekcha qoldi.
  `notify.py`, `trust_score.py`, `botfmt.py`, `value.py` katalogga;
  «3.2 / 3,2 mln so'm» nomuvofiqligi yopildi.  Bot: javob tili a'zodan,
  notanish odam uchun Telegram `language_code` dan; `/start` da profil
  tili a'zoga yozib qo'yiladi (faqat standart `uz` turganda).  CSV:
  sarlavha va fayl nomi so'rov tilida (`otchet-magazina-…csv`), BOM
  saqlanadi.  Tarif kartasi: `PlanBullet.key` + `params`, matn
  `enes` ichida uz manba, tarjima katalogda; kamera soni
  `limits` dan (`{count}`).  `tests/test_i18n_surfaces.py` (7 test)
  qulflaydi.  Katalog: **1 160 kalit**, uch tilda teng.
- **🌐 F4c — EGA PANELI MATNI UCH TILDA (2026-09-08, `1edc5f3`).**
  Ega panelining barcha ko'rinadigan matni (12 fayl) `t("panel.*")`
  bilan chiziladi; ~850 yangi kalit (`panel.common.*` 43 umumiy so'z,
  `panel.nav/owner/cameras/employees/billing/telegram/traffic/settings/
  download/home/numbers/demo/heat/evidence/timeline/agent/setup/
  geometry/connect/login/lock/shell.*`).  `api.ts` sana/pul/«oldin»
  yordamchilari `format.*`/`money.*` dan, `Intl`siz.  Modul darajasidagi
  ro'yxatlar (`NAV_ITEMS`, `PERIODS`, `TELEGRAM_LEVELS`, `PRESETS`,
  `ROLE_CHOICES`) kalit saqlaydi, matn chizishda ochiladi.  Telegram
  a'zosini o'chirish `ConfirmDialog` bilan.  Testlar kalitga bog'landi
  (`key_text` yordamchisi `test_connect_ui`/`test_events_ui` da).
  Admin paneli matni o'zbekcha qoldi (ichki vosita, oxirgi navbat).
  **Ega ko'rigi kerak:** ruscha/inglizcha tarjima mashina emas, lekin
  tarjimon ko'rmagan — `i18n/ru.json`, `i18n/en.json` ni bir marta
  o'qib chiqish (ayniqsa `panel.agent.*`, `bot.*`, `digest.*`).
- **🎨 F4a — ADMIN VOSITALARI REACT'GA KO'CHDI (2026-09-08, `dc60e2c`).**
  `/admin/customers/{id}` — mijoz tafsiloti: holat banneri, kamera
  ro'yxati (probe/sifat/rol), qurilma health satrlari (tashlangan
  hodisalar, klip, zanjir, yuz kadri, demografiya, eski zanjirlar),
  `feature_problems`/`geometry_problems`/`role_problems`; tugmalar:
  kamera qo'shish, kamera soni, ulanish havolasi, yangilanish siyosati,
  chiziq va zona (`GeometryEditor kind="admin"`), diagnostika (+ sig'im
  o'lchovi natijasi), eski jarayonlarni tozalash, sig'imni o'lchash;
  login yaratish/parol, Telegram egasi, kirish havolasi; AI imkoniyatlar
  (katalog, to'plam, narx, qoralama, tasdiq), hisob ochish, to'lovsiz
  uzaytirish, tarif almashtirish; yuz tanish (xodim, rasm, kadrlar);
  obunani to'xtatish (nomni terib).  Yangi sahifalar: **Jamoa**
  (loginlar, holat, parol, yaratish; o'rnatuvchi biriktirish) va
  **Sozlamalar** (tayyorlik, Telegram sinovi, yangilanishni to'xtatish,
  provayderlar).  To'lovlar: modal orqali qayd (naqd/bank), bekor
  qilish, havola.  `window.confirm` yo'q — `ConfirmDialog`/`Modal`
  (`components.tsx`).  Marshrut ikkinchi segmentni o'qiydi
  (`router.ts: param`).  Ikkala `xfail` olindi.  Qobiq sarlavhalari va
  paneldagi ko'rinadigan matn ENES.  **Deploy to'sig'i ochildi** —
  React admin eski adminni to'liq qoplaydi (yuz tanish va faces
  hodisalari ham).
- **🎨 F3 SAYT TUGADI (2026-09-08, `4f199ce` + `99ed0e6`).**  Bosh sahifa va
  qolgan 13 sahifa `cloud/site/` shablonlaridan quriladi; umumiy nav va
  footer `cloud/site/partials/` da.  Uch tilli: bosh sahifa, aloqa,
  hamkorlik, holat, ulash, yuklab olish (`/ru/aloqa`, `dl.` hostida
  `/ru/`).  O'zbekcha qoladi (yuridik va texnik): oferta, maxfiylik,
  rozilik, kuzatuv eslatmasi, o'rnatish yo'riqnomasi, edu, to'lov,
  o'rnatuvchi qo'llanmasi.  Hujjat sahifalari (`docs/`) brend va
  tokenlarga o'tdi.  `owner.css`/`panel.css` O'CHIRILDI (`pay.html`
  `site.css` ga o'tdi).  Hamma shablonli sahifa `_render_public` orqali
  (nav/footer'dagi `__APP_URL__` uchun).  `hamkorlik` matnidagi yolg'on
  va'da («obyekt ochib kod olasiz») rostiga almashdi.
  **Qoldi (F5/F7/F8/F9):** tarif kartalari matni, `@chaqimchi_ai_bot`
  va `chaqimchi.uz` havolalari (docs sahifalarida, eslatmada) — cutover
  kuni; `ENES_Setup` fayl nomi — qurilma relizi; `og-v3.png`;
  install/edu tarjimasi (ega xohlasa).
- **🎨 F3.1 — BOSH SAHIFA UCH TILDA, YANGI DIZAYNDA (2026-09-08, `4f199ce`).**
  `cloud/site/index.html` (shablon) + `i18n/*.json` dagi **172 ta
  `site.*` kaliti** → `scripts/build_site.py` → `cloud/static/site.html`,
  `site.ru.html`, `site.en.html` (commit qilinadi, `--check` `make test`
  ichida).  Marshrutlar `/`, `/ru/`, `/en/` (+ slash'siz), canonical va
  `hreflang` har sahifada, `sitemap.xml` da `xhtml:link` alternativlari.
  Namunadagi ritm: qorong'i hero → ochiq imkoniyatlar → qorong'i «AI
  ko'radi» → ochiq qadamlar/kameralar/panel/narx → qorong'i aloqa.
  Sayt tema tugmasiga bo'ysunmaydi (`data-theme="light"`), bo'lim
  ranglari `site.css` dagi `--band-*` tokenlaridan.  Kesh tokeni (`?v=`)
  endi qurish paytida hisoblanadi.  Shior har tilda o'z tilida
  («Kameralaringiz. Endi aqlli.») — ega inglizchasini xohlasa bitta
  kalit (`site.hero.title_*`).
  **Yo'l-yo'lakay topilgan xato:** `Dockerfile.cloud` F2 katalogini
  (`i18n/`) konteynerga nusxalamasdi — deployda birinchi `t()` 500
  berardi.  `COPY i18n ./i18n` qo'shildi, test qulflaydi.
  **F3 dan qolgani (F3.2):** qolgan 14 sahifa + 7 hujjat sahifasi hali
  eski nav/brend bilan (`aloqa.html`, `edu.html`, `install.html`…);
  tarif kartalari matni serverdan o'zbekcha keladi (F5 da katalogga);
  `og-v3.png` eski brend (F9); `edu.html` da «Chaqimchi Edu».
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

- **🎨 REBRENDING BOSHLANDI: ENES Monitoring → ENES Monitoring (enes.uz).**
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
  ruxsat etilmagan; ishlaydigani — `ENES_DEPLOY_SSH_KEY`
  (loyihaning `.env` fayli).  `deploy` foydalanuvchisi bilan
  `docker compose` ISHLAMAYDI (`/home/deploy/enes/.env` faqat
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
  panelga yozildi (`ENES_UI_V2_OWNER=1` production uchun majburiy);
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
  jonli sinaldi (1,1 MB arxiv ketdi).  ⚠️ `ENES_BACKUP_PASSWORD`
  hali FAQAT serverda — parol menejeriga ko'chirilmaguncha bu nusxa
  server o'lganda ochilmaydi.
- **Kamera rollari KODDA TAYYOR (0.6.26, nashr qilinmagan):** rol endi
  saqlanadi va zanjirni boshqaradi — sehrgar → `config.yaml` →
  bulut (`site_cameras.role`) → edge config → `CameraPlan.role`.
  Tizim rol TAKLIF qiladi (kanal nomi + oqim o'lchami), odam
  tasdiqlaydi; «kirish» roli kamerani davomat ro'yxatiga avto-qo'shadi
  (faqat o'tishda, maks. 2); 4 tadan ko'p topilsa eng yaxshi 4 belgilanadi.
  Yagona manba: `enes/camera_roles.py`. **Soak muzlatishi
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
  ochiladi: `dl.chaqimchi.uz/releases/enes-windows-0.6.22.exe`,
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

**REJA 2026-09-12 — qolgan bloklar.**  To'liq reja (bog'liqliklar,
soat bahosi, tuzoqlar) `~/.claude/plans/md-file-ichii-o-qi-linear-tulip.md`
va topilmalar `docs/REJA_2026-09-12_tugallanmagan_ishlar.md` da.
Bajarilgani: **A, D1, D2–D6** (yuqoriga qarang).  Qolgani:

1. **B — sayt xatolari** (~6–8 soat) — **KEYINGI**.  Foydalanuvchi forma xatosida
   `[object Object]` o'qiydi (`cloud/static/site.js:55` + `main.py` da
   `RequestValidationError` handleri YO'Q); JS o'chiq bo'lsa bosh
   sahifada yuklab olish qatori bo'sh; bosh sahifa futeri partialdan
   NUSXA, ya'ni RU/EN sahifada o'zbekcha `/status`, `/hamkorlik`,
   `/aloqa`; `__TELEGRAM_REGISTER_URL__` zaxirasi `/#pilot` — bunday id
   yo'q; edu forma xatosi kulrang va xom `error.message` + `@fibotai`.
2. ✅ **C — panel xatolari** bajarildi (`dbda134`, `5cce2eb`, `1bb740c`).
3. ✅ **E — usta paneli React'ga** bajarildi (commit qilinmagan,
   yuqoriga qarang).  ⏳ Qolgani: **`npm run build`** (qobiq
   `cloud/static/v2/installer.html` shundan keyin paydo bo'ladi) va
   jonli tekshiruv — usta oqimi telefonda uchidan uchiga sinalmagan
   (ro'yxatdan o'tish → obyekt → kamera → chizma).
4. **F — demo 7/14 kun + karta** (~14–18 soat).  Ega qarori: kartasiz
   7 kun, karta ulasa 14 kun va birinchi oyga chegirma; kartadan oylik
   avtomatik yechish.  `cloud/payments/` da recurring kodi UMUMAN yo'q.
   Oferta recurring bandi — yuridik matn, yurist ko'rigi shart.
   Payme/Click merchant kaliti kelmaguncha yoqilmaydi.
5. **G — A1 capture-rate** (~5–6 soat).  Cloud `config["capture"]`
   yubormaydi, ya'ni qurilmadagi 0.6.33 kodi abadiy yopiq;
   `people_seen` `REPORT_EVENT_TYPES` da ham, `TIMELINE_HIDDEN_TYPES`
   da ham yo'q (`MEDIALESS_EVENTS` esa `cloud/main.py:1478` da, event_store'da EMAS).
6. ✅ **I — ops KOD TOMONI TUGADI (2026-09-12).**  CSP majburiy;
   `releases/` o'zini tozalaydi (`prune_windows_releases`).  **Qoldi —
   deploy va ega:** Caddy `--force-recreate` + jonli konsol tekshiruvi;
   serverdagi 1,9 GB birinchi tozalashdan keyin o'lchansin
   (`scripts/prune_releases.py --reja` → host tomonda `rm`);
   UptimeRobot `/health/deep`; `.env.production`.
7. **H — admin i18n** (~8–10 soat, eng kam shoshilinch, E dan keyin).

**UI/UX (2026-09-11) — qoldiqlar:**
1. ✅ Deploy bajarildi.  ⏳ Egadan: panelga kirib bosh sahifa,
   kamera sahifasi (`/owner/cameras/camera-01`) va telefonda tugmalarni
   ko'rib chiqishi; haqiqiy ma'lumotda issiqlik xaritasi rangi.
2. ✅ Ikkita eski yiqilgan test yopildi (`2a6ece3`).
3. NICE (rejada qolgan): issiqlik xaritasi oqarishi — REAL ma'lumotda
   tekshirish (pilot tirilgach), kerak bo'lsa `paintHeat` alfa yig'indi
   usuli; `#aloqa` fonida `shop-corridor-v1.webp`; «AI yordamchi» tabini
   funksiya o'chiq bo'lsa yashirish; Modal fokus tuzog'i; kirish sahifasi
   standart tili (brauzer EN bo'lsa UZ?); `admin.tsx` literal matnlari;
   `panel-bugun-v4.webp` (bosh sahifa o'zgardi — sayt skrinshoti eski);
   EventEvidence kamera sahifasida ikkinchi sarlavhasiz (`embedded`).
4. Playwright `.venv` da ad-hoc (requirements-dev'da yo'q) — harnes CI'da
   ishlamaydi; qo'shish alohida qaror.

**BUGUNGI HOLAT (2026-09-10).** 0.6.32 uch commitga bo'linib commit
qilindi (`fb42f06`, `23b4cad`, `413aef0`) va nashr etildi
(`chaqimchi-windows-0.6.32`, `LEGACY_NAME=1`).  **Egadan DNS va bot
@username KELDI**, Payme/Click, yuridik nom/STIR va NS SVG hali yo'q —
ya'ni F7 cutover yopiq va **deploy taqiqi kuchda**.  Navbatdagi ish,
tartib bilan:

1. **🔴 PILOTNI TIKLASH — do'kon kompyuterida, YAGONA YO'L.**
   «ENES Monitoring» vazifasini to'xtatish → `C:\ProgramData\Chaqimchi`
   ni `C:\ProgramData\ENES` ga NUSXA (ko'chirish emas) → vazifani qayta
   ishga tushirish.  Bu ish **masofadan bajarilmaydi**: yangilagich
   sozlamadan `device_token` o'qiydi, sozlama esa aynan yo'qolgan
   papkada (sabab tepada).  Shundan keyin qurilma 0.6.30 da tirilib,
   15 daqiqada 0.6.32 ni o'zi oladi.
   ⚠️ **Zaxira yo'lini — panelda ulanish kodini tasdiqlashni —
   TANLAMANG:** u yangi papkaga `config.yaml` yozadi va ko'prik eski
   papkani boshqa hech qachon tanlamaydi; outbox navbati va bufer
   abadiy yetim qoladi.
2. **✅ 0.6.32 NASHR QILINDI (2026-09-10)** — papka ko'prigi, capture
   rate 1-bosqichi va 0.6.31 dagi klip tuzatmasi ichida.  Pilotga
   1-qadamdan KEYIN yetadi.  Yetgach tekshirish: `app_version 0.6.32`,
   `clips.written > 0` va `clips_last_error` bo'sh, `no_segments`
   o'smasligi, `disk_free_bytes` o'sib ketishi (ikki oy tozalanmagan
   bufer), `seen.total` — `SEEN_LINE_BAND` ni kalibrlash uchun
   (`seen ≈ entered × 1,5…4`).
3. **A1 «avtomatik konversiya» (capture rate)** — reja va bosqichlar:
   `~/.claude/plans/ok-nimalar-qoldi-tugatishimiz-*.md`.
   **1-bosqich BAJARILDI** (0.6.32): maxraj qurilmada sanaladi va
   heartbeatda ko'rinadi.  Qolgani:
   - **✅ 2-bosqich BAJARILDI (2026-09-10, `b268325`)** — oyna
     yopilganda har kameradan bitta `people_seen` chiqadi
     (`metadata.seen`, `metadata.window_sec`), `capture.enabled`
     darvozasi ortida.  **Qurilma tomoni tayyor, keyingi relizni
     kutadi** (0.6.32 da hali yo'q).
     Yo'l-yo'lakay uchta bo'shliq topildi: `read_sotqin_cache()`
     kalitlarni OQ RO'YXAT bilan qaytaradi (yangi kalit u yerga
     qo'shilmasa keshdagi bayroq filtrgacha yetib bormaydi);
     hodisaga uch tilda nom kerak edi; zanjirni qayta yoqish testi
     manba matnini AYNAN grep qilardi.
   - **3-bosqich (deploy kutadi):** cloud `config["capture"]`,
     `REPORT_EVENT_TYPES`, `TIMELINE_HIDDEN_TYPES` (busiz `people_seen`
     har 10 daqiqada lentaga chiqadi),
     `_retail_report_from_events` → `traffic.seen`,
     `_owner_report_dict` → `capture`.
   - **4-bosqich (deploy kutadi):** `digest.py` 🚶 qatori (faqat foiz
     bo'lsa — sokin kun xabari qisqa qolsin), `Numbers.tsx`, i18n.
   - **5-bosqich (cutover kuni):** `cloud_feature_revision` ni
     ko'tarish — busiz qurilma yangi bayroqni ko'rmaydi.
4. **Cutovergacha qiladigan cloud ishi** (hammasi deploy kutadi).
   ✅ Bajarildi 2026-09-10 da: biometrik qo'riqchi to'rt marshrutda
   (`1d70c43`), `status.js` endi `/health/deep` ni o'qiydi va
   `auth/verify` ga IP cheklovi (`e86615a`).
   ⏳ Qoldi: bundle eskirish qulfi, domen/bot almashuvi (DNS va
   @username keldi — faqat botning aniq nomi kerak).
5. **Egadan kutilmoqda:** `enes.uz` DNS, bot @username, Payme/Click,
   yuridik nom/rekvizit, NS SVG.  Bularsiz F7 boshlanmaydi.

**F7 QOLDIG'I (2026-09-11) — tartib bilan:**
1. ✅ DNS qo'yildi (2026-09-11 02:10, ega) — yuqorida.
2. ✅ Sertifikatlar, host tekshiruvi, webhook `api.enes.uz` — bajarildi.
   ✅ Apex tarqaldi (02:37) — to'rt ommaviy resolver, server serti
   `CN=enes.uz`; faqat mahalliy keshlar TTL 14400 tugaguncha eski IP
   beradi.  Pochta: `@enes.uz` pochtasi kerak bo'lsa `mail` A →
   185.196.212.52 va MX → `mail.enes.uz` qo'shiladi (hozir MX → enes.uz,
   ya'ni bizning serverga — pochta serveri yo'q).
3. ✅ Ega yangi botda `/start` bosdi (2026-09-11 02:20): webhook 5×200,
   xato yo'q, ikki `owner` a'zo (uz, en) o'z joyida, bot menyusi
   `hisobot/kamera/panel/yordam`.  ⏳ Kechqurun 21:00 hisobot rasm+matn
   bo'lib kelishini tekshirish.
4. Ega (agent qila olmaydi — tashqi akkauntlar): UptimeRobot monitor
   `https://api.enes.uz/health/deep` + status page `status.enes.uz`
   (CNAME); Google Search Console yangi mulk `enes.uz` (DNS TXT);
   GitHub `vars.ENES_DEFAULT_CLOUD_URL=https://api.enes.uz` — `gh`
   tizimga kirmagan (`gh auth login`), lekin workflow standarti allaqachon
   `api.enes.uz`, ya'ni o'zgaruvchi ixtiyoriy.
5. Repo: `.env.production.example` — fayl agent uchun to'liq yopiq
   (o'qish/yozish/git ham); qo'lda: `ENES_DOMAIN=enes.uz`,
   `*_URL=https://*.enes.uz`, `ENES_TELEGRAM_BOT_USERNAME=enes_monitoring_bot`.
6. Keyinroq (ega aytganda) — 301 bosqichi: eski domen hostlari
   `enes.uz` ga yo'naltiriladi, `api.chaqimchi.uz` pilot `config.yaml`
   yangilanguncha proxy qoladi; `test_brand.py` dan `chaqimchi\.uz`
   olinadi; eski `chaqimchi_*` volume'lar va `chaqimchi-backup*` unit
   fayllari o'chiriladi.
7. F8 reliz (pilot tirilgach): `ENES_DEFAULT_CLOUD_URL=https://api.enes.uz`,
   `LEGACY_NAME` endi shart emas (yangi cloud `enes-windows-*` ni ham
   tarqatadi) — lekin pilotdagi 0.6.25 hali `chaqimchi-windows-*` ni
   qidiradi, ya'ni BIRINCHI reliz baribir `LEGACY_NAME=1`.

**TUN / PANEL / BOT (2026-09-10) — deploydan KEYIN tekshirish:**
- Cutover deployi (cloud): 21:00 hisobot rasm+matn bo'lib keladimi,
  `/hisobot` rasm bilan (5/600 s cheklov), ruscha a'zoda kirill o'qiladimi;
  panelda 8 bo'lim, eski havola (`/owner/telegram`) o'z joyiga o'tadimi,
  «Tahlil» 4 grafik, Sozlamalar → ish vaqti saqlanib `GET /owner/config`
  da qaytadimi; bosh sahifada ish vaqti kiritilmagan banneri.
- Egadan: pilot do'konining **ish vaqtini panelda kiritish** — usiz
  `after_hours_presence` ham, `night_motion` ham chiqmaydi.
- Qurilma 0.6.33 (F8, pilot tirilgach, cloud deploydan KEYIN): kechqurun
  heartbeat `cameras[].night_mode` (`ir`/`dark`/`day`), tun bo'yi
  `tamper_alerts` o'smasligi, `night.relearns` 1–2 (kechqurun va tong),
  birinchi `night_motion` Telegramda 🌙 va kadr ustida vaqt bilan;
  `night_motion` haddan ko'p bo'lsa `NIGHT_MOTION_RATIO` ni ko'tarish.

**REBREND (2026-09-09).** To'liq holat + xatolar + tartib:
`~/.claude/plans/loyihada-nimalar-qilishimiz-kerak-*.md` (avvalgisi:
`loyiha-bo-yicha-nimalar-qilishimiz-*.md`).  F0–F6 va F9 tugadi
(F4b: panel ikki tema × uch tilda skrinshot bilan tekshirildi,
namunaga mos); shox `main` ga qo'yildi; cutovergacha qilinadigan
cloud tuzatishlari (Qadam 3) ham tugadi.  **Qoldi — egaga va soakka
bog'liq:**

**⏭ CUTOVERDAN KEYIN, kichik lekin unutilmasin:**
- ✅ **CSP majburiy rejimda (2026-09-12).**  Ikkala Caddyfile'da
  `Content-Security-Policy`; siyosat mazmuni va hash o'zgarmadi.
  `tests/test_security_headers.py` endi `-Report-Only` ning qaytishini
  ham bloklaydi (`REQUIRED` dagi oddiy "matn ichida bormi" tekshiruvi
  eski nomni o'tkazib yuborardi — yangi nom uning ichida turadi).
  **Deployda:** Caddy `--force-recreate`, keyin jonli konsolda bitta
  ham `Refused to …` bo'lmasin (`docs/PRODUCTION_RUNBOOK.md` §3.1).
- **UptimeRobot aynan `/health/deep` ni so'rasin** (`/health` ataylab
  doim 200 — Docker HEALTHCHECK uchun).
- **Telegram Mini App va `X-Frame-Options: DENY`.**  `app.` hosti
  `security` snippetini import qiladi, ya'ni panel iframe ichida
  ochilmaydi.  Telegram Desktop/Android'da Mini App WebView (muammo
  yo'q), Telegram **Web** da esa iframe — u yerda mini app ishlamasligi
  mumkin.  Tekshirilmagan; CSP `frame-ancestors 'none'` mavjud xulqni
  takrorlaydi, o'zgartirmaydi.

**F7 — cutover (egadan kirishlar kelgach, bir kunda, tartib bilan):**
1. Egadan: `enes.uz` DNS boshqaruvi (TTL 300 ga tushirish), bot
   @username (BotFather'da yangi nom yoki yangi bot), yuridik nom va
   rekvizit (oferta, `site.*` kalitlari), Payme/Click kabineti, NS SVG
   belgi (`enes-mark.svg`, `og-enes.png` o'rniga).
2. Serverda: zaxira → `/home/deploy/chaqimchi-ai` → `/home/deploy/enes`
   (`mv`), `/etc/chaqimchi` → `/etc/enes`, env fayllarida `CHAQIMCHI_*` →
   `ENES_*` (`sed`; ko'prik tufayli Python uchun shoshilinch emas, lekin
   compose `${ENES_*}` almashtirishlari Python'dan o'tmaydi — shu sabab
   SHART), `ENES_COMPOSE_FILE=docker-compose.enes.yml`, MinIO bucket va
   Postgres nomlari eski qolsa env'da aniq yozilsin
   (`ENES_S3_BUCKET=chaqimchi-snapshots` yoki ko'chirish), compose
   `name:` o'zgargani uchun konteyner/volume nomlari yangi —
   **volume'larni ko'chirish** (`docker volume` nusxa) yoki compose'da
   eski nomni `external` deb ko'rsatish.
3. Kodda (bitta commit): `chaqimchi.uz` → `enes.uz` (Caddyfile, env
   example, CI default `ENES_DEFAULT_CLOUD_URL`, sayt/hujjat havolalari),
   `@chaqimchi_ai_bot` → yangi nom (`i18n/*.json`, `cloud/site/*`,
   `docs/`), `tests/test_brand.py` dagi `ALLOWED_TOKENS` bo'shatiladi.
4. GitHub: `vars.ENES_DEFAULT_CLOUD_URL` o'rnatish; lokal `.deploy_keys/enes_prod`
   (kalit faylini qayta nomlash), `~/.chaqimchi` → `~/.enes`.
5. Caddy sertifikat → `/health` → hodisa/media soni ko'chirishdan
   oldingi bilan teng → heartbeat → `getWebhookInfo` (Telegram webhook
   yangi domenga) → Payme/Click callback → UptimeRobot, Search Console →
   shundan keyin eski domen 301.

**F8 — qurilma relizi (soak tugagach):** versiya ko'tarish, `make
windows-release`, `enes-windows-<v>.exe` nashr.  **Pilotda tekshirish
SHART** (kodda bor, lekin Windows'da sinalmagan): yangi o'rnatuvchi eski
`Software\ChaqimchiAI` o'rnatishni topib olib tashlaydimi; «Chaqimchi
AI» vazifalari o'chib, «ENES Monitoring» yaratildimi (bitta nusxa);
`ProgramData\Chaqimchi` papkasi ishlatilyaptimi (juftlik saqlanganmi);
eski `-m chaqimchi_ai.local.updater` vazifasi ko'prik orqali
ishlayaptimi.  0.6.26 rollar va capture rate (A1) o'zgarishlari ham shu
relizga kiradi.

**Ega ko'rigi:** `i18n/ru.json`, `i18n/en.json` tarjimalari (ayniqsa
`panel.agent.*`, `bot.*`, `digest.*`) — tarjimon ko'rmagan.
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
`ENES_BACKUP_PASSWORD` faqat serverda (`/etc/enes/backup.env`).
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
  darvozalari (`ENES_AVAILABLE_FEATURES` +
  `ENES_N100_ACCEPTANCE_FILE`, oferta STIR/yurist).

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

**✅ YOPILDI (2026-09-09, `188a7c5`) — KLIP: sabab fayl NOMIDA edi**

Tashxis ikki marta noto'g'ri yo'lga burilgan: avval "manzil berilmagan"
(0.6.22 gacha), keyin "recorder buferga yozmayapti" (31-avgust).
Ikkalasi ham qurilmani ayblardi, aslida recorder yozib turgan —
**yozgan faylining nomini o'quvchi tanimasdi**: patternda ortiqcha `%`
(`%%` → literal `%`), ustiga nomdagi vaqt mahalliy, o'qish esa UTC
bo'lgan.  Ikkalasi ham lokal ffmpeg bilan ko'rsatildi va testga
aylantirildi.  Saboq: "recorder yozmayapti" degan xulosa **bufer
papkasiga qaralmasdan** qo'yilgan edi — bir marta `dir data\buffer`
qilinsa sabab birinchi kuni ko'rinardi.

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
  (2026-08-31): `ENES_AVAILABLE_FEATURES` serverda QO'YILGAN**
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
  `ENES_CLIP_RETENTION_DAYS=60` o'rnatilishidan OLDIN standart
  7 kunni muzlatib olardi; to'liq to'plamda oqim kechikib test saytiga
  yetib borib klipni o'chirardi. Fixture endi fon halqalarini no-op
  qiladi (testlar purge'ni sinxron o'zi chaqiradi).
- ✅ **YOPILDI (2026-09-09, 5B) — `cloud/store.py` ikki dialektli.**
  Yoqish ixtiyoriy (`ENES_CONTROL_DATABASE_URL`).  Ochiq qolgani —
  JONLI bazani ko'chirish (`PRODUCTION_RUNBOOK.md` §1.1) va shundan
  keyin `ENES_CLOUD_WORKERS=2` (§1.2).  Ikkalasi ham deploy kuni.
- ✅ **YOPILDI (2026-09-09, 5B) — rate limit umumiy bazada**
  (`rate_limit_windows`).  ✅ **Qoldig'i ham yopildi (2026-09-10,
  `e86615a`):** `POST /api/v1/owner/auth/verify` ga IP cheklovi
  (30/10 daqiqa).  Diqqat — bu kodni sindirishdan emas, **BLOKLASHDAN**
  himoya: kodning o'zi allaqachon `attempts >= 5` bilan qulflangan edi,
  ochiq qolgani esa boshqa xavf — Telegram ID sir emas, ya'ni hujumchi
  begona akkauntga beshta noto'g'ri kod yuborib, qurbonning HAQIQIY
  kodini kuydirib qo'yardi.
- ✅ **YOPILDI (2026-09-12, I bloki) — CSP MAJBURIY** (O'RTA-2).  Ikkala
  Caddyfile'da `Content-Security-Policy`; mazmun o'zgarmadi.  ⏳ Deploy
  paytida Caddy **`--force-recreate`** bilan qayta yaratilsin
  (`docs/PRODUCTION_RUNBOOK.md` §3.1) va jonli konsol tekshirilsin.
- ✅ **YOPILDI (2026-09-09) — server tomonda chiqish bor**
  (`owner_members.auth_version`, `POST /api/v1/owner/auth/logout`).
  Token hamon `localStorage` da, lekin endi uni BEKOR QILISH mumkin.
- ✅ **YOPILDI (2026-09-10, `e86615a`) — `/status` halol tekshiruvni
  o'qiydi.**  Ilgari yengil `/health` edi va baza o'lgan bo'lsa ham
  «ishlayapti» derdi — sahifa aynan kerak bo'lgan daqiqada yolg'on
  gapirardi.  Endi `/health/deep`.  Qarorni test qulflaydi
  (`test_the_status_page_asks_the_honest_health_check`).
  ⏳ UptimeRobot ham `/health/deep` ga qaratilishi kerak — u hali
  qilinmagan (O'RTA-1 qoldig'i).
- **AI aniqligi hech qachon o'lchanmagan** (YUQORI-6) — endi asbob bor
  (masofaviy `benchmark` topshirig'i), o'lchov hali olinmagan.
- **Haqiqiy video/model bilan test yo'q** (YUQORI-8) — chegaralar
  kontrakti (`test_face_crop_contract.py`) yopildi, model yo'li esa yo'q.
- **Faqat o'zbek tili** — rus tili yo'q (O'RTA-3).
- **Vision agent (Gemini) deyarli ishlatilmagan** — `vision_observations`
  0 ta. Saytda va'da qilinmagan, lekin funksiya sifatida o'lik.
- ⏳ **`releases/` da ~1,9 GB eski `.exe`** — 19 ta fayl.  Kod tomoni
  tayyor (`prune_windows_releases`, 2026-09-12), lekin konteynerda
  papka `:ro` — **jonli tozalash hali bajarilmagan**: deploydan keyin
  `docker compose exec -T cloud python scripts/prune_releases.py --reja`
  → ro'yxatni host tomonda `rm` qilish (yoki `publish_windows_release.sh`
  ni keyingi nashrda ishlatish — u shu ikki qadamni o'zi bajaradi).

## TUZOQLAR — bir marta yeb bo'lingan

- **FastAPI validatsiya xatosida `detail` — RO'YXAT, satr emas.**
  `new Error(body.detail)` brauzerda `[object Object]` bo'lib
  chiqadi.  Ochiq API (`/api/v1/public/*`) uchun handler matn
  qaytaradi, panel va qurilma API'lari esa STRUKTURALI `detail` ni
  saqlaydi — `frontend/src/api.ts` uni maydon bo'yicha o'qib qaysi
  maydon xato ekanini ko'rsatadi va matnga aylantirish tashxisni
  yo'qotardi.
- **Brauzer tekshiruvi server qoidasi bilan TENG bo'lsin.**  Telefon
  maydonida `minlength` yo'q edi, server esa `min_length=5` talab
  qilardi — forma jo'natilar, server 422 berar va mijoz sababini
  bilmasdi.
- **JS bilan ko'rsatiladigan blok STANDART HOLDA ko'rinishi kerak.**
  Ikkala variant ham `hidden` bilan boshlansa, JS o'chiq yoki API
  javob bermaganda sahifada bo'sh oq maydon qoladi.  To'g'ri naqsh:
  «kutish» holati ko'rinadi, JS muvaffaqiyatda uni yashiradi.
- **Yuridik hujjatga raqam YOZMANG, havola qiling.**  Ofertadagi narx
  test bilan katalogga bog'langan edi, lekin bu hujjatni har narx
  o'zgarishida tahrirlashni talab qilardi va bir kun unutilishi
  muqarrar.  Endi oferta `/#narx` ga havola qiladi.
- **Telefonda `dblclick` va o'ng tugma YO'Q.**  Zona chizishni
  yakunlash `dblclick` ga, o'chirish `contextmenu` ga bog'langan edi
  — usta obyektda zona chiza olmasligi mumkin edi va buni hech narsa
  aytmasdi.  `.d.ts` da e'lon qilinmagan metod ham shunday yashirinadi
  (`finishDraft()` 2026-08-17 dan bor edi, paneldan chaqirib
  bo'lmasdi).
- **Karta tokeni — «pul yechish huquqi».**  Kamera parolidan
  qimmatroq: ALOHIDA Fernet kaliti (`ENES_CARD_SECRET_KEY`), javobga
  chiqmaydi, «o'chir» deganda `active=0` emas — butunlay o'chadi.
  Yechishdan OLDIN belgi qo'yiladi (jarayon o'rtada yiqilsa ikkinchi
  marta yechilardi) va vazifa FAQAT yetakchida ishlaydi.
- **Sinov muddati uch joyda: kod, sayt matni, oferta.**  Ular testga
  bog'langan bo'lsin — sayt 14 kun deb turaverса mijoz bir hafta
  keyin «vaqt tugadi» xabarini olardi.  Qaytarish muddati (14 kun)
  BOSHQA son va u bilan adashtirmaslik kerak.

- **`releases/` konteynerga `:ro` bilan ulangan — ilova o'zi
  tozalay olmaydi.**  Uchala compose faylida `./releases:/app/releases:ro`
  va ustiga `read_only: true`.  Ya'ni `prune_windows_releases()`
  konteynerda ishlaganda REJA tuzadi, lekin `unlink()` EROFS bilan
  yiqiladi.  Shu sabab tozalash ikki qadamli: QAROR konteynerda
  (`--reja` — qurilma versiyalari bazadan o'qiladi, baza esa faqat
  docker tarmog'i ichidan ko'rinadi), O'CHIRISH hostda.  Mount'ni
  `:rw` qilish yechim EMAS — internetga qaragan ilova qurilmalar
  o'rnatadigan faylni o'zgartira olmasligi ataylab shunday.
- **Reliz papkasida bizning ishimiz bo'lmagan fayllar ham turadi.**
  `ENES_Setup.exe` (relizlar topilmaganda saytga beriladigan zaxira,
  `_windows_installer_file`) va Box/R1 yo'lining `enes-sotqin-*` /
  `enes-lite-*` arxiv-manifestlari.  "Tanimadim" qoidasiga qo'shib
  o'chirilsa yuklab olish 503, Box yangilanishi 404 berardi — shuning
  uchun "tanimadim" faqat `.exe` ga va o'rnatuvchi nomlaridan
  tashqarisiga tegadi.
- **Versiya `device_health` da USTUN emas.**  `app_version`
  `payload_json` ichidagi kalit (`EdgeHeartbeatBody`), ya'ni uni SQL
  bilan olish dialektga bog'lanib qolardi (`json_extract` ↔ `->>`).
  JSON Python'da ochiladi.  Xuddi shu fakt boshqaruv bazasida ham bor
  (`devices.app_version`) — tozalash IKKALASINI o'qiydi: ikki jadval
  ikki BOSHQA bazada va bittasi ko'chirish oynasida bo'shab turishi
  mumkin, bo'sh ro'yxat esa "hech kim ishlatmayapti" degani emas.
- **Fon vazifasi NOL-qadamda o'chirmasin.**  `_maintenance_loop`
  birinchi aylanishi ilova ko'tarilgan zahoti ketadi va o'sha payt
  "qaysi versiya hali kerak" ro'yxati bo'sh bo'lishi mumkin (yangi yoki
  ko'chirilgan baza).  Reliz tozalash shuning uchun 1-qadamdan
  boshlanadi (30 daqiqa): qurilma har daqiqada aloqa qiladi.  Yon
  foyda — `TestClient` bilan ketadigan testlar halqaning faqat nol
  qadamini ko'radi, ya'ni test repodagi `releases/` ni o'chira olmaydi.
- **`fetchone()[0]` qo'riqchisi IZOHGA ham ilinadi.**
  `test_the_store_never_reads_a_row_by_number` faqat `#` bilan
  boshlanadigan qatorni tashlab ketadi — docstring ichida `row[0]`
  deb YOZISH ham testni yiqitadi (loyihada «test o'z izohiga ilindi»
  tuzog'ining takrori).  Naqshning o'zini so'z bilan ta'riflang
  («pozitsion indeks»).
- **Panel qobig'i — BUILD ARTEFAKTI, marshrut esa unga tayanadi.**
  `/owner`, `/admin` va (2026-09-12 dan) `/installer` `cloud/static/v2/*.html`
  ni beradi.  Jonli serverda uni Docker o'zi quradi (`Dockerfile.cloud`
  `frontend-builder`), LEKIN repodagi nusxa ham commit qilinadi va
  **testlar hamda lokal `make run-cloud` aynan o'shanga qaraydi**:
  manbani commit qilib bundle'ni qurmasdan qoldirsangiz, lokalda panel
  404 beradi va `/installer` ni tekshiradigan test qulaydi.  CI
  `npm run build` QILMAYDI — u faqat `typecheck`.  Yangi panel kirish
  nuqtasi qo'shsangiz: `frontend/vite.config.ts` ga yozing, bundle'ni
  bir marta quring va marshrut bilan BIR commitda chiqaring.

- **Muharrirda zonani telefonda YAKUNLAB bo'lmasdi.**  `zone-editor.js`
  da zonani yopish `dblclick` ga, qoralamani tashlash va shaklni
  o'chirish esa `contextmenu` ga (sichqonchaning o'ng tugmasi)
  bog'langan — teginishli ekranda ikkalasi ham yo'q (iOS'da
  `touch-action: none` ostida `contextmenu` umuman chiqmaydi).  Usta
  esa obyektda AYNAN telefondan chizadi: u nuqtalarni qo'yardi, zona
  esa hech qachon saqlanmasdi va sababi ekranda ko'rinmasdi.
  `finishDraft()`/`cancelDraft()` metodlari muharrirda 2026-08-17 dan
  BOR edi — ular `zone-editor.d.ts` da e'lon qilinmagani uchun panelda
  chaqirib bo'lmasdi va hech kim yo'qligini sezmagan.  Saboq:
  sichqonchaga bog'langan har amalning teginish yo'li ham bo'lsin,
  aks holda funksiya telefonda JIMGINA yo'q.

- **Panel testi FAQAT adminni tekshirardi.**  `test_the_admin_uses_no_native_dialogs`
  nomi aynan shunday aytib turgan va `GeometryEditor.tsx` ga
  `window.prompt`/`window.confirm` jimgina qaytib kelgan edi.  Yangi
  qulflar `ADMIN_FILES + OWNER_FILES` ustida ishlaydi — yangi ega
  fayli qo'shilsa `OWNER_FILES` ga ham yozing.
- **`window.prompt` Telegram WebView'da ko'rsatilmasligi mumkin.**
  Zona nomlash shu sababdan JIM o'lardi: foydalanuvchi chizadi, oyna
  chiqmaydi, shakl saqlanmaydi, xato ham yo'q.  `zone-editor.js`
  callbacklari endi `Promise.resolve()` orqasida — satr ham, promise
  ham ishlaydi, ya'ni lokal sehrgar (`prompt()` normal ishlaydigan
  joy) o'zgarmadi.
- **Modal oynada `aria-modal="true"` klaviaturani TO'SMAYDI.**  U faqat
  skrinriderga aytadi.  Izoh «fokus oyna ichida» deb yozilgan, kod esa
  buni qilmasdi — Tab bosgan odam oyna ortidagi ko'rinmas tugmalarni
  bosardi.  `useFocusTrap` ishlatilsin.  Dropdown'ga (qo'ng'iroq
  paneli) tuzoq QO'YILMAYDI: u yerda Tab bilan chiqib ketish to'g'ri.
- **`<a download>` DOMga qo'shilmasa Safari uni jimgina tashlaydi.**
  Tugma bosiladi, fayl kelmaydi, xato ham chiqmaydi.  `revokeObjectURL`
  ni sinxron chaqirish ham xuddi shunday: brauzer yuklashni boshlashga
  ulgurmaydi.  `api.ts: downloadBlobUrl()` ishlatilsin — to'rtta joyda
  boilerplate takrorlangan va uchtasida ikkala xato ham bor edi.
- **`t()` MODUL darajasida chaqirilmasin.**  Til `initLang()` dan keyin
  tanlanadi, ya'ni import paytida ochilgan yorliq doim o'zbekcha
  qoladi (`admin.tsx` dagi `leads` shunday qotib qolgan edi).  Ro'yxat
  KALIT saqlaydi, matn chizish paytida ochiladi (`owner.tsx: NAV_ITEMS`).
- **`t` ni soyalash — tayyor xato.**  `const t=(n:number)=>…` i18n `t()`
  ni bosib turardi; renomlashning O'ZI ikkita chaqiruvni ochib berdi.
  Son formatlagichi `fmt` deb nomlanadi.
- **`useEffect` deps'ga obyekt qo'shsangiz standart qiymatni MODUL
  darajasiga chiqaring.**  `legacy: LegacyRoutes = {}` har chizishda
  yangi obyekt yasaydi — shu sababdan `router.ts` da u deps'dan
  tushirib qoldirilgan va `popstate` eski xaritani ushlab turgan edi.
- **Kanvas rangini tokendan o'qishda ZAXIRA shart.**  `getComputedStyle`
  birinchi chizishdan oldin bo'sh satr qaytaradi; buzuq token esa
  `NaN` beradi va kanvasda ko'rinmas piksel bo'ladi — xarita jimgina
  bo'sh chiqardi.  `--heat-scale` xom RGB uchligi saqlaydi (kanvas
  `rgb()` satrini emas, son talab qiladi).

- **`enes/sotqin_agent.py` — Box yo'li, do'kon kompyuteriga TEGISHLI
  EMAS.**  `report_camera_probes()`, `upload_previews()` va qolganlari
  `control = SotqinAgent()` orqali FAQAT Box/R1 xizmatida ishlaydi.
  Windows yo'lida (`enes/local/`) chaqiruvchi yo'q.  Oqibati 2026-09-12
  da topildi: `site_cameras.width/height` pilotda oylab NULL turgan,
  `probe_status: pending` qotib qolgan va `camera_roles.face_id_check()`
  «o'lcham noma'lum» dan boshqa javob bera olmagan — ya'ni yuz tanish
  darvozasi ko'r edi.  Sabab kamera emas, YO'Q KOD.  Yangi telemetriya
  qo'shsangiz: bu modulda emas, `enes/local/cloud_config.py:
  send_heartbeat()` da yozing va zanjirning to'rt bo'g'inini tekshiring.
- **`benchmark.FRAME_WIDTH/FRAME_HEIGHT` (640x360) — TAHLIL o'lchami
  EMAS.**  U `enes/local/benchmark.py` da `rng.integers` bilan yasaladigan
  SUN'IY kadr o'lchami (o'lchov uchun).  Haqiqiy zanjir
  (`retail/pipeline.py`) RTSP dan kelgan kadrni kichraytirmaydi.
  `cloud_jobs.py:334` dagi izoh «kadr har doim shunga keltiriladi» deb
  yozilgan edi va xulosani TESKARISIGA o'girardi («720p ga o'tishning
  foydasi yo'q» — aslida bor).  Admin UI ham shu sonni «tahlil» deb
  ko'rsatardi.  Kamera rostdan nima berayotganini `native_size` yoki
  heartbeatdagi `cameras[].width/height` aytadi.
- **Yo'riqnomadagi son koddan ajralib ketadi.**  `docs/DOKON_MVP.md`
  «yuz kadri 14 kun yashaydi» deb turardi, kod esa 48 soatga o'tgan —
  kontrakt hujjati o'z mahsuloti haqida yolg'on gapirardi.  Shuning
  uchun `docs/KAMERA_JOYLASHUVI.md` dagi har son testga qulflangan
  (`tests/test_camera_placement_doc.py`) va u darhol foyda berdi:
  hujjatdagi arifmetik xatoni o'zi topdi.  Yangi texnik hujjat yozsangiz
  sonlarni qulflang.
- **Saytga emoji qo'ymang** (⚠️ ✅ ❌).  Har qurilmada boshqacha
  chiziladi (Windows'da rangsiz kvadrat) va brend ranglarini bermaydi.
  `tests/test_static_pages.py: test_public_pages_use_the_icon_sprite_not_emoji`
  qulflaydi — ikonka spraytidan foydalaning yoki so'z bilan yozing.
- **Panel uch tilda, server matni o'zbekcha.**  Yangi qaror qo'shsangiz
  QARORNI va MATNNI ajrating: `face_id_state()` mashina o'qiydigan
  qiymat qaytaradi (`ok`/`edge`/`low`/`unknown`), matnni har sahifa
  `panel.*` kalitidan chizadi.  `bool` yetarli emasligiga misol:
  «chegarada» va «720p kerak» ikkalasi ham `False`, lekin usta uchun
  BOSHQA ish.
- **Chizmani UCH xil odam saqlaydi** — ega, admin va o'rnatuvchi, uchta
  alohida endpoint (`/owner/config`, `/admin/sites/{id}/config`,
  `/installer/sites/{id}/config`).  Tekshiruv yoki yangi maydon
  qo'shsangiz uchalasini ham ko'ring; `tests/test_geometry_feedback.py`
  strukturaviy qulf qo'yadi (`SiteConfigBody` olgan har funksiya).
  Xuddi shu tarqalish funksiya darvozasida ham bo'lgan (uch joy).

- **Docker qurilishi lokal `make ui-build` dan FARQ qiladi.**  Dockerfile
  frontend bosqichi faqat `frontend/` ni nusxalaydi; `styles.css` esa
  `../../cloud/static/tokens.css` ni import qiladi (F1).  Lokal build
  buni ko'rmaydi (repo to'liq), konteynerda ENOENT — 2026-09-11 deployi
  shunda yiqilib sayt ~8 daqiqa o'chiq turdi.  Frontend yangi tashqi
  faylni import qilsa Dockerfile'ga `COPY` qo'shilsin
  (`test_the_cloud_image_can_build_the_panel_bundle`).  Umuman: deploy
  oldidan `docker build --target frontend-builder -f Dockerfile.cloud .`
  lokal ham ishlaydi.
- **Deploy kaliti `.deploy_keys/chaqimchi_prod`** (hujjatlar `enes_prod`
  deydi — endi symlink, `.env` dagi `ENES_DEPLOY_SSH_KEY` o'z holicha).
- **Qurilma cloud manzilini masofadan o'zgartirib bo'lmaydi va 3xx ni
  tushunmaydi** (`cloud_sync.py`, `cloud_config.py` — `follow_redirects`
  yo'q).  Eski `api.` hosti pilot `config.yaml` qo'lda yangilanguncha
  PROXY bo'lib qolishi shart; 301 qilinsa heartbeat va hodisa to'xtaydi.

- **Yangi hodisa turi — AVVAL cloud, KEYIN qurilma relizi.**  Cloud
  `EdgeEvent.model_validate` bilan butun batchni tekshiradi: eski cloud
  `night_motion` (yoki istalgan yangi `EventType`) ni ko'rsa 422 beradi,
  qurilma esa rad etilgan batchni `permanent=True` bilan o'ldiradi —
  hodisalar QAYTARIB BO'LMAS yo'qoladi (`people_seen` bilan bo'lgan
  `capture.enabled` darvozasi shu sababdan yopiq turadi).  0.6.33 ni
  cloud deploy qilinmasdan nashr QILMANG.
- **Ega panelidagi grafik uchun kalit `panel.*` prefiksida bo'lsin.**
  `scripts/build_i18n.py` faqat `PANEL_PREFIXES` ni TS katalogiga
  ko'chiradi — `chart.*` (server rasmi) va `digest.*` panelga chiqmaydi,
  `t("chart.total")` ekranda kalitning o'zini ko'rsatadi.
- **`.page-actions` telefonda YASHIRILMAYDI (2026-09-11 dan).**  Ilgari
  ≤480 px da `display:none` edi va kamera «Jonli/AI», Dalillar «Rasm/Klip»,
  «Xodim qo'shish», hisobot yuklash tugmalari telefonda yo'q edi — QA
  ushladi.  Endi `.page-header .page-actions` sarlavha ostiga tushadi,
  `.event-row .page-actions` qator ostiga (aks holda nom «Navbat …» bo'lib
  siqiladi).  Tugma matni ham yashirilmaydi (`aria-label`siz ikonka).
  Qulf: `test_page_actions_stay_usable_on_phones`.
- **Kamera sahifasi — manzilning UCHINCHI segmenti.**  `cameras` bo'limida
  ikkinchi segment tab nomi (`live|setup|zones`) ham, kamera ID
  (`camera-NN`, server naqshi bilan bir xil) ham bo'ladi; uchinchisi kamera
  tabi.  `CAMERA_TABS` ni `TABS` ga QO'SHMANG — `LEGACY_ROUTES` testi
  `TABS` matnini o'qiydi va menyu tablari bilan aralashib ketadi.
  Kamera plitkalari `Cameras.tsx` da — `owner.tsx` ga qaytarilsa
  `test_live_view_uses_its_own_endpoint` boshqa faylni qidiradi.
- **Tema boot skripti = CSP hash.**  `frontend/owner.html` va `admin.html`
  dagi inline skript AYNAN bir xil bo'lishi shart (bitta hash); o'zgarsa
  `make ui-build` → `pytest tests/test_security_headers.py` yangi hashni
  aytadi → `deploy/Caddyfile` VA `Caddyfile.enes` → deployda Caddy qayta
  yaratiladi.  Hash qurilgan `cloud/static/v2/*.html` dan hisoblanadi.
- **`tokens.css`/`site.css` o'zgarsa kesh tokenlari zanjiri.**
  `scripts/bump_asset_tokens.py` → `build_site.py` → testlar.  Qo'lda
  yozilgan `installer.html` ni `build_site.py` yangilamaydi — skript
  yangilaydi.
- **Chrome `--window-size=390` skrinshoti YOLG'ON toshish ko'rsatadi.**
  Haqiqiy telefon o'lchovi faqat Playwright `is_mobile` + DPR 2 bilan;
  `scrollWidth > clientWidth` — yagona ishonchli mezon.  Lazy rasmlar
  full-page skrinshotda bo'sh katak bo'lib chiqadi — bu ham artefakt.
- **Harnes `--fail-api` da `dashboard`/`sites` yiqilmasin** — aks holda
  panel «aloqa yo'q» ekraniga tushadi va sahifa skeletlari tekshirilmaydi.
- **Yangi owner fayli → `OWNER_FILES`** (`tests/test_panel_v2.py`); aks holda
  brend/jargon qulflari unga tegmaydi.
- **UI tekshiruvi FAQAT o'zbekchada yetarli emas.**  Ruscha yorliqlar
  1.3–1.6 barobar uzun: grid/flex ichidagi karta (`min-width:auto`),
  `.segmented`, `.bottom-nav` o'zbekchada sig'ib, ruschada sahifani yon
  tomonga cho'zdi.  Harnesni doim `--langs uz,ru,en` bilan yuriting;
  yangi konteynerga `min-width: 0` va o'raladigan `flex-wrap`.

- **`read_sotqin_cache()` kalitlarni OQ RO'YXAT bilan qaytaradi.**  Cloud
  yuborgan yangi kalitni `apply()` keshga yozadi, lekin o'quvchi uni
  o'tkazmasa u zanjirgacha yetib bormaydi va bayroq JIMGINA ishlamaydi:
  fayl to'g'ri, kod to'g'ri, natija yo'q.  2026-09-10 da `capture` aynan
  shunday tutildi va uni faqat test topdi — qo'lda tekshirilganda kesh
  faylida kalit turgani "ishlayapti" degan taassurot berardi.  Keshga
  kalit qo'shsangiz `enes/retail/inventory.py` ni ham yangilang.

- **Ma'lumot papkasi yo'qolsa YANGILAGICHNING O'ZI ham o'ladi — nosozlik
  masofadan tuzatilmaydi.**  Bu papka ko'prigi tuzog'ining ikkinchi
  qavati va u 2026-09-10 da kod bo'yicha tasdiqlandi:
  `updater.py:79` `_cloud()` sozlamadan `device_token` o'qiydi, sozlama
  esa aynan yo'qolgan papkada.  Ya'ni «tuzatmani reliz bilan yuboramiz»
  degan reja ishlamaydi — tuzatma yetib boradigan kanal ham o'sha
  papkaga bog'liq.  Saboq: sozlama papkasiga tegadigan o'zgarish
  **o'zini o'zi tiklay olmaydigan** sinfga kiradi; bunday o'zgarishda
  ko'prik relizdan OLDIN yozilishi shart, keyin emas.

- **Ma'lumot papkasi nomi o'zgarsa dastur o'zini YANGI kompyuter deb
  tanishtiradi.**  Rebrendda `%PROGRAMDATA%\Chaqimchi` →
  `%PROGRAMDATA%\ENES` bo'ldi; ko'prik `enes/paths.py` da yozildi
  (Box yo'li), `enes/local/paths.py` da esa **unutildi** — do'kon
  dasturi aynan ikkinchisini ishlatadi.  Yangilangandan keyin dastur
  bo'sh papkani ko'rib sozlash sehrgarini ochdi va 15 soat
  `device-handover` so'rab turdi.  Uch saboq:
  **(1)** bir xil vazifani ikki modul bajarsa, ko'prik ham IKKALASIGA;
  **(2)** hujjat «ko'prik bor» deb yozgani ko'prik borligini
  ISBOTLAMAYDI — CLAUDE.md, NSI izohi va daftar uchalasi ham yolg'on
  aytardi (CLAUDE.md 7-qoidasi: chaqiruv joyini ham ko'ring);
  **(3)** `tests/test_brand.py` da «eski papka ishlatiladi» degan test
  BOR edi, lekin u faqat `enes/paths.py` ning LINUX tarmog'ini
  tekshirardi — ya'ni yashil test noto'g'ri modulni qo'riqlab turgan edi.

- **Papkaning BORLIGI «bu yerda o'rnatish bor» degani emas.**
  `data_dir()` papkani har chaqiruvda `mkdir` bilan yaratadi, ya'ni
  dastur bir marta ishga tushishi bilan yangi nomdagi bo'sh papka
  paydo bo'ladi va `exists()` ga asoslangan ko'prik shu ondan boshlab
  hech qachon eski papkani tanlamaydi.  Belgi — papka emas, ichidagi
  `config.yaml`.  (`enes/paths.py` hali `exists()` ga tayanadi; u yerda
  papkani boshqa hech kim yaratmagani uchun bugun ishlaydi.)

- **`Path(...)` `os.name` ga qarab tur tanlaydi.**  Testda
  `monkeypatch.setattr(os, "name", "nt")` qilinsa `Path()` `WindowsPath`
  qaytaradi va u POSIX mashinada umuman yaratilmaydi (`NotImplementedError`).
  Shuning uchun platforma tarmog'i patch qilinadigan funksiya orqali
  tekshiriladi (`enes.paths.is_windows()`) — bu naqsh o'sha modulda
  ataylab shunday yozilgan va endi `enes/local/paths.py` ham uni
  ishlatadi.

- **f-string ichidagi `%` formatli patternga YANA `%` qo'shmang.**
  `f"{cam}-%{SEGMENT_TIME_FORMAT}.mp4"` ffmpegga `%%Y…` beradi,
  `-strftime 1` esa `%%` ni literal `%` deb yozadi: fayl
  `camera-01-%Y0909-041347.mp4` bo'lib chiqadi.  Nosozlik jimgina —
  hisoblagich faqat "buferda segment yo'q" deydi va barmoq recorder'ga
  ko'rsatiladi.  Ikki oy shu yo'l bilan yo'qotildi.

- **`ffmpeg -strftime 1` MAHALLIY vaqt yozadi, UTC emas.**  Kod nomni
  UTC deb o'qisa, UTC+5 mashinada har segment besh soat "kelajakda"
  ko'rinadi va hodisa oynasiga hech qachon tushmaydi.  Bu yerda
  `STORE_TZ` ham ishlatilmaydi: u «do'kon devoridagi soat», ffmpeg esa
  MASHINA zonasida yozadi (sinov do'konining kompyuteri bir vaqtlar
  UTC+3 da turgan edi).

- **`prune()` faqat O'ZI taniydigan nomni o'chiradi.**  Yozuvchi bilan
  o'quvchi nomda kelishmay qolsa fayllar **abadiy** qoladi: na
  retention, na kvota ularni ko'radi va papka disk to'lguncha o'sadi.
  Tozalash ro'yxatida "tanimadim" degan holat ham bo'lsin
  (`RingBuffer._purge_unknown`).

- **Testda fayl nomini QO'LDA yasamang.**  `test_retail_ringbuffer.py`
  segment nomini o'zi to'g'ri formatda yozardi, ya'ni yozuvchini
  (`record_command`) umuman tekshirmasdi va ikkala xato ham 14 ta
  yashil test ostida yashirinib yotdi.  Nom endi yozuvchining o'z
  patternidan olinadi — yozuvchi va o'quvchi bitta joyda uchrashadi.

- **Boshqa dialektga ko'chirishda REJA emas, HAQIQIY baza o'rgatadi.**
  `store.py` ni PostgreSQL'ga tayyorlashda hamma dialekt farqi
  oldindan sanab chiqilgan edi.  Lokal PostgreSQL 17 esa besh
  daqiqada beshta narsani ko'rsatdi, va ularning HECH BIRI ro'yxatda
  yo'q edi: (1) SQL izohi ichidagi `;` skriptni bo'lakka ajratishni
  buzdi; (2) `LIKE 'ENES Windows%'` dagi literal foiz `%s` o'rin
  egasiga aralashib ketdi; (3) takroriy login `sqlite3.IntegrityError`
  emas, psycopg `UniqueViolation` beradi — tutilmasa mijoz 500
  ko'rardi; (4) `payments/store.py` da yana bitta `rowid`; (5) sxema
  urug'i tahrirlangan katalog narxini jimgina standartga qaytardi va
  qatorlar soni BARIBIR mos kelardi.  Xulosa: bunday ishni
  boshlashdan oldin haqiqiy bazani ko'taring — `createdb` bir
  soniya, taxmin esa bir hafta.

- **Urug'lanadigan jadvalni ko'chirayotganda AVVAL urug'ni tozalang.**
  `_init_db` bo'sh bazaga standart katalogni yozadi.  Ko'chirish
  `ON CONFLICT DO NOTHING` bilan borsa manbadagi HAQIQIY qatorlar
  o'tkazib yuboriladi — ya'ni admin tahrirlagan narx standartga
  qaytadi.  Eng yomoni: qatorlar soni mos keladi, ya'ni sanoqqa
  asoslangan tekshiruv buni ko'rmaydi.

- **Shablondan qurilmaydigan sahifaning kesh tokeni QO'LDA
  yangilanadi.**  `site.css` o'zgarganda `build_site.py` hamma
  shablonli sahifada `?v=` ni qayta hisoblaydi, `installer.html` esa
  qo'lda yozilgan — u eski tokenda qolib ketdi va mijozning brauzeri
  eski uslubni keshdan olib turardi.  `test_cache_token_matches_the_
  file_contents` buni ushladi (u aynan shu sinf xato uchun yozilgan:
  2026-09-06 da 13 sahifa oylab eskirgan edi).

- **Sahifadan skriptni ko'chirsangiz, unga qaraydigan TESTLAR ham
  ko'chadi.**  Inline `<script>` lar tashqi faylga chiqarilganda 11 ta
  test bir vaqtda qulab tushdi — hammasi HTML matnidan JS bo'lagini
  qidirardi (`html.index("<script>")`, `"release.version" in html`).
  Ish o'zi to'g'ri edi, test esa sahifa tuzilishiga bog'lanib qolgan
  edi.  Yangi test yozganda: mazmun QAYERDA turishiga emas, BOR-YO'QLIGIGA
  bog'laning — kerak bo'lsa sahifa va uning skriptini birga o'qing.

- **CSP `script-src` inline `onclick=` ATRIBUTINI ham bloklaydi.**
  Faqat `<script>` bloklarini ko'chirish yetarli emas: HTML
  atributidagi ishlov beruvchi ham inline skript hisoblanadi va
  jimgina ishlamay qoladi — brauzer xato ko'rsatmaydi, tugma
  shunchaki bosilmaydi.  Yechim loyihada allaqachon bor edi:
  `data-act` + bitta delegatsiya tinglovchisi (`geometry-panel.js`).
  U qayta chizishdan keyin qayta bog'lashdan ham ozod qiladi.

- **Birinchi chizishdan oldin ishlashi kerak bo'lgan skriptni
  `defer` qilib bo'lmaydi.**  Tema bootstrap'i tashqi faylga
  chiqarilsa sahifa bir zumga yorug' ochilib, keyin qorayardi.
  Bunday skript CSP hashida qoladi; hash `tests/test_security_headers.py`
  da o'zi hisoblanadi, ya'ni skript o'zgarsa test yangi qiymatni
  aytadi — qo'lda hisoblash kerak emas.

- **O'QILADIGAN-U QAYTA YOZILMAYDIGAN maydon.**  Egizak tuzoq:
  `production_events.line_name` yozilardi-yu hech qayerda o'qilmasdi;
  `zone.shelf` esa AKSINCHA — muharrir uni serverdan yuklardi
  (`zone-editor.js:84`), andoza qo'yardi (`:360`), lekin
  `serialise()` uni qaytarmasdi.  Ya'ni belgi ekranda ko'rinardi va
  saqlash tugmasi bosilgan zahoti o'chardi — hech qanday xato
  chiqmasdan.  Yangi maydon qo'shsangiz **yuklash va saqlash
  yo'lini birga** tekshiring; eng ishonchlisi — Node ichida
  «qo'ydim → saqladim → o'qidim» testi
  (`test_the_shelf_flag_survives_a_save`).

- **Bir manba ikki chaqiruvchida — kesh tokeni ham ikkita.**
  `/vendor/zone-editor.js` ni `installer.html` `?v=2` bilan, React
  `GeometryEditor.tsx` esa `?v=3` bilan yuklardi.  Bitta fayl ikki
  manzil ostida keshlanadi, ya'ni faylni tuzatib bittasini
  ko'tarmasangiz yarim mijoz eski nusxada qoladi.  Manbaga tegilsa
  HAMMA chaqiruvchida token ko'tarilsin.

- **Test o'z IZOHIGA ilinishi mumkin.**  CI qulfi «`pytest` matni
  bo'lmasin» deb yozilgan edi, lekin o'sha faylning izohida
  «…→ pytest» so'zi turardi va test o'zini yiqitdi.  Yechim:
  tekshirishdan oldin `#` dan keyingi qismni tashlash
  (`test_ci_workflow.py:_commands`).  Xuddi shu naqsh loyihada
  allaqachon bor edi — `geometry-panel.js` da `onclick=` tenglik
  belgisi bilan qidiriladi.

- **Brendni ommaviy almashtirishda QO'RIQCHI testlar ham almashadi.**
  `Chaqimchi` → `ENES` perl o'tishi `tests/test_panel_v2.py` dagi
  `re.search(r"Chaqimchi(?![_A-Z])")` ni `ENES(...)` ga aylantirdi va
  test o'z brendini «eski» deb yiqildi; `test_site_build` ham.  Bot nomi
  `@chaqimchi_ai_bot` ham `enes_bot` bo'lib ketdi (egadan kelmagan nom).
  Ommaviy almashtirishdan keyin `git diff -- tests | grep "not in"` va
  tashqi identifikatorlar (bot, domen, GitHub repo) ro'yxatini alohida
  tekshiring.  `tests/test_brand.py` endi ruxsat ro'yxatini ushlab
  turadi.

- **Parallel agentlar bitta JSON'ga yozmasin.**  F4c/F5 da yetti agent
  bir vaqtda ishladi; har biri o'z `i18n_<X>.json` ga yozdi, birlashtirish
  `merge_i18n` (to'qnashuv → xato).  Sessiya limiti agentlarni yarim
  yo'lda uzdi — qolgan ishni ularning diffidan tiklab qo'lda tugatish
  kerak bo'ldi.  Katta parallel ishni 3-4 agentdan oshirmang va har agent
  natijasini kichik bo'laklarda commit qiling.

- **Panelda `t()` ni modul yuklanganda chaqirmang.**  `initLang()`
  `owner.tsx`/`admin.tsx` ichida, modullar importidan KEYIN ishlaydi;
  `const NAV = [{label: t("…")}]` doim o'zbekcha qolardi.  Ro'yxat
  kalit saqlaydi, `t(item.key)` render paytida (`NAV_ITEMS`, `PERIODS`,
  `TELEGRAM_LEVELS` naqshi).

- **Fon vazifasida `i18n.t()` — hech kimning tili.**  `BackgroundTasks`
  va `create_task` so'rov kontekstini meros oladi: hodisa
  ogohlantirishi qurilma so'rovining (ya'ni standart) tilida ketardi.
  Telegram/digest/CSV faqat `tg(lang, key)`; bir necha a'zoga ketadigan
  matn `OwnerMessage` (alerts) yoki `build(lang)` (digest) — til a'zo
  qatoridan (`owner_members.language`).  `cloud/main.py` da `t` import
  qilinmagan — `i18n.t(...)` yozing (HTTP yo'lida).

- **Testni matnga emas, kalitga bog'lang.**  ~70 test aniq o'zbekcha
  satr tekshirardi; katalogga ko'chganda hammasi bir vaqtda qulardi.
  Endi `tests/i18n_assert.py::assert_text` (server) va `key_text`
  (`test_connect_ui`/`test_events_ui`, manba kalitni ishlatadimi +
  kalit shu ma'noni beradimi).  Yangi test yozganda ham shu.

- **Repo ildiziga yangi papka qo'shsangiz `Dockerfile.cloud` ga ham
  qo'shing.**  `COPY` ro'yxati aniq sanaladi (`enes`, `cloud`,
  `deploy`, `scripts`, `models`); F2 da `i18n/` qo'shildi-yu Dockerfile
  yangilanmadi — lokalda hamma test o'tardi, konteynerda esa birinchi
  `t()` `FileNotFoundError` berardi.  Bir kun kechroq topilganda bu
  deploydan keyingi 500 bo'lardi.  Endi test qulflaydi
  (`test_the_cloud_image_carries_the_language_catalogue`); yangi papka
  uchun shunga o'xshash qator qo'shing.

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

- **`ENES_AVAILABLE_FEATURES` dagi xato kod JIMGINA yutiladi.**
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
  `enes` ko'chiriladi (`build_windows_payload.py: CODE_DIRS`).
  Shu sabab "avval `benchmark_n100.py` bilan o'lchang" degan tavsiya
  bajarib bo'lmaydigan edi — o'lchov ma'noli bo'ladigan yagona mashinada
  skript yo'q. Qurilmada ishlashi kerak bo'lgan kod `enes`
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
- ✅ `test_admin_panel_has_no_native_dialogs` → `test_the_admin_uses_no_native_dialogs`
  (F4a: `ConfirmDialog`/`Modal`, `window.confirm` yo'q).
- ✅ `test_admin_customer_page_is_deep_linkable` → `test_the_customer_page_is_deep_linkable`
  (F4a: `router.ts` ikkinchi segment, `/admin/customers/{id}`).
- ✅ `test_admin_panel_promises_the_same_interval` — React adminda
  (`AdminCustomer.tsx`), `xfail` olindi.
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

**✅ YOPILDI (2026-09-08, F4a) — eski adminning vositalari React adminga
ko'chdi** (`AdminCustomer.tsx`, `AdminTeam.tsx`, `AdminSettings.tsx`);
qulf `test_the_admin_can_fix_a_shop_remotely` endi 18 endpointni
tekshiradi, `test_the_admin_uses_no_native_dialogs` va
`test_the_customer_page_is_deep_linkable` qo'shildi.  Ro'yxat tarix
uchun qoldirildi (endpoint bo'yicha, `556d33c` dan keyin o'lchangan):
`sites/{id}` tafsilot sahifasi (config_health: `geometry_problems`,
`feature_problems`, `role_problems`), `sites/{id}/camera-inventory`
(masofaviy kamera va chizma — 2026-08-21 qarori),
`sites/{id}/jobs/clean-chains` va `jobs/benchmark`,
`sites/{id}/diagnostics`, `sites/{id}/features/draft|quote|approve`
(**sotuv darvozasi**), `sites/{id}/faces`, `sites/{id}/onboarding`,
`accounts/{id}` va `installer-assignments` (Jamoa), `alerts` +
`alerts/test`, `business-templates`, `payments/providers`,
`updates-paused`, `windows-releases`.  Ko'chirilmagani: `alerts/check`
(darhol tekshiruv — fon halqasi baribir 5 daqiqada qiladi),
`portal-audit` (jurnal ko'rinishi — kerak bo'lsa keyin).

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

### 2026-09-12 — sayt, konversiya, karta va usta paneli (`ac30722`…`d7e57c4`)

Nima: (1) saytdagi forma xatosi endi O'QILADIGAN matn va so'rov
tilida; (2) holat sahifasi qaysi qism yiqilganini aytadi; (3)
avtomatik konversiya ishlaydi — qurilmadagi kod tiriltirildi; (4)
CSP majburiy, `releases/` o'zini tozalaydi; (5) usta paneli React'da
va telefonda zona chizish ROSTDAN ishlaydi; (6) demo 7 kun, karta
ulasa 14, obuna kartadan o'zi uzayadi.

Nega: bular birgalikda «mijoz birinchi ko'radigan joy» dan «pul
kelishi» gacha bo'lgan zanjirning uzilgan bo'g'inlari edi.  Eng
qimmatlari jimgina turgan: cloud `config["capture"]` yubormagani
uchun qurilmadagi 0.6.33 kodi abadiy yopiq turgan; zona chizish
telefonda `dblclick` va o'ng tugmaga bog'langan, ya'ni usta obyektda
zona chiza olmasligi mumkin edi; forma validatsiyasida mijoz
`[object Object]` o'qirdi.

Qayerda: `cloud/main.py` (validatsiya handleri, `config["capture"]`,
`_with_capture`, `bump_feature_revision`, karta endpointlari,
`_auto_renew_*`, `prune_windows_releases`), `cloud/event_store.py`
(`people_seen` uchta ro'yxatda), `cloud/payments/{cards,store}.py`,
`cloud/static/{site,status,edu}.js`, `cloud/site/*`,
`frontend/src/{installer,InstallerJobs,InstallerCamera}.tsx` (yangi),
`enes/local/static/zone-editor.js`, `deploy/Caddyfile*`,
`scripts/{bump_feature_revision,prune_releases}.py`.

Test: `tests/test_public_form_errors.py` (27), `test_capture_rate_chain.py`
(13), `test_payment_cards.py` (30), `test_release_prune.py` (18),
`test_panel_v2.py` (+6), `test_security_headers.py` (+1).
Jami **2449 passed, 13 skipped**.

Diqqat: **deploy tartibi — AVVAL cloud, KEYIN qurilma relizi.**
Deploydan keyin `scripts/bump_feature_revision.py` bir marta (usiz
qurilma eski keshdagi konfigda qoladi va `capture` yonmaydi).  Caddy
`restart` EMAS, `--force-recreate` (CSP).  `releases/` birinchi
tozalash `--reja` + hostda `rm` (papka konteynerga `:ro` ulangan).
Karta bo'limi Payme/Click kalitlari kelmaguncha panelda ko'rinmaydi,
oferta bandi esa yurist ko'rigini kutadi.


### 2026-09-12 — I bloki: CSP majburiy, `releases/` o'zini tozalaydi (`e4200fd`, `afbfe3c`)

Nima: sayt va panelda CSP endi kuzatmaydi — **bloklaydi**; reliz
papkasi o'zini tozalaydi va qurilmalar hali so'rayotgan versiya
saqlanadi.

Nega: (1) `-Report-Only` hech narsani to'xtatmaydi — XSS yo'li bir
hafta kuzatuv ostida ochiq turdi; (2) `releases/` hech qachon
tozalanmasdi va serverda 19 ta eski `.exe` bilan 1,9 GB ga o'sdi —
Postgres va MinIO o'sha diskda turadi.

Qayerda: `deploy/Caddyfile:45`, `deploy/Caddyfile.enes:58` (faqat
sarlavha nomi; hash va `style-src` o'sha holda);
`docs/PRODUCTION_RUNBOOK.md` §3.1 (Caddy `--force-recreate`);
`cloud/main.py: prune_windows_releases` / `_protected_release_versions`
/ `_release_prune_plan` (+ `_maintenance_loop` da kuniga bir marta,
yetakchi darvozasi ortida), `cloud/event_store.py:
reported_app_versions`, `cloud/store.py: pinned_update_versions`,
`scripts/prune_releases.py`, `scripts/publish_windows_release.sh`
(nashrdan keyin).

Test: `tests/test_security_headers.py`
(`test_the_policy_is_enforced_not_report_only` + `REQUIRED`),
`tests/test_release_prune.py` (18 ta: ishlatilayotgan va qotirilgan
versiya o'chmaydi, baza o'qilmasa umuman o'chmaydi, har prefiks o'z
uchtasini saqlaydi, juftsiz `.exe`/yetim manifest/tanilmagan nom
tozalanadi, `ENES_Setup.exe` va `sotqin`/`lite` fayllari tegilmaydi,
`keep=0` da ham jonli reliz qoladi).

Diqqat: konteynerda papka `:ro` — jonli serverda tozalash IKKI
qadamli (`--reja` konteynerda, `rm` hostda; nashr skripti buni o'zi
qiladi).  Deployda Caddy **`restart` emas, `--force-recreate`**, aks
holda eski inode qolib ketadi va sarlavha o'zgarmaydi.  Serverdagi
1,9 GB hali tozalanmagan.
### 2026-09-12 — E bosqichi: usta paneli React'da (`commit qilinmagan`)

Nima: o'rnatuvchi obyektda telefondan ishlaydigan panelni oldi — uch
til, qora tema, xato holatlari, teginish bilan chiziladigan zona.
Oxirgi eski statik panel (`cloud/static/installer.html`) o'chdi.

Nega: usta paneli mustaqil yashagani uchun 2026-09-11 dagi UI/UX
ishidan ham, 2026-09-12 dagi panel tuzatishlaridan ham HECH NARSA
olmagan edi: faqat o'zbekcha, API yiqilsa xato ko'rsatmasdi (bo'sh
ekran), har tasdiq `confirm()` da — Telegram WebView'da u jim o'lishi
mumkin.  Obyekt modal oynada ochilardi: havola qilib bo'lmasdi va
«orqaga» panelni tark etardi.

Qayerda: yangi `frontend/installer.html`, `frontend/src/installer.tsx`,
`InstallerJobs.tsx`, `InstallerCamera.tsx`; `frontend/vite.config.ts`
(uchinchi kirish nuqtasi); `frontend/src/api.ts` (`PanelKind` —
`installer` tokeni `localStorage` da, `whoAmI`, `registerInstaller`);
`components.tsx: LoginScreen` (uchinchi tur + `extra`);
`GeometryEditor.tsx` (`kind="installer"`, `embedded`, teginish
tugmalari, shaklni o'chirish); `zone-editor.d.ts`
(`finishDraft`/`cancelDraft`); `cloud/main.py: _installer_panel()` +
`/installer/{panel_path:path}`; o'chdi: `cloud/static/installer.html`,
`installer.js`, `geometry-panel.js`.  119 ta yangi `panel.installer.*`
va `panel.geometry.*` kaliti uch tilda.

Test: `tests/test_panel_v2.py` — `INSTALLER_FILES` ro'yxati va oltita
yangi qulf (React marshruti, uchala qobiqdagi bir xil tema skripti,
skeletsiz xato, uch til, Face ID qarori serverdan, barmoq bilan zona
yakunlash); `test_zone_editor.py` ikkita testi React manbasiga
ko'chirildi; `test_platform_hosts.py` va `test_portal_auth.py` qobiq
build artefakti ekanini hisobga oladi.  `2360 passed, 12 skipped`.

Diqqat: **bundle qurilmagan** — `cloud/static/v2/installer.html` yo'q va
lokal `/installer` shu sababdan 404.  `npm run build` (asosiy sessiya)
shart: jonli deployni Docker o'zi quradi, lekin testlar va lokal ishga
tushirish repodagi nusxaga qaraydi.  Tema bootstrap skripti
uchala qobiqda BAYT-BAMA-BAYT bir xil bo'lib qoldi — CSP hashi
o'zgarmadi, Caddyfile'larga tegilmadi.

### 2026-09-12 — panel xatolari: ega + admin (`dbda134`, `5cce2eb`, `1bb740c`)

Nima: usta zonani telefondan nomlay oladi; admin API yiqilganda xato
va «Qayta urinish» ko'radi, abadiy skelet emas; CSV Safari'da ham
yuklanadi; yoqilmagan bo'lim («AI yordamchi», «Xodimlar») menyuda
turmaydi; klaviatura bilan ishlash tuzatildi (fokus tuzog'i, tab
sohalari, fokus halqasi, muhimlik nuqtasi); telefonda qidiruv qaytdi.

Nega: 2026-09-11 QA faqat ega panelini qamradi va ikki tomonlama
qarz qoldirdi — adminda tuzatilmagan naqshlar, ega panelida esa
qaytib kelgan brauzer oynalari.  Eng qimmati `GeometryEditor` dagi
`window.prompt`: Telegram WebView'da u ko'rsatilmasligi mumkin va zona
nomlash jim o'lardi, usta esa obyektda aynan telefondan chizadi.
Test buni ushlamagan, chunki nomi ham, qamrovi ham faqat ADMIN edi.

Qayerda: `enes/local/static/zone-editor.js` (callbacklar
`Promise.resolve()` orqasida), `frontend/src/components.tsx`
(`useFocusTrap`, `PromptModal`/`usePrompt`, `TabPanel`, `MetricCard`
o'chdi), `api.ts: downloadBlobUrl/downloadCsv`,
`admin.tsx`/`AdminSettings.tsx`/`AdminTeam.tsx`/`AdminCustomer.tsx`
(skelet + `ErrorStrip onRetry`), `owner.tsx` (tab darvozasi, nav
darvozasi, qo'ng'iroq fokusi), `EventEvidence.tsx` (`embedded`),
`Heatmap.tsx`/`theme.ts` (ranglar tokendan), `router.ts` (deps),
`styles.css`, `cloud/main.py` (`capabilities.agent`,
`capabilities.attendance`), `cloud/static/tokens.css` (`--heat-scale`).

Test: `tests/test_panel_v2.py` (+13 qulf: native oyna ikkala panelda,
admin skelet tiklanishi, fokus tuzog'i, tab sohalari, telefon
qidiruvi, fokus halqasi, muhimlik nuqtasi, AI darvozasi, davomat
darvozasi, kamera sahifasi sarlavhasi, bitta KPI, o'lik CSS,
tokenlar, router deps), `tests/test_camera_frame_size.py` (darvozalar
dashboard javobida).

Diqqat: `TABS` va `LEGACY_ROUTES` literallari ATAYLAB o'zgarmadi —
tab `hidden` propi orqali yashiriladi.  Admin `devices` bo'limi
o'chdi, eski manzil `LEGACY_ROUTES` orqali `monitoring` ga boradi.
Deploy: cloud qismi (`capabilities`) deploy talab qiladi.

### 2026-09-12 — kamera joylashuvi, Face ID darvozasi, qizil testlar (`2a6ece3`, `b11381e`, `3200772`)

Nima: usta endi kamerani qayerga qo'yishni BILADI (yo'riqnomada rol
bo'yicha, Face ID chegarasi obyektda o'lchanadigan qoida bilan), panel
har kamera uchun «yuz tanish uchun yetarli / chegarada / 720p kerak»
deb aniq aytadi, yaroqsiz chiziq yoki zona haqida esa chizgan odamning
o'ziga darhol aytiladi.  Yo'l-yo'lakay ikkita oylik qizil test yashil
bo'ldi va `/chek` bot menyusiga chiqdi.

Nega: kamera noto'g'ri qo'yilgani DARHOL ko'rinmaydi — tizim
ishlayotgandek turadi va nosozlik oylar o'tib, `face_crops.too_small`
dan topiladi (pilotda 93 kesmadan 93 tasi tashlangan).  Bungacha kamera
joylashuvi haqida hech qayerda bitta ham qator yo'q edi, usta
yo'riqnomasi esa Ubuntu o'rnatishni o'rgatardi — sotuv Windows'da.
Eng muhimi: **kamera o'lchami cloudga hech qachon yubormasdi**, ya'ni
Face ID tekshiruvining mantig'i bor-u kirish ma'lumoti yo'q edi.

Qayerda: `enes/retail/runner.py:108,233,445`,
`enes/retail/service.py: write_status`, `enes/local/supervisor.py: status`,
`enes/local/cloud_config.py: send_heartbeat`, `cloud/main.py:
EdgeCameraHealth` + `edge_health_heartbeat` + `_with_geometry_problems`,
`cloud/store.py: record_camera_frame_size` + `list_cameras`,
`enes/camera_roles.py: face_id_state`, `enes/paths.py: _has_installation`,
`docs/KAMERA_JOYLASHUVI.md`, `cloud/site/installer-guide.html`,
`cloud/site/install.html`, `frontend/src/{Cameras,CameraDetail,GeometryEditor,types}.tsx|ts`.

Test: `tests/test_camera_frame_size.py` (zanjir + eski qurilma
o'chirmasligi + qaror holatlari), `tests/test_camera_placement_doc.py`
(hujjat sonlari kodga qulflangan), `tests/test_geometry_feedback.py`
(uchala config PUT + strukturaviy qulf), `tests/test_bot_commands.py`,
`tests/test_static_pages.py` (yo'riqnoma Windows yo'lida va kamera
bo'limi bor), `tests/test_status_chain.py`, `tests/test_local_paths.py`.

Diqqat: **deploy tartibi — AVVAL cloud, KEYIN qurilma relizi.**  Cloud
`cameras[].width/height` ni qabul qila olmasa qurilma yuborgan
heartbeat 422 oladi.  Reja bo'yicha keyingi bloklar: B (sayt), C
(panel), E (usta paneli React'ga), F (demo + karta), G (A1), I (ops),
H (admin i18n) — tartib va bog'liqliklar
`~/.claude/plans/md-file-ichii-o-qi-linear-tulip.md` da.

### 2026-09-11 — UI/UX QA va dizayn-3: sayt + panel (`3c19d63`…`28b73cd`)

Nima: ega endi (1) telefonda ham hamma tugmani ko'radi, xato chizig'i
bilan yonma-yon abadiy skelet ko'rmaydi, inglizcha server matnini
o'qimaydi; (2) panel qora ochiladi, bosh sahifada 5 doimiy ko'rsatkich,
rasmli hodisalar va do'kon chipi, har kamera uchun alohida sahifa
(jonli/tahlil/hodisalar); (3) saytda hero'da o'z fotosi va rost hodisa
kartasi, telefon menyusi, brendli 404.

Nega: ega «xatolar ko'p» dedi — jonli QA 30+ nuqson topdi (ro'yxat reja
faylida); mockup dizayni sotuvga kerak, lekin undagi va'dalar
kontraktga zid — dizayn olindi, matn rost qoldi.

Qayerda: `frontend/src/{components,api,EventEvidence,VisionAgent,
Analytics,owner,OwnerHome,Cameras,CameraDetail,router,Heatmap,
EventTimeline,theme}.tsx|ts`, `styles.css`, `tokens.css`,
`frontend/{owner,admin}.html`, `deploy/Caddyfile*`,
`cloud/site/{index,404,partials/nav-sub}.html`, `cloud/static/{site.css,
site.js,icons.svg,hero-lobby-v1.webp,shop-corridor-v1.webp}`,
`cloud/main.py` (`branded_not_found`), `scripts/build_site.py`,
`scripts/{ui_qa_screenshots,bump_asset_tokens,make_panel_screenshots}.py`,
`i18n/*.json` (+~40 kalit), `.gitignore`/`.dockerignore`/`DEPLOY_TARIFLAR`.

Test: `test_panel_v2.py` (+7: skelet, xom detail, telefon tugmalari, Excel
yorlig'i, hisobot xatosi, 5 karta, rasmcha, kamera deep link),
`test_site_build.py` (+2: telefon menyusi, brendli 404); `make test` —
faqat ikkita ESKI yiqilish (HOZIRGI HOLAT da).

Diqqat: deployda Caddy qayta yaratilsin (CSP hash).  Playwright harnesi
`.venv` da; skrinshotlar scratchpad'da, repoga kirmaydi.  Mockupdagi
«Suspicious» yozuvli rasm (`ae4564c2`) ishlatilmadi; `dizayn-3/` git va
rsync'dan chetlatilgan.

### 2026-09-11 — F7 dan keyingi jonli tekshiruv: apex tarqaldi, pilot 44 soat o'lik (faqat docs)

Nima: `enes.uz`/`www` to'rt ommaviy resolverda yangi IP, serverda apex
serti Let's Encrypt `CN=enes.uz`, 8 host serti olingan, Caddy ACME
urinishlari DNS'dan keyin to'xtagan; cloud/worker loglarida 0 xato,
webhook 200 (Telegram IP'dan 18 ta/soat); pilot o'zgarmagan — 0.6.30
jarayoni 21:11 UTC da yana handover so'ragan.

Nega: daftardagi ikki «⏳» bandini yopish (apex keshi, cutoverdan keyin
server holati) va pilot chorasi hali qilinmaganini qayd etish.

Qayerda: `docs/ISH_DAFTARI.md` (HOZIRGI HOLAT, F7 qoldig'i 2-band).

Test: yo'q — kod o'zgarmadi.

Diqqat: `curl https://enes.uz` agent Mac'ida hali `*.ahost.uz` serti
bilan yiqiladi — bu MAHALLIY mDNSResponder keshi (`dig` yangi IP beradi),
serverga tegishli emas; `--resolve` bilan 200.
Diqqat: boshqaruv DB (`devices`, `pending_devices`) cloud konteyneridagi
SQLite `/app/data/cloud/cloud.db` da; Postgres faqat hodisalar uchun.
Diqqat: `.deploy_keys/enes_prod` bilan kiring — `~/.ssh/id_ed25519`
serverda yo'q, `ssh-add` bo'sh.

### 2026-09-11 — F7 cutover: enes.uz, yangi bot, server yangi kodda (`ea7c7cd`, `7b5686c`)

Nima: jonli server `enes` nomida, `enes.uz` asosiy domen (env, canonical,
sitemap, bot tugmalari), eski `chaqimchi.uz` hostlari PARALLEL ishlaydi
(Caddy ikki nomli bloklar), yangi bot `@enes_monitoring_bot` webhook
bilan, 10-sentabrdagi tungi nazorat/panel/rasmli hisobot ishi jonli.

Nega: rebrendning oxirgi tashqi qadami; deploy taqiqi shu kunni kutardi.
Parallel rejim — pilot qurilmasi `api.chaqimchi.uz` ga ulangan va 3xx
ni tushunmaydi.

Qayerda: `deploy/Caddyfile.enes` (`X.enes.uz, X.chaqimchi.uz`),
`Dockerfile.cloud` (`tokens.css`), CI/skript standartlari, sayt/hujjat
sahifalari, `tests/test_platform_hosts.py` (ikki domen qulfi),
`test_proxy_limits.py`, `test_brand.py`; serverda: papkalar (symlink),
`.env.production`/`backup.env` `ENES_*`, `enes_*` volume nusxalari,
`enes-backup*` timer'lar.

Test: to'plam yashil; serverda `/health/deep` ok, hodisa 5 894 = 5 894,
eski hostlar 200, `getWebhookInfo` → yangi bot, pending 0.

Diqqat: aHost DNS hali ega tomonidan qo'yilmagan — `enes.uz`
sertifikatlari DNS kelgach o'zi chiqadi; `www.chaqimchi.uz` → 301
`enes.uz` shu paytgacha aHost sahifasiga tushadi.
Diqqat: bot tokeni chatga tushgan edi — ega xohlasa BotFather `/revoke`
+ `.env.production` + `set_telegram_webhook.py` (uch qadam birga).
Diqqat: `.env.production.example` agent uchun yopiq — qo'lda yangilansin.

### 2026-09-10 — Tungi nazorat, dizayn-3 paneli, Telegramda rasmli hisobot (`ec34ccb`, `05e2b04`, `43dfa99`, `f6897de`, `b7a1e02`)

Nima: ega endi (1) panelda 8 bo'limli menyu, mockupdagi bosh sahifa va
«Tahlil» sahifasida 4 grafikni (kunlar kesimida, 7/14/30) ko'radi;
(2) Sozlamalarda ish vaqtini o'zi kiritadi va tungi nazorat shu bilan
yonadi; (3) Telegramda kunlik/haftalik hisobot va `/hisobot` ni grafik
rasm bilan oladi, tungi hodisa kadrida vaqt/kamera yozilgan; (4) qurilma
kamera IR rejimga o'tganini sezib yolg'on «kamera buzildi» bermaydi,
IR'siz kamerani «tunda ko'rmaydi» deb aytadi va yopiq do'kondagi
harakatni odam tanilmasa ham xabar qiladi (`night_motion`).

Nega: `after_hours_presence` ish vaqtisiz umuman ishlamas, ish vaqtini
esa faqat o'rnatuvchining sozlash ustasi yozardi — ega panelida maydon
yo'q edi.  `tamper.py` o'z izohida IR o'tishini ajrata olmasligini yozib
qo'ygan edi.  Grafik kutubxonasiz `charts.tsx` bor edi-yu, `Donut`/`Bars`
ega panelida ishlatilmasdi; cloudda rasm chizadigan kutubxona yo'q edi
(`cv2.putText` kirillcha yozolmaydi → Pillow + repo ichidagi DejaVu).

Qayerda: `frontend/src/{owner,OwnerHome,Analytics,overview,charts,
Heatmap,router,components}.tsx`; `cloud/main.py` (`/owner/overview`,
`night_watch`, `/hisobot`, alert annotatsiyasi, `EdgeCameraHealth.night_mode`);
`cloud/event_store.py: retail_overview`; `cloud/chartimg.py` (yangi),
`cloud/assets/fonts/`; `cloud/digest.py` (`photo_sender`, 🌙 qator);
`cloud/notify.py` (🌙); `enes/retail/nightmode.py` (yangi),
`pipeline.py` (probe, `night_motion`, `metadata.night`, dark yoritish),
`tamper.py: relearn`, `scene_analytics.py: MotionGate.reset, size_boost`,
`service.py`, `runner.py`, `enes/local/cloud_config.py`,
`config/rules.yaml` (tungi qoidalar birinchi), `enes/event_models.py`.

Test: `tests/test_retail_night.py` (12), `test_retail_nightmode.py` (5),
`test_chartimg.py` (9), overview (`test_owner_report.py`,
`test_cloud_events_owner.py`), rasm→matn tartibi va izoh ≤1024,
`/hisobot` rasm, tungi kadr annotatsiyasi, `night_watch`, menyu/eski
marshrut qulflari (`test_panel_v2.py`), shrift konteynerga kirishi.
To'liq to'plam yashil (`make test PY=.venv/bin/python`).

Diqqat: mockupdagi «Shubhali harakat» yorlig'i ATAYLAB yo'q — MVP niyat
taxmin qilmaydi; «1000+ mijoz», «99.9%» namuna raqamlari ham.
Diqqat: `make test` tizim `python3` bilan `pytest` topmaydi — `PY=.venv/bin/python`.
Diqqat: yangi hodisa turi — avval cloud deploy, keyin reliz (tuzoqlar).
Diqqat: IR/qorong'ilik chegaralari haqiqiy kamerada kalibrlanmagan.

### 2026-09-10 — Uchta kichik qarz: OTP bloklashi, `/status` yolg'oni, Box tripwire (`e86615a`)
Nima: `POST /owner/auth/verify` ga IP cheklovi (30/10 daq), `/status`
sahifasi endi `/health/deep` ni o'qiydi, `enes/paths.py` farazi testga
olindi.
Nega: uchalasi ham "jimgina yolg'on" sinfidan.  OTP cheklovi kodni
sindirishdan emas, BLOKLASHDAN himoya qiladi — kodning o'zi allaqachon
`attempts >= 5` bilan qulflangan, lekin Telegram ID sir emas va hujumchi
begona akkauntga beshta noto'g'ri kod yuborib qurbonning haqiqiy kodini
kuydirib qo'yardi (qurbon yangisini 10 daqiqada faqat uch marta so'ray
oladi).  `/status` esa yengil `/health` ni o'qirdi — u Docker
HEALTHCHECK uchun va doim 200, ya'ni Postgres o'lgan bulut ham
"ishlayapti" bo'lib ko'rinardi.
Qayerda: `cloud/main.py` (`owner_verify_otp`), `cloud/static/status.js`
+ qurilgan `status*.html` (JS ning kesh-hashi ichida), `enes/paths.py`
(`_windows_dir` izohi).
Test: `test_otp_verification_is_capped_per_ip`,
`test_the_status_page_asks_the_honest_health_check`,
`test_the_box_bridge_stays_safe_because_nothing_creates_its_folders`.
Uchalasi ham tuzatmasiz yiqilishi tekshirildi.
Diqqat: **`enes/paths.py` ataylab QAYTA YOZILMADI.**  U hamon papkaning
borligiga qarab tanlaydi, ya'ni egizak moduldagi tuzoqning o'zi — lekin
bugun xavfsiz, chunki bu modul papka yaratmaydi.  Belgiga o'tkazish har
yo'l uchun boshqa belgi tanlashni talab qiladi (`/opt/enes` va
`/etc/enes` da bir xil fayl yo'q), ya'ni sotuvga chiqmagan yo'lga xavf
kiritardi.  O'rniga faraz qulflandi: `mkdir` qo'shilsa test aytadi.

### 2026-09-10 — A1 2-bosqichi: `people_seen` hodisasi (`b268325`)
Nima: oyna yopilganda har kameradan bitta `people_seen` chiqadi
(`metadata.seen`, `metadata.window_sec`), `capture.enabled` darvozasi
ortida.  Qurilma tomoni tayyor — keyingi relizni kutadi (0.6.32 da yo'q).
Nega: maxraj 1-bosqichda sanala boshlagan edi, lekin faqat heartbeatda
ko'rinardi, ya'ni tashxisga yarardi-yu hisobotga bormasdi.
Sabab (darvoza nega majburiy): eski cloud noma'lum turni jimgina
tashlamaydi — RAD ETADI, qurilma esa rad etilgan hodisani
`permanent=True` bilan o'ldiradi.  Bayroqsiz yuborilgan har qator
qaytarib bo'lmas yo'qolardi va `outbox_poisoned` o'sardi.
Qayerda: `enes/event_models.py` (`people_seen`), `enes/retail/service.py`
(`retail_event_filter` + `_seen_flush_loop`), `enes/retail/inventory.py`
(oq ro'yxat), `enes/local/cloud_config.py` (`_capture_signature`),
`enes/local/app.py` (qayta yoqish ro'yxati), `i18n/*.json`.
Test: `test_people_seen_needs_the_cloud_flag_not_just_a_paid_plan`,
`test_the_seen_window_becomes_one_event_per_camera`,
`test_capture_bayrogi_ozgarishi_sezib_qolinadi`.
Diqqat: son alohida ustunda emas, `metadata` da — kunlik hisobot SQL'da
emas, Python siklida yig'iladi (`_retail_report_from_events`), ya'ni
ustun tezlik bermaydi-yu cloud sxemasini ko'chirishni talab qilardi.
Halqa `pipeline.process()` dan tashqarida yuradi, ya'ni tarif filtri
QO'LDA chaqiriladi.  Qoldi: 3–5-bosqichlar, hammasi deploy kutadi.

### 2026-09-10 — Yuzdan olingan xulosa ham menejerdan yopildi (`1d70c43`)
Nima: `GET /owner/faces`, `/owner/employees`, `/owner/attendance{,.csv}`
va `/owner/events?event_type=employee_seen` endi `require_biometric_access`
dan o'tadi; oylik smena hisoboti Telegramda menejerga bormaydi.
Nega: to'rttasi faqat `require_attendance()` bilan turgan edi — u
qo'riqchi emas, RUBILNIK: "bu serverda davomat yoqilganmi" degan savolga
javob beradi va rolga umuman qaramaydi.  Auditning KRITIK-4 sinfi, boshqa
URL orqali.  O'sha auditdagi "rasmni yopdik, ro'yxatni ataylab ochiq
qoldirdik" qarori xato bo'lib chiqdi: rozilik shabloni xodimni "kim
ko'rdi" dan himoya qiladi, "nimani ko'rdi" dan emas, va `person_name`
rasmsiz ham to'liq javob berardi.
Qayerda: `cloud/main.py` (`may_see_biometrics`, to'rt marshrut,
`owner_events` filtri), `cloud/owner_auth.py` (`BIOMETRIC_ROLES`),
`cloud/digest.py` (oluvchilar), `frontend/src/owner.tsx` (menyu),
`docs/AUDIT_TAHLIL.md`.
Test: `test_a_manager_cannot_open_any_biometric_image` (ro'yxat
kengaytirildi), `test_a_manager_keeps_the_evidence_page_without_the_face_rows`,
`test_the_monthly_shift_report_skips_managers`.  Uchalasi ham tuzatmasiz
yiqilishi tekshirildi.
Diqqat: **`/owner/events` ga marshrut darajasida qo'riqchi qo'yilmadi.**
U «Dalillar» sahifasining yagona manbai va `event_type` ni umuman
yubormaydi — butun marshrut yopilsa menejerning asosiy ish quroli
o'lardi.  Qo'riqchi TURGA qo'yildi.  Faqat `?event_type=` ga qo'yish ham
yetmasdi: turi so'ralmagan umumiy ro'yxatda ham yuz hodisalari qaytardi.
`BIOMETRIC_ROLES` `cloud/owner_auth.py` da, `main` da emas — `main`
`digest` ni import qiladi, teskarisi mumkin emas.

### 2026-09-10 — 0.6.32 commit va reliz; pilot hamon qo'l kutmoqda
Nima: kechagi ish (papka ko'prigi + capture rate 1-bosqichi) uch commitga
bo'lindi va 0.6.32 relizi chiqarildi (`fb42f06`, `23b4cad`, `413aef0`).
Nega uch commit: ikki mustaqil o'zgarish bitta commitga qorishmasin —
biri nosozlik tuzatmasi (papka ko'prigi), ikkinchisi yangi funksiya
(maxraj).  `tests/test_local_paths.py` kuzatilmagan fayl bo'lib turgan
edi: `git add` unutilsa butun tuzatma qulfsiz ketardi.
Tekshirildi: `make test` to'liq yashil (2 250 test, TS typecheck va
i18n/sayt `--check` bilan birga), `ruff` toza.
Jonli tekshiruv: oxirgi heartbeat hamon `2026-09-09T01:51:09Z` /
`0.6.25`, `pending_devices` dagi qator bugun `02:29:34` da yangilangan —
qurilma tirik, lekin juftlanmagan.  Ya'ni papka do'kon kompyuterida
nusxalanmagan.
Yangi bilim: pilotni MASOFADAN tiklab bo'lmaydi — yangilagich sozlamadan
`device_token` o'qiydi va sozlama yo'qolgan papkada (tuzoqlarga qo'shildi).
Qoldi: do'kon kompyuterida papka nusxasi (ega qiladi), keyin pilotda
`clips.written > 0`, `disk_free_bytes` o'sishi va `seen.total` bo'yicha
`SEEN_LINE_BAND` kalibrlash.

### 2026-09-09 — A1 capture rate, 1-bosqich: maxraj qurilmada sanaladi (0.6.32)
Nima: kirish kamerasida eshikka YAQINLASHGAN noyob odamlar sanaladi va
son heartbeat orqali ko'rinadi — «200 kirdi» yonida «1000 yaqinlashdi»
degan maxraj paydo bo'ldi.
Nega: `SeenCounter` (`enes/retail/conversion.py`) va
`cloud/value.py: capture_rate` ikkalasi ham 09-06 da yozilgan edi, lekin
**ikkalasi ham yetim**: birinchisi pipeline'ga ulanmagan, ikkinchisi hech
qayerdan chaqirilmaydi.  Zanjirning o'rtasi butunlay yo'q edi.
Qayerda: `enes/limits.py` (`SEEN_LINE_BAND = 0.15`),
`enes/retail/lines.py` (`distance_to_segment`, `LineCounter.near`),
`enes/retail/conversion.py` (`mark(force=)`),
`enes/scene_analytics.py` (`count_seen`, trek siklida sanash),
`enes/retail/pipeline.py` (`drain_seen`, `_stats()["seen"]`),
`enes/retail/service.py` (`count_seen`, `_seen_flush_loop`, `write_status`),
`enes/local/supervisor.py`, `enes/local/cloud_config.py`,
`cloud/main.py` (`EdgeHeartbeatBody.seen`).
Test: `tests/test_status_chain.py::test_the_capture_rate_denominator_survives_the_whole_chain`
(to'rt qo'l), `tests/test_scene_retail.py` (tasma: zaldagi odam
sanalmaydi, `entered ⊆ passed`, bir kadrli kesish),
`tests/test_retail_lines.py` (kesmagacha masofa, cheksiz chiziqqa emas),
`tests/test_retail_pipeline.py` (`drain_seen` bo'shatadi),
`tests/test_retail_service.py` (faqat chiziqli kamerada).
Diqqat: **`SEEN_LINE_BAND = 0.15` — TAXMIN, pilotda o'lchanadi.**
Heartbeatda `seen.total` va `entered` solishtiriladi; kutilgan nisbat
`seen ≈ entered × 1,5…4`.  `seen > entered × 10` — kamera savdo zalini
ko'ryapti yoki chiziq noto'g'ri; `seen < entered` — xato.
Hodisa (`people_seen`) HALI YO'Q va bu ataylab: eski cloud noma'lum
`event_type` ni jimgina tashlamaydi — RAD ETADI, qurilma esa uni
`permanent=True` bilan o'ldiradi (`outbox_poisoned` o'sadi).  Avval
cloud tomonidagi `capture.enabled` darvozasi kerak (2-bosqich).

### 2026-09-09 — Pilot yangilanishdan keyin «juftlanmagan» bo'lib qoldi: ma'lumot papkasiga ko'prik (0.6.32)
Nima: `enes/local/paths.py` endi eski `%PROGRAMDATA%\Chaqimchi` papkasini
topsa o'shani ishlatadi — yangilangan kompyuter sozlamasini, kamera
manzillarini va outbox navbatini yo'qotmaydi.
Nega: pilot do'kon 15 soat to'xtab qoldi.  Avto-yangilanish (0.6.25 →
0.6.30) o'tdi, yangi kod bo'sh `%PROGRAMDATA%\ENES` ni ko'rdi va o'zini
YANGI kompyuter deb tanishtirdi: `01:52:42` dan boshlab har 21 soniyada
`device-handover` (2 516 marta, javob `pending`), heartbeat `01:50:47` da
uzildi, eski zanjir yetim jarayon sifatida `12:49` gacha hodisa yubordi.
Ko'prik `enes/paths.py` da bor edi (Box yo'li), do'kon dasturi
ishlatadigan modulda esa yo'q — CLAUDE.md, NSI izohi va daftar uchalasi
ham borligini aytardi.
Qayerda: `enes/local/paths.py:20-90` (`_MARKER`, `_pick`, `data_dir`),
`scripts/windows_installer.nsi:439`, `CLAUDE.md:105`,
`docs/ISH_DAFTARI.md:211`, `tests/test_brand.py:30-60`,
`enes/__init__.py:16` + `pyproject.toml:3` (0.6.32).
Test: `tests/test_local_paths.py` (8 ta) — eng muhimi
`test_an_empty_new_folder_does_not_win` (papka BORLIGI belgi emas, chunki
`data_dir()` uni o'zi yaratadi) va
`test_the_two_path_modules_agree_on_the_old_vendor_name`.
Diqqat: ko'prik faqat YANGI o'rnatishlarga yordam beradi — pilot
allaqachon bo'sh papka bilan qolgan, ya'ni do'kon kompyuterida
`C:\ProgramData\Chaqimchi` ni `C:\ProgramData\ENES` ga NUSXA qilish
kerak (ko'chirish emas).  Reliz `LEGACY_NAME=1` bilan chiqadi: jonli
cloud hali eski kodda va faqat `chaqimchi-windows-*` prefiksini qidiradi.

### 2026-09-09 — Klip nihoyat yoziladi: ortiqcha `%` va mahalliy vaqt (`188a7c5`)
Nima: `enes/retail/ringbuffer.py` da ikkita ustma-ust xato tuzatildi va
yozuvchi↔o'quvchi shartnomasi testga olindi.
Nega: jonli do'konda klip **hech qachon** yozilmagan
(`clips {written: 0, no_segments: 36}`), sabab esa ikki marta noto'g'ri
joyda qidirilgan.
Sabab: (1) `record_command()` patternida ortiqcha `%` — ffmpeg
`%%` ni literal `%` deb yozgan va fayl `camera-01-%Y0909-041347.mp4`
bo'lgan, `SEGMENT_PATTERN` esa uni tanimagan → `scan()` doim bo'sh, ya'ni
klip ham, tozalash ham ishlamagan; (2) `-strftime` mahalliy vaqt yozadi,
`_parse_stamp` esa nomni UTC deb o'qigan → UTC+5 da segment besh soat
"kelajakda".  Ikkalasi lokal ffmpeg 8.1.1 bilan qayta ko'rsatildi.
Qo'shimcha: `segment_retention_sec` (10 daqiqa) xom segment oynasini
tayyor klip muddatidan ajratdi — aks holda tuzatishdan keyin bufer
40 GB gacha o'sib, har 30 soniyada ~60 000 fayl `stat()` qilinardi;
`prune()` eski nomli fayllarni o'zi tozalaydi; `.gitignore` dagi reliz
qoidasi brenddan mustaqil bo'ldi (pinlangan nom `test_brand.py` ni
yiqitib turgan edi).
Tekshirildi: yangi testlar eski kodda **12 ta yiqiladi**, tuzatilganda
20/20 o'tadi; to'liq to'plam yashil.  Haqiqiy ffmpeg bilan yozib-o'qish
testi qo'shildi (ffmpeg bo'lmasa `skip`).
Qoldi: 0.6.31 relizi (`LEGACY_NAME=1`) va pilotda `clips.written > 0`.

### 2026-09-09 — 5B: boshqaruv bazasi PostgreSQL'da (`0045f4a`…`7a30b77`)
Nima: `cloud/store.py` va `cloud/payments/store.py` ikki dialektli
bo'ldi, ma'lumot ko'chiradigan skript va zaxira himoyasi qo'shildi.
Yoqish ixtiyoriy (`ENES_CONTROL_DATABASE_URL`).
Nega: production `--workers 1` da ishlardi va sababi shu ikki fayl —
SQLite bitta faylga ko'p jarayondan yozishga yaramaydi.
Qayerda: `cloud/store.py` (`_PostgresConnection`, `_to_postgres`,
`_split_statements`, `INTEGRITY_ERRORS`, `device_jobs.seq`),
`cloud/payments/store.py` (ulanish CloudStore'dan, `invoices.seq`),
`cloud/main.py` (`control_database_url`), `cloud/vision_worker.py`,
`scripts/migrate_control_db.py`, `scripts/backup_production.sh`,
`docs/PRODUCTION_RUNBOOK.md` §1.1.
Test: `tests/test_store_postgres.py` — SQL tarjimasi bazasiz,
integratsiya `ENES_TEST_DATABASE_URL` bilan.  SQLite 2 182 passed;
haqiqiy PostgreSQL 17 da 19 passed.
Diqqat: **haqiqiy baza beshta xatoni ko'rsatdi** — ular tuzoqlar
bo'limida.  Jonli ko'chirish hali QILINMAGAN; `--workers` rate limit
bazaga ko'chmaguncha ko'tarilmaydi.

### 2026-09-09 — 5A: «Tarmoq» kalkulyatori (`cbe7599`)
Nima: rasmiy saytda tarmoq uchun taxminiy hisob — do'kon soni,
funksiya va kamera tanlanadi, summa darhol ko'rinadi, ariza shu hisob
bilan ketadi.
Nega: «so'rov bo'yicha» degan javob mijozni kattalik haqida
tasavvursiz qoldirardi va ko'pchilik shu joyda to'xtardi; operator ham
suhbatni noldan boshlardi.
Qayerda: `cloud/main.py` (`PublicQuoteBody`, `public_quote`,
`NETWORK_QUOTE_MAX_SHOPS`), `cloud/site/index.html`,
`cloud/static/site.js` (`openCalculator`, `requestQuote`),
`cloud/static/site.css` (`.calc*`), `i18n/*.json` (10 kalit).
Test: `test_cloud_api.py` da to'rtta, `test_site_build.py` da ikkita.
To'liq: 2 171 passed, 1 skipped.
Diqqat: narx qoidasi FAQAT serverda (`feature_quote`) — saytga
formula ko'chirilmasin.  Tannarx/marja public javobga chiqmasligini
`test_the_public_quote_never_leaks_cost_or_margin` qulflaydi.
Tarmoq chegirmasi YO'Q: hisob do'kon soniga oddiy ko'paytma, ya'ni
kelishuvda narx faqat pasayishi mumkin.

### 2026-09-09 — 5A: obuna eslatmasi to'lov sahifasiga ulandi (`e713a7d`)
Nima: obuna tugashi haqidagi Telegram eslatmasida endi to'lov
sahifasining havolasi turadi; hisob-faktura o'zi ochiladi va davr
davomida qayta ishlatiladi.
Nega: eslatma «panelda ochasiz» deb tugardi — ega hisobni qidirishi
kerak edi va ko'pchilik shu joyda to'xtardi.  To'lov zanjirining
qolgan qismi (`mark_paid` → `extend_subscription`) allaqachon bor edi,
yetishmagani aynan shu havola edi.
Qayerda: `cloud/digest.py` (`build_renewal(pay_url=…)`,
`DailyDigestService(renewal_invoice=…)`, `_renewal_once`),
`cloud/main.py` (`_renewal_pay_url`, xizmat qurilishi),
`i18n/*.json` (`digest.renewal.pay_link`).
Test: `test_owner_report.py` da to'rtta, `test_payments_api.py` da
to'rtta.  To'liq: 2 165 passed, 1 skipped.
Diqqat: Payme/Click merchant kalitlari hali yo'q — to'lov sahifasi
ularsiz «Onlayn to'lov hozircha ulanmagan» deb aloqa yo'lini
ko'rsatadi, ya'ni havola baribir foydali (summa va hisob raqami
ko'rinadi).  Kalitlar kelgach tugmalar o'zi paydo bo'ladi.

### 2026-09-09 — Inline skriptlar tashqi faylga: CSP majburiy rejimga tayyor (`701ec62`, `e068cf9`)
Nima: sakkiz sahifadan 691 qator JS `cloud/static/*.js` ga chiqdi,
10 ta `onclick`/`onsubmit` atributi `data-act` delegatsiyasiga o'tdi,
server qo'yadigan qiymatlar `application/json` bloklariga ko'chdi.
Endi CSP ni majburiy qilish uchun sarlavha nomini almashtirish yetadi.
Nega: `script-src` da `'unsafe-inline'` yo'q — majburiy rejimda bu
sahifalar jimgina ishlamay qolardi va brauzer buni ekranda
ko'rsatmasdi.  Frontend versiyalari ham qotirildi (`latest`
takrorlanmaydigan qurilish berardi).
Qayerda: `cloud/static/{status,dl,connect,install,edu,pay,installer,
print-button}.js` (yangi), `cloud/site/*.html` (shablonlar),
`cloud/static/installer.html`, `frontend/owner.html`,
`frontend/src/api.ts` (`telegramBotUrl`), `cloud/static/site.js`,
`deploy/Caddyfile{,.enes}` (hash), `frontend/package.json`.
Test: `test_no_page_carries_an_inline_event_handler`,
`test_every_inline_script_is_covered_by_a_hash`,
`test_the_shell_theme_script_is_the_only_hashed_one`,
`test_the_frontend_pins_its_versions`.  To'liq: 2 157 passed.
Diqqat: sahifaga qaraydigan 11 test yangi joyga yo'naltirildi —
tuzoqlar bo'limiga qarang.  Panel qobig'idagi tema skripti ataylab
inline qoldi (hash bilan): u birinchi chizishdan oldin ishlashi shart.

### 2026-09-09 — Shox `main` ga, Qadam 3: cutovergacha cloud tuzatishlari (`39352a8`…`a466e06`)
Nima: rebrend `main` ga qo'yildi va cutoverga bog'liq bo'lmagan
oltita tuzatish yopildi — CI to'liq, «javon» bayrog'i saqlanadi,
chiqish serverda ham amalga oshadi, CSP hisobot rejimida, `/health/deep`
resurs ogohlantirishi, yetim fayl o'chdi.
Nega: cutover egadan Payme/Click va NS SVG kelishini kutadi, F8 esa
soakni.  Shu ikki darvozaga tegmaydigan ish oldindan bajarilib,
cutover kuni bitta deployda chiqadi.
Qayerda: `.github/workflows/ci.yml`, `enes/local/static/zone-editor.js`
(`serialise`), `cloud/static/geometry-panel.js`, `cloud/event_store.py`
(`owner_members.auth_version`, `member_by_id`, `revoke_member_sessions`),
`cloud/owner_auth.py`, `cloud/store.py` (`revoke_account_sessions`),
`cloud/main.py` (`require_active_owner`, ikkala `logout`, `health_deep`),
`cloud/alerts.py` (`server_health_warnings`), `frontend/src/api.ts`
(`logout`), `deploy/Caddyfile{,.enes}`.
Test: `test_ci_workflow.py`, `test_security_headers.py`,
`test_the_shelf_flag_survives_a_save`,
`test_both_editors_offer_the_same_zone_flags`,
`test_logging_out_kills_the_owner_token_on_the_server`,
`test_logging_out_kills_the_portal_token_on_the_server`,
`test_logging_out_asks_the_server_too`,
`test_deep_health_warns_about_resources_without_crying_503`.
To'liq: 2 153 passed, 1 skipped.
Diqqat: **`main` ni cutover kunigacha deploy qilmang** — sabab yuqorida,
HOZIRGI HOLAT tepasida.  CSP hali `-Report-Only`: majburiy qilishdan
oldin inline `<script>` lar tashqi faylga chiqarilishi kerak.
`shelf` tuzatishi eski sozlamani QAYTARMAYDI — u allaqachon o'chgan
bo'lsa, javon zonasi qayta belgilanishi kerak.

### 2026-09-08 — F6/F9: ichki nomlar ENES, ko'priklar, hujjat va tozalash (`b8883d8`, `ef558cd`, `c0c8cbb`)
Nima: paket, env, reliz, xizmat, yo'l, Docker va Windows nomlari ENES;
eski o'rnatilgan qurilma va jonli server ko'priklar orqali ishlayveradi.
Nega: rebrend rejasi F6; ko'priklarsiz deploy kuni har unutilgan nom
alohida nosozlik bo'lardi, pilot kompyuteri esa yangilanmay qolardi.
Qayerda: `chaqimchi_ai/__init__.py` (ko'prik), `enes/envcompat.py`,
`enes/paths.py` (`_windows_dir`, `_linux_dir`), `enes/local/autostart.py`
(`_drop_legacy_tasks`), `enes/local/chain_processes.py`
(`LEGACY_CHAIN_MODULE`), `scripts/windows_installer.nsi` (`.onInit`
eski o'rnatish), `cloud/main.py` (`WINDOWS_RELEASE_PREFIXES`,
`_windows_release_files`), `cloud/store.py` (moliya SQL),
`scripts/sign_release.py`/`generate_update_key.py` (eski kalit yo'li),
`scripts/build_windows_payload.py` (`CODE_DIRS` ko'prik bilan).
Test: `tests/test_brand.py` (qo'riqchi + ko'priklar), `tests/test_envcompat.py`,
`test_windows_installer.py`, to'liq `make test` yashil.
Diqqat: Windows tomoni (NSI, avtostart, papka ko'priki) real mashinada
SINALMAGAN — F8 relizidan oldin pilotda tekshiriladi (KEYINGI ISH
ro'yxati).  `releases/` dan 42 eski fayl o'chirildi (lokal).

### 2026-09-08 — F5: Telegram, hisobot, CSV va tarif matni a'zo tilida (`28e2c8b`)
Nima: ruscha a'zo kunlik/haftalik hisobotni, ogohlantirishni, bot
javobini ruscha oladi; `?lang=ru` tarif kartasi va `X-Lang: ru` CSV
ruscha; o'zbekcha chiqish harfma-harf avvalgidek («3,2 mln so'm»
bundan mustasno — panel bilan tenglashtirildi).
Nega: F2 til yadrosi bor edi, lekin server matni hali literal edi va
`_deliver` bitta matnni hammaga yuborardi.
Qayerda: `cloud/digest.py` (`TextBuilder`, `_deliver`), `cloud/alerts.py`
(`OwnerMessage`, `OwnerNotify`), `cloud/main.py` (`_notify_site_members`,
`_bot_lang`, `_adopt_telegram_language`, `_bullet_text`,
`_localized_network_card`, CSV funksiyalari), `cloud/notify.py`,
`cloud/trust_score.py`, `cloud/botfmt.py`, `cloud/value.py`,
`enes/licensing/plans.py` (`PlanBullet.key/params`).
Test: `tests/test_i18n_surfaces.py`, `test_value.py`, `test_cloud_alerts.py`,
`test_device_health_alerts.py` (kalitga o'tkazildi).
Diqqat: `owner_text` endi satr emas, `OwnerMessage` — `.for_lang("uz")`.
Ichki ops matni (`_problem_text` va h.k.) ataylab katalogsiz.

### 2026-09-08 — F4c: ega paneli matni uch tilda (`1edc5f3`)
Nima: ega paneli UZ/RU/EN — til tanlagich sahifani yangi tilda ochadi,
serverdan keladigan matn ham (`X-Lang`) o'sha tilda.
Nega: rebrend rejasining O-3 (rus tili yo'q) topilmasi; matn TSX
ichida bo'lgani uchun tarjima qilib bo'lmasdi.
Qayerda: `frontend/src/*.tsx` (12 fayl), `frontend/src/api.ts`
(`formatDateUz`, `formatMoney`, `relativeMinutes` katalogdan),
`i18n/{uz,ru,en}.json`, `frontend/src/i18n/catalogue.generated.ts`.
Test: `test_connect_ui.py`/`test_events_ui.py` (`key_text`),
`test_panel_v2.py`, `test_i18n_catalogue.py` (uch tilda kalit tengligi,
o'rinbosarlar).
Diqqat: ish parallel agentlar bilan qilindi — har agent kalitlarini
alohida JSON'ga yozdi, birlashtirish `merge_i18n` skripti bilan
(to'qnashuv → xato).  Sessiya limiti ikki marta uzdi; qoldiq ish qo'lda
yakunlandi.  Lokal `data/cloud/cloud.db` da skrinshot uchun yaratilgan
«Surat do'koni»/`shotadmin` qoldi — jonli emas, faqat lokal.

### 2026-09-08 — F4a: admin support vositalari React adminga ko'chdi (`dc60e2c`)

Nima: eski `admin.html` ning 18 ta endpointi endi React adminda —
mijoz tafsiloti (`/admin/customers/{id}`), Jamoa, Sozlamalar, to'lov
modallari.  Bitta `window.confirm` ham yo'q: `Modal`, `ConfirmDialog`
(nomni terib tasdiqlash), `useToast`, `MonthPicker`, `CopyField`
(`components.tsx`).  `GeometryEditor` ikkala panel uchun bitta
(`kind="admin"` — admin config/preview yo'llari).  Marshrut ikkinchi
segmentni o'qiydi (`usePanelRoute` → `[active, navigate, param]`).
Qobiq sarlavhalari va paneldagi ko'rinadigan matn ENES.

Nega: `556d33c` eski adminni o'chirgan, lekin React adminda faqat
«Arizalar» qo'shilgan edi — do'konni masofadan tuzatish, funksiya
biriktirish (sotuv darvozasi), reliz boshqaruvi yo'q edi va shox shu
sabab deploy qilinmas edi.

Qayerda: `frontend/src/AdminCustomer.tsx` (yangi, 637 q.),
`AdminTeam.tsx`, `AdminSettings.tsx` (yangi), `admin.tsx`
(`CustomersPage` → tafsilot, `PaymentsPage` modal, `team`/`settings`),
`components.tsx` (+Modal/Confirm/Toast/MonthPicker/CopyField),
`router.ts`, `GeometryEditor.tsx`, `styles.css` (+70 q.),
`frontend/{owner,admin}.html` sarlavha, `cloud/static/v2/` (bundle).

Test: `test_panel_v2.py` — `test_the_admin_can_fix_a_shop_remotely`
(18 endpoint), `test_the_admin_uses_no_native_dialogs`,
`test_the_customer_page_is_deep_linkable`,
`test_the_geometry_editor_serves_both_panels`,
`test_the_old_brand_stays_off_the_panels`;
`test_windows_installer.py::test_admin_panel_promises_the_same_interval`
(xfail olindi, `AdminCustomer.tsx`); `test_cloud_api` qobiq «ENES».
Playwright bilan jonli tekshirildi: login → mijoz sahifasi → AI
imkoniyatlar oynasi → Jamoa → Sozlamalar (skrinshotlar).

Diqqat: lokal serverda portal login uchun `ENES_PORTAL_JWT_SECRET`
(≥32 belgi) SHART — usiz `/api/v1/auth/login` 503 beradi va bu
«tugma ishlamayapti» kabi ko'rinadi.  Baza yo'li — `ENES_CLOUD_DB`.
Diqqat: onboarding bosqich matnlari serverdan («Sotqin cloudga
juftlandi») — F6 da o'zgaradi.
Diqqat: skrinshot sinovi lokal `data/cloud/cloud.db` ga «Surat do'koni»
sayti va `shotadmin` akkauntini qoldirdi (birinchi urinish standart
bazaga tushgan) — lokal dev bazasi, production'ga aloqasi yo'q.

### 2026-09-08 — F3.2: qolgan sayt sahifalari shablonga, eski CSS o'chdi (`99ed0e6`)

Nima: 13 sahifa `cloud/site/` shablonlariga ko'chdi (jami 26 qurilgan
fayl).  Umumiy nav va footer — `cloud/site/partials/`.  Aloqa, hamkorlik,
holat, ulash, yuklab olish uch tilda (`/ru/aloqa`, `/en/status`; `dl.`
hostida `/ru/`); sitemap aloqa va hamkorlikni alternativlari bilan
sanaydi.  `pay.html` `site.css` ga o'tdi, `owner.css`/`panel.css`
o'chirildi.  Hujjat sahifalari brendga va `tokens.css` ga o'tdi.
`installer.html` (partner paneli) faqat brend matni.

Nega: rebrend F3 — bitta nav/footer, bitta brend, uch til.

Qayerda: `scripts/build_site.py` (`Page` reyestri, `include:`, `page:`),
`cloud/site/*.html`, `cloud/site/partials/{nav-sub,footer}.html`,
`cloud/main.py` (`_render_public` endi `__PUBLIC_ORIGIN__` ni ham qo'yadi;
statik sahifalar `_render_public` ga; `/ru/{slug}`, `/en/{slug}`;
`dl.` hostida til; sitemap guruhlari), `i18n/*.json` (+131 kalit),
`cloud/static/docs/*`, `tests/test_site_build.py` (+14).

Test: `test_every_subpage_is_built_in_three_languages`,
`test_uzbek_only_pages_still_come_from_the_template`,
`test_no_generated_page_carries_the_old_brand`,
`test_shared_navigation_reaches_every_templated_page`,
`test_localized_subpages_are_served_with_placeholders_filled`,
`test_uzbek_pages_get_their_placeholders_filled` (footer'dagi
`__APP_URL__` — `FileResponse` uni qo'ymasdi),
`test_the_download_host_serves_each_language`.  Eski CSS testlari
o'chdi (React'dagi qulflar `test_panel_v2.py` da).

Diqqat: shablon IZOHIDA ham `{{` yozmang — `build_site.py` uni
o'rinbosar deb o'qiydi (footer izohi shu bilan yiqildi).
Diqqat: `test_the_payment_page_is_not_a_dark_developer_screen` xom
HTML'ni o'qiydi — izohda eski fayl nomi ham «bor» hisoblanadi.
Diqqat: `installer.html` shablon EMAS (o'z JS/CSS qobig'i, partner
paneli) — brend matni qo'lda; F4 da React'ga ko'chsa o'chadi.

### 2026-09-08 — F3.1: bosh sahifa uch tilda, yangi dizaynda (`4f199ce`)

Nima: `/`, `/ru/`, `/en/` — ENES dizaynidagi bosh sahifa, har til o'z
canonical va `hreflang` bilan; sitemap uchala tilni alternativlari
bilan e'lon qiladi.  Sahifa `cloud/site/index.html` shablonidan
`scripts/build_site.py` bilan quriladi, matn `i18n/*.json` dagi
`site.*` kalitlaridan (172 ta × 3 til).  `site.js` uchala tilda bitta
fayl: satrlar sahifaga `window.__SITE__` bilan qo'yiladi.

Nega: rebrend F3.  Qidiruv tizimiga har til uchun alohida sahifa kerak,
yangi bog'liqlik qo'shilmaydi, server so'rov paytida hech narsa render
qilmaydi — shuning uchun statik qurilish, natija commit qilinadi.

Qayerda: `cloud/site/index.html` (yangi), `scripts/build_site.py`
(yangi), `cloud/static/site.css` (qayta yozildi — `--band-*` bo'lim
tokenlari), `cloud/static/site.js`, `cloud/static/site{,.ru,.en}.html`
(qurilgan), `cloud/main.py` (`LANDING_PAGES`, `/ru`, `/en`, sitemap
`xhtml:link`), `Dockerfile.cloud` (`COPY i18n`), `Makefile`
(`build_site.py --check`), `i18n/{uz,ru,en}.json`, 13 sahifada `?v=`.

Test: `tests/test_site_build.py` (yangi, 21 ta) — `--check` eskirmagani,
har tilda canonical/hreflang, til tanlagichda joriy til, JSON-LD har
tilda yaroqli va FAQ savoli sahifada, eski brend yo'q, `site.js`
satrlari katalogdan, kesh tokeni hisoblangan, marshrutlar 200 (307
emas), subdomenda 404, sitemap alternativlari.  `test_static_pages.py`
endi uchala tilni ham yuradi; `test_the_cloud_image_carries_the_language_catalogue`.
Yangilangan: `test_platform_hosts` («ENES»), `test_cloud_api`
(«2–4 kamera» + «Boshlang‘ich 2, Biznes 4»).

Diqqat: nav ichida «button» SO'ZI ham bo'lmasin — `test_dark_nav_button_is_gone`
`<nav>…</nav>` ni matn sifatida o'qiydi, izohdagi so'z ham hisob.
Diqqat: `site.css` qayta yozilganda boshqa 13 sahifa ishlatadigan
sinflar SAQLANDI (`test_shared_pages_keep_the_styles_they_use`) — ular
F3.2 da shablonga o'tgach o'lik qoidalar tozalanadi.
Diqqat: tarif kartalari matni serverdan o'zbekcha keladi (`plans.py`,
`NETWORK_PLAN_CARD`) — ru/en sahifada ham; F5 da katalogga o'tadi.
Diqqat: namunadagi «1000+ mijoz», «99.9%», App Store, qurilma surati
ataylab yo'q — bugun rost emas (`FORBIDDEN_CLAIMS` va sayt qoidasi).

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
`chaqimchi.uz` **168 marta**, **132 ta** `ENES_*` sozlama;
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

- `enes/retail/conversion.py: SeenCounter` — bir kamerada oynada
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
ga tegilmadi.  Deploydan oldin serverda `ENES_UI_V2_OWNER` ni
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
uzoqlashib ketardi.  `ENES_CLIP_RETENTION_DAYS` va
`ENES_FACE_RETENTION_DAYS` o'rniga
`ENES_MEDIA_RETENTION_HOURS` (standart 48).

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
`enes/outbox.py: failure_reason(), requeue_dead_letters()`,
`enes/cloud_sync.py`, `scripts/dead_letters.py` (yangi).

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

Qayerda: `enes/camera_roles.py` (yangi — konstantalar + taklif
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
purge boshlab, test env'i (`ENES_CLIP_RETENTION_DAYS=60`)
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

Qayerda: `enes/local/benchmark.py`,
`enes/local/cloud_jobs.py:338`, `cloud/static/admin.html:1621`.
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
`enes/local/cloud_config.py` (`publish_cameras`),
`enes/retail/inventory.py` (`InventoryCamera.record_url`,
`merge_cameras`), `enes/local/cloud_jobs.py`.
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

Qayerda: `enes/local/cloud_jobs.py`, `cloud/store.py`
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
`scripts/benchmark_n100.py` dan `enes/local/benchmark.py` ga
ko'chdi (payload'da `scripts/` yo'q edi, ya'ni tavsiya bajarib
bo'lmasdi) va admin panelda «Sig'imni o'lchash» tugmasi paydo bo'ldi.

Profilaktika: `cloud/store.py` dagi 8 ta raqamli qator o'qish nomli
aliasga o'tkazildi va naqsh uchala baza moduli uchun testda qulflandi.

Qayerda: `cloud/digest.py`, `cloud/event_store.py`,
`cloud/config_health.py` (yangi), `cloud/main.py`, `cloud/store.py`,
`cloud/static/admin.html`, `cloud/static/owner.html`,
`enes/limits.py`, `enes/scene_analytics.py`,
`enes/retail/pipeline.py`, `enes/retail/ringbuffer.py`,
`enes/retail/service.py`, `enes/local/benchmark.py`
(yangi), `enes/local/cloud_config.py`,
`enes/local/cloud_jobs.py`, `enes/local/supervisor.py`,
`enes/local/app.py`.

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
`enes/limits.py`, `enes/retail/pipeline.py`,
`enes/retail/service.py`, `enes/local/supervisor.py`,
`enes/local/cloud_config.py`, `enes/local/app.py`,
`enes/outbox.py`, `enes/cloud_sync.py`.

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
(`copyText`), `enes/local/camera_probe.py` (`audio_track`).

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

1. **`enes/local/chain_processes.py`** (yangi) —
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

Qayerda: `enes/local/chain_processes.py` (yangi),
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

Qayerda: `enes/local/supervisor.py`,
`enes/retail/service.py` (`write_status` ga `pid` qo'shildi).
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
Qayerda: `enes/cloud_sync.py:_upload_media` (4xx endi hodisani
o'ldirmaydi, 5xx esa avvalgidek qayta urinadi);
`cloud/main.py:upload_event_snapshot` (yuz kadri endi FAQAT o'z
chegarasini sarflaydi, umumiy byudjetga tegmaydi);
`enes/scene_analytics.py` (`FACE_EMITS_PER_HOUR = 40` — track
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
Qayerda: `enes/local/cloud_config.py:_attendance_signature`,
`enes/local/app.py` (restart sharti + yangi sozlama qo'shganda
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
`ENES_COST_KWH_UZS=1000`, `ENES_COST_SERVER_MONTHLY_USD=8`
(ikkalasi serverda qo'yilgan), vatt — Windows 65, Box 12.

### 2026-08-26 — 0.6.16 va yuklab olish pinidan qutulish (`503f98a`, `925e63b`)
Nima: mijoz endi eng yangi imzolangan relizni oladi; kompyuter soati
nazorati mijozgacha yetdi.
Nega: `ENES_WINDOWS_INSTALLER_URL` serverda qotirilgan edi va
0.6.14/0.6.15 nashr qilingani holda mijozlar 0.6.13 olib turardi.
Qayerda: server `.env.production` (pin olib tashlandi),
`latest_windows_release()`, `cloud/static/install.html`.
Diqqat: **bu pinni qayta qo'ymang.** Yon natija — fayl nomi endi
`ENES_Setup-<versiya>.exe` (redirect emas, to'g'ridan-to'g'ri
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
umuman tekshirmasdi); `enes/licensing/edu.py` (`MODULES` endi
faqat `faceid` + `branch`, qolgani `PLANNED_MODULES` da narxsiz);
`/maxfiylik` ga ikkita yangi bo'lim; `/health/deep` javobi rolga qarab
qisqaradi.
Test: `tests/test_cloud_faces.py::test_a_manager_cannot_open_any_biometric_image`,
`tests/test_static_pages.py` (`FORBIDDEN_CLAIMS` — 4 ta ibora
qulflandi, qaytib kela olmaydi).
Diqqat: `/health/deep` **butunlay yopilmadi** — UptimeRobot aynan shu
manzilga qaraydi; begona faqat `ok`/`name`/`ms` ni ko'radi.
Serverda `ENES_JWT_SECRET` **qo'yilmagan** (A9 tekshirildi) —
owner/portal kalit ajratilishi buzilmagan, O'RTA-7 yopildi.

### 2026-08-25 — Audit hujjati (`1daf474`)
Nima: [AUDIT_TAHLIL.md](AUDIT_TAHLIL.md) — chaqimchi.uz va mahsulot
holati bo'yicha 22 topilma, tuzatish holati va A/B/C/D reja.
Diqqat: audit **ikki marta xato qildi** va ikkalasi bekor qilindi —
O-0 (`config/sotqin.yaml` da 4 va 8 ikkalasi ham to'g'ri: SLA va
apparat shifti) va O-6 (chidamli Telegram tormozi allaqachon bor).
Saboq "Tuzoqlar" bo'limiga yozilgan.
