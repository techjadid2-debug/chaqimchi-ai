# Sotqin R1 — lokal qurilma va edge AI

**Sotqin** Chaqimchi AI'ning barcha bizneslar uchun yagona lokal qurilmasi.
Mijoz NVR va kameralar bilan birga Sotqinni buyurtma qiladi; dastur oldindan
o'rnatiladi va pairing orqali Chaqimchi Cloud'ga bog'lanadi.

## R1 apparat profili

- Intel N100 x86_64, Intel Quick Sync Video;
- 8 GB RAM va 128 GB NVMe;
- kamera/NVR va internet uchun 2 ta Ethernet;
- TPM 2.0, aktiv sovutish, BIOS auto-power-on va UPS;
- Ubuntu Server 24.04 LTS;
- 4 kamera kafolatlangan; 8 kamera 72 soatlik qabul testidan keyin.

Ichki profil kodi: `SOTQIN-N100-8-128-R1`. Mijoz uchun nom doim **Sotqin**.

## Vazifa chegarasi

> **Bu chegara o'zgardi.** Avvalgi rejada Sotqin AI umuman ishlatmaydigan
> gateway edi. Amalda bu ishlamadi: har kadrni cloudga yuborish uchun
> do'kondan chiqadigan internet kanali ham, cloud GPU narxi ham yetmaydi.
> Yechim — **yengil** inferensni qurilmada bajarish, qimmatini cloudda
> qoldirish.

**Qurilmada** (`chaqimchi-retail.service`):

- ONVIF/RTSP, hardware decode (QSV), harakat va sifat filtri;
- **odam deteksiyasi** — `person-detection-retail-0013` (OpenVINO, iGPU,
  2.3 GFLOPs, Apache 2.0). Bu N100 ko'taradigan darajadagi yuk;
- tracking, kirish/chiqish sanog'i, dwell, navbat uzunligi;
- kamera yopilgani/burilgani, ish vaqtidan tashqari harakat;
- qoida dvigateli (severity, cooldown, harakatlar) — qoidalar cloud'dan
  config sifatida keladi;
- hodisa klipi (`-c copy`, dekodlashsiz) va 3 kun/40 GB event buffer.

**Cloudda**:

- ko'rish agenti (Claude) — "nima bo'layapti" degan savolga javob. Bu pul
  sarflaydi, shuning uchun qurilmada emas va tormozlar bilan ishlaydi;
- hodisa arxivi, admin panel, Telegram xabarlari, obuna va to'lov;
- ko'p obyekt bo'yicha hisobotlar.

**NVR'da**: to'liq video arxiv. Sotqin uni takrorlamaydi.

Nega shunday bo'lingani va qurilma sig'imi qanday hisoblangani:
[chaqimchi_ai/retail/README.md](../chaqimchi_ai/retail/README.md).

## Control plane (hozir implementatsiya qilingan)

- `chaqimchi_ai.sotqin_agent` — yengil agent;
- `scripts/install_sotqin.sh` — atomik release katalogiga installer;
- `scripts/pair_sotqin.py` — pairing va hardware identity;
- `chaqimchi-sotqin.service` — systemd supervision;
- `/api/v1/sotqin/claim`, `/heartbeat`, `/config`, `/config/ack`;
- admin kamera inventari: RTSP credentiallari cloud DBda Fernet bilan
  shifrlanadi, admin ro'yxatida qayta ko'rinmaydi;
- Sotqin `ffprobe` bilan RTSP substreamni tekshiradi va codec/rezolyutsiya/FPS
  holatini cloudga qaytaradi;
- product/model/revision/serial, health va config ACK/NACK admin panelda;
- config 0600 permission bilan atomik saqlanadi;
- Sotqin uchun `chaqimchi-sotqin`/`x86_64` imzolangan update va rollback.

Eski `/api/v1/edge/*`, `pair_edge.py` va `install_edge.sh` vaqtincha
compatibility alias bo'lib qoladi.

## O'rnatish

```bash
sudo ./scripts/install_sotqin.sh
sudo /opt/chaqimchi/venv/bin/python \
  /opt/chaqimchi/current/scripts/pair_sotqin.py \
  --cloud https://YOUR_DOMAIN --code ABC123
sudo systemctl start chaqimchi-sotqin
```

Pairingdan so'ng `/etc/chaqimchi/sotqin.env` ichida device token, Intel modeli,
R1 revision va serial saqlanadi. Secret fayl permission'i `0600`.

## Kamera ulash

1. Admin `PUT /api/v1/admin/sites/SITE_ID/camera-inventory/camera-01` orqali
   kamera nomi va `rtsp://.../sub` manzilini yozadi.
2. Sotqin keyingi config poll'da manzilni HTTPS orqali oladi va lokal 0600
   config cache'iga atomik saqlaydi.
3. Sotqin `ffprobe` bilan streamni tekshiradi; admin inventory'da online/offline,
   codec, rezolyutsiya va FPS ko'rinadi.

RTSP/NVR loginlari `.env` yoki browserga qaytmaydi. Production cloud uchun
`CHAQIMCHI_CAMERA_SECRET_KEY` alohida Fernet kaliti bo'lishi shart.

## Do'kon analitikasi xizmati

Qurilmadagi AI alohida jarayonda ishlaydi:

```bash
systemctl start chaqimchi-retail     # deploy/chaqimchi-retail.service
```

Alohida bo'lgani ataylab: detektor yoki ffmpeg yiqilsa control plane,
heartbeat va yuz tanish ishlashda davom etadi. Sozlama `CHAQIMCHI_CONFIG`
ko'rsatgan faylning `scene:` va `retail:` bo'limlarida.

## Qolgan bosqichlar

| # | Vazifa | Holat |
|---|--------|-------|
| 1 | ONVIF discovery va NVR kanal ro'yxati | [ ] |
| 2 | Frame/clip worker, motion/sifat filtri, sampling | [x] `retail/runner.py` |
| 3 | Hodisa buferi (3 kun / 40 GB) va cloud upload | [x] ring buffer + outbox |
| 4 | 4/8 kamera, internet/elektr uzilishi, rollback soak-testlari | [ ] |

Ikkita ma'lum bo'shliq:

- **Kamera ro'yxati ikki joyda.** Cloud inventarida RTSP manzillari bor
  (`camera-inventory`), lekin do'kon analitikasi xizmati kameralarni lokal
  YAML dan o'qiydi. Hozircha ikkalasini qo'lda mos qilish kerak; keyingi
  qadam — xizmat `sotqin-config.json` dan o'qishi.
- **Dekodlash hozircha dasturiy.** Profilda `hardware_decode: qsv` yozilgan,
  lekin retail xizmati OpenCV/FFmpeg orqali oqim ochadi va QSV so'ramaydi.
  Substream (640×360) uchun bu odatda yetarli — narxi
  `scripts/benchmark_n100.py` da o'lchanadi.
