# Vision Agent — kamera dalillari bo'yicha AI yordamchi

Do'kon egasi panelda yoki Telegram botda oddiy Uzbek tilida savol beradi
("Kecha 14 dan 16 gacha kirishda kimdir kirdimi?"), agent esa **faqat
qurilma yuborgan tasdiqlangan eventlar** va ularning saqlangan kadrlari
asosida javob qaytaradi. RTSP oqimi, tracker yoki motion cloudda YO'Q —
ular Edge'da qoladi.

## Arxitektura

1. Savol `vision_jobs` jadvaliga yoziladi (`status=queued`) — panel
   (`/api/v1/owner/agent/queries`), admin yoki Telegram webhook orqali.
2. Worker (`cloud/vision_worker.py`, compose'da `vision-worker` servisi)
   jobni `claim` qiladi: savolni offline Uzbek parser (`parse_query`)
   bilan vaqt/kamera/event turiga ajratadi, `production_events`dan
   qidiradi, eng yangi 3 ta kadrli eventni Gemini vision bilan ko'radi
   (`vision_observations`da keshlaydi), javob yozadi.
3. Panel jobni poll qiladi; Telegram'da javob xabar bo'lib keladi.

Muhim xossalar:

- **Rozilik:** har filial egasi panelda (`AI yordamchi` bo'limi) rozilik
  bermaguncha hech qanday media Gemini'ga yuborilmaydi. Rozilik
  `vision_agent_site_settings`da, kim berganini yozib qo'yamiz.
- **Yuz kadrlari yubORILMAYDI:** `face_captured` eventlari qidiruvdan
  chiqariladi; `employee_seen` faqat yozma rozilik belgisi bilan.
- **Kvota:** filial boshiga kuniga 20 savol; hisob DB'dan (`vision_jobs`
  COUNT) — restart uni nolga tushirmaydi. Bu to'g'ridan-to'g'ri pul
  (Gemini chaqiruvi) himoyasi.
- **Requeue:** worker qulasa `running` joblar 5 daqiqadan keyin qayta
  navbatga olinadi; 3 urinishdan keyin aniq xato bilan yopiladi.
- **Retention:** agent yozuvlari (savol, javob, kuzatuvlar, ovoz
  javoblari) 90 kundan keyin o'chadi; savol audiosi job tugashi bilan
  darhol o'chadi.

## Sozlash

`.env.production`ga (namuna: `.env.production.example`):

```
CHAQIMCHI_GEMINI_API_KEY=...          # Google AI Studio'dan
CHAQIMCHI_GEMINI_VISION_MODEL=...     # aniq stable nom, "latest" emas
# CHAQIMCHI_GEMINI_FALLBACK_MODEL=... # ixtiyoriy zaxira
# CHAQIMCHI_GEMINI_NATIVE_AUDIO_MODEL=...  # ixtiyoriy ovozli javob
```

**Ikkalasi ham shart**: kalit bo'lib model bo'sh qolsa preflight va
lifespan deploy'ni to'xtatadi (aks holda har savol yiqilib kvota yer edi).
Kalit umuman berilmasa agent panelda halol "sozlanmagan" holatda ko'rinadi
va joblar metadata-javob rejimida ishlaydi (Gemini chaqirilmaydi).

Worker `docker-compose.chaqimchi.yml`da alohida servis:
`CHAQIMCHI_VISION_WORKER_IN_APP=0` cloud'da in-app siklni o'chiradi.
Worker `frontend` tarmog'ida bo'lishi SHART (Gemini'ga chiqish uchun).
Boshqa compose fayllarda worker yo'q — u yerda in-app rejim (default `1`)
ishlaydi.

Healthcheck `/tmp/vision-worker.heartbeat` faylining yoshini o'lchaydi;
marker `worker_loop`ning o'zida yangilanadi, ya'ni sikl o'lsa healthcheck
ham yiqiladi.

## Kalit rotatsiyasi

1. Yangi kalitni Google AI Studio'da yarating.
2. `.env.production`da almashtiring.
3. `docker compose ... up -d cloud vision-worker` (ikkalasi ham o'qiydi).
4. Eski kalitni bekor qiling.

## Diagnostika

- Panel savoli abadiy "tekshirilmoqda"da qolsa: worker konteyneri
  ishlayaptimi (`docker compose ps vision-worker`), log'ida
  "ishga tushmadi" xatosi yo'qmi.
- "Gemini javob bermadi": model nomi to'g'riligini va kalit kvotasini
  tekshiring.
- Javob "N ta hodisa topildi" shablonida bo'lsa — eventlarda snapshot
  yo'q (media faqat xavfsizlik hodisalarida saqlanadi) yoki Gemini
  sozlanmagan.
