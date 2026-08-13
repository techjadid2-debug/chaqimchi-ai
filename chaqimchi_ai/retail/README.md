# chaqimchi_ai/retail — do'kon analitikasining edge qismi

## Muammo

8 kamera × 5 FPS = sekundiga **40 ta inferens**. N100 iGPU esa
`person-detection-retail-0013` (2.3 GFLOPs) bilan taxminan **30 tasini**
ulguradi. "Hammasi bir vaqtda" ishlamaydi: navbat cheksiz o'sadi, kechikish
o'nlab sekundga chiqadi va hodisa kech keladi — tizim ishlayotgandek ko'rinib,
aslida foydasiz bo'lib qoladi.

## Yechim

Bitta umumiy byudjet, kameralar uning uchun raqobatlashadi.

```
kamera-01 → motion gate → submit() ┐
kamera-02 → motion gate → submit() ├→ FrameBroker → acquire() → detektor
kamera-08 → motion gate → submit() ┘        ↑                       │
                                     InferenceBudget ←── complete() ┘
                                     (latency o'lchovi)
```

### Uchta qoida

1. **Kredit** — har kamera o'z ulushiga qarab kredit yig'adi va tahlil
   qilinganda sarflaydi. Ulushlar byudjetga normallashtiriladi, ya'ni og'irlik
   mutlaq tezlik emas, **nisbat**.
2. **Ochlik kafolati** — kamera `floor_fps` dan sekinroq ko'rilayotgan bo'lsa,
   kreditdan qat'i nazar navbatni oladi.
3. **Latest-frame-wins** — har kameradan ko'pi bilan bitta kadr kutadi. Navbat
   tabiiy chegaralangan, eskirgan kadr tahlil qilinmaydi.

### Prioritet va kafolat

| Sinf | Og'irlik | Kafolat | Nima uchun |
|------|----------|---------|------------|
| `SECURITY` | 4 | 1.0 FPS | taqiqlangan zona, ish vaqtidan tashqari, kamera yopilishi |
| `RETAIL` | 2 | 0.5 FPS | sanash, navbat, dwell |
| `BACKGROUND` | 1 | 0.1 FPS | heatmap, uzoq muddatli statistika |

Og'irlik harakat miqdoriga ham bog'liq: `og'irlik × (0.5 + 0.5 × motion_score)`.
Kam harakatli kamera yarim og'irlikni saqlaydi — sekin o'g'irlik tez yurishdan
kam muhim emas.

## Ishlatish

```python
from chaqimchi_ai.retail import FrameBroker, InferenceBudget, Priority

budget = InferenceBudget(target_fps=30.0, min_fps=2.0, max_fps=45.0)
broker = FrameBroker(budget)
broker.register("camera-01", priority=Priority.SECURITY, now=time.monotonic())

# Motion gate o'tgan kadr:
broker.submit("camera-01", frame, motion_score=0.7, now=time.monotonic())

# Worker halqasi:
claim = broker.acquire(now=time.monotonic())
if claim is not None:
    started = time.monotonic()
    detections = detector.detect(claim.frame)
    broker.complete(claim.camera_id, latency_sec=time.monotonic() - started,
                    now=time.monotonic())
```

Vaqt **tashqaridan** beriladi (`now`) — testlar soatga bog'lanmasin va natija
takrorlanadigan bo'lsin.

## Muhim cheklovlar

- **Chaqirish chastotasi.** `acquire()` halqasi `burst / target_fps` dan tez
  aylanishi kerak (30 FPS, `burst=2` → 66 ms). Sekinroq bo'lsa to'planmagan
  token yo'qoladi va o'tkazuvchanlik pasayadi. Bu ataylab: ishlatilmagan
  quvvatni yig'ib, keyin qurilmani bir zumda bosib qo'yish mumkin emas.
- **Broker quvvat qo'shmaydi.** Barcha kameraning kafolatlangan minimumi
  byudjetdan katta bo'lsa, u buni yashirmaydi: `floor_violations` va
  `starved_at_capacity` metrikalari o'sadi. Bu "qurilma kam quvvatli" degan
  signal — kamera sonini tushirish yoki kuchliroq apparat kerak.
- **Byudjet o'lchovga tayanadi.** `complete()` chaqirilmasa adaptatsiya
  ishlamaydi va target boshlang'ich qiymatda qotib qoladi.
