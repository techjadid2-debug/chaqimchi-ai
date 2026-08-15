# Chaqimchi o‘rnatuvchi qo‘llanmasi

Ikkita yo‘l bor va ular bir-biridan mustaqil:

| Yo‘l | Kim uchun | Qurilma | Cloud kerakmi |
|---|---|---|---|
| **Windows lokal** (0-bo‘lim) | do‘kon egasi o‘zi o‘rnatadi | mavjud Windows 10/11 | yo‘q |
| **Sotqin R1** (1–3-bo‘limlar) | o‘rnatuvchi mutaxassis | Intel N100 mini-PC | ha |

---

## 0. Windows lokal o‘rnatish (mijoz o‘zi)

Mijoz `Chaqimchi_AI_Setup.exe` ni saytdan yuklab oladi. Ichida Python, AI
modeli va barcha kutubxonalar bor — **internet ham, `pip` ham kerak emas**.

1. Faylni ishga tushiradi → Windows ruxsat so‘raydi (UAC) → “Ha”.
2. Keyingi → Keyingi → O‘rnatish → Tayyor.
3. Brauzerda sozlash ustasi ochiladi: `http://localhost:8760`.
4. Kamera qo‘shadi → kadr ko‘rinadi → kirish chizig‘ini chizadi → ishga tushiradi.

Fayl imzolanmagan, shuning uchun Windows birinchi marta ogohlantiradi:
**“Qo‘shimcha ma’lumot” → “Baribir ishga tushirish”**.

| Nima | Qayerda |
|---|---|
| Dastur | `C:\Program Files\Chaqimchi AI` (faqat o‘qish) |
| Sozlama, log, hodisalar | `C:\ProgramData\Chaqimchi` |
| Panel | `http://localhost:8760` (faqat shu kompyuterda) |

Bu rejimda kamera ro‘yxati lokal `config.yaml` da turadi
(`retail.cameras_source: config`) va cloud ulanmasa ham tahlil ishlaydi.
Cloudga ulash keyinroq, pairing kod bilan bajariladi (3-bo‘lim).

### O‘rnatuvchini qurish

```bash
python scripts/build_windows_payload.py     # Python + wheel + model → build/payload
makensis -V2 scripts/windows_installer.nsi  # → releases/Chaqimchi_AI_Setup.exe
```

CI ham shuni qiladi (`.github/workflows/windows-installer.yml`) va faylni
GitHub Releases’ga yuklaydi. Cloud uni git ichida tashimaydi — deployda
shu ikki o‘zgaruvchi beriladi:

```bash
export CHAQIMCHI_WINDOWS_INSTALLER_URL="https://github.com/.../Chaqimchi_AI_Setup.exe"
export CHAQIMCHI_WINDOWS_INSTALLER_SIZE_MB=68
```

Berilmasa sayt yuklab olish tugmasi o‘rniga “tayyor bo‘lganda xabar bering”
formasini ko‘rsatadi — buzuq tugma chiqmaydi.

---

## 1. Cloud (markaz)

```bash
export CHAQIMCHI_CLOUD_ADMIN_KEY="maxfiy-admin-kalit"

# Ogohlantirish (tavsiya etiladi): mijoz tizimi o'chsa Telegramga xabar keladi
export CHAQIMCHI_CLOUD_TELEGRAM_TOKEN="123456:ABC..."   # @BotFather dan
export CHAQIMCHI_CLOUD_TELEGRAM_CHAT_ID="-1001234567890"
# Public deep-link uchun BotFather bergan username:
export CHAQIMCHI_TELEGRAM_BOT_USERNAME="chaqimchi_bot"
# Maslahat arizasini faqat shaxsiy akkauntga yuborish:
export CHAQIMCHI_TELEGRAM_LEAD_CHAT_IDS="5476913898"

make run-cloud
```

Bot yaratish: Telegramda **@BotFather** → `/newbot` → token. Shaxsiy xabar
kelishi uchun foydalanuvchi botga avval `/start` yuborishi shart. Leadlar
guruhdan avtomatik yig‘ilmaydi; faqat `CHAQIMCHI_TELEGRAM_LEAD_CHAT_IDS`
ro‘yxatiga boradi. Panelda **“Sinov xabari”** tugmasi bilan tekshiring.

## 2. Yangi mijoz

```bash
export CHAQIMCHI_CLOUD_ADMIN_KEY="maxfiy-admin-kalit"
python scripts/provision_site.py "Oq Saroy Do'kon" --plan lite --months 1
```

Chiqadi: `site_id`, `pairing_code`, narxlar.

## 3. Sotqin R1 (mijoz joyida)

Canonical profil: `config/sotqin.yaml`. Installer control agent, retail AI,
verifikatsiya qilingan OpenVINO model va ixtiyoriy attendance pilot
dependencylarini o‘rnatadi. Admin paneldagi pairing kod bilan:

```bash
sudo ./scripts/install_sotqin.sh
sudo /opt/chaqimchi/venv/bin/python /opt/chaqimchi/current/scripts/pair_sotqin.py \
  --cloud https://YOUR_DOMAIN --code ABC123
sudo systemctl start chaqimchi-sotqin
sudo systemctl start chaqimchi-retail
curl http://127.0.0.1:8742/health
```

Pairing skripti `/etc/chaqimchi/sotqin.env` dagi lokal secretlarni
saqlaydi, cloud identifikatorlarini atomik yangilaydi va fayl huquqini `0600`
qiladi. Admin onboarding ro‘yxatida Sotqin juftlangan va online bo‘lishi
kerak.

Attendance faqat yozma rozilikli yopiq pilot bo‘lsa
`CHAQIMCHI_ATTENDANCE_PILOT=true` qilinadi va lokal xizmat yoqiladi:

```bash
sudo systemctl enable --now chaqimchi-attendance
# enrollment paneliga servis SSH tunnel orqali ulanadi:
ssh -L 8743:127.0.0.1:8743 installer@SOTQIN_IP
```

Developmentda `make run-web` attendance pilot rejimini va `:8743` portini
o‘zi qo‘yadi. Cloud inventar/config kerak bo‘lsa avval control agentni pairing
qiling va `CHAQIMCHI_SOTQIN_CONFIG_CACHE` ni uning kesh fayliga yo‘naltiring.

```bash
make install-dev
make run-web
```

## 4. Obuna uzaytirish (to‘lovdan keyin)

```bash
curl -X POST "http://127.0.0.1:8750/api/v1/admin/sites/SITE_ID/extend" \
  -H "X-Cloud-Admin-Key: $CHAQIMCHI_CLOUD_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"months": 1}'
```

## 5. Zaxira nusxa (faqat attendance pilotida)

Embeddinglar cloudga chiqmaydi. SSD ishdan chiqsa yoki Sotqin almashsa,
xodimlarni qayta enrollment qilish kerak bo‘lmasligi uchun shifrlangan lokal
nusxa olinadi. Retail-only o‘rnatishda biometrik baza yo‘q.

**O‘rnatishdan keyin va har oy** nusxa oling, fleshka yoki o‘z serveringizda
saqlang:

```bash
make backup                    # data/backups/ ga
make backup OUT=/Volumes/USB   # fleshkaga
python scripts/backup_db.py info nusxa.zip   # ichida nima bor
```

Yoki serverdan (API kalit bilan):

```bash
curl -H "X-API-Key: $CHAQIMCHI_API_KEY" http://MINI_PC:8743/api/backup -O -J
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

**Kamera**: panelda `3/4` ko‘rinsa — bitta kamera o‘chgan. Telegramga ham xabar
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
