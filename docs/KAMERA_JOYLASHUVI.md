# Kamera joylashuvi — qaysi kamera qayerga

> Bu hujjat **usta va jamoa** uchun texnik manba.  Mijozga ko'rinadigan
> qisqartmasi: `/installer-guide` (usta) va `/install` (mijoz).
>
> Hujjatdagi har bir son **koddan** olingan va manbasi ko'rsatilgan.
> Kod o'zgarsa bu yerdagi son ham o'zgarishi kerak — taxmin qilingan
> qiymatlar alohida «kalibrlanmagan» deb belgilangan.

## Nega bu hujjat kerak

Kamera noto'g'ri qo'yilgani **darhol ko'rinmaydi**.  Tizim ishlayotgandek
turadi: qurilma online, kamera online, hodisalar kelyapti — faqat
davomat ishlamaydi, konversiya yolg'on, javon nazorati jim.  Sabab
oylar o'tib, `face_crops.too_small` hisoblagichidan topiladi.

Jonli misol: pilot do'konida 93 ta yuz kesmasining **93 tasi ham** «juda
mayda» deb tashlangan.  Bu sozlash masalasi emas edi — kamera
352×288 oqim berardi va o'sha oqimda chegaradan o'tish **matematik
ravishda imkonsiz** edi.

## Bir qarashda

| Rol | Kod nomi | Nima beradi | Eng qattiq talab |
|---|---|---|---|
| Kirish eshigi | `entrance` | kirdi/chiqdi, konversiya, **Face ID/davomat**, ish vaqtidan tashqari harakat | oqim **≥ 720p** |
| Kassa | `checkout` | navbat uzunligi, «kassada hech kim yo'q» | kassa zonasi kadrga to'liq sig'sin |
| Savdo zali | `sales` | issiqlik xaritasi, uzoq turish, sig'im, javon | zal ko'rinsin, odamlar bir-birini to'smasin |
| Ombor | `storage` | taqiqlangan zona, buzilish, tungi harakat | eshik/o'tish yo'li kadrda bo'lsin |

Bitta do'konda **ko'pi bilan 4 kamera** (`enes/limits.py: SHOP_MAX_CAMERAS`).
NVR skaneri 8 kanalgacha qaraydi (`NVR_SCAN_CHANNELS`) — mijozning
kamerasi 5-kanalda turgan bo'lishi mumkin, lekin tanlov baribir 4 ta.

Rolni tizim **taklif qiladi**, odam tasdiqlaydi
(`enes/camera_roles.py: suggest_role`).  Taklif ikkita halol signaldan
chiqadi: NVR kanalining nomi va namunadagi odam oqimi.  Kanal RAQAMI
signal emas — «1-kanal = kirish» degan jim taxmin 2026-08-22 da hamma
kamerani noto'g'ri rolga qo'ygan edi.

---

## 1. Face ID — eng qattiq chegara

Davomat yuz kesmasini talab qiladi va zanjir ikkita qat'iy sondan iborat
(`enes/limits.py`):

```
FACE_MIN_CROP_PX  = 96     # embedding modeli 128x128 kutadi; kichigi — shovqin
FACE_CROP_RATIO   = 0.35   # kesma odam ramkasining yuqori 35% idan olinadi
```

Demak odam ramkasi kamida **275 piksel** balandlikda bo'lishi kerak
(`limits.face_min_bbox_px()` — taxmin emas, tekshirib hisoblanadi:
96/0,35 = 274,3 va 274 px ramkadan `int(95,9) = 95` px chiqadi, ya'ni
bir piksel yetmagani uchun kesma baribir rad etilardi).

Bu talab kadr balandligiga nisbatan:

| Oqim | Odam ramkasi kadrning shunchasini egallasin | Amalda |
|---|---|---|
| 288p (CIF) | 95% | **imkonsiz** |
| 360p | 76% | **imkonsiz** |
| 480p | 57% | chegarada — odam kameraga juda yaqin kelsin |
| **720p** | **38%** | **ishlaydi** |
| 1080p | 25% | bemalol |

Chegara qattiq son emas, formuladan chiqadi
(`limits.face_min_bbox_ratio`) — oqim sifati ko'tarilsa chegara o'zi
pasayadi, qo'lda tuzatish kerak emas.

Panel shu javobni o'zi aytadi (`camera_roles.face_id_check`) va past
sifatli oqimga **kirish rolini umuman taklif qilmaydi**: davomat unda
printsipial ishlamaydi, mijoz esa «Face ID buzilgan» deb o'ylardi.

### Obyektda qanday tekshiriladi

Obyektiv burchagini bilish shart emas.  Panelda kadrni oching, eshik
oldida odam tursin:

> **Odamning bo'yi kadr balandligining uchdan biridan baland bo'lsin.**

