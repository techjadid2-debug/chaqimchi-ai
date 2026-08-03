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

Batafsil: [INSTALLER.md](INSTALLER.md)

## Texnik

- Cloud: `make run-cloud` (8750)  
- Edge: `make run-web` (8742)  
- Admin: `CHAQIMCHI_CLOUD_ADMIN_KEY`
