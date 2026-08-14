# Ko‘rish agenti — AI kadrni ko‘rib tushuntiradi

> **ARXIV / faol MVP emas.** Canonical do‘kon xavfsizligi faqat kamera tamper,
> after-hours person, restricted zone va loitering hodisalaridan iborat.
> `vision.enabled: false`; bu modul taxminiy niyat yoki “shubhali xatti-harakat”
> sifatida sotilmaydi va `config/rules.yaml` undan foydalanmaydi.

Yuz tanish **“bu kim?”** degan savolga javob beradi. Ko‘rish agenti boshqa
savolga: **“nima bo‘layapti?”**

| Yuz tanish | Ko‘rish agenti |
|------------|----------------|
| Bazadagi odamni taniydi | Sahnani tushunadi |
| Mini PC da ishlaydi, bepul | Internet orqali AI ga so‘rov, **pullik** |
| Millisekundlarda | 3–10 soniya |
| Baza kerak | Baza kerak emas |

Nimani ko‘radi: kassada navbat, yiqilgan odam, janjal, tutun, ish vaqtidan
tashqari harakat, ombor oldida shubhali xatti-harakat.

---

## ⚠️ Eng muhimi: bu pul sarflaydi

Har tahlil Anthropic hisobingizdan pul yechadi. **Kamera sekundiga 25 kadr
beradi** — ularning hammasini yuborish oyiga o‘n minglab dollar bo‘lardi.
Shuning uchun modul ikki qavatli tormoz bilan yozilgan:

1. **Har kadrda emas.** Bitta kamera uchun ikki tahlil orasida kamida
   `min_interval_sec` (standart **5 daqiqa**) o‘tishi shart.
2. **Qattiq limit.** Kunlik va oylik chaqiruvlar soni cheklangan. Limit tugasa
   modul **butunlay to‘xtaydi**. Hisob diskda saqlanadi — serverni qayta
   ishga tushirib limitni aylanib o‘tib bo‘lmaydi.

Standart sozlama: kuniga **100 tahlil**, oyiga **2000**.

---

## Narx (o‘lchangan, taxmin emas)

Hisob `chaqimchi_ai/vision_agent.py` ichida: `claude-opus-5` uchun
1M kirish token = $5, 1M chiqish token = $25. Quyidagi jadval 1 dollar ≈
**12 900 so‘m** kursida (kurs o‘zgarsa raqamni qayta hisoblang).

### Bitta tahlil

| Kadr o‘lchami | Rasm tokeni | Narx | So‘mda |
|---------------|-------------|------|--------|
| 512px | 196 | $0.0055 | ~71 so‘m |
| **768px (standart)** | **442** | **$0.0068** | **~87 so‘m** |
| 1024px | 786 | $0.0085 | ~109 so‘m |
| 1920px (to‘liq HD) | 2764 | $0.0184 | ~237 so‘m |

Kadrni kichraytirish — narxni tushirishning eng kuchli usuli. Do‘kondagi
sahnani tushunish uchun 768px yetarli; to‘liq HD uch barobar qimmat.

### Oylik

| Kuniga | Oyiga | So‘mda |
|--------|-------|--------|
| 20 tahlil | $4.06 | ~52 000 so‘m |
| 50 tahlil | $10.14 | ~131 000 so‘m |
| **100 tahlil** | **$20.28** | **~262 000 so‘m** |
| 200 tahlil | $40.56 | ~523 000 so‘m |
| 500 tahlil | $101.40 | ~1 308 000 so‘m |

### Tarifga ta’siri

Bu **eng muhim raqam**: AI xarajati mijozdan olayotgan puldan qancha yeydi.

| Tarif | Oylik narx | AI (kuniga 100) | Daromaddan |
|-------|-----------|-----------------|------------|
| Starter | 790 000 so‘m | ~131 000 (kuniga 50) | **16.6%** |
| Business | 1 490 000 so‘m | ~262 000 (kuniga 100) | **17.6%** |
| Enterprise | 2 990 000 so‘m | ~523 000 (kuniga 200) | **17.5%** |

**Xulosa:** hozirgi tariflarga AI ni tekin qo‘shib bo‘lmaydi — foydangizning
oltidan biri ketadi. Uchta yo‘l bor:

1. **Alohida qo‘shimcha sifatida soting** — masalan “AI kuzatuv: +490 000
   so‘m/oy”. Eng toza yechim.
