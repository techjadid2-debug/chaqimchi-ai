# Tugallanmagan ishlar: UI/UX + cloud + operatsion — audit va reja

> Holat: 2026-09-12. `main` toza, HEAD `eeabca6`. Jonli server 0.6.33 kodida (F7 cutover 11-sen).
> Pilot qurilmasi o'lik (do'kon kompyuterida qo'l ishi kutadi) — real ma'lumotli tekshiruvlar undan keyin.
> Uchta parallel audit (panel / sayt / cloud) + ikkala qizil test lokal qayta yurgizildi; quyidagi har band manbada tasdiqlangan.

## Kontekst

11-sentabrdagi UI/UX QA + dizayn-3 ishi deploy qilindi, lekin (1) auditning NICE qoldiqlari ochiq, (2) o'sha QA **admin panelni qamramagan** — u yerda ega panelida tuzatilgan xatolarning aynan o'zi turibdi, (3) sayt formalarida foydalanuvchi `[object Object]` o'qiydi, (4) cloud A1 capture-rate zanjirining o'rtasi yo'q — qurilmadagi tayyor kod cloud `config["capture"]` yubormagani uchun o'lik, (5) operatsion qarzlar (Postgres, CSP majburiy, `releases/`, UptimeRobot) turibdi va (6) `make test` ikki eski test bilan qizil — keyingi regressiya ko'rinmaydi.

**Foydalanuvchi qarorlari (2026-09-12):** to'rt yo'nalish ham rejaga kiradi (UI/UX panel+sayt, A1 3–5, operatsion, admin i18n); `night` stat heartbeatga chiqariladi; «AI yordamchi» tabi Gemini kaliti bo'lmasa yashiriladi (`capabilities.agent`); ish oxirida cloud deploy ham qilinadi.

**Farazlar (so'ralmagan, o'zim qaror qildim):** oferta bo'sh joylari (STIR/rekvizit/sana) egadan kelmaguncha qoladi — faqat jadval uslubi va qotirilgan narx tuzatiladi; kirish sahifasining brauzer tiliga ergashishi (EN brauzer → EN) xato emas, o'zgartirilmaydi; issiqlik xaritasi oqarishi pilot tirilgach real ma'lumotda ko'riladi; Postgres ko'chirish `.env.production` ni qo'lda tahrirlashni talab qiladi (fayl agent uchun yopiq) — bu qadam ega bilan birga alohida oynada.

---

## Topilmalar xulosasi (nima ochiq)

