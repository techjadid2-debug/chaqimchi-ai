# Chaqimchi AI
PY ?= python3

.PHONY: install-dev test lint fmt run-web run-cloud demo calibrate validate-antispoof provision backup restore docker-build cloud-config cloud-deploy benchmark-set1 verify-models

install-dev:
	$(PY) -m pip install -r requirements.txt -r requirements-dev.txt

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check chaqimchi_ai webapp cloud tests scripts

fmt:
	$(PY) -m ruff format chaqimchi_ai webapp cloud tests scripts

run-web:
	$(PY) -m uvicorn webapp.main:app --host 127.0.0.1 --port 8742

run-cloud:
	$(PY) -m uvicorn cloud.main:app --host 127.0.0.1 --port 8750

PLAN ?= business
MONTHS ?= 12

provision:
	@test -n "$(NAME)" || (echo 'Usage: make provision NAME="Mijoz nomi" [PLAN=starter] [MONTHS=12]' && exit 1)
	$(PY) scripts/provision_site.py "$(NAME)" --plan $(PLAN) --months $(MONTHS)

# Zaxira nusxa: make backup [OUT=/Volumes/USB]
backup:
	$(PY) scripts/backup_db.py save $(if $(OUT),--out $(OUT),)

# Tiklash: make restore FILE=nusxa.zip
restore:
	@test -n "$(FILE)" || (echo 'Usage: make restore FILE=nusxa.zip' && exit 1)
	$(PY) scripts/backup_db.py restore "$(FILE)"

demo:
	$(PY) face_engine_core.py --camera 0 --frame-skip 2

calibrate:
	$(PY) scripts/calibrate_threshold.py

validate-antispoof:
	$(PY) scripts/validate_antispoof.py

docker-build:
	docker build -t chaqimchi-ai .

cloud-config:
	docker compose --env-file .env.production -f docker-compose.prod.yml config --quiet

cloud-deploy:
	./scripts/deploy_cloud.sh

benchmark-set1:
	$(PY) scripts/benchmark_streams.py --config config/production.yaml --duration 300 --output benchmark-set1.json

verify-models:
	$(PY) scripts/verify_model_bundle.py models/manifest.json
