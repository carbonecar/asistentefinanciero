# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Multi-agent financial assistant for Argentine retail investors. Combines fixed income (Obligaciones Negociables) and variable income (stocks/ETFs) in a single portfolio management tool. Exposed via Telegram bot. Academic project for a Master's in AI.

## Setup inicial

```bash
cp .env.example .env  # completar tokens y passwords
make setup            # crea venv + instala deps + registra pre-commit hooks
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

Hexagonal (Ports & Adapters). Dependency rule: imports flow inward only. Todo el código fuente vive bajo `src/financial_assistant/`.

```
domain/          ← Pure business logic. Zero external deps.
  models/        ← Dataclass entities (Portfolio, Position, OHLCV, AuditReport, QuantResult,
                    ExchangeRate, SentimentResult, NewsArticle)
  ports/         ← Abstract interfaces (IPortfolioRepository, IMarketDataGateway,
                    INewsGateway, IExchangeRateGateway)
  services/      ← Domain calculators (Sharpe ratio, costs, etc.)

application/     ← Use cases. Depends only on domain ports.
  services/      ← AuditService, PortfolioService, QuantService, NewsService, MarketDataService
  dtos/          ← Command/Query objects (AuditPortfolioQuery, etc. Sin ORM leakage)

infrastructure/  ← Adapter implementations. Depend on domain ports.
  db/            ← SQLAlchemy ORM models + async repositories (PostgreSQL)
  market/        ← YFinanceGateway (wraps yfinance sync API in thread executor)
  fx/            ← DolarApiGateway (tipos de cambio USD/ARS)
  news/          ← NewsAPIGateway + YFinanceNewsGateway
  nlp/           ← TextBlobSentimentAnalyzer + FinBERTSentimentAnalyzer
  container.py   ← Wires everything together (manual DI)

agents/          ← LangGraph orchestration. Calls application services.
  state.py       ← AgentState TypedDict (shared across all graph nodes)
  graph.py       ← build_graph() — wires nodes + conditional edges
  llm_factory.py ← Factory para ChatOpenAI o ChatOllama según LLM_PROVIDER
  supervisor/    ← Classifies intent via LLM function calling
  data_fetcher/  ← Fetches + persists market data (BLOCKING)
  auditor/       ← Historical performance vs S&P 500 benchmark
  quant/         ← PyPortfolioOpt + Monte Carlo GBM simulation
  news_scout/    ← News fetch + sentiment scoring
  fx_fetcher/    ← Obtiene tipos de cambio USD/ARS
  ux_agent/      ← LLM synthesis into user-friendly Spanish response

telegram/        ← Driving adapter. Entry point for user interactions.
  bot.py         ← aiogram Bot + Dispatcher factory
  handlers/      ← message_handler.py (LangGraph bridge) + command_handler.py
  keyboards/     ← inline_keyboards.py (aiogram InlineKeyboardMarkup)
  middleware/    ← session_middleware.py injects session into handler context
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
- **LLM provider flexibility**: `llm_factory.py` crea `ChatOpenAI` o `ChatOllama` según `LLM_PROVIDER` en `.env`. Default: `openai` con `gpt-4o-mini`.
- **Dual sentiment analyzers**: TextBlobSentimentAnalyzer (rápido, sin GPU) y FinBERTSentimentAnalyzer (más preciso para textos financieros en inglés). Se selecciona vía config.
- **Dual news sources**: NewsAPIGateway (newsapi.org) y YFinanceNewsGateway (noticias embebidas en yfinance). Ambos implementan `INewsGateway`.
- **Sentiment adjustment**: `E[R_adj] = E[R_hist] * (1 + λ * s)` donde `s ∈ [-1,1]`, `λ` es `SENTIMENT_LAMBDA`
- **Portfolio optimization**: PyPortfolioOpt `min_volatility()` con L2 regularization (avoids corner solutions)
- **Monte Carlo**: GBM with per-ticker weighted mu/sigma over `MONTE_CARLO_HORIZON_DAYS` days
- **DB upserts**: `ON CONFLICT DO UPDATE` for OHLCV records (idempotent data ingestion)

## Environment Variables

Copy `.env.example` to `.env` and fill in:

```
# Telegram
TELEGRAM_BOT_TOKEN=        # from @BotFather

# LLM
LLM_PROVIDER=openai        # "openai" | "ollama"
OPENAI_API_KEY=            # requerido si LLM_PROVIDER=openai
OPENAI_MODEL=gpt-4o-mini
OLLAMA_BASE_URL=http://localhost:11434   # requerido si LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.1

# Base de datos
POSTGRES_USER=financial_user
POSTGRES_PASSWORD=          # any strong password
POSTGRES_DB=financial_db
POSTGRES_HOST=localhost     # "localhost" en dev, "postgres" en Docker
POSTGRES_DSN=postgresql+asyncpg://...   # construido automáticamente desde las vars anteriores

# Redis
REDIS_URL=redis://localhost:6379/0

# APIs externas (opcionales)
NEWSAPI_KEY=               # from newsapi.org — news agent returns empty without it

# Parámetros del modelo financiero
SENTIMENT_LAMBDA=0.15
MONTE_CARLO_SIMULATIONS=5000
MONTE_CARLO_HORIZON_DAYS=252

# Observabilidad
LANGCHAIN_TRACING_V2=false
SQL_ECHO=false
```

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
