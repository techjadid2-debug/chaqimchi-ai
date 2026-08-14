# Chaqimchi kamera mosligi va kross-platform o‘rnatish rejasi

## Hozirgi holat

| Qism | Holat | Izoh |
|---|---|---|
| Hikvision / HiLook RTSP | Qisman tayyor | Odatdagi RTSP substream shabloni panelga qo‘shilgan; model va firmware obyektning o‘zida probe qilinadi. |
| Dahua RTSP | Qisman tayyor | Odatdagi RTSP substream shabloni panelga qo‘shilgan; model va firmware obyektning o‘zida probe qilinadi. |
| Boshqa ONVIF kameralar | Qo‘lda | RTSP URI qo‘lda kiritiladi. ONVIF avtomatik qidiruv va URI olish hali yo‘q. |
| Linux installer | Tayyor | Ubuntu Server 24.04 LTS, `systemd`, pairing va checksumli bootstrap. |
| Windows installer | Yo‘q | Windows 11 x64 uchun alohida installer va xizmat qurilishi kerak. |
| Kafolatlangan sig‘im | Qabul sinovi kerak | 1–4 ta H.264 720p substream. Har bir sotiladigan N100 konfiguratsiya 72 soatlik sinovdan o‘tadi. |

Bu holatda “O‘zbekiston bozoridagi barcha kameraga tayyor” deb aytib bo‘lmaydi.
Mahsulot lokal RTSP beradigan Hikvision, HiLook, Dahua va boshqa NVR/IP kameralar
bilan ishlashi mumkin, ammo kafolat faqat laboratoriya matritsasidan o‘tgan model va
firmware’larga beriladi.

## Fizik ulanish

```text
IP kamera(lar) -- Cat5e/6 PoE --> NVR/PoE switch -- LAN --> Router/switch -- Internet
                                                       |             |
                                                       |             +-- LAN --> Sotqin N100
                                                       +-- HDMI --> Monitor (ixtiyoriy)

Sotqin N100 -- HTTPS 443, chiqish aloqasi --> Chaqimchi Cloud
Sotqin N100 -- RTSP 554, faqat lokal LAN --> NVR/kamera
```

NVR uchun public port-forwarding ochilmaydi. Sotqin NVR bilan bir LAN’da turadi va
cloud’ga faqat tashqariga HTTPS ulanish qiladi. NVR’da Chaqimchi uchun alohida,
faqat live-view huquqiga ega foydalanuvchi yaratiladi.

## 1-bosqich — kamera protokoli

1. Hikvision/HiLook va Dahua RTSP shablonlarini saqlash.
2. ONVIF Profile T va mavjud Profile S qurilmalarini LAN’dan topish.
3. Qurilma tanlanganda kanallar va stream URI’larni olish.
4. Avval H.264 substreamni tanlash; H.265/H.265+ bo‘lsa foydalanuvchiga aniq
   ogohlantirish va NVR sozlamasini almashtirish ko‘rsatmasini berish.
5. FFprobe bilan codec, resolution, FPS va 30 soniyalik barqarorlik tekshiruvi.
6. Parolni log, HTML yoki API javobiga chiqarmaslik; secret store’da shifrlash.

## 2-bosqich — yagona o‘rnatish ustasi

Linux va Windows bitta foydalanuvchi oqimidan foydalanadi:

1. Xush kelibsiz va tizim talablari.
2. Admin paneldagi bir martalik pairing kodini kiritish.
3. Lokal tarmoqni tekshirish va NVR/kameralarni qidirish.
4. Qurilma, kanal va substreamlarni tanlash.
5. Har bir kamera uchun jonli preview va stream-test.
6. Cloud’ga bog‘lash va operatsion tizim xizmatini o‘rnatish.
7. Reboot sinovi, yakuniy health check va mijoz panelini ochish.

## 3-bosqich — Windows 11 x64

- Code-signed MSI yoki EXE bootstrapper: **Next → Next → Finish**.
- Python runtime, OpenVINO modeli, FFmpeg va kerakli Microsoft runtime’larni bundle
  qilish; internetdan tasodifiy paket yuklamaslik.
- Dastur: `%ProgramFiles%\Chaqimchi\Sotqin`.
- Konfiguratsiya va log: `%ProgramData%\Chaqimchi\Sotqin`.
- AI agentlarini alohida Windows Service sifatida o‘rnatish va avtomatik start.
- Localhost setup wizard; firewall’da faqat kerakli lokal qoida.
- Signed update, rollback, repair va toza uninstall.
- Windows 10 umumiy qo‘llovi tugaganligi sababli asosiy target Windows 11 x64.
  Windows 10 faqat ESU/LTSC qurilmalar uchun alohida qabul sinovi bilan.

## 4-bosqich — Linux paketini soddalashtirish

- Ubuntu 24.04 uchun signed `.deb` paket.
- Hozirgi bir qatorli checksumli bootstrapni professional o‘rnatuvchilar uchun
  saqlab qolish.
- Windows bilan bir xil localhost setup wizard.
- `systemd`, signed update, rollback, repair va uninstall buyruqlari.

## Qabul matritsasi

Har bir qo‘llab-quvvatlanadigan kombinatsiya uchun quyidagilar yozib boriladi:

- brend, model, firmware va NVR modeli;
- RTSP yoki ONVIF Profile T/S;
- H.264 substream, resolution va FPS;
- 1, 2 va 4 kamera bilan 72 soatlik ishlash;
- elektr o‘chib-yonishi, internet uzilishi va NVR rebootidan tiklanish;
- pairing, upgrade, rollback, repair va uninstall;
- loglarda URL paroli yoki boshqa secret chiqmaganligi.

Birinchi laboratoriya to‘plami: Hikvision/HiLook NVR, Dahua NVR va kamida bitta
generic ONVIF Profile T kamera. Shu matritsa o‘tmaguncha “barcha kameralar” degan
marketing va’dasi berilmaydi.

## Hozir scope’ga kirmaydi

- lokal RTSP bermaydigan faqat vendor cloud kameralar;
- USB web-kameralar;
- analog kamerani bevosita mini-PC’ga ulash (RTSP DVR orqali mumkin);
- NVR RTSP portini internetga ochish;
- H.265+, Smart Codec yoki yopiq vendor protokoliga kafolat.