2. **Faqat Enterprise ga kiriting** va narxni ko‘taring.
3. **Limitni past qo‘ying** (kuniga 20–30) va “kunlik xulosa” sifatida bering
   — oyiga ~52 000 so‘m, bu tarifga sig‘adi.

Narxni o‘zingiz hisoblang:

```bash
python -c "
from chaqimchi_ai.vision_agent import estimate_monthly_usd
print(estimate_monthly_usd(calls_per_day=50, max_side=768) * 12900, 'so\'m/oy')
"
```

---

## Yoqish

```bash
pip install -r requirements-optional.txt   # anthropic kutubxonasi
export ANTHROPIC_API_KEY="sk-ant-..."
```

`config/config.yaml`:

```yaml
vision:
  enabled: true
  model: claude-opus-5
  max_side: 768            # kadr o'lchami — narxning asosiy sozlamasi
  min_interval_sec: 300    # bitta kamera uchun 5 daqiqada bir marta
  max_calls_per_day: 100
  max_calls_per_month: 2000
  effort: low              # low | medium | high — murakkab sahnaga medium
  telegram_alerts: true
```

`enabled: false` bo‘lsa modul umuman qurilmaydi va bir tiyin ham sarflanmaydi.

---

## Kameraga ulash (avtomatik ko‘rik)

`enabled: true` o‘zi hech narsa qilmaydi — u faqat modulni yoqadi. Kamera
oldida turgan AI hech qachon “o‘zi qaraydigan” bo‘lmasligi kerak: 8 kamera ×
sutkasiga 24 soat = oyiga minglab dollar. Shuning uchun chegara boshqacha
qo‘yilgan:

> **Qurilmadagi arzon model “nimadir bo‘ldi” deb topadi, qimmat model esa
> faqat o‘sha lahzani ko‘radi.**

Ya’ni ko‘rik do‘kon analitikasi hodisasidan **keyin** boshlanadi va uni
qoida so‘raydi (`config/rules.yaml`):

```yaml
rules:
  - name: Kamera buzilishi
    event_type: camera_tampered
    severity: critical
    cooldown_sec: 600
    actions: [cloud_sync, telegram_alert, save_clip, ai_review]
```

`ai_review` — kadrni ko‘rish agentiga yuborish. Yo‘l:

```
kamera → odam deteksiyasi → qoida → ai_review → AI → outbox → cloud → Telegram
                                                (alohida oqim)
```

Nima uchun alohida oqim: AI javobi 3–10 soniya oladi. Uni inferens halqasida
kutish o‘sha vaqtda **hamma** kamerani to‘xtatib qo‘yardi — navbat, dwell,
kirish-chiqish sanog‘i, hammasi. Shuning uchun kadr navbatga tushadi va
analitika ishlashda davom etadi. AI yiqilsa yoki tarmoq uzilsa analitika
sezmaydi ham.

### Uch qavatli tormoz

| Qavat | Nima cheklaydi | Qayerda |
|-------|----------------|---------|
| Qoida | Qaysi hodisa umuman ko‘rikka arziydi | `rules.yaml` — `ai_review` standart harakatlar ichida **yo‘q** |
| Oraliq | Bitta kamera uchun 5 daqiqada bir marta | `vision.min_interval_sec` |
| Limit | Kunlik va oylik chaqiruvlar soni | `vision.max_calls_per_day/month`, hisob diskda |

Oraliq **navbatga qo‘yishda** boshlanadi, javob kelganda emas. Sabab: AI sekin
javob berayotganda o‘nlab hodisa o‘tib ketishi mumkin va ularning har biri
yangi chaqiruv bo‘lardi.

Qaysi qoidaga `ai_review` qo‘yish kerak — amaliy tavsiya:

| Hodisa | AI kerakmi | Nega |
|--------|-----------|------|
| `camera_tampered` | ✅ ha | “Qop bilan yopilgan” va “chiroq o‘chgan” — ikki xil muammo |
| `after_hours_presence` | ✅ ha | Qorovulmi yoki begonami — raqam aytmaydi |
| `queue_threshold_exceeded` | ❌ yo‘q | “6 kishi navbatda” — raqamning o‘zi yetarli |
| `line_crossed`, `person_detected` | ❌ yo‘q | Kuniga minglab marta; hisob bir kunda tugaydi |

### Xulosa qayerga boradi

AI xulosasi yangi `ai_review` hodisasi bo‘lib outboxga tushadi va oddiy yo‘ldan
cloudga, u yerdan Telegramga ketadi. Mijoz “AI ko‘rdi — kassa-01” emas, aynan
**jumla** oladi:

