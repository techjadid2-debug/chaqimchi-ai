# Chaqimchi AI

> Lokal qurilma — **Sotqin R1**: Intel N100 mini-kompyuter, NVR/IP kameralar
> va Chaqimchi Cloud orasidagi xavfsiz ko'prik. Yengil inferens (odam
> deteksiyasi, do'kon analitikasi) qurilmaning o'zida; qimmat AI — ko'rish
> agenti va hisobotlar — cloudda. To'liq video arxiv NVR'da qoladi.

Mahsulot scope'i, edge/server chegarasi, o‘rnatish va rollout:
[docs/CHAQIMCHI_LITE.md](docs/CHAQIMCHI_LITE.md). Batafsil apparat, benchmark,
backup va rollback: [docs/PRODUCTION_SET1.md](docs/PRODUCTION_SET1.md).

Muhim: repository’dagi InsightFace demo modeli commercial mahsulot litsenziyasi degani emas. Litsenziyalangan model manifesti tasdiqlanmaguncha production Face ID fail-closed holatda qoladi. Oddiy mijozlar uchun persistent Face ID V1 scope’ida yo‘q.

Sotqin control plane pairing, hardware identity, heartbeat, cloud config,
ACK/NACK va imzolangan update/rollbackni bajaradi. Do‘kon analitikasi (odam
sanog‘i, dwell, navbat, kamera buzilishi) alohida xizmatda ishlaydi —
`make run-retail`, batafsil
[chaqimchi_ai/retail/README.md](chaqimchi_ai/retail/README.md). ONVIF discovery
keyingi bosqichda.

Real vaqtga yaqin yuzni tanish: SCRFD deteksiya, ArcFace 512 embedding, ko‘p kamera va veb-dashboard.

## Talablar

- Python **3.12** — rasmiy qo‘llab-quvvatlanadigan versiya (Docker va CI shu).
  3.10–3.14 da ham ishlaydi, lekin faqat 3.12 test qilinadi.
- macOS Apple Silicon yoki Linux (CPU; CoreML Mac da avtomatik)

## Tez boshlash

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
make test
make run-web
```

Brauzer: [http://127.0.0.1:8742](http://127.0.0.1:8742)

Birinchi ishga tushirishda `buffalo_l` modellari `~/.insightface` ga yuklanadi.

## Konfiguratsiya

`config/config.yaml` — kamera manbalari, `compare_threshold`, voqea `match_debounce_sec`, snapshot saqlash, arxiv muddati, Telegram va yo‘llar.

Muhit o‘zgaruvchisi: `CHAQIMCHI_CONFIG=/yo'l/config.yaml`

## Buyruqlar

| Buyruq | Vazifa |
|--------|--------|
| `make install-dev` | Bog‘liqliklar |
| `make test` | Pytest |
| `make lint` / `make fmt` | Ruff |
| `make run-web` | FastAPI server (8742) |
| `make run-sotqin` | Sotqin R1 control agent (8742) |
| `make run-retail` | Do‘kon analitikasi xizmati (`retail.enabled: true` kerak) |
| `make demo` | CLI kamera |
| `make backup` | Baza zaxira nusxasi (`OUT=/Volumes/USB`) |
| `make restore FILE=n.zip` | Nusxadan tiklash |
| `make calibrate` | Threshold tavsiyasi |
| `make validate-antispoof` | Anti-spoof sifatini o‘lchash |

## API (qisqa)

| Endpoint | Vazifa |
|----------|--------|
| `GET /health`, `GET /ready` | Holat |
| `GET /api/metrics` | Inferens statistikasi |
| `GET /api/calibrate/threshold` | Threshold tavsiyasi |
| `POST /api/calibrate/apply` | Tavsiyani qo‘llash (xotira) |
| `POST /api/identify` | Rasmni bazadan qidirish |
| `POST /api/analyze` | Yuz deteksiya (bazasiz) |
| `POST/DELETE /api/persons/...` | Boshqaruv (API kalit) |
| `GET /api/retention` | Arxiv muddati va oxirgi tozalash |
| `POST /api/retention/purge` | Arxivni darhol tozalash (API kalit) |
| `GET /api/backup` | Bazani ZIP qilib yuklab olish (API kalit) |
| `POST /api/backup/restore` | Nusxadan tiklash (API kalit) |
| `GET /api/vision/status` | Ko‘rish agenti: sozlama va sarf |
| `POST /api/vision/analyze` | Kadrni AI ga tahlil qildirish (API kalit) |

