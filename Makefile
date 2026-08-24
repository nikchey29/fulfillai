PYTHON ?= python

ifneq (,$(wildcard ./.env))
include .env
export
endif

POSTGRES_USER ?= fulfillai
POSTGRES_DB ?= fulfillai

.PHONY: help install install-dev verify test compile db-up db-down db-preflight db-load generate validate-data sql-models validate-features build-features clean-python

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

install:
	$(PYTHON) -m pip install -r requirements.txt

install-dev:
	$(PYTHON) -m pip install -r requirements-dev.txt

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
