# Do‘kon MVP — canonical kontrakt va joriy holat

Sana: 2026-08-16. Bu hujjat mahsulot bo‘yicha yagona faol qaror manbasi.
Eski Orange Pi, umumiy Face platforma va taxminiy tarif hujjatlari arxivda;
lokal Face ID davomat to‘plami ham arxivlandi
(`git tag archive/attendance-local`).

## Mahsulot qarori

| Qaror | Canonical qiymat |
|---|---|
| Mijoz | Do‘kon |
| Pilot | 1 do‘kon, 4 kamera (yagona manba: `chaqimchi_ai/limits.py`) |
| Asosiy qurilma | **Mijozning mavjud Windows 10/11 kompyuteri** (`Chaqimchi_AI_Setup.exe`) |
| Keyingi bosqich | Chaqimchi Box — Sotqin R1: Intel N100, 8 GB, 128 GB NVMe (kod tayyor, sotuv fokusda emas) |
| Video | To‘liq arxiv NVR’da; qurilma faqat event buffer/klip |
| Kamera ulash | Sozlash ustasi: ONVIF qidiruv, NVR kanal skaneri yoki qo‘lda RTSP; admin panelda masofadan ham kiritish mumkin |
| AI | Odam deteksiyasi/tracking lokal (OpenVINO, CPU; yaroqli iGPU bo‘lsa GPU); event/hisobot/alert cloud |
| Xodim davomati (Face ID) | Lite ichida, **10 xodimgacha**, hozircha tekin. Qurilma yuzni tanimaydi — kadrni kesib yuboradi, tanish cloudda |
| Panelga kirish | Kirish havolasi (`?key=`, admin/bot beradi) yoki Telegram OTP; parolli portal akkauntlar |

## MVP’da bor

- Verifikatsiya qilingan OpenVINO `person-detection-retail-0013` modeli;
- motion gate, inference budget, tracking, line crossing, occupancy, dwell va
  queue hodisalari;
- kamera tamper, after-hours person, restricted zone va loitering;
- qoida engine, cooldown, snapshot va pre/post event MP4 klip;
- offline SQLite outbox, cloud replay, tenantga ajratilgan media;
- Windows o‘rnatuvchi: Keyingi→Keyingi→Tayyor, pairing kod fayl nomidan,
  sozlash ustasi (ONVIF/NVR skaner), imzolangan OTA (15 daqiqa tekshiruv,
  faqat yangiroq versiya, avto-rollback);
- admin provisioning, pairing, encrypted RTSP inventari, heartbeat va config
  ACK/NACK, per-site update policy (auto/hold/pin);
- owner statistikasi, trend, kamera rollari, line/zone/ish vaqti sozlamasi,
  Telegram alert/digest, kirish havolasi;
- cloud o‘z-o‘zini kuzatishi: qurilma offline/kamera yo‘qolishi alertlari,
  server disk alerti, site boshiga media kvotasi, kunlik shifrlangan backup.

## Kod bor, lekin hali real qurilmada qabul qilinmagan

- 4 kamerali sig‘im bahosi real i5-4590 da o‘lchov bilan tasdiqlanmagan
  (`chaqimchi_ai/local/hardware.py` dagi `INFERENCES_PER_CORE=8.0` — taxmin);
- 72 soatlik elektr/internet/kamera uzilishi barqarorlik sinovi;
- real do‘konlarda line/queue/tamper/loitering aniqlik kalibratsiyasi;
- Windows OTA rollback stsenariysining real qurilmada sinovi;
- N100 Box yo‘li uchun benchmark/soak (Box keyingi bosqichga qoldirilgan).

Shu bandlar tugamaguncha saytdagi funksiyalar production’da sotuvga
ochilmaydi. `CHAQIMCHI_AVAILABLE_FEATURES` ning o‘zi yetarli emas:
`CHAQIMCHI_N100_ACCEPTANCE_FILE` ham tekshiruvdan o‘tishi shart.

## MVP’da yo‘q

- o‘g‘rilik, jinoyatchi yoki “shubhali niyat” klassifikatsiyasi;
- mijoz Face ID (do‘konga kirgan xaridorni tanish) — faqat xodim davomati bor;
- uzluksiz videoni cloudga ko‘chirish;
- POS/savdo konversiyasi, shelf/stock va heatmap;
- vendor P2P (faqat lokal tarmoqdagi RTSP/ONVIF bilan ishlaymiz);
- QSV hardware decode va 8 kamera SLA;

## Xodim davomati (Face ID)

Do‘kon egasi `app.chaqimchi.uz` → **Xodimlar** bo‘limida xodimini o‘zi
qo‘shadi va rasmini telefon kamerasidan oladi (1–3 rasm). Kamera uni
tanib, kelgan-ketgan vaqtini yozib boradi; jadval "Bugun"/"Shu oy" va CSV
bo‘lib chiqadi.

| Nima | Qiymat |
|---|---|
| Chegara | 10 xodim (`plans.py: lite.max_persons`) |
| Narx | hozircha tekin |
| Qaysi kamera | mijoz panelda o‘zi tanlaydi, ko‘pi bilan 2 ta |
| Rasm | brauzerda JPEG ga aylantiriladi (iPhone HEIC beradi), ≤ 2 MB |
| Biometrika | embedding Fernet bilan shifrlanadi; xodim ro‘yxatdan
chiqarilsa rasm ham, embedding ham o‘chadi; yuz kadri 14 kun yashaydi |

**Litsenziya bandi YOPILDI (2026-08-21).** Modellar OpenVINO Open Model
Zoo'ga ko'chirildi va uchalasi ham **Apache-2.0** — tijoratga ochiq:

