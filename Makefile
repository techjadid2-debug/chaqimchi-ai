# Chaqimchi AI
PY ?= python3

.PHONY: install-dev test lint fmt run-sotqin run-cloud run-local run-retail provision docker-build cloud-config cloud-deploy benchmark windows-installer

install-dev:
	$(PY) -m pip install -r requirements.txt -r requirements-dev.txt

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check chaqimchi_ai cloud tests scripts

fmt:
	$(PY) -m ruff format chaqimchi_ai cloud tests scripts

run-sotqin:
	$(PY) -m uvicorn chaqimchi_ai.sotqin_agent:app --host 127.0.0.1 --port 8742

run-cloud:
	$(PY) -m uvicorn cloud.main:app --host 127.0.0.1 --port 8750

# Mijozning o'z kompyuteridagi dastur: sozlash ustasi + do'kon paneli.
# Windows o'rnatuvchisi aynan shuni ishga tushiradi.
run-local:
	$(PY) -m chaqimchi_ai.local.app

run-retail:
	$(PY) -m chaqimchi_ai.retail.service

PLAN ?= lite
MONTHS ?= 1

provision:
	@test -n "$(NAME)" || (echo 'Usage: make provision NAME="Mijoz nomi" [PLAN=lite] [MONTHS=12]' && exit 1)
	$(PY) scripts/provision_site.py "$(NAME)" --plan $(PLAN) --months $(MONTHS)

docker-build:
	docker build -f Dockerfile.cloud -t chaqimchi-cloud .

cloud-config:
	docker compose --env-file .env.production -f docker-compose.prod.yml config --quiet

cloud-deploy:
	./scripts/deploy_cloud.sh

# Sotqin R1 qabul o'lchovi (faqat qurilmada ishlaydi).
benchmark:
	$(PY) scripts/benchmark_n100.py --seconds 300 --json benchmark-n100.json

# Windows o'rnatuvchisi: payload (Python + kutubxona + AI modeli) yig'iladi,
# keyin NSIS uni bitta .exe ga kompilyatsiya qiladi.  `makensis` kerak:
#   macOS: brew install makensis   ·   Ubuntu: sudo apt install nsis
windows-installer:
	$(PY) scripts/build_windows_payload.py
	makensis -V2 scripts/windows_installer.nsi
