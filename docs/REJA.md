# Chaqimchi AI — Face Core: Rivojlanish Rejasi (Roadmap)

Ushbu reja **qisqa muddat → o‘rta muddat → uzoq muddat** tartibida tuzilgan va loyiha ustuvorliklariga qarab moslashtirilishi mumkin.

## Qanday rivojlantiramiz (amaliy yo‘l xaritasi)

**1-qadam — barqaror “asos” (1–2 hafta)**  
Maqsad: loyiha har bir kompyuterda bir xil ishlaydigan bo‘lsin.

- `pyproject.toml` yoki `requirements.lock` (versiyalar qotirilgan) qo‘shish.
- `config.yaml` (yoki `.env`): `det_size`, `frame_skip`, `threshold`, kamera manbasi.
- `pytest` + `compare_faces` va `preprocess_image` uchun minimal testlar.
- `Makefile` yoki `justfile`: `fmt`, `lint`, `test`, `demo` buyruqlari.

**2-qadam — ma’lumot va API (2–4 hafta)**  
Maqsad: yadrodan tashqaridagi mahsulot qatlamlari paydo bo‘lsin.

- Embeddinglar uchun saqlash: boshlang‘ichda SQLite + `numpy` blob, keyinroq FAISS / vektor DB.
- REST (FastAPI) yoki gRPC: `embed`, `compare`, `stream` (WebSocket / chunked) endpointlari.
- Autentifikatsiya (API kalit / JWT) va tezlik cheklovi (rate limit).

**3-qadam — real vaqt sifati (paralel ish mumkin)**  
Maqsad: foydalanuvchi tajribasi va aniqlik barqaror bo‘lsin.

- Validatsiya to‘plami (o‘z suratlaringiz) + `threshold` kalibrlash.
- Kuzatuv (track ID): bir kadr ichida bir nechta yuz, vaqt bo‘yicha izchil ID.
- Anti-spoofing (agar kirish nazorati bo‘lsa) — alohida modul sifatida.

**4-qadam — deploy va kuzatuv**  
Maqsad: ishlab chiqarishga chiqarish xavfsiz bo‘lsin.

- Docker (Apple Silicon va server uchun alohida taglar yoki CPU-only build).
- CI: testlar + (ixtiyoriy) model keshi artefaktlari.
- Log/metrrika: inferens vaqti, FPS, xatolar soni (Prometheus / oddiy JSON log).

**Ustuvorlik qoidasi**: avvalo **barqarorlik va testlar**, keyin **samaradorlik optimizatsiyasi**, so‘ng **xavfsizlik va masshtab**. Shunda har bosqichda “ishlaydigan mahsulot” qoladi.

## Bosqich A — MVP (hozirgi holat)

| Vazifa | Tavsif | Holat |
|--------|--------|-------|
| FaceEngine | Modellarni yuklash, inferens, logging | Bajarildi |
| Alignment + ArcFace 512 | `norm_crop` + `get_feat` | Bajarildi |
| CoreML + CPU provayderlar | M3 uchun tezlashtirish | Bajarildi |
| Frame skip | Real vaqt samaradorligi | Bajarildi |
| Async video generator | `run_in_executor` bilan bloklanmaslik | Bajarildi |
| Cosine compare | `threshold=0.4` | Bajarildi |

## Bosqich B — Integratsiya va mahsuloddoshlik

1. **Konfiguratsiya fayli** (masalan, `yaml` / `toml`): `det_size`, `frame_skip`, `threshold`, kamera URL — kodni qayta tuzmasdan sozlash.
2. **Sog‘liq tekshiruvi (healthcheck)**: modellarning yuklanganligi, provayderlar ro‘yxati, sinov inferensi.
3. **Xatoliklarni standartlashtirish**: `FaceEngineError`, `ModelLoadError` kabi istisnolar — yuqori qatlamda toza xato boshqaruvi.
4. **Unit testlar**: `compare_faces` uchun sintetik vektorlar; preprocess o‘lchamlari.

## Bosqich C — Samaradorlik va sifat

1. **Batch inferens**: bir freymda ko‘p yuzlar uchun `get_feat` ga ro‘yxat uzatish (model qo‘llab-quvvatlasa).
2. **ROI (qiziqish zonasi)**: kadrning faqat bir qismida deteksiya (sport / kuzatuv kameralari uchun).
3. **Chegara kalibrlash**: `threshold` ni validation to‘plami bo‘yicha ROC/FAR-FRR grafigidan tanlash.
4. **Profilga olish**: macOS Activity Monitor bilan CoreML ishlatilayotganini tasdiqlash + kerak bo‘lsa ONNX graph optimizatsiyasi.

## Bosqich D — Mahsulot xavfsizligi