| Vazifa | Model | Kirish → chiqish |
|---|---|---|
| Yuzni topish | `face-detection-retail-0005` | 300×300 BGR → SSD |
| Tayanch nuqta | `landmarks-regression-retail-0009` | 48×48 BGR → 5 nuqta |
| Embedding | `face-reidentification-retail-0095` | 128×128 BGR → **256** |

URL va sha256 — `models/faces_manifest.json`; o'rnatish —
`scripts/fetch_face_models.py`.  Litsenziya endi env sozlamasi emas,
koddagi fakt (`cloud/faces.py: MODELS_LICENSED_FOR_COMMERCIAL_USE`) —
ilgari `CHAQIMCHI_FACE_MODEL_LICENSED` bayrog'ini noto'g'ri qo'yish
tadqiqot modelini "tijoriy" qilib ko'rsatib qo'yardi.

**Bir martalik migratsiya:** yangi model 256 o'lchamli vektor beradi,
eskisi 512 — mavjud xodim rasmlari qayta hisoblanishi shart
(`scripts/reembed_faces.py`).  Hisoblanmagan yozuv moslashga umuman
qo'shilmaydi; log ogohlantiradi.

**Chegara:** standart 0.6 (`CHAQIMCHI_FACE_MATCH_THRESHOLD`).  Sinovda
boshqa odam 0.01, bir xil odam buzilgan rasmda 0.67–0.98.  Haqiqiy
do'kon kadrlarida qayta o'lchash —
`scripts/calibrate_face_threshold.py`.

## Qabul mezoni

### Windows yo‘li (asosiy)

Sotuvga ochishdan oldin real do‘kon kompyuterida:

- 4 kamera bilan **72 soat** uzluksiz ishlash: kutilmagan restart 0,
  yo‘qolgan critical event 0, kamera uptime ≥ 99%;
- kunlik kirish soni qo‘lda sanash bilan solishtirilganda ±10% ichida;
- hodisa klipi cloudga yetib borishi va owner panelda ochilishi;
- OTA yangilanish (test relizi bilan) muvaffaqiyatli o‘tishi.

Natija qabul JSON fayliga yoziladi va `CHAQIMCHI_N100_ACCEPTANCE_FILE`
orqali ulanadi (fayl nomi tarixiy — mexanizm bitta).

Amalda:

```bash
# 1. Sig'imni o'lchash (RTSP manzili haqiqiy kameradan)
python scripts/benchmark_n100.py --device CPU --source rtsp://... \
  --seconds 300 --cameras 4 --json benchmark-windows.json

# 2. 72 soat kuzatish (do'kon kompyuterida, fon rejimida)
python scripts/soak_windows.py --hours 72 --cameras 4 \
  --output soak-windows.json --samples-file soak-samples.jsonl

# 3. Qabul fayli — uchta maydonni odam tasdiqlaydi
python scripts/accept_n100_pilot.py --platform windows \
  --benchmark benchmark-windows.json --soak soak-windows.json \
  --daily-count-delta 4.2 --clip-delivered --ota-ok \
  --approved-by "Ism" --output acceptance-windows.json
```

Windows profili (`CHAQIMCHI-WINDOWS-W1`) N100 dan **faqat ikki joyda**
farq qiladi: benchmark CPU'da bo'lishi mumkin (do'kon kompyuterlarining
iGPU'si odatda OpenVINO uchun yaroqsiz) va harorat o'lchanmasligi mumkin
(Windows uni bermaydi).  Qolgan hamma mezon bir xil, chunki mijozga
beriladigan va'da bir xil.

### Box / N100 yo‘li (keyingi bosqich)

`scripts/accept_n100_pilot.py` tekshiradi: benchmark Intel GPU’da, haqiqiy
do‘kon videosida ≥ 60 soniya; verdict 4 kamera uchun warning’siz `ok`; soak
≥ 72 soat, uptime ≥ 99%, restart 0, harorat ≤ 85°C. Soak hisobotini
`scripts/soak_n100.py` tuzadi.

## Qolgan ishlar tartibi

1. Jonli Windows qurilmada 4 ta haqiqiy RTSP substream bilan to‘liq oqimni
   tekshirish (hodisa → snapshot → klip → owner panel → Telegram).
2. `INFERENCES_PER_CORE` ni real i5-4590 da bir marta o‘lchash va
   `hardware.py` ni o‘lchovga bog‘lash.
3. Kamera rollari, line, restricted zone, queue va ish vaqtini kalibrlash.
4. 72 soat barqarorlik sinovi va qabul artefaktini yaratish.
5. Natija o‘tgach public feature’larni ochish (`person_count`,
   `queue_length`, `store_security`).
6. Keyingi bosqich: o‘rnatuvchini Authenticode bilan imzolash, Box
   sotuvini qayta ochish.

Bajarildi (0.6.8): nazorat kompyuter yonganda avtomatik ishga tushadi —
rejalashtirilgan vazifa, SYSTEM nomidan, tizimga kirish shart emas
(`docs/INSTALLER.md`, "Avtomatik ishga tushish qanday ishlaydi").

## Ochiq qarorlar

- Pilot do‘kon, NVR va to‘rtta kamera modeli/RTSP profili qaysi?
- Qaysi kamera kirish, kassa, savdo zali va ombor rolida bo‘ladi?
- Taqiqlangan zonalar va ish soatlari aniq qanday?
- Telegram alert kimlarga va qaysi severity’dan yuboriladi?
- 72 soat sinovni boshlash sanasi va qabul qiluvchi mas’ul kim?