### 🔴 Kritik / foydalanuvchi ko'radi
| # | Qayerda | Nima |
|---|---|---|
| S1 | `cloud/static/site.js:55`, `cloud/main.py` (handler yo'q) | Validatsiya xatosida `detail` ro'yxat → foydalanuvchi **`[object Object]`** o'qiydi. Trigger oson: `#phone`/`#notifyPhone` da `minlength` yo'q, server `min_length=5` |
| S2 | `cloud/static/edu.js:256-286`, `cloud/site/edu.html:242` | Edu forma: `reportValidity()` chaqirilmaydi, xato sinfi `err` (CSS `error`) — xato **kulrang**, xabarga «Telegram: @fibotai» + xom `error.message` |
| S3 | `cloud/site/index.html:162,174` | JS o'chiq/API yiqilsa yuklab olish qatori **bo'sh joy** (`install.html` to'g'ri qilingan) |
| S4 | `cloud/site/index.html:442-446` | Bosh sahifa futeri partialdan nusxa — RU/EN sahifadan **o'zbekcha** `/status`, `/hamkorlik`, `/aloqa` |
| S5 | `cloud/main.py:2331,2752` | `__TELEGRAM_REGISTER_URL__` zaxirasi `/#pilot` — bunday id **yo'q** (bo'lim `#aloqa`) |
| P1 | `frontend/src/GeometryEditor.tsx:114-115` | Ega panelida **`window.prompt`/`window.confirm`** qaytib kelgan (Telegram WebView'da chiqmasligi mumkin → zona nomlash jim o'ladi). Test faqat `ADMIN_FILES` ni tekshiradi |
| P2 | `admin.tsx:164,184,267`, `AdminSettings.tsx:24`, `AdminTeam.tsx:30`, `AdminCustomer.tsx:379` | Admin: 6 sahifa API yiqilsa **xato + abadiy skelet** (ega panelida tuzatilgan naqsh, adminga ko'chmagan) |
| P3 | `owner.tsx:49,378`; `cloud/main.py:7158-7197` | «AI yordamchi» tabi hech qanday darvozasiz; `capabilities.agent` yo'q |
| C1 | `cloud/main.py:6615-6656` | Cloud **`config["capture"]` yubormaydi** → qurilmadagi `people_seen` (0.6.33) doim yopiq |
| C2 | `cloud/event_store.py:27-61` | `people_seen` `REPORT_EVENT_TYPES` da ham, `TIMELINE_HIDDEN_TYPES` da ham yo'q → C1 yopilgan kuni lenta har 10 daqiqada axlatlanadi, hisobot esa maxrajni ko'rmaydi |
| T1 | `tests/test_status_chain.py`, `tests/test_windows_installer.py:376` | Ikkita qizil test: `night` stat holat fayliga yozilmaydi; test eski domenni (`api.chaqimchi.uz`) kutadi |

### 🟡 Muhim
- **Panel:** CSV yuklash `<a>` DOMga qo'shilmay `revokeObjectURL` darhol (`owner.tsx:301,313,326`, `admin.tsx:75`), `downloadTrafficCsv` toast'siz (`owner.tsx:334`); `Modal` fokus tuzog'i/qaytarish yo'q (`components.tsx:326-342`, izoh yolg'on gapiradi), `.notif-panel` ham; `Tabs` da `aria-controls`/`tabpanel` yo'q; `CameraDetail.tsx:69` ichida `EventEvidence` **ikkinchi `PageHeader`** + kun tanlagich + maxfiylik chizig'i (`embedded` prop yo'q); `admin.tsx:41` `t()` modul darajasida (`leads` yorlig'i doim UZ); `admin.tsx:210` `const t=(n:number)=>…` — `t` soyalangan; admin qidiruv telefonda yetib bo'lmaydi (`styles.css:596`); `outline:none` `:focus-within`siz (`styles.css:289,343`); drawer yopish tugmasi `aria-label`siz (`admin.tsx:384`); `sev-*` nuqta faqat rang (`owner.tsx:209`); «Xodimlar» nav funksiya o'chiq bo'lsa ham chiziladi (`owner.tsx:28`).
- **Sayt:** oferta jadvallari uslubsiz, mobil o'ramsiz (`oferta.html:81,136`; `site.css` da `table` qoidasi yo'q), narx qotirilgan (`oferta.html:82-85`); status sahifasi `checks[]` ni tashlaydi, qizil holat yo'q, timeout yo'q (`status.js:17-30`, `site.css:396`); telefon menyusi tashqi bosishda yopilmaydi (`site.js:103-111`); futer havolalari ~20 px (`site.css:349-352`); `#notifyPhone` `label`siz, kalkulyator `<label>` ichida ikki control (`site.js:335-339`); OG meta faqat bosh sahifada, `og-enes.png` hali PIL; canonical 3 sahifada, `/privacy` = `/maxfiylik` dublikat; `panel-bugun-v3.webp` eskirgan (test `test_static_pages.py:533` qulflaydi); `/edu` ichki sahifalardan yetib bo'lmaydi; UZ-only sahifada til almashtirgich bosh sahifaga tashlaydi; server xato matnlari `X-Lang` ni o'qimaydi (`main.py:3348-3355,3198`); `aloqa.html:20` bot nomi literal; `install.html:45` `0.6.16` zaxira matni; `Inter` yuklanmaydi (`site.css:63`).
- **Cloud/ops:** CSP ikkala Caddyfile'da `-Report-Only` (bir hafta o'tdi; test `:30` `REQUIRED` da eski nom); `/chek` `BOT_COMMANDS` da yo'q (`main.py:1296`), lekin yordamda bor; `releases/` server tomonda **hech qachon tozalanmaydi** (~1.9 GB); UptimeRobot hali `/health` da; boshqaruv DB (to'lovlar, parollar) SQLite — kod tayyor, jonli ko'chirish yo'q; `enes/paths.py` ko'prigi hali `exists()` bilan (Box yo'li; `enes/local/paths.py` da tuzatilgan naqsh `config.yaml`); `cloud/value.py:166-230` uch funksiya o'lik (C1–C2 gacha).
- **Admin i18n:** 5 faylda ~463 ta literal, 45 ta `t()` (97% tarjimasiz).