1. **Anti-spoofing** moduli (2D / print / ekran hujumlari).
2. **Ma’lumotlarni shifrlash**: embeddinglar va metadata saqlashda.
3. **Audit jurnali**: kim, qachon, qaysi manba bilan solishtirgani (GDPR / mahalliy qonunlar bo‘yicha).

## Bosqich E — Kengaytirilgan arxitektura

1. **Mikroservis**: gRPC/REST orqali inferens xizmati (GPU serverda ham ishlaydigan konteyner).
2. **Kuzatuv (tracking)**: bir xil shaxsni kadrlar bo‘yicha ID bilan bog‘lash.
3. **Ko‘p kamera**: parallel oqimlar uchun `asyncio` strukturasini kengaytirish yoki `multiprocessing` bilan ajratish.

## Qabul mezonlari (Definition of Done)

- Real vaqt rejimida **barqaror FPS** (loyiha talabiga qarab aniq son).
- **Inferens vaqti** loglarida ko‘rinadi va regressiya uchun baseline sifatida ishlatiladi.
- **Taqqoslash** natijalari testlar bilan tasdiqlangan chegara atrofida barqaror.

---

**Eslatma**: model fayllari birinchi ishga tushirishda internet orqali yuklanishi mumkin; CI muhitida ularni keshlash strategiyasi alohida rejalashtiriladi.

---

## “Super” loyiha uchun takliflar (mahsulot + muhandislik)

Bu bo‘lim maqsadni **“ishlaydi”** dan **“ishonchli, tez, xavfsiz va foydalanishga qulay”** darajasiga ko‘tarish uchun yo‘naltirilgan.

### 1) Mahsulot va foydalanuvchi tajribasi (UX)

- **Aniq foyda**: “nima uchun kamera?” — 1 jumlalik qiymat taklifi (masalan: tezkor kirish / davomat / identifikatsiya).
- **Holatlar**: kamera yo‘q, ruxsat rad, server band, model yuklanmagan — har biri uchun tushunarli xabar va keyingi qadam.
- **Ishonch ko‘rsatkichi**: ekranda “ishonch %” yoki “mos / emas” + **tushuntirish** (masalan: yorug‘lik past, yuz qisman yashirin).
- **Maxfiylik**: “freym serverga yuboriladi / faqat lokal” degan aniq siyosat matni (haqiqiy arxitekturaga mos).

### 2) Muhandislik sifati (barqarorlik)

- **Performance budget**: masalan, 95-percentil inferens < N ms, FPS past bo‘lsa avtomatik `frame_skip` oshirish.
- **Regressiya testlari**: bir xil etalon suratlar bo‘yicha “score diapazoni” tekshiruvi (aniqlik siljishini erta tutish).
- **Versiyalar**: `lock` fayl + aniq Python minor (3.12/3.11) tavsiyasi; “3.14 eksperimental” kabi holatlar hujjatda yozilsin.
- **Kuzatuv**: `healthcheck`, `readiness`, asosiy metrikalar (inferens vaqti, skip foizi, WS ulanishlari).

### 3) Xavfsizlik va huquqiy tayyorgarlik

- **Anti-spoofing** (ixtiyoriy, lekin “super” uchun ko‘p hollarda shart): ekran/print hujumlariga qarshi modul yoki tashqi servis integratsiyasi.
- **Ma’lumot minimallashtirish**: embeddingdan tashqari biometrik kadrlarni saqlamaslik yoki qisqa muddatli TTL.
- **Audit**: kim identifikatsiya qildi, qachon, qaysi qurilma (kamida texnik jurnal).

### 4) Arxitektura va masshtab

- **Galereya**: bir nechta etalon + “eng yaxshi” tanlash (score bo‘yicha).
- **Tracking**: bir odamni bir nechta deteksiya orasida izchil tutish (ID barqarorligi).
- **Deploy**: Docker + CPU/GPU profillari; staging muhiti bilan sinov.

### 5) Jamoa va jarayon (tez, lekin tartibli)

- **Haftalik sprint**: 1 ta foydalanuvchiga ko‘rinadigan natija (demo video / screenshot) majburiy chiqishi.
- **PR qoidalari**: kichik PR, test talabi, asosiy o‘zgarishlarda `docs/ARXITEKTURA.md` ni qisqa yangilash.

### 6) “Super” mezonlari (qisqa checklist)

- [ ] Konfiguratsiya fayli + bir xil `dev/prod` ishga tushirish skripti  
- [ ] Minimal testlar CI da  
- [ ] Veb demo: xato holatlari + ishonch ko‘rsatkichi  
- [ ] Validatsiya to‘plami + threshold kalibrlash hujjati  
- [ ] (Kerak bo‘lsa) anti-spoofing va audit  

Ushbu checklist tugagach, loyiha “tajriba demo” emas, **mahsulotga tayyor prototip** sifatida baholanadi.
