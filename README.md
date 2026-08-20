# Chaqimchi AI — do‘kon MVP

Chaqimchi AI hozir **mijozning mavjud Windows kompyuteri + NVR/IP kamera +
Cloud** sifatida faqat do‘konlar uchun qurilmoqda. Birinchi qabul profili —
bitta do‘kon va ko‘pi bilan **4 kamera** (yagona manba:
`chaqimchi_ai/limits.py`). Uzluksiz video NVR’da qoladi; tahlil do‘kon
kompyuterida lokal ishlaydi, cloudga esa hodisa, ruxsat etilgan media,
hisobot va health yuboriladi.

**Chaqimchi Box** (Intel N100 mini-PC, usta bilan o‘rnatiladi) — keyingi
bosqich mahsuloti: kodi repoda saqlanadi va ishlaydi, lekin faol sotuv va
rivojlantirish fokusi hozir Windows yo‘lida.

Canonical mahsulot kontrakti va joriy holat:
[docs/DOKON_MVP.md](docs/DOKON_MVP.md). Box qurilma tafsiloti:
[docs/SOTQIN.md](docs/SOTQIN.md).

## MVP doirasi

- odam kirishi/chiqishi, bandlik, navbat va zonada turish;
- kamera yopilishi/burilishi, ish vaqtidan tashqari odam, taqiqlangan zona va
  uzoq turish;
- owner panel (kirish havolasi yoki Telegram kod bilan), Telegram
  alert/digest, CSV, offline outbox va event klip;
- kamera ulash: qo‘lda RTSP, ONVIF qidiruv va NVR kanal skaneri (bitta
  login/parol bilan barcha kanallar).

Tizim o‘g‘rilik, jinoyat yoki niyatni taxmin qilmaydi. **Xodim davomati
(Face ID)** Lite ichida: mijoz panelda 10 tagacha xodim qo‘shadi va
rasmini telefondan oladi, tanish cloudda bo‘ladi (qurilma yuzni
tanimaydi). Xaridorni tanish — scope’da emas. Orange Pi mahsuloti va
8 kamera va’dasi ham scope’da emas.

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
| `make run-local` | Mijoz kompyuteridagi sozlash ustasi va panel (`:8760`) |
| `make run-retail` | Lokal do‘kon analitikasi (AI zanjiri) |
| `make run-sotqin` | Box (N100) control agenti — keyingi bosqich |

## Windows lokal o‘rnatish (asosiy yo‘l)

Do‘kon egasi mavjud Windows kompyuteriga o‘zi o‘rnatadi: `Chaqimchi_AI_Setup.exe`
→ Keyingi → Keyingi → Tayyor → brauzerda sozlash ustasi ochiladi. Python va AI
modeli o‘rnatuvchi ichida, internet talab qilinmaydi. Kamera ro‘yxati lokal
konfigda turadi, ya’ni cloud ulanmasa ham tahlil ishlaydi.

```bash
python scripts/build_windows_payload.py     # → build/payload
makensis -V2 scripts/windows_installer.nsi  # → releases/Chaqimchi_AI_Setup.exe
```

Mijozga beriladigan qadam-baqadam yo‘riqnoma saytda: `/install`.
Texnik tafsilot: [docs/INSTALLER.md](docs/INSTALLER.md) 0-bo‘lim.
Reliz imzolash va masofadan yangilash (15 daqiqalik tekshiruv, avto-rollback):
[docs/RELIZ_VA_OTA.md](docs/RELIZ_VA_OTA.md).

## Box (N100) o‘rnatish — keyingi bosqich

```bash
./scripts/build_sotqin_release.sh
# release arxivini ochib, uning ichida:
sudo ./scripts/install_sotqin.sh
```

## Sotuv darvozasi

Public AI funksiyalarini ochish uchun faqat environment flag yetmaydi —
haqiqiy do‘konda o‘tkazilgan qabul sinovi fayli kerak
(`CHAQIMCHI_N100_ACCEPTANCE_FILE` + `CHAQIMCHI_AVAILABLE_FEATURES`).

Windows yo‘li uchun mezon: **real do‘kon kompyuterida 4 kamera bilan 72
soat uzluksiz, restartsiz ishlash** va kunlik hisobotning qo‘lda sanash
bilan solishtirilgan tekshiruvi. Hozircha bu qabul o‘tkazilmagan — shuning
uchun sotuvda ehtiyotkor va’da beriladi (batafsil:
[docs/DOKON_MVP.md](docs/DOKON_MVP.md)).

## Asosiy hujjatlar

- [Do‘kon MVP kontrakti va gap-list](docs/DOKON_MVP.md)
- [Sotqin R1 / Box](docs/SOTQIN.md)
- [Retail pipeline](chaqimchi_ai/retail/README.md)
- [Installer](docs/INSTALLER.md)
- [Reliz chiqarish va OTA](docs/RELIZ_VA_OTA.md)
- [Production runbook](docs/PRODUCTION_RUNBOOK.md)
- [To‘lov](docs/TOLOV.md)
- [Eski hujjatlar arxivi](docs/archive/README.md)
