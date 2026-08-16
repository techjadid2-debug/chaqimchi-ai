# Reliz chiqarish va masofadan yangilash (OTA)

Ikki narsa uchun: yangi Sotqin qurilmasini o'rnatish va ishlab turgan
qurilmani yangilash. Ikkalasi ham bitta imzolangan paketdan foydalanadi.

---

## Bir marta: imzo kalitini yaratish

```bash
python scripts/generate_update_key.py
```

* Maxfiy kalit — `~/.chaqimchi/sotqin-release-signing.pem`, 0600,
  **repo daraxtidan tashqarida**.
* Ochiq kalit — `deploy/update-public.pem`, commit qilinadi va reliz
  paketi ichida qurilmaga boradi.

**Maxfiy kalitni darhol parol menejeriga zaxiralang.** Uni yo'qotsangiz
mavjud qurilmalarni boshqa yangilay olmaysiz — ular yangi kalit bilan
imzolangan paketni rad etadi (va bu to'g'ri xatti-harakat).

Kalit `install_sotqin.sh` tomonidan `/etc/chaqimchi/update-public.pem` ga
bir marta yoziladi va keyin **almashtirilmaydi**. Sababi: birinchi
o'rnatishda ishonch cloudga tayanadi (HTTPS + SHA-256), lekin kalit
qotirilgach — cloud buzilsa ham hujumchi imzo yasay olmaydi va qurilma
eski kodda qolaveradi. Ataylab almashtirish uchun
`CHAQIMCHI_ROTATE_UPDATE_KEY=true`.

---

## Har reliz uchun

```bash
# 1. Versiyani ko'taring — ikkala joyda ham (test buni tekshiradi)
#    pyproject.toml  va  chaqimchi_ai/__init__.py
# 2. Commit qiling (iflos worktree'dan qurish rad etiladi)
make lint && pytest -q
git commit -am "0.6.1"

# 3. Quring va imzolang
./scripts/build_sotqin_release.sh
python scripts/sign_release.py releases/chaqimchi-sotqin-0.6.1.tar.gz

# 4. Serverga ikkala faylni ham qo'ying
scp releases/chaqimchi-sotqin-0.6.1.{tar.gz,json} <server>:<deploy-dir>/releases/
```

Imzolovchi uch narsani o'zi tekshiradi va xato bo'lsa manifest yozmaydi:
arxiv nomi bilan ichidagi `__version__` mos kelishi, versiya qurilma qabul
qiladigan belgilardan iborat bo'lishi, va imzo **aynan qurilmadagi ochiq
kalit** bilan tekshirilishi.

### Yangi o'rnatishlar uchun (`/downloads/sotqin-installer.sh`)

`.env.production` da ikkita qatorni yangilang va `deploy_cloud.sh` ni
qayta ishlating:

```
CHAQIMCHI_SOTQIN_RELEASE_URL=https://<domen>/releases/chaqimchi-sotqin-0.6.1.tar.gz
CHAQIMCHI_SOTQIN_RELEASE_SHA256=<sign_release.py chop etgan sha256>
```

Busiz `/downloads/sotqin-installer.sh` **503** qaytaradi — bu ataylab:
yarim sozlangan cloud ishlamaydigan o'rnatish buyrug'ini bermasligi kerak.

---

## Qurilmani yangilash

```bash
sudo /opt/chaqimchi/venv/bin/python \
  /opt/chaqimchi/current/scripts/apply_signed_update.py \
  --fetch-version 0.6.1 --cloud https://<domen>
```

Qo'lda ko'chirilgan fayllar bilan (zaxira yo'l):

```bash
sudo /opt/chaqimchi/venv/bin/python \
  /opt/chaqimchi/current/scripts/apply_signed_update.py \
  paket.tar.gz paket.json
```

### Chiqish kodlari

| Kod | Ma'nosi | Nima qilish |
|---|---|---|
| 0 | Yangilandi | — |
| 1 | Tekshiruv yiqildi, **qurilmada hech nima o'zgarmadi** | Sababni o'qing, tuzating, qayta urining |
| 2 | Health o'tmadi, oldingi versiya qaytarildi | Qurilma ishlayapti; relizni tuzating |
| 3 | Rollback ham yiqildi | **Qurilma holati noaniq — SSH bilan qo'lda tekshiring** |

### Nima tekshiriladi

Yiqilishi mumkin bo'lgan hamma narsa `current` almashtirilishidan **oldin**:

```
imzo → arxitektura → yoyish → model → requirements → systemd unitlar → chown
  → `current` almashtirish → daemon-reload → restart → health → (rollback)
```

Health darvozasi qoidasi: *yangilanish qurilmani oldingidan sog'lomroq
bo'lishini talab qilmaydi.* Agent javob berishi shart (503 ham bo'ladi —
u pairing yo'qligini bildiradi, lekin ilova import bo'lganini isbotlaydi);
boshqa xizmatlardan esa faqat yangilanishdan **oldin ishlab turganlari**
so'raladi. Shu sababdan kamerasiz stendda `chaqimchi-retail` ishga
tushmasligi yangilanishni rad etish uchun sabab bo'lmaydi.

