# Threshold kalibrlash

> Do‘kon MVP’da bu faqat rozilikli xodim attendance piloti uchun lokal
> kalibrlash. Lokal servis manzili `127.0.0.1:8743`.

## 1. Ma’lumotlar bazasi (tez)

Kamida **2 ta** ro‘yxatdan o‘tgan shaxs bo‘lsin. Tizim boshqa shaxslar bilan kosinus ballarini “manfiy” deb hisoblaydi va `p95 + margin` asosida threshold tavsiya qiladi.

```bash
curl http://127.0.0.1:8743/api/calibrate/threshold
```

yoki:

```bash
python scripts/calibrate_threshold.py
```

`config.yaml` da yangilash:

```yaml
face:
  compare_threshold: 0.42  # tavsiya qiymati
```

## 2. Calibration papkasi (aniqroq)

Struktura:

```
data/calibration/
  Abdulvosit/
    img1.jpg
    img2.jpg
  Boshqa/
    a.jpg
```

```bash
python scripts/calibrate_threshold.py --dir
curl "http://127.0.0.1:8743/api/calibrate/threshold?use_dir=true"
```

Bir papkada bir nechta surat → musbat juftlar; turli papkalar → manfiy juftlar.

## API kalit

```yaml
security:
  api_key_enabled: true
```

Muhit:

```bash
export CHAQIMCHI_API_KEY="maxfiy-kalit"
```

So‘rovlar:

```bash
curl -H "X-API-Key: maxfiy-kalit" -F "name=Ali" -F "file=@photo.jpg" \
  http://127.0.0.1:8743/api/persons/add
```

O‘qish (health, events, calibrate) ochiq qoladi; qo‘shish/o‘chirish himoyalangan.