## Struktura

- `chaqimchi_ai/` — yadro (face_engine, database, camera_manager)
- `webapp/` — FastAPI + dashboard
- `docs/` — arxitektura va roadmap (`REJA.md`)

## Docker

```bash
docker build -t chaqimchi-ai .
docker run -p 8742:8742 -v "$(pwd)/config:/app/config" chaqimchi-ai
```

## Xizmat (o‘rnatish + obuna)

- Tariflar: [docs/BIZNES_MODEL.md](docs/BIZNES_MODEL.md)
- O‘rnatuvchi: [docs/INSTALLER.md](docs/INSTALLER.md)
- Cloud: `make run-cloud` + `CHAQIMCHI_CLOUD_ADMIN_KEY`
- Admin panel: [http://127.0.0.1:8750/admin](http://127.0.0.1:8750/admin) — mijoz ochish, obunani uzaytirish/to‘xtatish, pairing kod, hisob-fakturalar
- Rasmiy sayt: [http://127.0.0.1:8750/](http://127.0.0.1:8750/) — Lite mahsuloti va pilot ariza
- Sotqinni ulash: [http://127.0.0.1:8750/connect](http://127.0.0.1:8750/connect)
- Lite mijoz ochish (CLI): `make provision NAME="Do'kon nomi" PLAN=lite MONTHS=1`
- To‘lov (Payme/Click): [docs/TOLOV.md](docs/TOLOV.md) — hisob-faktura ochiladi,
  to‘lov tushgach obuna avtomatik uzayadi

## Xavfsizlik va kalibrlash

- **API kalit**: `CHAQIMCHI_API_KEY` — qo‘shish/o‘chirish.
- **JWT**: `POST /api/auth/token` → `Authorization: Bearer <token>`.
- **Embedding shifrlash**: `storage.encrypt_embeddings` + `CHAQIMCHI_EMBEDDING_KEY`.
- **FAISS**: `pip install -r requirements-optional.txt`, `storage.vector_backend: faiss`.
- **Prometheus**: `GET /metrics`.
- **Threshold**: [CALIBRATION.md](docs/CALIBRATION.md).
- **Zaxira nusxa**: `make backup` — butun yuz bazasi bitta ZIP faylga.
  Qurilma almashganda `make restore FILE=n.zip`. Nusxa biometrik ma’lumot:
  himoyalangan joyda saqlang. Batafsil: [INSTALLER.md](docs/INSTALLER.md).
- **Arxiv muddati**: `events.retention_days` — muddati o‘tgan voqealar va yuz
  rasmlari avtomatik o‘chadi (6 soatda bir marta). `0` bo‘lsa tarif belgilaydi:
  Starter 30, Business 90, Enterprise 365 kun. Diskni to‘lib ketishdan saqlaydi
  va biometrik kadr kerakdan ortiq saqlanmaydi.
- **Anti-spoofing**: `antispoof.enabled` — ekran/bosma suratni filtrlash.
  Imkoniyat va chegaralari: [ANTISPOOF.md](docs/ANTISPOOF.md). Kirish nazorati
  uchun faqat yuzga tayanmang.

## Hujjatlar

- [Umumiy reja](docs/MASTER_PLAN.md)
- [Chaqimchi Lite: mahsulot, ulanish va rollout](docs/CHAQIMCHI_LITE.md)
- [Sotqin R1: apparat va cloud kontrakti](docs/SOTQIN.md)
- [Do‘kon analitikasi (Retail AI)](chaqimchi_ai/retail/README.md) — inferens
  byudjeti, zanjir va qurilma sig‘imi
- [Ko‘rish agenti (AI)](docs/KORISH_AGENTI.md) — narx jadvali bilan
- [To‘lov integratsiyasi](docs/TOLOV.md)
- [Arxitektura](docs/ARXITEKTURA.md)
- [Rivojlanish rejasi](docs/REJA.md)
- [Threshold kalibrlash](docs/CALIBRATION.md)