38% ≈ uchdan bir.  Agar odam kadrning yarmini egallasa — juda yaxshi;
choragini egallasa — kamerani yaqinlashtiring yoki pastroq qo'ying.

### Buni masofaga aylantirsak

1,70 m bo'yli odam kadrning 38% ini egallashi kerak bo'lsa, kadrda
ko'rinadigan **vertikal maydon** 1,70 / 0,38 ≈ **4,5 metrdan katta
bo'lmasin**.  1080p da bu 6,7 m gacha kengayadi, 360p da esa 2,2 m ga
tushadi — ya'ni shiftdagi kamera uchun amalda imkonsiz.

> Bo'y 1,70 m — hisob uchun olingan **faraz**; qolgan sonlar koddan.

### Ikkita amaliy qoida (kodda emas, amaliyotdan)

- **Kamera eshik oynasiga qaramasin.** Orqadan tushayotgan yorug'lik
  yuzni qorayтиradi va detektor ramkani topsa ham kesma yaroqsiz chiqadi.
- **Yuz frontal ko'rinsin.** Kamera juda tik qo'yilsa (shiftdan pastga)
  kadrda faqat bosh ustki qismi qoladi.

---

## 2. Eng ko'p uchraydigan xato: substream

Tahlil **substream**dan ketadi, asosiy oqimdan emas.  Asosiy oqim faqat
klip yozish uchun ishlatiladi (`record_url`).

NVR'lar substreamni odatda zavod sozlamasida CIF yoki D1 da qoldiradi.
Ya'ni:

> **NVR'da asosiy oqim 4K bo'lishi mumkin, substream esa 352×288 —
> va Face ID printsipial ishlamaydi.**

Kirish kamerasining **substreami** 1280×720 ga qo'yilsin.  Qabul
profili: H.264, RTSP over TCP, alohida faqat ko'rish huquqidagi
foydalanuvchi.  H.265+, Smart Codec va ishlab chiqaruvchining yopiq
protokoli kafolatlanmaydi.

