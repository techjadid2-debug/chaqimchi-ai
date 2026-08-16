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
| Yuz tanish | Faol scope’da YO‘Q — keyinchalik **cloud** tomonda quriladi |
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
- yuz tanish: mijoz Face ID ham, xodim davomati ham (davomat keyin cloudda);
- uzluksiz videoni cloudga ko‘chirish;
- POS/savdo konversiyasi, shelf/stock va heatmap;
- vendor P2P (faqat lokal tarmoqdagi RTSP/ONVIF bilan ishlaymiz);
- QSV hardware decode va 8 kamera SLA;
- Windows xizmat (service) rejimi — hozircha user sessiyasida ishlaydi.

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
6. Keyingi bosqich: o‘rnatuvchini Authenticode bilan imzolash, Windows
   service rejimi, Box sotuvini qayta ochish, cloud yuz tanish davomati.

## Ochiq qarorlar

- Pilot do‘kon, NVR va to‘rtta kamera modeli/RTSP profili qaysi?
- Qaysi kamera kirish, kassa, savdo zali va ombor rolida bo‘ladi?
- Taqiqlangan zonalar va ish soatlari aniq qanday?
- Telegram alert kimlarga va qaysi severity’dan yuboriladi?
- 72 soat sinovni boshlash sanasi va qabul qiluvchi mas’ul kim?
