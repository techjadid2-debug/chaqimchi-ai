# Chaqimchi AI — do‘kon MVP

Chaqimchi AI hozir **Intel N100 Sotqin R1 + NVR/IP kamera + Cloud** sifatida
faqat do‘konlar uchun qurilmoqda. Birinchi qabul profili — bitta do‘kon va
ko‘pi bilan **4 kamera**. Uzluksiz video NVR’da qoladi; Sotqin lokal tahlil
qiladi, cloudga esa hodisa, ruxsat etilgan media, hisobot va health yuboriladi.

Canonical mahsulot kontrakti va joriy holat:
[docs/DOKON_MVP.md](docs/DOKON_MVP.md). Qurilma tafsiloti:
[docs/SOTQIN.md](docs/SOTQIN.md).

## MVP doirasi

- odam kirishi/chiqishi, bandlik, navbat va zonada turish;
- kamera yopilishi/burilishi, ish vaqtidan tashqari odam, taqiqlangan zona va
  uzoq turish;
- owner panel, Telegram alert/digest, CSV, offline outbox va event klip;
- yozma rozilikli xodimlar uchun lokal davomat Face ID — hozircha faqat
  **bepul yopiq pilot**.

Tizim o‘g‘rilik, jinoyat yoki niyatni taxmin qilmaydi. Oddiy mijoz Face ID’i,
Orange Pi mahsuloti va 8 kamera va’dasi faol MVP scope’ida emas. Commercial yuz
modelining manifesti tekshirilmaguncha pullik davomat production’da fail-closed.

## Ishga tushirish

Developer muhiti Python 3.12 bilan test qilinadi:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
make lint
make test
```

Asosiy xizmatlar:

| Buyruq | Vazifa |
|---|---|
| `make run-cloud` | Admin, owner, billing va event cloud’i (`:8750`) |
| `make run-sotqin` | Sotqin control agent |
| `make run-retail` | Lokal do‘kon analitikasi |
| `make run-web` | Lokal yopiq-pilot davomat/enrollment paneli (`:8743`) |

Production release qurish va N100 ga o‘rnatish:

```bash
./scripts/build_sotqin_release.sh
# release arxivini ochib, uning ichida:
sudo ./scripts/install_sotqin.sh
```

Installer control, retail va ixtiyoriy attendance xizmatlarini, verifikatsiya
qilingan OpenVINO retail modelini va lokal secretlarni o‘rnatadi. Kameralar
hozir admin panelda RTSP manzilini qo‘lda kiritish orqali ulanadi; ONVIF
discovery hali yo‘q.

## Sotuv darvozasi

Public funksiyani ochish uchun faqat environment flag yetmaydi. Haqiqiy do‘kon
videosida N100 benchmark va 4 kamera bilan 72 soat soak hisobotidan qabul fayli
yaratilishi kerak:

```bash
python scripts/benchmark_n100.py --seconds 60 --cameras 4 \
  --source pilot-store.mp4 --json benchmark.json
sudo /opt/chaqimchi/venv/bin/python /opt/chaqimchi/current/scripts/soak_n100.py \
  --hours 72 --output soak-72h.json
python scripts/accept_n100_pilot.py --benchmark benchmark.json \
  --soak soak-72h.json --approved-by "Qabul komissiyasi" \
  --output acceptance/n100-r1.json
```

So‘ng production’da `CHAQIMCHI_N100_ACCEPTANCE_FILE` va
`CHAQIMCHI_AVAILABLE_FEATURES` sozlanadi. Qabul mezonlari va qolgan ishlar
[docs/DOKON_MVP.md](docs/DOKON_MVP.md) da.

## Asosiy hujjatlar

- [Do‘kon MVP kontrakti va gap-list](docs/DOKON_MVP.md)
- [Sotqin R1](docs/SOTQIN.md)
- [Retail pipeline](chaqimchi_ai/retail/README.md)
- [Installer](docs/INSTALLER.md)
- [Production runbook](docs/PRODUCTION_RUNBOOK.md)
- [To‘lov](docs/TOLOV.md)
- [Eski hujjatlar arxivi](docs/archive/README.md)