Tekshiruv: heartbeat kelgach panel kameraning **haqiqiy** o'lchamini
ko'rsatadi — u dekodlangan kadrning o'zidan olinadi, NVR sozlamasidan
emas (`CAP_PROP` RTSP da drayver taxminini qaytaradi va yolg'on aytadi).

---

## 3. Chizma chegaralari

Chiziq yoki zona juda kichik chizilsa **saqlanadi, revizya ko'tariladi,
qurilma qabul qiladi — va jim nol hodisa beradi**.  Pilotda aynan shunday
bo'lgan: `camera-02` da 4 px chiziq va 29×20 px zona.

Chegaralar (`cloud/config_health.py`, normallashtirilgan 0..1 birlikda):

| Nima | Chegara | 720p da | 1080p da |
|---|---|---|---|
| Kirish chizig'i uzunligi | ≥ 5% (`MIN_LINE_LENGTH`) | ≥ 64 px | ≥ 96 px |
| Zona yuzasi | ≥ 1% (`MIN_ZONE_AREA`) | ≥ 9 216 px² | ≥ 20 736 px² |
| Zonaning eng qisqa tomoni | ≥ 8% (`MIN_ZONE_SIDE`) | ≥ 102×58 px | ≥ 154×86 px |

Zona turlari (`enes/local/static/zone-editor.js`): `queue` (navbat),
`shelf` (javon), `restricted` (taqiqlangan) va kirish chizig'i.

**Chiziq odam butunlay kesib o'tadigan joyga chizilsin** — eshikning
o'ziga emas, undan bir qadam ichkariga.  Qaror ramkaning MARKAZI
bo'yicha qabul qilinadi.

---

## 4. Konversiya: kamera zalni ko'rmasin

«Eshikka nechta odam yaqinlashdi» maxraji chiziqdan
**0,15 masofadagi tasma** ichida sanaladi
(`enes/limits.py: SEEN_LINE_BAND` — kadr enining ~1/7).

Kirish kamerasi savdo zalini ham ko'rsa maxraj shishadi va konversiya
foizi **sun'iy pasayadi** — nol emas, lekin YOLG'ON, ya'ni mahsulotning
eng qattiq taqig'i.

Kutilgan nisbat: `seen ≈ entered × 1,5…4`.
- `seen > entered × 10` — kamera zalni ko'ryapti yoki chiziq noto'g'ri;
- `seen < entered` — xato (chiziqni kesgan odam ta'rifiga ko'ra tasmadan o'tgan).

Raqam heartbeatda keladi (`seen.total`) — obyektdan chiqishdan oldin
emas, birinchi ish kunidan keyin tekshiriladi.

---

## 5. Tunda

Tungi rejim kadrning o'zidan aniqlanadi (`enes/retail/nightmode.py`):

| Nima | Qiymat | Ma'nosi |
|---|---|---|
| `CHROMA_MAX_IR` | 8.0 | to'yinganlik shundan past — IR chirog'i yoqilgan (oq-qora) |
| `DARK_BRIGHTNESS` | 25.0 | yorug'lik shundan past — kamera tunda **ko'r** |
| `NIGHT_MOTION_RATIO` | 0.03 | yopiq do'konda kadrning 3% i qimirlasa |
| `NIGHT_MOTION_SEC` | 3.0 | shuncha soniya davom etsa — hodisa |

⚠️ **To'rtala qiymat ham haqiqiy IR kamerada sinalmagan.**  Pilotda
birinchi tekshiruv: kechqurun heartbeatda `cameras[].night_mode: ir`
ko'rinsin va `tamper_alerts` o'smasin.

`dark` chiqsa — kamerada IR yoritgich yo'q yoki o'chiq.  Bu kamerani
**tungi nazorat uchun ishonchsiz** qiladi; do'kon egasiga aytilsin.

Ish vaqti panelda kiritilmasa **tungi nazorat umuman ishlamaydi** —
na `after_hours_presence`, na `night_motion`.  Sozlamalar → ish vaqti.

---

## 6. Obyektdan chiqishdan oldin

- [ ] Har kameraning **substreami** panelda ko'rinadi va kirish kamerasi ≥ 720p
- [ ] Panelda kirish kamerasida **✅ yuz tanish uchun yetarli** belgisi bor
- [ ] Eshik oldida turgan odam kadr balandligining **uchdan biridan baland**
- [ ] Kirish chizig'i chizilgan va ogohlantirish chiqmadi
- [ ] Kassa/zal zonalari chizilgan va ogohlantirish chiqmadi
- [ ] Kamera eshik oynasiga qaramaydi (orqa yorug'lik yo'q)
- [ ] Har kameraga rol qo'yilgan (`Rol tanlanmagan` qolmagan)
- [ ] Klip kerak bo'lsa `record_url` (asosiy oqim) berilgan
- [ ] Do'kon **ish vaqti** panelda kiritilgan
- [ ] Kabel va qurilma mahkamlangan, NVR internetdan ochilmagan

Birinchi ish kunidan keyin (masofadan):
- [ ] `face_crops.too_small` o'smayapti
- [ ] `seen ≈ entered × 1,5…4`
- [ ] Kechqurun `night_mode: ir`, `tamper_alerts` o'smayapti
- [ ] `clips.written > 0` (agar klip sotilgan bo'lsa)

---

## 7. Nosozlik → sabab

| Belgi | Eng ehtimolli sabab | Tekshiruv |
|---|---|---|
| Davomat hech kimni tanimaydi | substream 720p emas | panelda kamera o'lchami |
| `face_crops: {written: 0, too_small: N}` | odam kadrda juda mayda | kadrda odam bo'yi ≥ 1/3 |
| Kirdi/chiqdi nol | chiziq juda qisqa yoki noto'g'ri joyda | chizma ogohlantirishi |
| Konversiya juda past | kamera zalni ko'ryapti | `seen / entered` nisbati |
| Navbat hodisasi yo'q | navbat zonasi chizilmagan yoki mayda | chizma ogohlantirishi |
| Tunda hech narsa yo'q | ish vaqti kiritilmagan | Sozlamalar → ish vaqti |
| `night_mode: dark` | kamerada IR yo'q/o'chiq | kamera sozlamasi |
| Klip yozilmaydi | `record_url` berilmagan | `clips.unavailable` |
| Demografiya juda past | oqim past sifatli | kamera o'lchami |

---

## 8. Kalibrlanmagan qiymatlar (halollik ro'yxati)

Bular haqiqiy do'konda o'lchanmagan va pilotda tekshiriladi:

- `CHROMA_MAX_IR`, `DARK_BRIGHTNESS`, `NIGHT_MOTION_RATIO`, `NIGHT_MOTION_SEC`
- `SEEN_LINE_BAND` (0,15 — boshlang'ich taxmin)
- Ushbu hujjatdagi 1,70 m bo'y farazi
- «Eshik oynasiga qaramasin» va «yuz frontal» qoidalari — amaliyot, kodda chegara yo'q

## Manbalar

| Nima | Fayl |
|---|---|
| Yuz kesmasi geometriyasi, tasma, kamera soni | `enes/limits.py` |
| Rol, taklif dvigateli, Face ID tekshiruvi | `enes/camera_roles.py` |
| Chizma chegaralari | `cloud/config_health.py` |
| Tungi rejim | `enes/retail/nightmode.py`, `enes/retail/pipeline.py` |
| Zona turlari | `enes/local/static/zone-editor.js` |
| Hodisa turlari | `enes/event_models.py` |
| Mahsulot kontrakti | `docs/DOKON_MVP.md` |
