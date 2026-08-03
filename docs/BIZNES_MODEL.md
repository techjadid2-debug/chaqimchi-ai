# Chaqimchi — biznes modeli va tariflar

## Model

1. **O‘rnatish** — bir martalik (qurilma + sozlash + o‘qitish)  
2. **Obuna** — oylik yoki yillik (litsenziya + qo‘llab-quvvatlash)  
3. **Cloud** — markazda mijoz va obuna boshqaruvi; edge Mini PC da tanish

## Tariflar (tavsiya narxlar, UZS)

| Tarif | Kamera | Shaxs bazasi | Voqea arxivi | Oylik | O‘rnatish |
|-------|--------|--------------|--------------|-------|----------|
| **Starter** | 1 | 50 | 30 kun | 790 000 | 6 500 000 |
| **Business** | 3 | 200 | 90 kun | 1 490 000 | 9 500 000 |
| **Enterprise** | 8 | 2000 | 365 kun | 2 990 000 | 15 000 000+ |

Yillik: oylik × **10** (2 oy tekin).

## Davomat tariflari (xodim bo‘yicha)

Korxona uchun qiymat kamera sonida emas, **xodim sonida**: 200 xodimli zavodga
2 kamera yetadi, lekin 200 ta yuz kerak.

```
Oylik = eng kam narx  YOKI  xodim × narx  (qaysi biri katta)
```

| Tarif | Eng kam/oy | Har xodim | Kamera | Arxiv | O‘rnatish |
|-------|-----------|-----------|--------|-------|-----------|
| **Davomat S** | 500 000 | 15 000 | 2 | 30 kun | 6 500 000 |
| **Davomat M** | 1 200 000 | 12 000 | 5 | 90 kun | 9 500 000 |
| **Davomat L** | 2 500 000 | 9 000 | 15 | 365 kun | 15 000 000 |

Katta tarifda xodim arzonroq — mijoz o‘sganda ko‘tarilishni **o‘zi so‘raydi**:

| Xodim | Eng arzon tarif | Oylik |
|-------|----------------|-------|
| 30 | Davomat S | 500 000 |
| 50 | Davomat S | 750 000 |
| 100 | Davomat M | 1 200 000 |
| 200 | Davomat M | 2 400 000 |
| 300 | Davomat L | 2 700 000 |
| 500 | Davomat L | 4 500 000 |

**Baza chegarasi = to‘langan xodim soni.** 100 xodim uchun to‘lasa, 101-chisini
qo‘shmoqchi bo‘lganda tizim “tarifni kengaytiring” deydi — tijorat mantiqi va
texnik cheklov bir joyda.

Narxni qo‘lda hisoblamang:

```bash
curl "http://CLOUD:8750/api/v1/quote?persons=120"
# → tarif, oylik, yillik va shartnoma kuni qo'lga tushadigan summa
```

Admin panelda “Xodim soni” maydoniga son yozsangiz narx o‘zi chiqadi va mos
tarif tanlanadi.

Xodim soni o‘zgarganda (mijoz o‘sdi yoki qisqardi):

```bash
curl -X POST "http://CLOUD:8750/api/v1/admin/sites/SITE_ID/persons" \
  -H "X-Cloud-Admin-Key: $CHAQIMCHI_CLOUD_ADMIN_KEY" \
  -H "Content-Type: application/json" -d '{"persons": 260}'
```

Keyingi hisob-faktura avtomatik yangi narxda ochiladi.

> Kamera tariflari (Starter/Business/Enterprise) **o‘zgarmadi**. Hozirgi
> mijozlarning narxi va shartnomasi avvalgidek qoladi.

Cheklovlar rostdan qo‘llanadi: kamera soni va shaxs bazasi limitdan oshmaydi,
voqea arxivi esa muddati o‘tgach avtomatik tozalanadi (rasmlar bilan birga).

## O‘rnatish jarayoni

1. Admin panel ([`/admin`](http://127.0.0.1:8750/admin)) da “Yangi mijoz ochish”
   — yoki CLI: `scripts/provision_site.py "Mijoz nomi" --plan business`  
2. **Pairing kod** ni o‘rnatuvchiga bering (48 soat)  
3. Mijoz `config.yaml` da `license.pairing_code` — birinchi ishga tushirishda avtomatik `device_token`  
4. Panelda “Hisob” → mijozga to‘lov havolasi (Payme/Click) — to‘lov tushgach
   obuna **avtomatik** uzayadi. Naqd bo‘lsa: “To‘landi” tugmasi.  
5. To‘lov kechiksa → panelda “Obunani to‘xtatish” (kameralar to‘xtaydi), to‘langach “Qayta yoqish”

Batafsil: [TOLOV.md](TOLOV.md)

## Admin panel

```bash
export CHAQIMCHI_CLOUD_ADMIN_KEY="maxfiy-kalit"
make run-cloud     # http://127.0.0.1:8750/admin
```

Panelda ko‘rinadi: mijozlar soni, faol obunalar, **7 kun ichida tugaydiganlar**,
**ishlamayotgan tizimlar**, juftlangan qurilmalar va **oylik daromad**
(faol + grace mijozlar bo‘yicha).

“Ishlamayapti” qizil raqami — to‘lovi joyida, lekin 24 soatdan beri aloqaga
chiqmagan mijozlar. Ularga o‘zingiz qo‘ng‘iroq qiling: mijoz shikoyat qilguncha
kutish — obunani yo‘qotishning eng oson yo‘li.

Telegram ulansa panelni ochish ham shart emas — cloud o‘zi xabar beradi
(`CHAQIMCHI_CLOUD_TELEGRAM_TOKEN`, [INSTALLER.md](INSTALLER.md)).

Batafsil: [INSTALLER.md](INSTALLER.md)

## Texnik

- Cloud: `make run-cloud` (8750)  
- Edge: `make run-web` (8742)  
- Admin: `CHAQIMCHI_CLOUD_ADMIN_KEY`