- **Bosim signali tashqaridan.** CPU/harorat `set_pressure(0..1)` orqali
  beriladi; bu modul o'zi o'lchamaydi.

## Metrikalar

`broker.stats()` → `served`, `dropped`, `rescued`, `floor_violations`,
`starved_at_capacity`, `budget_denied`, `idle_polls` va kamera bo'yicha
tafsilot. `budget` ichida `target_fps`, `p95_latency_ms`, `pressure`.

Ishga tushirishda kuzatiladigan asosiy ikki raqam: **`floor_violations`**
(qurilma yetishmayapti) va **`p95_latency_ms`** (model sekinlashgan).

## Zanjir (`pipeline.py` va `runner.py`)

Yuqoridagi broker — zanjirning bir bo'g'ini. To'liq yo'l:

```
kamera → grab/retrieve → harakat filtri → broker → detektor+analiz → qoida → harakat
   (runner.py)              (pipeline.offer)        (pipeline.step)      │
                                                                        ├→ cloud_sync
                                                                        ├→ telegram_alert
                                                                        └→ save_clip → ring buffer
```

`RetailPipeline` — mantiq (kadr qabul qilish, tahlil, qoida, klip navbati).
`RetailRunner` — o'sha mantiqni qurilmada aylantiruvchi oqimlar. Ikkalasi ham
kamera, ffmpeg va soatsiz sinaladi.

### Uchta halqa, uchta tezlik

| Halqa | Kim chaqiradi | Tezlik | Nima uchun ajratilgan |
|-------|---------------|--------|-----------------------|
| `offer()` | har kameraning o'z oqimi | kameraning FPS'i | filtr arzon, bloklanmasin |
| `step()` | bitta inferens oqimi | `burst/target_fps` dan tez (~66 ms) | byudjet token yo'qotmasin |
| `flush_clips()` | uy ishlari oqimi | 30 soniyada | ffmpeg sekin, byudjetni yemasin |

### Nega dekodlash tejaladi

`grab()` kadrni oladi, `retrieve()` esa dekodlaydi. Kamera 15 FPS bersa ham
tahlilga sekundiga 5 ta kadr yetadi — qolgani dekodlanmasdan tashlanadi. Har
kadrni dekodlash 8 kamerada N100 ning katta qismini yeb qo'yardi.

### Nega klip kechiktiriladi

Hodisa 14:30:00 da bo'lsa klip [14:29:50, 14:30:20] — oxirgi 20 soniya hali
yozilmagan. Darhol kesilsa aynan "keyin nima bo'ldi" degan qism yo'qoladi.
Shuning uchun so'rov navbatga tushadi va `post_sec` o'tgach kesiladi.
**Hodisaning o'zi kutmaydi** — u allaqachon yuborilgan, klip keyin qo'shiladi
(`metadata.clip_path` + `on_clip`).

### Ishlatish

```python
pipeline = RetailPipeline(broker, rules, on_action=send, clip_dir=Path("data/clips"))
runner = RetailRunner(pipeline)
runner.add_camera(
    CameraSource("kassa-01", "rtsp://nvr/sub", priority=Priority.SECURITY,
                 record_url="rtsp://nvr/main", sample_fps=5.0),
    analyzer,
    clips=RingBuffer("kassa-01", Path("data/buffer")),
)
runner.start()
```

`on_action(action, event)` — `cloud_sync` va `telegram_alert` ni chaqiruvchi
bajaradi (mavjud `EventOutbox` va Telegram moduli). `save_clip` ni zanjirning
o'zi bajaradi.

## Holat

Sig'im raqamlari (30 inf/s) boshqa modeldan miqyoslangan **taxmin**, o'lchov
emas. `scripts/benchmark_n100.py` (T1.10) haqiqiy qurilmada tasdiqlamaguncha
8 kamera sotilmasin.

Zanjir **ishga tushirilmagan**: uni qaysi jarayon boshlashi (alohida xizmatmi
yoki mavjud webapp ichidami) hal qilinmagan — mavjud `CameraManager` o'sha
kameralarni yuz tanish uchun allaqachon ochadi va ikkalasi bir vaqtda ishlasa
oqim ikki marta dekodlanadi.
