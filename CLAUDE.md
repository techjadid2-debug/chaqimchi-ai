# ENES Monitoring — agent uchun kirish

> Bu faylni Claude Code har sessiyada o'zi o'qiydi. Qisqa turadi;
> tafsilot havolalarda.

## Bu nima

Do'kon videoanalitikasi. Mijozning **o'z Windows kompyuteri** + NVR/IP
kamera (ko'pi bilan **4 ta**) + bizning cloud. Uzluksiz video NVR'da
qoladi, tahlil do'kon kompyuterida lokal ketadi, cloudga faqat hodisa,
ruxsat etilgan media, hisobot va health boradi.

**ENES Box** (Intel N100 mini-PC) — keyingi bosqich mahsuloti:
kodi repoda ishlaydi, lekin sotuv fokusi hozir Windows yo'lida.

Tizim o'g'rilik, jinoyat yoki niyatni **taxmin qilmaydi**.

## AVVAL SHUNI O'QI

| Fayl | Nima uchun |
|---|---|
| [docs/ISH_DAFTARI.md](docs/ISH_DAFTARI.md) | **Birinchi shu.** Joriy holat, keyingi ish, ochiq muammolar, tuzoqlar va o'zgarishlar tarixi |
| [docs/ARXITEKTURA_XARITASI.md](docs/ARXITEKTURA_XARITASI.md) | Qayerda nima turadi — 9 ta chizma + "qaysi faylda" jadvallari |
| [docs/DOKON_MVP.md](docs/DOKON_MVP.md) | Mahsulot kontrakti: nima sotiladi, nima sotilmaydi |
| [docs/AUDIT_TAHLIL.md](docs/AUDIT_TAHLIL.md) | 2026-08-25 auditi — 22 topilma va tuzatish holati. Muammo ustida ishlashdan oldin shu yerda yozilgan-yozilmaganini qarang |
| [docs/PRODUCTION_RUNBOOK.md](docs/PRODUCTION_RUNBOOK.md) | Env, zaxira, deploydan keyingi tekshiruv |

## Qattiq qoidalar — buzilmasin

1. **Kamera soni faqat `enes/limits.py` dan** (`SHOP_MAX_CAMERAS = 4`).
   Ilgari uch joyda alohida yozilgan edi va bir joyni o'zgartirish
   qolganlarini jimgina eskirtirardi.

2. **Versiya ikki joyda:** `enes/__init__.py` va `pyproject.toml`.
   Ikkalasini birga ko'taring — `tests/test_sotqin_release_contract.py`
   mosligini qulflaydi. (`importlib.metadata` ishlatilmaydi: paket
   qurilmada pip bilan o'rnatilmaydi.)

3. **`ENES_WINDOWS_INSTALLER_URL` pinini qayta qo'ymang.** Bu pin
   tufayli mijozlar 3 versiya orqada qolgan edi. Endi manzil
   `latest_windows_release()` dan keladi — eng yangi imzolangan reliz
   o'zi tanlanadi.

4. **Sayt va'dalari qulflangan.** `FORBIDDEN_CLAIMS`
   (`tests/test_static_pages.py`) — bajarilmayotgan va'da qaytib kela
   olmaydi. Yangi va'da qo'shishdan oldin: "buni bugun yetkazib bera
   olamizmi?"

5. **Yuzga tegadigan har marshrut `require_biometric_access()` dan
   o'tsin** (`cloud/main.py:877`). Ikkita marshrut umuman tekshirmasdi.

6. **Deploy — faqat `scripts/deploy_cloud.sh` orqali** (u zaxira talab
   qiladi). Serverda git yo'q: kod `rsync` bilan boradi.

7. **Modul ichini o'qish yetarli emas — chaqiruv joyini ham ko'ring.**
   Audit shu sababdan ikki marta xato topilma yozdi (standart qiymatni
   o'qib, production nima uzatishini tekshirmadi).

## Buyruqlar

```bash
make lint                 # ruff: enes cloud tests scripts
make test                 # TS typecheck + i18n/sayt --check + pytest (~2 330 test)
make ui-install           # frontend/node_modules yo'q bo'lsa

make run-cloud            # cloud API      → :8750
make run-local            # do'kon paneli  → :8760
make run-retail           # AI zanjiri (kamera kerak)
```

**Windows reliz** (macOS'da ishlaydi, `PYTHONPATH` SHART — usiz oxirgi
qadam yiqiladi):

```bash
# 1) versiyani enes/__init__.py va pyproject.toml da ko'taring
# (cloud manzili F7 cutovergacha api.chaqimchi.uz, keyin api.enes.uz)
PYTHONPATH="$PWD" ENES_DEFAULT_CLOUD_URL=https://api.chaqimchi.uz \
  python scripts/build_windows_payload.py
makensis -V2 scripts/windows_installer.nsi
PYTHONPATH="$PWD" ENES_RELEASE_HOST=root@169.58.198.111 \
  ./scripts/publish_windows_release.sh --exe releases/ENES_Setup.exe
```
Imzo kaliti: `~/.enes/sotqin-release-signing.pem` (hali `~/.chaqimchi/` da
bo'lsa skript o'sha yerdan oladi — `mv ~/.chaqimchi ~/.enes` qilib qo'ying).

**Cloud deploy:**

```bash
rsync -az --delete ... root@169.58.198.111:/home/deploy/enes/
ssh root@169.58.198.111 'cd /home/deploy/enes && \
  set -a && . /etc/enes/backup.env && set +a && \
  ENES_COMPOSE_FILE=docker-compose.enes.yml ./scripts/deploy_cloud.sh'
```
To'liq `--exclude` ro'yxati: [docs/DEPLOY_TARIFLAR.md](docs/DEPLOY_TARIFLAR.md) §3.
Zaxira kalitlari serverdagi `/etc/enes/backup.env` da (repoda emas).

## Rebrend holati (2026-09, `enes-rebrend` shoxi)

Chaqimchi AI → **ENES Monitoring**.  Kod, sayt, panel (UZ/RU/EN),
Telegram, env nomlari, paket (`chaqimchi_ai` → `enes`) almashdi.
**Ataylab qolgan ko'priklar** — o'chirish alohida qaror (`tests/test_brand.py`
ro'yxati): `chaqimchi_ai/` (eski paket nomi — pilot kompyuteridagi
yangilanish vazifasi), `enes/envcompat.py` (`CHAQIMCHI_*` env),
eski reliz prefiksi (`chaqimchi-windows-*`), eski Windows vazifa/papka
nomlari (`paths.py`, `autostart.py`, NSI).  **Egadan kutilmoqda (F7):**
`enes.uz` DNS, bot @username, yuridik nom/rekvizit, Payme/Click;
shundan keyin domen (`chaqimchi.uz`) va `@chaqimchi_ai_bot` almashadi.
Cutover ro'yxati `docs/ISH_DAFTARI.md` da.

## Uslub

- **Izohlar o'zbekcha va "NEGA" ni tushuntiradi**, "nima" ni emas. Kod
  o'zi nima qilishini aytadi; izoh qaror sababini saqlaydi. Loyihadagi
  mavjud izohlarga qarang — ular naqsh.
- Sonlar va chegaralar uchun sabab yozilsin ("6 soniya: uchta oqim
  sinaladi, ya'ni eng yomon holatda ~18 soniya").
- Commit: `tur(soha): o'zbekcha jumla` — `feat(panel):`, `fix(moliya):`,
  `docs:`, `chore:`. Natija tilida yozing, kod tilida emas.
- Mijozga ko'rinadigan matn — o'zbekcha, texnik jargonsiz.
- Yangi funksiya taklifidan oldin [docs/DOKON_MVP.md](docs/DOKON_MVP.md)
  ga solishtiring.

## Ish tugagach — MAJBURIY

[docs/ISH_DAFTARI.md](docs/ISH_DAFTARI.md) ni yangilang:

1. Tepadagi **HOZIRGI HOLAT** va **KEYINGI ISH** ni to'g'rilang.
2. Yangi tuzoq yoki ochiq muammo chiqqan bo'lsa tegishli bo'limga qo'shing.
3. **Tarix** bo'limining tepasiga yozuv qo'shing (shablon o'sha faylda).

Bu 2 daqiqalik ish keyingi sessiyaga soatlab qidiruvni tejaydi.