### 🟢 Mayda
`.metric-grid-4`, `.traffic-card`, `.plan-heatmap`, `.band-tint` o'lik CSS; `site.js:251-255` `#heroPrice` o'lik + 2 o'lik katalog kaliti; `shop-corridor-v1.webp`, `design2-*.webp` yetim; `META_COLOR`/`heatRgb` ranglar tokenlardan tashqari; `devices`≡`monitoring` bir sahifa; `router.ts:70` deps'da `legacy` yo'q; `install.js:5-6` chiqindi qatorlar; `sitemap` xaritasi `PAGES` dublikati.

### ✅ Yopiq — qayta rejalashtirilmaydi
Tabs klaviatura; i18n uz/ru/en 1294 kalit teng; xom FastAPI `detail` ega panelida; ega paneli skeletlari; `.page-actions` telefon; bundle `cloud/static/v2` manba bilan bitta commitda; brendli 404; eski brend saytda yo'q; «Tarmoq» chevron rost accordion; multi-worker kod yo'li; O-3/O-8/O-9 audit bandlari; `benchmark` job zanjiri; to'lovlar rost integratsiya (faqat kalit yo'q).

---

## Bosqichlar (tartib bilan, har biri alohida commit(lar), `make test` yashil)

### Bosqich 0 — Qizil testlar + kichik cloud qarzlar (~1.5 soat, 1 commit)
`fix(qurilma,bot): tungi statistika heartbeatda, /chek menyuda, ikki eski test yashil`
1. **`night` → heartbeat** (foydalanuvchi qarori): `enes/retail/service.py: write_status()` ga `"night": {"motion_alerts", "relearns"}` (`clips` yonida, sabab izohi: pilotda `relearns` 1–2 kutiladi — IR o'tishi ishlayotganini faqat shu ko'rsatadi); `enes/local/supervisor.py: status()` (`:414-426` naqshi); `enes/local/cloud_config.py: send_heartbeat()` (`:393` `clips` naqshi, `int()` bilan); `cloud/main.py: HeartbeatBody` (`:684` yonida `night: Dict[str,int]`). `modes` allaqachon `cameras[].night_mode` — takrorlanmaydi. `tests/test_status_chain.py` to'rt bo'g'inda o'zi tekshiradi.
2. `tests/test_windows_installer.py:376` → `https://api.enes.uz` (test eskirgan, workflow to'g'ri).
3. `cloud/main.py:1296` `BOT_COMMANDS` ga `{"command":"chek","description":"Bugungi chek soni"}` (uch tilda tavsif bo'lsa — mavjud naqshga qarang); `docs/TELEGRAM_BOT.md` ro'yxati.
4. `enes/paths.py` ko'prigi: `exists()` → `config.yaml` bor-yo'qligi (`enes/local/paths.py: _pick()` bilan bir xil mantiq; test qo'shing).

### Bosqich 1 — Sayt xatolari (~6–8 soat, 2 commit)
**1a** `fix(sayt): forma xatosi o'qiladigan matn, JS'siz yuklab olish, futer tili, o'lik #pilot`
- `cloud/main.py`: `@app.exception_handler(RequestValidationError)` — `/api/v1/public/*` uchun `{"detail": i18n.t("public.error.validation", lang), "code": "validation"}` (til `X-Lang`dan, `_render_public`/`branded_not_found` yonidagi naqsh), boshqa yo'llarda standart handler. `public_create_lead`/`public_quote` dagi qotirilgan o'zbekcha `HTTPException` matnlari (`:3348,3351,3355,3198`) katalogga (`public.error.*`, 3 til).
- `site.js:55`: `typeof body.detail === "string" ? body.detail : T("send_failed")`. `index.html:176,400` telefon maydonlariga `minlength="5" maxlength="32"` (server bilan bir xil son — izohda sabab).
- `edu.js`: `reportValidity()`, `err` → `error`, texnik matn o'rniga `T()` kaliti; `@fibotai` olib tashlanadi (rasmiy kanal — `__TELEGRAM_REGISTER_URL__`).
- `index.html:162-180`: `#downloadReady` standart ko'rinadigan «yuklab olish tayyorlanmoqda» matni bilan (`install.html:29-36` naqshi), JS kelgach almashtiradi; `<noscript>` yozuvi.
- `index.html:442-446` futer → `{{include:partials/footer.html}}` (partial `{{page:…}}` bilan to'g'ri). Test: `test_site_build.py` — RU sahifada `/ru/status` (yoki tegishli yo'l) bor, o'zbekcha `/status` yo'q.
- `cloud/main.py:2331,2752` `#pilot` → `#aloqa`; `test_static_pages.py:371` naqshini Python zaxirasiga ham kengaytiring.
- `aloqa.html:20` bot nomi `{{bot:…}}`/data blokdan (literal emas) + `target="_blank" rel="noopener noreferrer"`; `install.html:45` zaxira matn versiyasiz («ENES_Setup.exe»).

**1b** `feat(sayt): status sahifasi tekshiruvlar ro'yxati bilan, oferta jadvali, telefon menyusi va mayda a11y`
- `status.js`: `checks[]` ro'yxati (nom/ok/ms), qizil `.status-light.down`, `AbortController` 8 s timeout (sabab: `/health/deep` 3 tekshiruv × ~2 s), «yangilangan HH:MM»; `site.css` `.status-light.down`.
- `site.css`: `table` umumiy qoida + `.legal-table` o'rami `overflow-x:auto` (`installer-guide.html:15` `.port-table` naqshini umumiylashtiring); `oferta.html:82-85` narx → `/#narx` ga havola («amaldagi tarif sahifada»), qotirilgan son yo'q. Bo'sh joylar QOLADI (egadan rekvizit kutiladi — daftarda bor).
- `site.js:103-111`: tashqi bosishda yopish, Escape'dan keyin fokus `summary` ga.
- Futer havolalari `padding:8px 0` (≥40 px), `.calc-feature select` 40 px; `#notifyPhone` ga `aria-label`/`label`; kalkulyator `select` ga `aria-label`.
- `partials/nav-sub.html` ga `/edu` (UZ sahifalarda), RU/EN dan UZ-only sahifaga havola yashirilsin yoki «(UZ)» belgisi; til almashtirgich UZ-only sahifada RU/EN tugmalarini `aria-disabled` + `title` («Bu sahifa faqat o'zbekcha»).
- OG meta partial (`partials/head-og.html`) — barcha indexable sahifalar; `privacy.html`, `oferta`, `install`, `edu` ga `canonical` (`/maxfiylik` canonical, `/privacy` unga).
- `panel-bugun-v4.webp`: `scripts/make_panel_screenshots.py` DEMO bilan qora tema 1280 da qayta olinadi (< 200 KB), `index.html:310` + `test_static_pages.py:533`.
- O'lik: `site.js:251-255`, `site.js.from_per_month`/`plan_network_message` kalitlari, `.band-tint`, `install.js:5-6`; `shop-corridor-v1.webp` → `#aloqa` fon (rejadagi NICE, 3 qator CSS) yoki o'chirish.

### Bosqich 2 — Panel xatolari: ega + admin (~8–10 soat, 3 commit)
**2a** `fix(panel): zona nomlash o'z oynasida, admin skeletlari, CSV yuklash xatosi`
- `GeometryEditor.tsx:114-115`: `window.prompt/confirm` → `useConfirm()` (`admin.tsx:148` naqshi) + kichik `PromptModal` (`components.tsx` `Modal` ustida, `t("panel.geometry.name_title")`). `test_the_admin_uses_no_native_dialogs` qamrovini `OWNER_FILES` ga ham kengaytiring.
- Admin 6 joy: `catch` da `setItems([])`/`setLoadState("error")` + `ErrorStrip onRetry` (ega panelidagi `EventEvidence.tsx:114` naqshi). `test_a_failed_request_never_leaves_a_skeleton` ga `ADMIN_FILES` qo'shiladi.
- CSV: umumiy `downloadBlob(blob, name)` yordamchisi (`document.body.appendChild` → `click` → `setTimeout(revoke, 1000)`), 4 chaqiruvchi shunga; `downloadTrafficCsv` toast o'ramiga (`owner.tsx:345` naqshi); `admin.tsx:104` `exportSites` toast.
- `admin.tsx:41` `t()` modul darajasidan chiqariladi (`NAV` funksiyaga/`useMemo`); `admin.tsx:210` `t` → `fmt`.

**2b** `feat(panel): AI yordamchi faqat Gemini bo'lsa, kamera sahifasida ichki hodisalar, fokus tuzog'i`
- `cloud/main.py:7158` `capabilities["agent"] = {"ready": bool(vision_agent.configured()), "reason": …}` (`cloud/vision_agent.py:50-57` dagi kalit/model tekshiruvidan — bitta manba). Panel: `SectionTabs` `hidden` prop; `TABS` literali O'ZGARMAYDI (test regexi); `alerts/agent` ga to'g'ridan-to'g'ri kirilsa `EmptyState`. Xuddi shu yo'l bilan «Xodimlar» nav `features.panel` da `davomat` yo'q bo'lsa yashirinadi (`owner.tsx:28`; daftar `:1763` testi ko'chiriladi).
- `EventEvidence.tsx:92` `embedded?: boolean` — `true` da `PageHeader`, kun tanlagich va maxfiylik chizig'i chizilmaydi (kun `CameraDetail` dan prop); `CameraDetail.tsx:69` shunday chaqiradi.
- `Modal` (`components.tsx:326`): ochilganda birinchi fokuslanadigan elementga fokus, Tab halqasi, yopilganda oldingi elementga qaytarish; `.notif-panel` (`owner.tsx:215`) va `.palette-backdrop` ham shu hook (`useFocusTrap`). Izoh rostlanadi.
- `Tabs`: `aria-controls`/`id`, kontent `role="tabpanel" aria-labelledby`; `CAMERA_TABS` ham.
- `styles.css:596` telefonda qidiruv — drawerga «Qidiruv» bandi (`⌘K` matni faqat desktopda); `:289,:343` `outline:none` o'rniga `.palette-input:focus-within`/`.table-search:focus-within` halqa; `admin.tsx:384` `aria-label={t("panel.common.close")}`; `owner.tsx:209` `sev-*` nuqtaga `aria-label`/matn.

**2c** `chore(panel): bitta KPI komponenti, o'lik CSS, ranglar tokenlardan`
- `MetricCard` → `StatCard` (admin 6 joy), `.metric-grid-4`, `.traffic-card`, `.plan-heatmap` o'chadi; `theme.ts:31` `META_COLOR` → `tokens.css` dan o'qish yoki bitta manba izohi; `Heatmap.tsx:18` `heatRgb` `--heat-scale` dan; `devices`/`monitoring` bitta bo'lim (ikkinchisi `LEGACY` yo'naltirish); `router.ts:70` deps.
- `make ui-build` → `cloud/static/v2` commit (bundle manba bilan bitta commitda — tuzoq).

### Bosqich 3 — Cloud A1 capture-rate 3–5 (~5–6 soat, 2 commit)
**3a** `feat(cloud): capture-rate qabul va yig'ish — config["capture"], people_seen hisobotda, lentadan tashqarida`
- `cloud/main.py:~6637` (`config["attendance"]` yonida): `config["capture"] = {"enabled": _capture_enabled(site) and not expired}` — yoqish sharti: `person_count` funksiyasi faol va env `ENES_CAPTURE_RATE` o'chirilmagan (standart yoqiq; izohda «faqat yangi cloud tushunadi, shuning uchun bayroq server tomonda»).
- `cloud/event_store.py`: `REPORT_EVENT_TYPES` ga `people_seen`; `TIMELINE_HIDDEN_TYPES` ga `people_seen` (izoh: har 10 daqiqada kamera boshiga bitta, ega uchun hodisa emas); `_retail_report_from_events` `for row` halqasida `kind == "people_seen"` → `seen_by_camera[camera_id] += metadata.seen`; `traffic["seen"] = {"total", "by_camera": {...}}` (eski kunlarda kalit YO'Q — nol emas; `test_retail_rollup.py`).
- `cloud/main.py: _owner_report_dict` → `report["capture"] = value.capture_rate(entered=…, passed=value.select_passed(entrance_seen=<kirish chizig'i bor kamera(lar) seen yig'indisi>, outer_seen=None))` — A2 (`outer`) hozir yo'q, `None` uzatiladi (izoh). `MEDIALESS_EVENTS` ga `people_seen` (rasm/klip so'ralmasin).
- `cloud_feature_revision`: `scripts/bump_feature_revision.py` (server ichida `docker compose exec cloud python …`) — har faol sayt uchun `config["cloud_feature_revision"] += 1` (`main.py:4077` bilan bir xil mantiq, funksiyaga chiqarib ikkalasi ham chaqiradi). Deploydan keyin bir marta.

**3b** `feat(panel,bot): avtomatik konversiya qatori — hisobotda va kunlik xabarda`
- `cloud/digest.py:175` yonida `value.capture_rate_line(...)` — **faqat foiz bo'lsa** (sokin kun xabari qisqa qolsin; `test_owner_report.py`).
- `frontend/src/Numbers.tsx:58-64` qatori «Eshikkacha keldi / kirdi / %» (`panel.numbers.capture_*`, 3 til, `types.ts` `capture?`), `null` da chizilmaydi.
- `docs/DOKON_MVP.md` ga solishtiring: «avtomatik konversiya» sayt va'dasiga QO'SHILMAYDI (pilotda kalibrlanmagan) — faqat panel/xabar.

### Bosqich 4 — Admin panel i18n (~6–8 soat, 2 commit)
`feat(admin): admin paneli uch tilda` — `admin.tsx` + `AdminHome/Team/Settings` (1-commit), `AdminCustomer.tsx` (2-commit). Kalitlar `panel.admin.*` (build_i18n `PANEL_PREFIXES` shartini tekshiring), `scripts/build_i18n.py` → katalog; `t()` modul darajasida chaqirilmaydi (`owner.tsx:24-28` izohi); `test_i18n_surfaces.py` ga admin literal grep testi (`>{[A-Za-z'‘…]` naqshi, ruxsat ro'yxati bilan). Tarjima RU/EN — ega ko'rigi ro'yxatiga qo'shiladi (daftar «Ega ko'rigi»).

### Bosqich 5 — Operatsion (~2 soat kod + ega bilan oyna)
1. **CSP majburiy** (kodda): `deploy/Caddyfile:40` + `Caddyfile.enes:51` `Content-Security-Policy-Report-Only` → `Content-Security-Policy`; `tests/test_security_headers.py:30` `REQUIRED`. Deploydan oldin jonli konsolda CSP xabari yo'qligi (harnes `console.error` hisobi bilan) tekshiriladi; Caddy `--force-recreate`.
2. **`releases/` tozalash** (kodda): `cloud/main.py` `_windows_release_files` yonida `prune_windows_releases(keep=3)` — har prefiks bo'yicha eng yangi 3 juftlik + qurilmalar hali so'rayotgan versiya (`device_health.app_version` dan) saqlanadi; `_maintenance_loop` da kuniga bir marta (yetakchida). `scripts/publish_windows_release.sh` ham nashrdan keyin chaqiradi. Test: manifest'siz `.exe` va eski nom ham o'chadi, joriy pilot versiyasi o'chmaydi.
3. **Ega qiladi (agent qila olmaydi):** UptimeRobot monitorini `https://api.enes.uz/health/deep` ga; `.env.production` ga `ENES_CONTROL_DATABASE_URL` + `ENES_CLOUD_WORKERS=2` (faqat ko'chirishdan KEYIN); oferta rekviziti; Payme/Click kalitlari.
4. **Postgres ko'chirish** — alohida oyna, `docs/PRODUCTION_RUNBOOK.md` §1.1 → §1.2 tartibida (zaxira → `migrate_control_db.py --dry-run` → ko'chirish → env → restart → `/health/deep`). Bu rejaning deploy qadamiga KIRMAYDI; ega tayyor deganda.

### Bosqich 6 — Deploy + jonli tekshiruv + hujjat (~2 soat)
1. `make lint && make test` (ikkala eski test ham yashil, umumiy ~2 350).
2. `.venv/bin/python scripts/ui_qa_screenshots.py` (panel 19 × 3 til × 2 tema × 2 kenglik, `--fail-api`, `--site`) → 0 toshish / 0 xom kalit / 0 konsol / 0 skelet; admin marshrutlari harnesga qo'shiladi (`--routes admin`).
3. Docker frontend bosqichi lokal: `docker build --target frontend-builder -f Dockerfile.cloud .` (tuzoq).
4. rsync (`DEPLOY_TARIFLAR.md` §3 exclude) → `deploy_cloud.sh` → Caddy `--force-recreate` (CSP) → `bump_feature_revision.py` → jonli: 8 host 200, `/api/v1/public/lead` bo'sh telefon bilan → o'qiladigan xato; `curl -sI https://enes.uz | grep -i content-security-policy` (Report-Only emas); `/status` tekshiruvlar ro'yxati; `app.enes.uz/owner` — AI tabi yo'q (Gemini kalitsiz), `/owner/cameras/camera-01/alerts` bitta sarlavha; bot `/` menyusida `chek`; `GET /api/v1/edge/config` (test qurilma tokeni bilan) `capture.enabled: true`.
5. `docs/ISH_DAFTARI.md`: HOZIRGI HOLAT / KEYINGI ISH; TUZOQLAR: «`RequestValidationError` handleri public'da matn qaytaradi», «`releases/` avtomatik tozalanadi — pilot versiyasi saqlanadi», «`capabilities.agent`»; Tarix yozuvi. `docs/AUDIT_TAHLIL.md` jadvalida O-3 ✅ (eskirgan), O-2 ✅.

## Tartib va baho

| Bosqich | Soat | Deploy talab qiladimi |
|---|---|---|
| 0 Qizil testlar, night, /chek, paths | 1.5 | qurilma qismi 0.6.34 relizi bilan; cloud qismi deploy |
| 1 Sayt (1a, 1b) | 6–8 | ✅ |
| 2 Panel (2a, 2b, 2c) | 8–10 | ✅ (Caddy tegilmaydi — CSP hash o'zgarmaydi, boot skript tegilmaydi) |
| 3 A1 cloud (3a, 3b) | 5–6 | ✅ + `bump_feature_revision` |
| 4 Admin i18n | 6–8 | ✅ |
| 5 Ops (CSP, prune) | 2 | ✅ Caddy `--force-recreate` |
| 6 Deploy + docs | 2 | — |
| **Jami** | **~31–38** | |

Tartib: **0 → 1 → 2 → 3 → 5 → 4 → 6** (admin i18n eng katta va eng kam shoshilinch — deploy oldidan oxirgi; agar vaqt yetmasa 4 alohida deployga qoladi va bu daftarga yoziladi).

## Tuzoqlar (buzilmasin)
- **Yangi hodisa turi: AVVAL cloud, KEYIN qurilma** — `people_seen` allaqachon 0.6.33 da bayroq ortida; cloud deploy + revision bump'siz bayroq yonmaydi, bu KUTILGAN. 0.6.33/0.6.34 relizi cloud deploydan keyin.
- CSP hash: panel boot skripti (`owner.html`/`admin.html`) TEGILMAYDI — hash o'zgarmaydi. Tegilsa ikkala Caddyfile + test.
- `TABS`/`LEGACY_ROUTES` literal regexlari — `hidden` prop orqali yashiriladi, ro'yxat o'zgarmaydi. NAV ≤ 8.
- `<nav>` ichida `button` so'zi taqiq (sayt).
- Panel kalitlari `panel.*` prefiksida; `t()` modul darajasida emas.
- Rasm < 200 KB, `-vN` nom; `test_static_pages.py:533` skrinshot nomini qulflaydi.
- Docker frontend bosqichi faqat `frontend/` + `tokens.css` — yangi tashqi import yo'q.
- `RequestValidationError` handleri **faqat** `/api/v1/public/*` uchun matn qaytaradi — edge/owner API'lar strukturali `detail` ni saqlaydi (panel `api.ts:66-91` uni tushunadi).
- `releases/` prune: qurilmalar hali so'rayotgan versiyani o'chirish — pilot yangilanishini uzadi; `device_health` dan o'qilsin.
- Bundle `cloud/static/v2` manba bilan bitta commitda.

## Tekshirish (end-to-end)
- Har commitdan keyin: `make test`; tegishli fayllar: `tests/test_panel_v2.py tests/test_static_pages.py tests/test_site_build.py tests/test_security_headers.py tests/test_status_chain.py tests/test_windows_installer.py tests/test_retail_rollup.py tests/test_owner_report.py -q`.
- Lokal: `make run-cloud` → `/owner` (qora, AI tabi yo'q), `/owner/cameras/camera-01/alerts` (bitta sarlavha), `/admin` API yiqilganda `ErrorStrip` + «Qayta urinish»; zona nomlash o'z oynasida; CSV yuklanadi (Safari ham).
- Sayt: `curl -X POST localhost:8750/api/v1/public/lead -d '{"phone":"1"}' -H 'X-Lang: ru'` → ruscha matnli `detail`; JS o'chiq holatda hero'da yuklab olish matni ko'rinadi; `site.ru.html` futerida o'zbekcha yo'l yo'q.
- Harnes: `scripts/ui_qa_screenshots.py --fail-api` (owner + admin) → 0 skelet; `--site` → 404, menyu, status sahifasi.
- Jonli (Bosqich 6, 4-band).
