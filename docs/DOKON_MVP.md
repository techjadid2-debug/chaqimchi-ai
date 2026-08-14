# Do‘kon MVP — canonical kontrakt va joriy holat

Sana: 2026-08-13. Bu hujjat mahsulot bo‘yicha yagona faol qaror manbasi.
Eski Orange Pi, umumiy Face platforma va taxminiy tarif hujjatlari arxiv.

## Mahsulot qarori

| Qaror | Canonical qiymat |
|---|---|
| Mijoz | Do‘kon |
| Pilot | 1 do‘kon, 4 kamera |
| Edge | Sotqin R1: Intel N100, 8 GB RAM, 128 GB NVMe |
| Video | To‘liq arxiv NVR’da; Sotqin faqat event buffer/klip |
| Kamera ulash | Admin panelda qo‘lda RTSP/NVR substream |
| AI | Odam deteksiyasi/tracking lokal; event/hisobot/alert cloud |
| Davomat | Rozilikli xodim, embedding faqat edge’da, bepul yopiq pilot |
| Tijoriy Face | Commercial model bundle tasdiqlanmaguncha yopiq |

## MVP’da bor

- Verifikatsiya qilingan OpenVINO `person-detection-retail-0013` modeli;
- motion gate, inference budget, tracking, line crossing, occupancy, dwell va
  queue hodisalari;
- kamera tamper, after-hours person, restricted zone va loitering;
- qoida engine, cooldown, snapshot va pre/post event MP4 klip;
- offline SQLite outbox, cloud replay, tenantga ajratilgan media;
- admin provisioning, pairing, encrypted RTSP inventari, heartbeat va config
  ACK/NACK;
- owner statistikasi, trend, kamera rollari, line/zone/ish vaqti sozlamasi,
  Telegram alert/digest;
- xodim CRUD, haftalik jadval, keldi-ketdi/kechikish/erta ketish, CSV;
- lokal yuz enrollment/delete; embedding va davomat snapshoti cloudga
  chiqmaydi;
- installer control + retail + attendance xizmatlarini va modelni o‘rnatadi;
- public katalogda faqat `person_count`, `queue_length`, `store_security`.

## Kod bor, lekin hali real qurilmada qabul qilinmagan

- 4 kamerali N100 sig‘imi va termal barqarorlik;
- 72 soatlik elektr/internet/kamera uzilishi soak testi;
- real do‘konlarda line/queue/tamper/loitering aniqlik kalibratsiyasi;
- end-to-end production installer va rollback sinovi;
- davomat false accept/recall va ikki kamera arrival/departure sinovi.

Shu besh band tugamaguncha saytdagi funksiyalar production’da sotuvga
ochilmaydi. `CHAQIMCHI_AVAILABLE_FEATURES` ning o‘zi yetarli emas:
`CHAQIMCHI_N100_ACCEPTANCE_FILE` ham tekshiruvdan o‘tishi shart.

## MVP’da yo‘q

- o‘g‘rilik, jinoyatchi yoki “shubhali niyat” klassifikatsiyasi;
- mijozlarni yuz orqali tanish yoki qora ro‘yxat;
- uzluksiz videoni cloudga ko‘chirish;
- POS/savdo konversiyasi, shelf/stock va heatmap;
- ONVIF discovery, vendor P2P va avtomatik NVR kanal importi;
- QSV hardware decode va 8 kamera SLA;
- pullik davomat — commercial yuz modeli litsenziyasigacha.

## Davomat maxfiylik kontrakti

Owner cloud panelda xodim ismi, tabel ID, yozma rozilik va haftalik jadvalni
yaratadi. Enrollment Sotqinning lokal panelida bajariladi. Cloudga faqat
xodim UUID, canonical ism, jadval, first/last seen va hisoblangan status
boradi. Foto, embedding va lokal fayl yo‘li chiqmaydi. Xodim o‘chirilsa keyingi
config reconcile’da lokal embedding ham o‘chadi.

Davomat kamerasi `Kelish`, `Ketish` yoki `Ikkalasi` rolida belgilanadi.
Checkout missing faqat smena tugagach ketish kamerasi hodisasi bo‘lmasa
chiqadi; oddiy ketma-ket matchlar “ketdi” deb noto‘g‘ri hisoblanmaydi.

Production’da ikki rejimdan bittasi shart:

1. `CHAQIMCHI_ATTENDANCE_PILOT=true`, bepul yopiq pilot, snapshotlar o‘chiq;
2. `CHAQIMCHI_FACE_MODEL_LICENSED=true` va SHA256 bilan tekshiriladigan
   commercial model manifesti.

## Qabul mezoni

`scripts/accept_n100_pilot.py` quyidagilarni tekshiradi:

- benchmark Intel GPU’da, haqiqiy do‘kon videosida va kamida 60 soniya;
- verdict 4 kamera uchun warning’siz `ok`;
- soak kamida 72 soat va eng kam faol kamera soni 4;
- kamera uptime kamida 99%, kutilmagan restart va yo‘qolgan critical event 0;
- maksimal harorat 85°C dan oshmagan.

Soak hisoboti qurilmada qo'lda tuzilmaydi:

```bash
sudo /opt/chaqimchi/venv/bin/python /opt/chaqimchi/current/scripts/soak_n100.py \
  --hours 72 --output soak-72h.json
```

Soak hisoboti JSON maydonlari:

```json
{
  "duration_hours": 72.1,
  "cameras_min_active": 4,
  "unexpected_restarts": 0,
  "camera_uptime_percent": 99.5,
  "max_temperature_c": 78.0,
  "undelivered_critical_events": 0
}
```

## Qolgan ishlar tartibi

1. Sotqin R1 ga release o‘rnatish va 4 ta haqiqiy RTSP substream ulash.
2. Kamera rollari, line, restricted zone, queue va ish vaqtini kalibrlash.
3. Haqiqiy videoda benchmark, keyin 72 soat soak; qabul artefaktini yaratish.
4. Bitta do‘konda har hodisani owner panel/Telegram/klipgacha E2E tekshirish.
5. Yozma rozilikli 3–5 xodim bilan attendance pilot va CSVni qabul qilish.
6. Natija o‘tgach uch public feature’ni ochish; 8 kamera yoki yangi funksiyani
   faqat alohida o‘lchovdan keyin qo‘shish.

## Ochiq qarorlar

- Pilot do‘kon, NVR va to‘rtta kamera modeli/RTSP profili qaysi?
- Qaysi kamera kirish, kassa, savdo zali va ombor rolida bo‘ladi?
- Taqiqlangan zonalar va ish soatlari aniq qanday?
- Telegram alert kimlarga va qaysi severity’dan yuboriladi?
- 72 soat soak’ni boshlash sanasi va qabul qiluvchi mas’ul kim?
- Davomat pilotidagi xodimlar rozilik shakli va retention siyosati qanday?
