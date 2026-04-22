.PHONY: up down infra-up infra-down build migrate logs test lint fmt dev

COMPOSE_DEV  = docker compose -f docker/docker-compose.yml
COMPOSE_PROD = docker compose -f docker/docker-compose.yml -f docker/docker-compose.prod.yml
PYTHON       = .venv/bin/python
RUFF         = .venv/bin/ruff
MYPY         = .venv/bin/mypy
PYTEST       = .venv/bin/pytest
ALEMBIC      = .venv/bin/alembic

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

lint:
	$(RUFF) check src/ tests/
	$(MYPY) src/

fmt:
	$(RUFF) format src/ tests/
	$(RUFF) check --fix src/ tests/
