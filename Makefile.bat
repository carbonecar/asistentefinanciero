#!/usr/bin/env bash
set -euo pipefail

set -a
source .env
set +a

COMPOSE_DEV="docker compose -f docker/docker-compose.yml"
COMPOSE_PROD="docker compose -f docker/docker-compose.yml -f docker/docker-compose.prod.yml"

usage() {
    echo "Usage: $0 <command>"
    echo ""
    echo "Desarrollo local:"
    echo "  infra-up          Levanta postgres + redis"
    echo "  infra-down        Baja la infra local"
    echo "  migrate           Corre alembic upgrade head"
    echo "  dev               Arranca la app localmente"
    echo ""
    echo "Producción (Docker):"
    echo "  up                Levanta infra + migrate + bot"
    echo "  down              Baja todo"
    echo "  build             Construye las imágenes"
    echo "  logs              Tail logs del bot"
    echo "  shell             Shell interactivo en el contenedor bot"
    echo ""
    echo "Testing y calidad:"
    echo "  test              Unit tests"
    echo "  test-integration  Integration tests"
    echo "  lint              ruff + mypy"
    echo "  fmt               ruff format + autofix"
}

case "${1:-}" in
    infra-up)
        $COMPOSE_DEV up -d
        ;;
    infra-down)
        $COMPOSE_DEV down
        ;;
    migrate)
        alembic upgrade head
        ;;
    dev)
        python -m financial_assistant.main
        ;;
    up)
        $COMPOSE_PROD up -d
        ;;
    down)
        $COMPOSE_PROD down
        ;;
    build)
        $COMPOSE_PROD build
        ;;
    logs)
        $COMPOSE_PROD logs -f bot
        ;;
    shell)
        $COMPOSE_PROD exec bot bash
        ;;
    test)
        pytest tests/unit/ -v
        ;;
    test-integration)
        pytest tests/integration/ -v -m integration
        ;;
    lint)
        ruff check src/ tests/
        mypy src/
        ;;
    fmt)
        ruff format src/ tests/
        ruff check --fix src/ tests/
        ;;
    *)
        usage
        exit 1
        ;;
esac
    echo "El script terminó con código de salida: $?"
    read -p "Presione cualquier tecla para continuar..."