### Yangi Python paketi kerak bo'lsa

Standart holatda **rad etiladi**:

```
XATO: Bu relizda yangi Python paketlari bor (requirements-sotqin.txt).
`--pip` bilan qayta ishga tushiring.
```

Sababi: venv reliz tashqarisida va umumiy, ya'ni `pip install` orqaga
qaytmaydi. `current` ni qaytarish rollback'ni yolg'onga aylantirardi.
Ataylab davom etish uchun `--pip` qo'shing.

---

## Birinchi marta sinashdan oldin

**Yiqilishni mashq qiling.** Ataylab buzuq reliz tayyorlang (masalan
`sotqin_agent.py` ga sintaksis xatosi), imzolang va qo'llang. Health
darvozasi uni ushlashi, `current` qaytishi va `/health` eski versiyada
javob berishi kerak:

```bash
readlink -f /opt/chaqimchi/current     # eski versiya
curl -s 127.0.0.1:8742/health | head
```

O'n daqiqa, va aynan shu narsa yangilanishni mijoz qurilmasida
ishlatishga asos beradi.

## Yangilanishdan keyin

```bash
readlink -f /opt/chaqimchi/current                  # yangi versiya
curl -s 127.0.0.1:8742/health                       # versiya mos kelsin
ls /opt/chaqimchi/releases/<versiya>/models/retail/  # model joyida
systemctl status chaqimchi-sotqin chaqimchi-retail
python /opt/chaqimchi/current/scripts/sotqin_preflight.py
cat /opt/chaqimchi/shared/logs/update.log            # yangilanishlar tarixi
```

Bir daqiqa ichida cloud panelida ham yangi `app_version` ko'rinadi —
heartbeat uni allaqachon yuboradi.

---

## Bosqichli tarqatish (Windows relizlari uchun MAJBURIY tartib)

Windows qurilmalar yangilanishni har 15 daqiqada tekshiradi — buzuq reliz
15 daqiqada **hamma** qurilmaga yetadi. Shuning uchun tartib qat'iy:

1. **Relizdan oldin** admin panelda barcha mijoz saytlarini `hold` ga
   o'tkazing (Yangilanish tugmasi). O'z sinov qurilmangiz `auto` da qoladi.
2. Reliz fayllarini serverga qo'ying — 15 daqiqada faqat sizning
   qurilmangiz yangilanadi.
3. **24 soat kuting**: panel ochiladimi, hodisalar kelyaptimi, heartbeat'da
   yangi versiya ko'rinyaptimi.
4. Muammo bo'lmasa mijoz saytlarini yana `auto` ga qaytaring.

Himoya qatlamlari (`chaqimchi_ai/local/updater.py`):

- **Faqat yangiroq versiya** o'rnatiladi — serverga yozish huquqini olgan
  hujumchi eski (zaif) relizni qaytara olmaydi. `pin` bundan mustasno
  (admin ataylab qotirgan versiya).
- **Avto-rollback**: yangilashdan keyin panel `running` holatiga yetmasa
  (30 daqiqa ichida, dastur ishga tushishga uringan bo'lsa), updater
  oldingi versiyaning saqlangan o'rnatuvchisini (imzosini qayta tekshirib)
  qaytaradi va buzuq versiyani `blocked` qiladi — qayta o'rnatilmaydi.
- Rollback nishoni birinchi OTA'dan keyin paydo bo'ladi: qo'lda
  o'rnatilgan birinchi versiyada hali saqlangan oldingi `.exe` yo'q.

---

## Hali yo'q: cloud'dan boshqariladigan tarqatish

Hozir yangilanish har bir qurilmada qo'lda ishga tushiriladi. Cloud'dan
"barcha qurilmalarni 0.6.1 ga o't" deyish uchun **huquqlarni ajratish**
kerak: `chaqimchi-sotqin` xizmati `User=chaqimchi`, `NoNewPrivileges=true`
va `ProtectSystem=strict` bilan ishlaydi, ya'ni agent na
`/opt/chaqimchi/releases` ga yoza oladi, na `systemctl` chaqira oladi.

Rejalashtirilgan yechim: agent heartbeat javobini o'qib
`shared/data/update-request.json` yozadi, root egaligidagi systemd `.path`
unit uni kuzatadi va `chaqimchi-update.service` ni ishga tushiradi. Agent
hech qachon root olmaydi, applier esa cloudga ishonmaydi — imzoni baribir
tekshiradi.
