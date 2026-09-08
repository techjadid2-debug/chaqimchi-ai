# Reliz chiqarish va masofadan yangilash (OTA)

Ikki narsa uchun: yangi Sotqin qurilmasini o'rnatish va ishlab turgan
qurilmani yangilash. Ikkalasi ham bitta imzolangan paketdan foydalanadi.

---

## Bir marta: imzo kalitini yaratish

```bash
python scripts/generate_update_key.py
```

* Maxfiy kalit — `~/.enes/sotqin-release-signing.pem`, 0600,
  **repo daraxtidan tashqarida**.
* Ochiq kalit — `deploy/update-public.pem`, commit qilinadi va reliz
  paketi ichida qurilmaga boradi.

**Maxfiy kalitni darhol parol menejeriga zaxiralang.** Uni yo'qotsangiz
mavjud qurilmalarni boshqa yangilay olmaysiz — ular yangi kalit bilan
imzolangan paketni rad etadi (va bu to'g'ri xatti-harakat).

Kalit `install_sotqin.sh` tomonidan `/etc/enes/update-public.pem` ga
bir marta yoziladi va keyin **almashtirilmaydi**. Sababi: birinchi
o'rnatishda ishonch cloudga tayanadi (HTTPS + SHA-256), lekin kalit
qotirilgach — cloud buzilsa ham hujumchi imzo yasay olmaydi va qurilma
eski kodda qolaveradi. Ataylab almashtirish uchun
`ENES_ROTATE_UPDATE_KEY=true`.

---

## Har reliz uchun

```bash
# 1. Versiyani ko'taring — ikkala joyda ham (test buni tekshiradi)
#    pyproject.toml  va  enes/__init__.py
# 2. Commit qiling (iflos worktree'dan qurish rad etiladi)
make lint && pytest -q
git commit -am "0.6.1"

# 3. Quring va imzolang
./scripts/build_sotqin_release.sh
python scripts/sign_release.py releases/enes-sotqin-0.6.1.tar.gz

# 4. Serverga ikkala faylni ham qo'ying
scp releases/enes-sotqin-0.6.1.{tar.gz,json} <server>:<deploy-dir>/releases/
```

Imzolovchi uch narsani o'zi tekshiradi va xato bo'lsa manifest yozmaydi:
arxiv nomi bilan ichidagi `__version__` mos kelishi, versiya qurilma qabul
qiladigan belgilardan iborat bo'lishi, va imzo **aynan qurilmadagi ochiq
kalit** bilan tekshirilishi. Mahsulot nomi (`enes-windows` /
`enes-sotqin`) fayl nomidan o'zi aniqlanadi.

### Windows relizi (asosiy mahsulot)

Versiya ko'tarilib commit qilingandan keyin hammasi bitta buyruq:

```bash
# 1. Quring va imzolang (noutbukda, maxfiy kalit shu yerda)
make windows-release CLOUD_URL=https://api.chaqimchi.uz

# 2. Serverga chiqaring — shundan keyingina do'konlar ko'radi
ENES_RELEASE_HOST=deploy@169.58.198.111 \
  scripts/publish_windows_release.sh
```

`publish_windows_release.sh` `scp` ning o'rnini bosadi va uchta ishni
qo'shimcha qiladi: imzoni **qurilmadagi ochiq kalit bilan** qayta
tekshiradi, fayllarni serverga qo'yadi va **tashqaridan** (aynan qurilma
yuradigan `dl.` manzilidan) ularni o'qib ko'radi — hajm mos kelmasa xato
beradi. Ilgari bu qadam qo'lda `scp` edi va uni unutish "reliz chiqdi,
lekin hech kimga yetmadi" degan jim holatga olib kelardi.

