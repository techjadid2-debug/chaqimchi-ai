# Chaqimchi Sotqin o‘rnatuvchi qo‘llanmasi

## 1. Cloud (markaz)

```bash
export CHAQIMCHI_CLOUD_ADMIN_KEY="maxfiy-admin-kalit"

# Ogohlantirish (tavsiya etiladi): mijoz tizimi o'chsa Telegramga xabar keladi
export CHAQIMCHI_CLOUD_TELEGRAM_TOKEN="123456:ABC..."   # @BotFather dan
export CHAQIMCHI_CLOUD_TELEGRAM_CHAT_ID="-1001234567890"

make run-cloud
```

Bot yaratish: Telegramda **@BotFather** → `/newbot` → token. Keyin botni
o‘zingiz bilan (yoki xodimlar guruhi bilan) suhbatga qo‘shing va `chat_id` ni
oling. Panelda **“Sinov xabari”** tugmasi bilan tekshiring.

## 2. Yangi mijoz

```bash
export CHAQIMCHI_CLOUD_ADMIN_KEY="maxfiy-admin-kalit"
python scripts/provision_site.py "Oq Saroy Do'kon" --plan lite --months 1
```

Chiqadi: `site_id`, `pairing_code`, narxlar.

## 3. Sotqin R1 (mijoz joyida)

Canonical profil: `config/lite.yaml`. Hozir AI modelsiz control-only agent
o‘rnatiladi. Admin paneldagi pairing kod bilan:

```bash
sudo ./scripts/install_sotqin.sh
sudo /opt/chaqimchi/venv/bin/python /opt/chaqimchi/current/scripts/pair_sotqin.py \
  --cloud https://YOUR_DOMAIN --code ABC123
sudo systemctl start chaqimchi-sotqin
curl http://127.0.0.1:8742/health
```

Pairing skripti `/etc/chaqimchi/sotqin.env` dagi lokal secretlarni
saqlaydi, cloud identifikatorlarini atomik yangilaydi va fayl huquqini `0600`
qiladi. Admin onboarding ro‘yxatida Sotqin juftlangan va online bo‘lishi
kerak.

Development uchun `config/config.yaml`:

```yaml
license:
  enabled: true
  cloud_url: "http://YOUR_CLOUD_IP:8750"
  pairing_code: "ABC123"   # bir martalik
```

```bash
make install-dev
make run-web
```

Logda `device_token` chiqsa — keyingi safar:

```yaml
license:
  enabled: true
  cloud_url: "http://YOUR_CLOUD_IP:8750"
  site_id: "..."
  device_token: "..."
```

## 4. Obuna uzaytirish (to‘lovdan keyin)

```bash
curl -X POST "http://127.0.0.1:8750/api/v1/admin/sites/SITE_ID/extend" \
  -H "X-Cloud-Admin-Key: $CHAQIMCHI_CLOUD_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"months": 1}'
```

## 5. Zaxira nusxa (majburiy odat)

Yuz bazasi eng qimmat narsa: har bir shaxs bir marta kamera oldiga kelib
ro‘yxatdan o‘tgan. SSD ishdan chiqsa yoki Mini PC almashsa — nusxasiz bu ish
qaytadan boshlanadi.

**O‘rnatishdan keyin va har oy** nusxa oling, fleshka yoki o‘z serveringizda
saqlang:

```bash
make backup                    # data/backups/ ga
make backup OUT=/Volumes/USB   # fleshkaga
python scripts/backup_db.py info nusxa.zip   # ichida nima bor
```

Yoki serverdan (API kalit bilan):

```bash
curl -H "X-API-Key: $CHAQIMCHI_API_KEY" http://MINI_PC:8742/api/backup -O -J
```

### Qurilma almashganda

1. Eski qurilmadan nusxa oling (agar ishlayotgan bo‘lsa)
2. Panelda “Yangi pairing kod” → yangi Mini PC ni juftlang (3-bo‘lim)
3. Bazani tiklang:

```bash
make restore FILE=nusxa.zip
```

Ikki do‘kon bazasini birlashtirish kerak bo‘lsa: `--merge` (bor shaxslar
takrorlanmaydi).

> **Shifrlangan baza** (`storage.encrypt_embeddings: true`) nusxasi ham
> shifrlangan bo‘ladi. Tiklashda **o‘sha** `CHAQIMCHI_EMBEDDING_KEY` kerak —
> kalitni nusxadan **alohida** joyda saqlang. Kalit yo‘qolsa nusxa foydasiz.

> Nusxa — biometrik ma’lumot. Ochiq joyda, umumiy bulutda yoki messenjerda
> saqlamang.

## 6. Holatlar

**Obuna** (to‘lov bo‘yicha):

| status | Ma’nosi |
|--------|---------|
| active | Hammasi ishlaydi |
| grace | Muddati o‘tgan, 14 kun ichida to‘lov |
| expired | Kameralar ishlamaydi |
| suspended | Admin to‘xtatgan |

**Kamera**: panelda `2/3` ko‘rinsa — bitta kamera o‘chgan. Telegramga ham xabar
ketadi. Kamera ataylab olib tashlangan bo‘lsa kutilgan sonni tushiring:

```bash
curl -X POST "http://CLOUD:8750/api/v1/admin/sites/SITE_ID/cameras" \
  -H "X-Cloud-Admin-Key: $CHAQIMCHI_CLOUD_ADMIN_KEY" \
  -H "Content-Type: application/json" -d '{"expected": 2}'
```

**Aloqa** (tizim rostdan ishlayaptimi):

| Holat | Ma’nosi | Nima qilish kerak |
|-------|---------|-------------------|
| Ishlayapti | 1 soat ichida xabar bergan | — |
| Aloqa uzilgan | 1–24 soat jim | Kuzating; takrorlansa internetni tekshiring |
| Ishlamayapti | 24 soatdan ortiq jim | **Qo‘ng‘iroq qiling** — tok, internet yoki Mini PC |
| Juftlanmagan | Qurilma ulanmagan | O‘rnatish tugallanmagan (3-bo‘lim) |

O‘rnatishni tugatgach panelda mijoz “Ishlayapti” bo‘lganiga ishonch hosil
qiling — aks holda juftlash bajarilmagan.
