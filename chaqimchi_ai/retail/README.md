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

## Ishga tushirish (`service.py`)

Do'kon analitikasi **alohida xizmat**: yuz tanish yiqilsa u ishlashda davom
etadi, teskarisi ham.

```bash
python -m chaqimchi_ai.retail.service --config config/config.yaml
# qurilmada: systemctl start chaqimchi-retail  (deploy/chaqimchi-retail.service)
```

Sozlama `config.yaml` ning `retail:` bo'limida — kameralar, byudjet, buffer
hajmi va qoidalar fayli.

Har kamerada **ikkita manzil**: `stream_url` (substream) tahlil qilinadi,
`record_url` (main) esa klip uchun xom holda yoziladi. Yuqori sifatli oqimni
tahlil qilish N100 uchun juda og'ir bo'lardi. `record_url` berilmasa kamera
klipsiz ishlaydi — hodisa baribir yuboriladi.

Hamma kamera **bitta modelni** bo'lishadi: 8 kameraga 8 model yuklash
xotirani ham, iGPU compile vaqtini ham bekorga sarflardi.

### Ikki xavfsizlik hodisasi

**Kamera buzilishi** (`camera_tampered`, `tamper.py`) — yopilgan, burilgan,
bo'yalgan yoki fokusi buzilgan kamera. Tekshiruv **harakat filtridan oldin**
turadi: yopilgan kamerada harakat yo'q, ya'ni filtr ichida bo'lganda buzilish
hech qachon sezilmasdi va tizim "hammasi joyida" deb ko'rsatib turaverardi.

Model ishlatilmaydi — o'rtacha yorug'lik, Laplacian dispersiyasi va 8×8 imzo
o'rganilgan me'yorga solishtiriladi. Shovqinga qarshi ikki qoida: anomaliya
`tamper_min_duration_sec` davom etishi kerak (kamera oldidan o'tgan odam
hodisa emas) va hodisa **bir marta** chiqadi.

> **Diqqat:** chiroq o'chganda ham kadr qorong'i bo'ladi (IR yorug'ligi
> bo'lmagan kamerada). Buni algoritm ajrata olmaydi — do'kon yopilgandan
> keyingi soatlar uchun qoidaga jadval qo'ying:
>
> ```yaml
> schedules:
>   ish-vaqti: {start: "09:00", end: "21:00"}
> rules:
>   - name: Kamera buzildi
>     event_type: camera_tampered
>     schedule: ish-vaqti
>     severity: critical
>     actions: [save_clip, telegram_alert]
> ```

**Ish vaqtidan tashqari harakat** (`after_hours_presence`) — `open_from` va
`open_to` berilgan bo'lsa, o'sha oynadan tashqarida ko'ringan odam uchun
alohida hodisa chiqadi. Alohida tur kerak, chunki bu boshqa savol: kunduzi
kadrdagi odam — mijoz, kechasi — ogohlantirish. Mijoz panelida ham "Odam
aniqlandi" emas, "Ish vaqtidan tashqari harakat" deb ko'rinadi. Vaqt
berilmasa hodisa umuman chiqmaydi: noto'g'ri vaqt yolg'on signal beradi.

### Hodisa qayerga boradi

Xizmat hodisani mavjud outbox'ga (`data/outbox.db`) yozadi, uni allaqachon
bor cloud sync yuklaydi. Ya'ni bu xizmatga internet, token yoki qayta urinish
mantig'i kerak emas. Telegram xabarini ham cloud yuboradi
(`cloud/notify.py`), shuning uchun `telegram_alert` edge tomonda ikkinchi
Telegram mijozini talab qilmaydi — aks holda mijoz bitta hodisa uchun ikkita
xabar olardi.

Disk kvotasi (40 GB) yozayotgan kameralar orasida **teng bo'linadi**. Har
kamera to'liq kvotani o'ziniki deb bilsa 8 kamera 320 GB talab qilardi —
128 GB disk esa ancha oldin to'lardi.

## Sig'imni o'lchash (`scripts/benchmark_n100.py`)

Sig'im raqamlari (30 inf/s) boshqa modeldan miqyoslangan **taxmin** edi.
Mijozga 8 kamera va'da qilishdan oldin shu skript haqiqiy qurilmada
ishlatilsin:

```bash
python scripts/fetch_retail_model.py            # model + sha256
python scripts/benchmark_n100.py --seconds 120 --cameras 8 \
    --source rtsp://admin:parol@192.168.1.100:554/sub \
    --json releases/n100-benchmark.json
```

Skript to'rtta narsani o'lchaydi va bitta javob beradi — **shu konfiguratsiya
sotilishi mumkinmi**:

| O'lchov | Nima uchun |
|---------|-----------|
| Detektor p50/p95 va tezligi | Byudjet aynan p95 ga qarab target qo'yadi |
| Birinchi va oxirgi uchdan bir | Qurilma qizib sekinlashsa qisqa o'lchov yolg'on |
| Filtr + buzilish tekshiruvi | Har kadrda ishlaydi: 8 kamera × 5 FPS = 40/s |
| Dekodlash (`--source` bilan) | Kadr olishning o'zi ham CPU yeydi |

Xulosa **xom tezlikka emas**, byudjet qabul qiladigan songa asoslanadi
(`0.8 × workers / p95`) — ishlash paytida target aynan shu atrofda turadi.
Zaxira 25% dan kam bo'lsa ham "sotilmasin" deb chiqadi: issiq kunda yoki
og'irroq kadrda byudjet tushadi va kafolat buziladi.

O'lchov qachon yolg'on bo'ladi (skript o'zi ogohlantiradi): sun'iy kadrda
(`--source` bermasangiz), inferens CPU'ga tushib qolganda (iGPU drayveri yo'q)
va 60 soniyadan qisqa ishlaganda.

## Holat

Ochiq bandlar:

- **Benchmark hali ishlatilmagan.** Skript tayyor, lekin haqiqiy N100 da
  o'lchov o'tkazilmagan — shu vaqtgacha 8 kamera va'da qilinmasin.
- Buzilish chegaralari (`dark_ratio`, `blur_ratio`, `change_threshold`)
  boshqa tizimlardan olingan **boshlang'ich** qiymatlar. Haqiqiy obyektda
  kalibrlash kerak; shu sabab hodisa `score` bilan chiqadi.
- Bitta kamera ham yuz tanish, ham analitika uchun kerak bo'lsa oqim ikki
  marta ochiladi (ikki jarayon, ikki dekod). Ataylab: xato ajratilishi shu
  narxga arziydi.
- `config/sotqin.yaml` (`ai_inference: false`) va `docs/SOTQIN.md` ("AI faqat
  cloud'da") retail yo'lidan oldingi holatni aks ettiradi — yangilanishi
  kerak.
