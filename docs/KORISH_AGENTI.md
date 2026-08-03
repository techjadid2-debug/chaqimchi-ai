# Ko‘rish agenti — AI kadrni ko‘rib tushuntiradi

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
- **Internetga bog‘liq.** Aloqa uzilsa ishlamaydi (yuz tanish ishlaydi —
  u lokal).
- **Sekin.** 3–10 soniya. Real vaqt qaror uchun emas.
- **Xato qilishi mumkin.** Bir kadrni ko‘rib turib xulosa qiladi; kontekstni
  bilmaydi. Muhim qaror uchun odam tasdiqlashi kerak.
- **Kadr AI serveriga yuboriladi.** Mijozga buni **oldindan ayting** —
  yuz tanishdan farqli o‘laroq, bu yerda tasvir do‘kondan tashqariga chiqadi.
  Shartnomada yozilsin.
