PYTHON ?= python

ifneq (,$(wildcard ./.env))
include .env
export
endif

POSTGRES_USER ?= fulfillai
POSTGRES_DB ?= fulfillai

.PHONY: help install install-dev install-platform verify platform-preflight test compile db-up db-down db-preflight db-load generate validate-data sql-models validate-features build-features clean-python platform-up platform-down api mlflow-log dbt-build stream-up stream-down stream-producer stream-consumer platform-demo

help:
	@echo "FulfillAI developer commands"
	@echo "  make install          Install runtime dependencies"
	@echo "  make install-dev      Install runtime + test dependencies"
	@echo "  make verify           Fast data-free source/contract verification"
	@echo "  make test             Run lightweight source tests"
	@echo "  make db-up            Start PostgreSQL"
	@echo "  make generate         Generate deterministic synthetic data"
	@echo "  make validate-data    Validate generated operational data"
	@echo "  make db-preflight     Check DB/source before modifying PostgreSQL"
	@echo "  make db-load          Atomically replace/load PostgreSQL data"
	@echo "  make sql-models       Apply analytical/ML SQL views in order"
	@echo "  make validate-features Validate SQL feature sources"
	@echo "  make build-features   Build chronological Parquet feature datasets"
	@echo "  make install-platform Install optional API/MLOps/streaming/dbt dependencies"
	@echo "  make platform-preflight Validate platform source without touching data"
	@echo "  make platform-up      Start API + MLflow + Redpanda services"
	@echo "  make api              Run FastAPI locally"
	@echo "  make mlflow-log       Log frozen benchmark metrics to MLflow"
	@echo "  make dbt-build        Build/test dbt marts against PostgreSQL"
	@echo "  make stream-up        Start Redpanda + console"
	@echo "  make stream-producer  Publish synthetic order events to Redpanda"
	@echo "  make stream-consumer  Run PySpark Structured Streaming consumer"
	@echo "  make platform-demo    Start FastAPI + MLflow locally via Docker"

install:
	$(PYTHON) -m pip install -r requirements.txt

install-dev:
	$(PYTHON) -m pip install -r requirements-dev.txt

install-platform:
	$(PYTHON) -m pip install -r requirements-platform.txt

platform-preflight:
	$(PYTHON) scripts/platform_preflight.py

compile:
	$(PYTHON) -m compileall -q src scripts

verify:
	$(PYTHON) scripts/verify_source.py

test:
	$(PYTHON) -m pytest -q

db-up:
	docker compose up -d postgres

db-down:
	docker compose down

generate:
	$(PYTHON) -m src.fulfillai.data.generator

validate-data:
	$(PYTHON) -m src.fulfillai.data.validation

db-preflight:
	$(PYTHON) -m src.fulfillai.data.load

db-load:
	$(PYTHON) -m src.fulfillai.data.load --load --replace

sql-models:
	@set -e; \
	for f in $$(find sql/models -maxdepth 1 -name '*.sql' -type f | sort); do \
		echo "Applying $$f"; \
		docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U "$(POSTGRES_USER)" -d "$(POSTGRES_DB)" < "$$f"; \
	done

validate-features:
	$(PYTHON) -m src.fulfillai.features.validate

build-features:
	$(PYTHON) -m src.fulfillai.features.build_features

clean-python:
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete

platform-up:
	docker compose --profile platform --profile streaming up -d

platform-down:
	docker compose --profile platform --profile streaming down

api:
	$(PYTHON) -m uvicorn src.fulfillai.api.main:app --reload --host 0.0.0.0 --port 8000

mlflow-log:
	$(PYTHON) -m src.fulfillai.mlops.mlflow_tracking

dbt-build:
	cd dbt && DBT_PROFILES_DIR=. dbt build

stream-up:
	docker compose --profile streaming up -d redpanda redpanda-console

stream-down:
	docker compose --profile streaming stop redpanda redpanda-console

platform-demo:
	bash scripts/platform_demo.sh

stream-producer:
	$(PYTHON) -m src.fulfillai.streaming.producer

stream-consumer:
	bash scripts/run_spark_stream.sh
