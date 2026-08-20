# Uch tarif relizini serverga chiqarish

Bu reliz odatdagi `deploy_cloud.sh` dan **farq qiladi**: yuz tanish
modeli almashtirildi, ya'ni serverda ikkita qo'shimcha qadam bor.
Ularsiz davomat jimgina ishlamay qoladi — xodim kelib turadi, jadval
esa bo'sh.

Branch: `tariflar-3-ta` · Server: Contabo `169.58.198.111`

---

## Nima o'zgargani (qisqacha)

| O'zgarish | Ta'siri |
|---|---|
| Uch tarif: Boshlang'ich 149 000 / Biznes 299 000 / Tarmoq | Sayt va admin paneli |
| Mavjud `lite` mijozlar **ko'chirilmadi** | Ular $20 da qoladi, funksiyalari o'zgarmaydi |
| Kamera soni tarifdan | Boshlang'ich saytida 3-kamera qo'shilmaydi |
| Yuz modeli → OpenVINO OMZ (Apache-2.0) | **Model yuklab olish + rasmlarni qayta hisoblash** |
| Bosh sahifa qayta qurildi | Yangi rasmlar, yangi CSS/JS tokenlari |
| Obuna tugashi majburlanadi | `expired`/`suspended` → funksiya berilmaydi |
| Kassa va javon nazorati | **Qurilma relizi 0.6.9 kerak** |

---

## 1. Oldindan tekshirish (lokal, 2 daqiqa)

```bash
cd "/Users/abdulvosit/Desktop/Chaqimchi AI"
git checkout tariflar-3-ta
.venv/bin/python -m ruff check chaqimchi_ai cloud tests scripts
.venv/bin/python -m pytest -q
```

Ikkalasi ham toza bo'lishi shart. Toza bo'lmasa — deploy qilinmaydi.

---

## 2. Zaxira (majburiy — bu relizda baza sxemasi o'zgaradi)

`employee_faces` jadvalidagi embeddinglar **qayta yoziladi**. Xato
bo'lsa orqaga qaytishning yagona yo'li — zaxira.

```bash
ssh -i .deploy_keys/chaqimchi_prod root@169.58.198.111
/home/deploy/chaqimchi-ai/scripts/backup_production.sh
ls -la /var/backups/chaqimchi/   # bugungi fayl turibdimi
```

---

## 3. Kodni chiqarish

```bash
# Lokal mashinada
cd "/Users/abdulvosit/Desktop/Chaqimchi AI"
rsync -az --delete \
  --exclude '.git' --exclude '.venv' --exclude 'build' --exclude 'releases' \
  -e "ssh -i .deploy_keys/chaqimchi_prod" \
  ./ root@169.58.198.111:/home/deploy/chaqimchi-ai/
```

`root@` ataylab: `/home/deploy/chaqimchi-ai` fayllari uid 501 egaligida
va `deploy` foydalanuvchisi ularga yoza olmaydi.

---

## 4. Yuz modellarini o'rnatish (YANGI qadam)

```bash
ssh -i .deploy_keys/chaqimchi_prod root@169.58.198.111
cd /home/deploy/chaqimchi-ai

docker compose -f docker-compose.chaqimchi.yml --env-file .env.production \
  exec cloud python scripts/fetch_face_models.py
```

Kutiladigan natija — oltita fayl (`.xml` + `.bin`), har biri sha256 dan
o'tadi:

```
OK: face-detection-retail-0005.xml (219 KB)
OK: face-detection-retail-0005.bin (1993 KB)
OK: landmarks-regression-retail-0009.xml (64 KB)
OK: landmarks-regression-retail-0009.bin (372 KB)
OK: face-reidentification-retail-0095.xml (342 KB)
OK: face-reidentification-retail-0095.bin (2161 KB)
```

Checksum mos kelmasa skript to'xtaydi va hech narsa o'rnatmaydi — bu
to'g'ri xatti-harakat, qayta ishga tushiring.

---

## 5. Deploy

```bash
CHAQIMCHI_COMPOSE_FILE=docker-compose.chaqimchi.yml ./scripts/deploy_cloud.sh
```

Ko'tarilgach:

```bash
curl -s https://api.chaqimchi.uz/health | head
curl -s https://api.chaqimchi.uz/api/v1/public/pricing | jq '.plans[] | {code, monthly_uzs}'
```

Kutiladigan javob:

```json
{"code": "boshlangich", "monthly_uzs": 149000}
{"code": "biznes",      "monthly_uzs": 299000}
{"code": "tarmoq",      "monthly_uzs": null}
```

