# Bulutdan sozlash

Do‘kon egasi kamerani, chiziqni va zonani **bulut panelidan** sozlaydi.
Do‘kon kompyuteri oldida o‘tirish shart emas — telefon ham yetadi.

Bu hujjat oqimning texnik tomonini yozadi. Mijozga beriladigan matn
saytda: `/install` (`cloud/static/install.html`).

---

## Nega bunday qilindi

Kamera qidirish do‘kon tarmog‘idan bajarilishi **shart**: WS-Discovery
multicast, `/24` sweep va xususiy IP ga SOAP so‘rov. Bulut sahifasi u
yerga kira olmaydi va kirmasligi ham kerak — lokal API ataylab faqat
`127.0.0.1` dan keladigan so‘rovni qabul qiladi (DNS-rebinding himoyasi,
`chaqimchi_ai/local/app.py`).

Shuning uchun yo‘nalish teskari qilindi: **bulut buyruq beradi, qurilma
bajaradi**. Bu `live_requested`/`preview_requested` naqshining aynan
takrori, faqat javob rasm emas, JSON.

Ikkinchi qaror: **qurilma o‘zini tanishtiradi, egasi uni o‘ziga
biriktiradi**. Eski pairing kodni admin yoki usta yaratardi; o‘rnatgandan
keyin ro‘yxatdan o‘tgan ega esa kimdan kod so‘rashini bilmasdi.

---

## Ulanish oqimi

```
o‘rnatish  →  POST /api/v1/public/device-hello        (qurilma → bulut)
           →  brauzer app.chaqimchi.uz/owner?connect=<token> da ochiladi
           →  ega ro‘yxatdan o‘tadi (quick-trial) yoki kiradi
           →  POST /api/v1/owner/devices/claim        (ega → bulut)
           →  POST /api/v1/public/device-handover     (qurilma → bulut)
           →  shundan keyin hammasi mavjud kanal orqali: heartbeat ⇄ /edge/config
```

| Endpoint | Auth | Vazifa |
|---|---|---|
| `POST /api/v1/public/device-hello` | yo‘q | `{fingerprint, label, …}` → `{connect_token, connect_url, verify_code, panel_url}` |
| `GET /api/v1/public/device-connect?token=` | yo‘q | Tasdiqdan oldin qurilmani tasvirlaydi. **Sir yo‘q** |
| `POST /api/v1/owner/devices/claim` | `require_active_owner` | Kutayotgan qurilmani egasining saytiga biriktiradi |
| `POST /api/v1/public/device-handover` | yo‘q | `pending` / `claimed` (+ hisob ma’lumotlari) / `expired` |

