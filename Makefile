.PHONY: up down infra-up infra-down build migrate logs test lint fmt dev setup

COMPOSE_DEV  = docker compose -f docker/docker-compose.yml
COMPOSE_PROD = docker compose -f docker/docker-compose.yml -f docker/docker-compose.prod.yml

ifeq ($(OS),Windows_NT)
    ALEMBIC = .venv/Scripts/alembic.exe
    PYTHON = .venv/Scripts/python.exe
    RUFF = .venv/Scripts/ruff.exe
    MYPY = .venv/Scripts/mypy.exe
    PYTEST = .venv/Scripts/pytest.exe
else
    ALEMBIC = .venv/bin/alembic
    PYTHON = .venv/bin/python
    RUFF = .venv/bin/ruff
    MYPY = .venv/bin/mypy
    PYTEST = .venv/bin/pytest
endif

# Primera vez: crea el venv, instala deps y registra los hooks de pre-commit
setup:
	python3.11 -m venv .venv
	.venv/bin/pip install -e ".[dev]"
	.venv/bin/pre-commit install

# --- Desarrollo local ---
# Levanta solo postgres + redis; la app corre en tu máquina
infra-up:
	$(COMPOSE_DEV) up -d

infra-down:
	$(COMPOSE_DEV) down

# Corre las migraciones contra la infra local (POSTGRES_HOST=localhost en .env)
migrate:
	$(ALEMBIC) upgrade head

# Arranca la app localmente (requiere infra-up y .env configurado)
dev:
	$(PYTHON) -m financial_assistant.main

# --- Producción (todo en Docker) ---
up:
	$(COMPOSE_PROD) up -d

down:
	$(COMPOSE_PROD) down

build:
	$(COMPOSE_PROD) build

logs:
	$(COMPOSE_PROD) logs -f bot

shell:
	$(COMPOSE_PROD) exec bot bash

# --- Testing y calidad ---
test:
	$(PYTEST) tests/unit/ -v

test-integration:
	$(PYTEST) tests/integration/ -v -m integration

## Pre-computes historical sentiment and saves it to the DB.
## Requires: infra-up + migrate + ANALYSIS_TICKERS in .env
sentiment-batch:
	$(PYTHON) -m scripts.run_sentiment_batch

lint:
	$(RUFF) check src/ tests/
	$(MYPY) src/

fmt:
	$(RUFF) format src/ tests/
	$(RUFF) check --fix src/ tests/