---

## 6. Xodim rasmlarini qayta hisoblash (YANGI, MAJBURIY)

Yangi model **256** o'lchamli vektor beradi, eskisi **512** edi. Qayta
hisoblanmagan yozuv moslashga umuman kirmaydi — xodim "tanilmadi" bo'lib
qoladi va hech qanday xato chiqmaydi.

Avval nima bo'lishini ko'ring:

```bash
docker compose -f docker-compose.chaqimchi.yml --env-file .env.production \
  exec cloud python scripts/reembed_faces.py --dry-run
```

Keyin bajaring:

```bash
docker compose -f docker-compose.chaqimchi.yml --env-file .env.production \
  exec cloud python scripts/reembed_faces.py
```

Skript qayta ishga tushirishga chidamli: yarim yo'lda uzilsa davom
ettirsa bo'ladi. "YUZ TOPILMADI" chiqqan rasmlar bazada eski holicha
qoladi va moslashda ishlatilmaydi — mijozdan yangi rasm so'rash kerak.

**Tekshirish:** mijoz panelida (`app.chaqimchi.uz` → Xodimlar) xodim
kamera oldidan o'tsin va "Bugun" jadvalida ko'rinsin.

---

## 7. Chegarani o'lchash (tavsiya, majburiy emas)

Standart moslik chegarasi **0.6** — sun'iy sinovda o'lchangan. Haqiqiy
do'kon kadrlarida boshqacha bo'lishi mumkin:

```bash
docker compose -f docker-compose.chaqimchi.yml --env-file .env.production \
  exec cloud python scripts/calibrate_face_threshold.py
```

Har xodimda kamida **2 ta rasm** bo'lishi kerak, aks holda "bir xil
odam" juftligi chiqmaydi. Skript raqam tavsiya qilsa —
`CHAQIMCHI_FACE_MATCH_THRESHOLD` ga qo'ying va konteynerni qayta
ishga tushiring.

Ikki taqsimot kesishsa skript raqam **taklif qilmaydi**: bu chegara
masalasi emas, rasm sifati masalasi.

---

## 8. Saytni ko'z bilan tekshirish

- `https://chaqimchi.uz` — uchta tarif kartasi, o'rtadagisi "Eng
  ommabop", narxlar 149 000 va 299 000;
- hero'dagi izometrik sahna qimirlayotgan bo'lsin (nur suriladi,
  Telegram kartasi chiqadi);
- "Nima ko'rasiz" bo'limida ikkita panel ekrani;
- telefonda: gorizontal skroll yo'q, Biznes kartasi birinchi turadi;
- `https://chaqimchi.uz/hamkorlik` va `/rozilik-shabloni` —
  tugmalar uslubli ko'rinsin (ilgari oddiy matn edi).

Brauzer keshi eski CSS ni ko'rsatsa — `?v=` tokeni o'zgargan, ya'ni
majburiy yangilash kerak emas. Ko'rinmasa `Cmd+Shift+R`.

---

## 9. Qurilma relizi 0.6.9 (alohida, keyinroq)

Quyidagilar **qurilma tomonida** ishlaydi va yangi `.exe` talab qiladi:

- tarifdagi kamera chegarasi (`retail.max_cameras`);
- kassa nazorati (`checkout_unattended`, `checkout_second_till`);
- javon nazorati (`shelf_empty`).

Cloud tomoni ularsiz ham ishlaydi — shunchaki bu hodisalar hali
kelmaydi. Reliz `docs/RELIZ_VA_OTA.md` dagi bosqichli tarqatish bilan:
avval o'z qurilmangiz, 24 soatdan keyin hammaga.

---

## Orqaga qaytarish

Agar biror narsa buzilsa:

```bash
cd /home/deploy/chaqimchi-ai
git checkout soddalashtirish-bosqich-0     # oldingi holat
CHAQIMCHI_COMPOSE_FILE=docker-compose.chaqimchi.yml ./scripts/deploy_cloud.sh
```

**DIQQAT:** kod orqaga qaytsa, `reembed_faces.py` yozgan 256 o'lchamli
embeddinglar eski kod uchun yaroqsiz bo'lib qoladi — davomat ishlamaydi.
Bu holatda 2-qadamdagi zaxiradan `employee_faces` jadvalini tiklang:

```bash
./scripts/restore_production.sh --check   # avval quruq mashq
```

Qolgan hamma narsa (tariflar, sayt, obuna majburlash) orqaga qaytishda
muammosiz — ular faqat kodda.