```
🔴 2 ta ogohlantirish
• Kamera yopildi yoki burildi — ombor-02
• AI ko'rdi — ombor-02
   ↳ Kamera oldiga karton quti qo'yilgan, ko'rinish to'sib qo'yilgan
```

`ogohlantirish: false` bo‘lsa hodisa `info` bo‘lib qoladi: arxivda turadi,
lekin telefon jiringlamaydi. AI “hammasi joyida” deganini bilish kerak, lekin
uni xabar qilib yuborish shovqin.

Bitta istisno: manba hodisasi `critical` bo‘lsa (kamera yopilgan), AI uni
pasaytira olmaydi. Model xato qilishi mumkin, buzilgan kamera esa fakt.

### Kuzatish

Xizmat logida har 30 soniyada:

```
AI ko'rigi: 4 ta xulosa, $0.0312 | o'tkazib yuborilgan: oraliq=11 limit=0 navbat=0 xato=1
```

`oraliq` — tormoz ishlayapti (normal holat). `limit` noldan katta bo‘lsa
kunlik hisob tugagan. `navbat` — AI ulgurmayapti. `xato` — tarmoq yoki kalit.

**Cloud avval yangilansin.** `ai_review` yangi hodisa turi; eski cloud uni
tanimaydi va butun batchni rad etadi.

---

## Ishlatish

```bash
# Holat va sarf
curl http://127.0.0.1:8742/api/vision/status

# Rasmni tahlil qilish
curl -X POST http://127.0.0.1:8742/api/vision/analyze \
  -H "X-API-Key: $CHAQIMCHI_API_KEY" \
  -F "file=@kadr.jpg" \
  -F "camera_id=Kirish-1" \
  -F "question=Kassada necha kishi navbatda?"

# Oxirgi tahlillar va ularning narxi
curl http://127.0.0.1:8742/api/vision/recent
```

Javob:

```json
{
  "ok": true,
  "tavsif": "Kassada ikki xaridor navbatda turibdi, xodim ishlayapti.",
  "odamlar": 3,
  "ogohlantirish": false,
  "sabab": "",
  "cost_usd": 0.0068,
  "latency_ms": 4210
}
```

| Endpoint | Vazifa |
|----------|--------|
| `GET /api/vision/status` | Sozlama, sarf, limitdan qolgani |
| `GET /api/vision/recent` | Oxirgi tahlillar va narxi |
| `POST /api/vision/analyze` | Rasmni tahlil qilish (API kalit) |

---

## Yolg‘on ogohlantirishga qarshi

`ogohlantirish` faqat do‘kon egasi **darhol** bilishi kerak bo‘lgan holatda
rost bo‘ladi: yiqilgan odam, janjal, tutun, ish vaqtidan tashqari harakat.
Oddiy holat — xaridor yuribdi, navbat bor, xodim ishlayapti — ogohlantirish
emas.

Bu qasddan shunday: kuniga o‘nta yolg‘on ogohlantirish olgan do‘kon egasi
o‘n birinchisini o‘qimaydi, va o‘sha o‘n birinchisi haqiqiy bo‘lishi mumkin.

---

## Chegaralari — ochiq aytamiz

- **Bu doimiy kuzatuv emas.** 5 daqiqada bir kadr ko‘radi; ular orasida nima
  bo‘lganini bilmaydi. O‘g‘irlik 10 soniyada bo‘lsa — o‘tkazib yuboradi.
- **Bitta kadr ko‘radi, klipni emas.** Hodisa videosi saqlanadi
  (`save_clip`), lekin AI ga faqat bitta kadr ketadi — video yuborish bir
  necha barobar qimmat. Ya’ni “nima bo‘lganini” emas, “ayni damda nima
  ko‘rinayotganini” aytadi.
- **Internetga bog‘liq.** Aloqa uzilsa ishlamaydi (yuz tanish ishlaydi —
  u lokal).
- **Sekin.** 3–10 soniya. Real vaqt qaror uchun emas.
- **Xato qilishi mumkin.** Bir kadrni ko‘rib turib xulosa qiladi; kontekstni
  bilmaydi. Muhim qaror uchun odam tasdiqlashi kerak.
- **Kadr AI serveriga yuboriladi.** Mijozga buni **oldindan ayting** —
  yuz tanishdan farqli o‘laroq, bu yerda tasvir do‘kondan tashqariga chiqadi.
  Shartnomada yozilsin.