CI qurgan faylni chiqarish (GitHub Releases'dan yuklab olingan):

```bash
ENES_RELEASE_HOST=deploy@169.58.198.111 \
  scripts/publish_windows_release.sh --exe ~/Downloads/ENES_Setup.exe
```

Skript uni `enes-windows-<versiya>.exe` nomiga ko'chiradi: cloud
faqat shu nomni taniydi (`latest_windows_release`).

`CLOUD_URL` majburiy: u o'rnatuvchiga bake qilinadi va yangi mijoz
pairing kod bilan yuklaganda dastur cloudga o'zi ulanadi. Usiz sehrgar
manzilni qo'lda so'raydi (0.6.4 da bir marta shu unutilgan).

Serverga tushishi bilan: sayt tugmasi yangi versiyani ko'rsatadi,
qurilmalar 15 daqiqa ichida o'zi yangilanadi (`auto` siyosatda).
Tarqatish tartibi — pastdagi "Bosqichli tarqatish" bo'limi.

### Yangi o'rnatishlar uchun (`/downloads/sotqin-installer.sh`)

`.env.production` da ikkita qatorni yangilang va `deploy_cloud.sh` ni
qayta ishlating:

```
ENES_SOTQIN_RELEASE_URL=https://<domen>/releases/enes-sotqin-0.6.1.tar.gz
ENES_SOTQIN_RELEASE_SHA256=<sign_release.py chop etgan sha256>
```

Busiz `/downloads/sotqin-installer.sh` **503** qaytaradi — bu ataylab:
yarim sozlangan cloud ishlamaydigan o'rnatish buyrug'ini bermasligi kerak.

---

## Qurilmani yangilash

```bash
sudo /opt/enes/venv/bin/python \
  /opt/enes/current/scripts/apply_signed_update.py \
  --fetch-version 0.6.1 --cloud https://<domen>
```

Qo'lda ko'chirilgan fayllar bilan (zaxira yo'l):

```bash
sudo /opt/enes/venv/bin/python \
  /opt/enes/current/scripts/apply_signed_update.py \
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
so'raladi. Shu sababdan kamerasiz stendda `enes-retail` ishga
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
readlink -f /opt/enes/current     # eski versiya
curl -s 127.0.0.1:8742/health | head
```

O'n daqiqa, va aynan shu narsa yangilanishni mijoz qurilmasida
ishlatishga asos beradi.

## Yangilanishdan keyin

```bash
readlink -f /opt/enes/current                  # yangi versiya
curl -s 127.0.0.1:8742/health                       # versiya mos kelsin
ls /opt/enes/releases/<versiya>/models/retail/  # model joyida
systemctl status enes-sotqin enes-retail
python /opt/enes/current/scripts/sotqin_preflight.py
cat /opt/enes/shared/logs/update.log            # yangilanishlar tarixi
```

Bir daqiqa ichida cloud panelida ham yangi `app_version` ko'rinadi —
heartbeat uni allaqachon yuboradi.

---

## Bosqichli tarqatish (Windows relizlari uchun MAJBURIY tartib)

Windows qurilmalar yangilanishni har 15 daqiqada tekshiradi — buzuq reliz
15 daqiqada **hamma** qurilmaga yetadi. Shuning uchun tartib qat'iy va u
endi bitta buyruqda (`scripts/rollout.py`), admin panelda har do'konni
alohida bosish emas:

```bash
export ENES_CLOUD_ADMIN_KEY=...        # parol menejeridan

# 1. Relizdan OLDIN: faqat sinov do'koni yangilansin
python3 scripts/rollout.py --sinov <sinov_site_id>

# 2. Relizni chiqaring (yuqoridagi publish skripti)

# 3. 24 soat kuzating — qurilma versiyasi ustuniga qarang
python3 scripts/rollout.py --holat

# 4. Muammo bo'lmasa hammaga oching
python3 scripts/rollout.py --hammaga
```

Favqulodda holat — buzuq reliz allaqachon tarqala boshlagan bo'lsa,
har do'konni alohida to'xtatishga ulgurib bo'lmaydi:

```bash
python3 scripts/rollout.py --toxtat     # hamma qurilma darhol to'xtaydi
python3 scripts/rollout.py --davom      # tuzatilgach qayta yoqiladi
```

Himoya qatlamlari (`enes/local/updater.py`):

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

## Yangi versiya do'kongacha: to'liq zanjir

```
versiya ko'tariladi  →  make windows-release   (quriladi + imzolanadi)
                     →  publish_windows_release.sh  (serverga + tekshiruv)
                     →  rollout.py --sinov      (avval bitta do'kon)
                     →  qurilma 15 daqiqada o'zi oladi
                     →  30 daqiqada panel ko'tarilmasa — o'zi orqaga qaytadi
                     →  rollout.py --hammaga    (24 soatdan keyin)
```

Qurilma tomonida hech qanday qo'l ishi yo'q: yangilanish vazifasi
(`ENES Monitoring Update`, SYSTEM, har 15 daqiqa) o'rnatuvchi bilan birga
kelgan va u imzoni har safar tekshiradi.

---

## Hali yo'q: cloud'dan boshqariladigan tarqatish

Hozir yangilanish har bir qurilmada qo'lda ishga tushiriladi. Cloud'dan
"barcha qurilmalarni 0.6.1 ga o't" deyish uchun **huquqlarni ajratish**
kerak: `enes-sotqin` xizmati `User=chaqimchi`, `NoNewPrivileges=true`
va `ProtectSystem=strict` bilan ishlaydi, ya'ni agent na
`/opt/enes/releases` ga yoza oladi, na `systemctl` chaqira oladi.

Rejalashtirilgan yechim: agent heartbeat javobini o'qib
`shared/data/update-request.json` yozadi, root egaligidagi systemd `.path`
unit uni kuzatadi va `enes-update.service` ni ishga tushiradi. Agent
hech qachon root olmaydi, applier esa cloudga ishonmaydi — imzoni baribir
tekshiradi.