Qurilma tomonida: `chaqimchi_ai/local/cloud_link.py` →
`hello()`, `handover()`, `poll_connection()`. Holat `connect.json` da,
`C:\ProgramData\Chaqimchi\` ichida.

`poll_connection()` fon siklidan har 20 soniyada chaqiriladi. Ega
tasdiqlagan lahzada qurilma `cloud_sync` ni o‘zi to‘ldiradi — mijoz
do‘kon kompyuteriga qaytib borishi shart emas.

### Xavfsizlik chegaralari

* `connect_token` 256 bit, faqat HTTPS javobida va o‘sha kompyuter
  ekranida. Panel uni o‘qishi bilan `history.replaceState` orqali manzil
  qatoridan olib tashlaydi (tarix, skrinshot, `Referer`).
* `verify_code` **ikkala ekranda** ko‘rsatiladi. Mos kelmasa —
  tasdiqlamaslik kerak. Bu «qo‘shnining kompyuterini tasdiqlab
  yubordim» xatosining yagona to‘sig‘i.
* Sayt **sessiyadan** olinadi, so‘rovdan emas — begona saytga
  biriktirish imkonsiz.
* Noma’lum, eskirgan va ishlatilgan token uchun **bir xil** 404
  (orakul bermaslik).
* `device_token` `pending_devices` jadvalida **saqlanmaydi**: ega
  tasdiqlaganda faqat `status='approved'` yoziladi, haqiqiy token
  qurilma kelib so‘raganda yaratiladi. Bazada egasiz sir yotmaydi.
* Muddatlar: `CONNECT_TOKEN_TTL_SEC = 3600`, qator 7 kunda tozalanadi.

### Orqaga qaytish

`CHAQIMCHI_DEVICE_HELLO=0` → `device-hello` 404 qaytaradi va yangi
dastur **eski yo‘lga** (sehrgar + pairing kod) tushadi. Dala’dagi
qurilmalar ishlashda davom etadi.

---

## Skanerlash oqimi

Ega panelda «Qidirish» ni bosadi → `POST /api/v1/owner/scan` →
heartbeat javobida `job_requested` → qurilma bajaradi → natija bulutga.

| Turi | Nima qiladi | Muddat |
|---|---|---|
| `lan_scan` | WS-Discovery + `/24` sweep | 120 s |
| `onvif` | ONVIF profillarini so‘raydi | 60 s |
| `channels` | NVR kanallarini topadi | 150 s |
| `probe` | Bitta kadr oladi (sinov rasmi) | 45 s |

Qurilma tomonida: `chaqimchi_ai/local/cloud_jobs.py`.

**Topshiriq ALOHIDA oqimda bajariladi.** Skaner 90 soniyagacha
cho‘zilishi mumkin, heartbeat esa har 20 soniyada ketishi kerak. Bitta
oqimda bo‘lsa bulut qurilmani «oflayn» deb belgilardi va egasi aynan
panelga eng ko‘p qaraydigan daqiqada jonli ko‘rishni yo‘qotardi. Buni
`tests/test_local_jobs.py` qulflaydi.

Navbat xotirada va `maxsize=1`: ikki skaner bir vaqtda ishlasa ular bir
xil multicast portini talashib, ikkalasi ham hech nima topmasdi.

### NVR paroli brauzerga chiqmaydi

Skaner natijasidagi to‘liq RTSP manzili (u parol bilan keladi) Fernet
bilan shifrlanib `device_jobs.result_enc` da qoladi. Brauzerga
redaksiyalangan ko‘rinish beriladi: har `rtsp_url` o‘rniga `safe_url`
(`rtsp://…@host:port/path`) va `stream_ref` indeksi.

Sinash ham, saqlash ham **indeks** bilan ishlaydi:

```
POST /api/v1/owner/scan            {kind: "probe", from_job: "…", stream_ref: 2}
POST /api/v1/owner/cameras/from-scan  {job_id: "…", stream_ref: 2, label: "Kirish"}
```

Server manzilni shifrlangan natijadan o‘zi ochadi. Xom `rtsp_url` ni
qabul qiladigan yo‘l ataylab **yo‘q** — u bo‘lganda parol brauzer
tarixiga, log’ga va skrinshotga tushardi.

Tekshiruv: `tests/test_device_jobs.py`, `tests/test_cloud_rtsp_redact.py`.

---

## Ma’lum assimetriya

`cloud_config.apply()` bo‘sh kamera ro‘yxatini **e’tiborsiz
qoldiradi** — mijoz kamerani lokal sehrgarda qo‘shgan bo‘lsa, bulutdagi
bo‘sh javob uni o‘chirib yubormasligi kerak.

Oqibati: bulutdagi **oxirgi** kamerani o‘chirish qurilmada aks etmaydi.
Panelda bu haqda matn bor. To‘liq yechim — `/edge/config` ga
`cameras_authoritative` bayrog‘i qo‘shish (alohida reliz, alohida
qaror).

---

## Tegishli fayllar

| Nima | Qayerda |
|---|---|
| Bulut: jadvallar va API | `cloud/store.py`, `cloud/main.py` |
| Bulut: RTSP redaksiyasi | `cloud/rtsp.py` |
| Panel: ulash ekrani | `frontend/src/Connect.tsx` |
| Panel: kamera sehrgari | `frontend/src/SetupCameras.tsx` |
| Panel: chiziq va zona | `frontend/src/GeometryEditor.tsx` |
| Qurilma: ulanish | `chaqimchi_ai/local/cloud_link.py` |
| Qurilma: topshiriqlar | `chaqimchi_ai/local/cloud_jobs.py` |
| Qurilma: holat sahifasi | `chaqimchi_ai/local/static/panel.html` |
