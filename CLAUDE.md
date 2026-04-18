# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Multi-agent financial assistant for Argentine retail investors. Combines fixed income (Obligaciones Negociables) and variable income (stocks/ETFs) in a single portfolio management tool. Exposed via Telegram bot. Academic project for a Master's in AI.

## Setup inicial

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env  # completar tokens y passwords
```

## Commands

**Desarrollo local** (app en la máquina, infra en Docker):
```bash
make infra-up    # levanta solo postgres + redis
make migrate     # corre alembic upgrade head contra localhost
make dev         # arranca la app localmente
```

**Producción** (todo en Docker):
```bash
make up          # levanta infra + migrate + bot
make logs        # tail logs del bot
make down        # baja todo
```

**Tests:**
```bash
make test                          # unit tests
make test-integration              # requiere red (yfinance, etc.)
pytest tests/unit/domain/test_calculators.py::test_ohlcv_return_positive -v
```

**Calidad:**
```bash
make lint    # ruff + mypy
make fmt     # ruff format + autofix
pytest tests/unit/ -v --cov --cov-report=term-missing   # con coverage
```

## Architecture

Hexagonal (Ports & Adapters). Dependency rule: imports flow inward only.

```
domain/          ← Pure business logic. Zero external deps.
  models/        ← Dataclass entities (Portfolio, Position, OHLCV, NewsArticle, etc.)
  ports/         ← Abstract interfaces (IPortfolioRepository, IMarketDataGateway, INewsGateway)

application/     ← Use cases. Depends only on domain ports.
  services/      ← AuditService, PortfolioService, QuantService, NewsService, MarketDataService
  dtos/          ← Command/Query objects (no ORM leakage)

infrastructure/  ← Adapter implementations. Depend on domain ports.
  db/            ← SQLAlchemy ORM models + async repositories (PostgreSQL)
  market/        ← YFinanceGateway (wraps yfinance sync API in thread executor)
  news/          ← NewsAPIGateway
  nlp/           ← TextBlobSentimentAnalyzer
  container.py   ← Wires everything together (manual DI)

agents/          ← LangGraph orchestration. Calls application services.
  state.py       ← AgentState TypedDict (shared across all graph nodes)
  graph.py       ← build_graph() — wires nodes + conditional edges
  supervisor/    ← Classifies intent via OpenAI function calling
  data_fetcher/  ← Fetches + persists market data
  auditor/       ← Historical performance vs S&P 500 benchmark
  quant/         ← PyPortfolioOpt + Monte Carlo GBM simulation
  news_scout/    ← News fetch + TextBlob sentiment scoring
  ux_agent/      ← LLM synthesis into user-friendly Spanish response

telegram/        ← Driving adapter. Entry point for user interactions.
  bot.py         ← aiogram Bot + Dispatcher factory
  handlers/      ← message_handler.py bridges Telegram → LangGraph
  middleware/    ← GraphMiddleware injects graph into handler context
```

## LangGraph Flow

The supervisor classifies the message into one or more intents (`list[Intent]`). The graph fans out to the corresponding specialist nodes in parallel, then converges at `fx_fetcher → ux_agent`.

```
Telegram message → message_handler.py
                 → graph.ainvoke(initial_state, config={"thread_id": user_id})
                 → supervisor (intent classification via LLM function calling)
                 → [multi-intent fan-out]
                      "audit"      → auditor      ─┐
                      "optimize"   → quant         ├─→ fx_fetcher → ux_agent → final_response
                      "news"       → news_scout    ─┘
                      "data_fetch" → data_fetcher → post_fetch_router → (remaining intents) ─→ fx_fetcher → ux_agent
                      "general"    → fx_fetcher → ux_agent (skips specialists)
                      "unsupported"→ END (fixed response)
```

**Sequencing rule**: `data_fetch` is a blocking intent. When combined with other intents (e.g. `["data_fetch", "audit"]`), `data_fetcher` runs first and `post_fetch_router` dispatches the remaining specialists afterward, ensuring data is persisted before analysis.

All routing constants (`Node`, `NODE_FOR_INTENT`, `BLOCKING_INTENTS`, `ROUTING_OVERRIDES`) live in `agents/state.py` — no string literals in `graph.py`.

State persistence uses LangGraph `MemorySaver` (in-memory). For production, replace with Redis checkpointer.

## Key Design Decisions

- **Async everywhere**: aiogram + SQLAlchemy async + asyncio executor for sync libs (yfinance, newsapi)
- **Sentiment adjustment**: `E[R_adj] = E[R_hist] * (1 + λ * s)` where `s ∈ [-1,1]`, `λ` is `SENTIMENT_LAMBDA`
- **Portfolio optimization**: PyPortfolioOpt `min_volatility()` with L2 regularization (avoids corner solutions)
- **Monte Carlo**: GBM with per-ticker weighted mu/sigma over `MONTE_CARLO_HORIZON_DAYS` days
- **DB upserts**: `ON CONFLICT DO UPDATE` for OHLCV records (idempotent data ingestion)

## Environment Variables

Copy `.env.example` to `.env` and fill in:
- `TELEGRAM_BOT_TOKEN` — from @BotFather
- `OPENAI_API_KEY` — OpenAI API key
- `NEWSAPI_KEY` — from newsapi.org (optional; news agent returns empty without it)
- `POSTGRES_PASSWORD` — any strong password

## Docker Compose

Hay dos archivos en `docker/`:

| Archivo | Uso |
|---------|-----|
| `docker-compose.yml` | Infra base: `postgres` + `redis`. Se usa en **desarrollo** (`make infra-up`). |
| `docker-compose.prod.yml` | Extiende el base agregando `migrate` + `bot`. Se usa en **producción** (`make up`). |

En desarrollo, `POSTGRES_HOST=localhost` en `.env`. En producción (dentro de Docker), `POSTGRES_HOST=postgres`.


## CI

`.github/workflows/ci.yml` corre en cada push y en PRs a `main`. Dos jobs paralelos:

| Job | Qué hace |
|-----|----------|
| `lint` | `ruff check src/ tests/` + `mypy src/` |
| `test` | `pytest tests/unit/` con `pytest-cov` (umbral mínimo: 50%). Sube `coverage.xml` como artefacto. |

Los integration tests (`tests/integration/`) **no** corren en CI porque requieren postgres + redis.

Para ejecutar el CI localmente:
```bash
make lint && make test
# o con coverage explícito:
pytest tests/unit/ -v --cov --cov-report=term-missing
```

## Traza y monitoreo
 https://www.smith.langchain.com