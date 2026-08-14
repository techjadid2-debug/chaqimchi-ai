# Chaqimchi AI
PY ?= python3

.PHONY: install-dev test lint fmt run-web run-sotqin run-cloud run-retail calibrate provision backup restore docker-build cloud-config cloud-deploy benchmark verify-models

install-dev:
	$(PY) -m pip install -r requirements.txt -r requirements-dev.txt

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check chaqimchi_ai webapp cloud tests scripts

fmt:
	$(PY) -m ruff format chaqimchi_ai webapp cloud tests scripts

run-web:
	CHAQIMCHI_SERVICE_MODE=attendance CHAQIMCHI_ATTENDANCE_PILOT=true $(PY) -m uvicorn webapp.main:app --host 127.0.0.1 --port 8743

run-sotqin:
	$(PY) -m uvicorn chaqimchi_ai.sotqin_agent:app --host 127.0.0.1 --port 8742

run-cloud:
	$(PY) -m uvicorn cloud.main:app --host 127.0.0.1 --port 8750

run-retail:
	$(PY) -m chaqimchi_ai.retail.service

PLAN ?= lite
MONTHS ?= 1

provision:
	@test -n "$(NAME)" || (echo 'Usage: make provision NAME="Mijoz nomi" [PLAN=lite] [MONTHS=12]' && exit 1)
	$(PY) scripts/provision_site.py "$(NAME)" --plan $(PLAN) --months $(MONTHS)

# Zaxira nusxa: make backup [OUT=/Volumes/USB]
backup:
	$(PY) scripts/backup_db.py save $(if $(OUT),--out $(OUT),)

# Tiklash: make restore FILE=nusxa.zip
restore:
	@test -n "$(FILE)" || (echo 'Usage: make restore FILE=nusxa.zip' && exit 1)
	$(PY) scripts/backup_db.py restore "$(FILE)"

calibrate:
	$(PY) scripts/calibrate_threshold.py

docker-build:
	docker build -t chaqimchi-ai .

cloud-config:
	docker compose --env-file .env.production -f docker-compose.prod.yml config --quiet

cloud-deploy:
	./scripts/deploy_cloud.sh

# Sotqin R1 qabul o'lchovi (faqat qurilmada ishlaydi).
benchmark:
	$(PY) scripts/benchmark_n100.py --seconds 300 --json benchmark-n100.json

verify-models:
	$(PY) scripts/verify_model_bundle.py models/manifest.example.json
