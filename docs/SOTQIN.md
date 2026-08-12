# Sotqin R1 — lokal video gateway

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

Sotqin ONVIF/RTSP, hardware decode, non-AI motion/sifat filtri, frame/clip,
shifrlangan, priority asosidagi 3 kun/40 GB event buffer va cloud uploadni
bajaradi. To'liq video arxiv faqat NVR ichida qoladi. AI klassifikatsiya,
yuz identifikatsiyasi va biznes xulosalari faqat O'zbekistondagi Chaqimchi
Cloud GPU qatlamida bajariladi. NVR to'liq video arxivni saqlaydi.

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

## Qolgan media bosqichi

1. ONVIF discovery va NVR kanal ro'yxati.
2. FFmpeg/QSV frame/clip worker, motion/sifat filtri va sampling policy.
3. Shifrlangan priority buffer va resumable upload.
4. 4/8 kamera, internet uzilishi, elektr uzilishi va rollback soak-testlari.
