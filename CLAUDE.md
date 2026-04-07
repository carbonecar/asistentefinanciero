# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Multi-agent financial assistant for Argentine retail investors. Combines fixed income (Obligaciones Negociables) and variable income (stocks/ETFs) in a single portfolio management tool. Exposed via Telegram bot. Academic project for a Master's in AI.

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

```
Telegram message → message_handler.py
                 → graph.ainvoke(initial_state, config={"thread_id": user_id})
                 → supervisor (intent classification via OpenAI function calling)
                 → [conditional edge by intent]
                      "audit"      → auditor      → ux_agent
                      "optimize"   → quant        → ux_agent
                      "news"       → news_scout   → ux_agent
                      "data_fetch" → data_fetcher → ux_agent
                      "general"    → ux_agent (directly)
                 → final_response sent to Telegram
```

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
