# Asistente Financiero

Asistente financiero multi-agente para inversores minoristas argentinos. Combina renta fija (Obligaciones Negociables) y renta variable (acciones/ETFs) en una única herramienta de gestión de cartera, expuesta via bot de Telegram.

> Proyecto académico — Maestría en Inteligencia Artificial

---

## Funcionalidades

| Intención | Qué hace |
|---|---|
| **Auditar cartera** | Performance histórica vs benchmark S&P 500 |
| **Optimizar portfolio** | PyPortfolioOpt + simulación Monte Carlo GBM |
| **Noticias** | Fetch + scoring de sentimiento con TextBlob |
| **Agregar posiciones** | Descarga y persiste datos de mercado (yfinance) |
| **Consulta general** | Respuesta libre con tipo de cambio USD/ARS actualizado |

---

## Setup

```bash
cp .env.example .env   # completar tokens y passwords
make setup             # crea venv + instala deps + pre-commit hooks
```

Variables de entorno requeridas en `.env`:

| Variable | Descripción |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Obtenido desde @BotFather |
| `OPENAI_API_KEY` | API key de OpenAI |
| `NEWSAPI_KEY` | newsapi.org (opcional; sin él el agente de noticias retorna vacío) |
| `POSTGRES_PASSWORD` | Cualquier password seguro |

---

## Comandos

**Desarrollo local** (app en la máquina, infra en Docker):
```bash
make infra-up    # levanta postgres + redis
make migrate     # corre alembic upgrade head contra localhost
make dev         # arranca la app localmente
```

**Producción** (todo en Docker):
```bash
make up          # levanta infra + migrate + bot
make logs        # tail de logs del bot
make down        # baja todo
```

**Tests y calidad:**
```bash
make test        # unit tests
make lint        # ruff + mypy
make fmt         # ruff format + autofix
pytest tests/unit/ -v --cov --cov-report=term-missing
```

---

## Arquitectura

Arquitectura hexagonal (Ports & Adapters). La regla de dependencia fluye solo hacia adentro.

```
domain/          ← Lógica de negocio pura. Sin dependencias externas.
  models/        ← Entidades: Portfolio, Position, OHLCV, NewsArticle, ...
  ports/         ← Interfaces abstractas: IPortfolioRepository, IMarketDataGateway, ...

application/     ← Casos de uso. Solo depende de domain ports.
  services/      ← AuditService, PortfolioService, QuantService, NewsService, MarketDataService
  dtos/          ← Objetos Command/Query (sin ORM leakage)

infrastructure/  ← Implementaciones de los adapters.
  db/            ← SQLAlchemy async + repositorios (PostgreSQL)
  market/        ← YFinanceGateway (yfinance sync en thread executor)
  news/          ← NewsAPIGateway
  nlp/           ← TextBlobSentimentAnalyzer
  container.py   ← Inyección de dependencias manual

agents/          ← Orquestación LangGraph. Llama a application services.
  state.py       ← AgentState TypedDict (compartido entre todos los nodos)
  graph.py       ← build_graph() — nodos + conditional edges
  supervisor/    ← Clasifica intención via function calling
  data_fetcher/  ← Descarga y persiste datos de mercado
  auditor/       ← Performance histórica vs benchmark
  quant/         ← Optimización + Monte Carlo
  news_scout/    ← Noticias + scoring de sentimiento
  ux_agent/      ← Síntesis LLM en respuesta al usuario

telegram/        ← Adapter de entrada. Punto de entrada del usuario.
  bot.py         ← aiogram Bot + Dispatcher
  handlers/      ← message_handler.py conecta Telegram → LangGraph
  middleware/    ← GraphMiddleware inyecta el grafo en el handler
```

---

## Grafo LangGraph

El supervisor clasifica el mensaje del usuario en una o más intenciones (`list[Intent]`). El grafo hace fan-out a los nodos especialistas correspondientes y converge en `fx_fetcher → ux_agent`.

![Grafo de agentes](doc/graph.png)

### Flujo por intención

```
Telegram → message_handler
         → graph.ainvoke(state, config={"thread_id": user_id})
         → supervisor (clasificación de intención)
         → [fan-out condicional]
              "audit"       → auditor      ─┐
              "optimize"    → quant         ├─→ fx_fetcher → ux_agent → respuesta
              "news"        → news_scout   ─┘
              "data_fetch"  → data_fetcher → post_fetch_router → (intenciones pendientes)
              "general"     → fx_fetcher → ux_agent
              "unsupported" → END (respuesta fija)
```

### Nodos del grafo

| Nodo | Tipo | Descripción |
|---|---|---|
| `supervisor` | LLM (function calling) | Clasifica la intención del usuario |
| `data_fetcher` | Servicio | Descarga OHLCV de yfinance y persiste en DB |
| `post_fetch_router` | Router | Despacha intenciones pendientes post data_fetch |
| `auditor` | Servicio | Calcula performance histórica vs S&P 500 |
| `quant` | Servicio | Optimización de cartera + simulación Monte Carlo |
| `news_scout` | Servicio | Fetching de noticias + análisis de sentimiento |
| `sentiment_router` | Router | Decide si `quant` usa sentimiento o va directo a `fx_fetcher` |
| `fx_fetcher` | Gateway | Obtiene tipo de cambio USD/ARS actualizado |
| `ux_agent` | LLM | Sintetiza los resultados en una respuesta en español |
| `unsupported` | Terminal | Respuesta fija para intenciones fuera de scope |

### Regla de secuenciación (blocking intents)

`data_fetch` es una intención **blocking**: cuando se combina con otras (ej. `["data_fetch", "audit"]`), `data_fetcher` corre primero y `post_fetch_router` despacha los especialistas restantes una vez que los datos están persistidos.

### Edges condicionales

```
supervisor      ──(conditional)──→ data_fetcher | auditor | quant | news_scout | fx_fetcher | unsupported
post_fetch_router ─(conditional)──→ auditor | quant | news_scout | fx_fetcher
sentiment_router ──(conditional)──→ quant | fx_fetcher
```

---

## Decisiones de diseño

- **Async everywhere**: aiogram + SQLAlchemy async + asyncio executor para libs sync (yfinance, newsapi)
- **Ajuste por sentimiento**: `E[R_adj] = E[R_hist] × (1 + λ × s)` donde `s ∈ [-1, 1]` y `λ` es `SENTIMENT_LAMBDA`
- **Optimización de cartera**: PyPortfolioOpt `min_volatility()` con regularización L2 (evita soluciones en esquinas)
- **Monte Carlo**: GBM con `mu`/`sigma` ponderados por peso de cada ticker sobre `MONTE_CARLO_HORIZON_DAYS` días
- **Upserts en DB**: `ON CONFLICT DO UPDATE` para registros OHLCV (ingestión idempotente)
- **Checkpointing**: `MemorySaver` en desarrollo. Para producción, reemplazar por Redis checkpointer.

---

## Docker Compose

| Archivo | Uso |
|---|---|
| `docker/docker-compose.yml` | Infra base: `postgres` + `redis`. Desarrollo (`make infra-up`). |
| `docker/docker-compose.prod.yml` | Extiende el base sumando `migrate` + `bot`. Producción (`make up`). |

En desarrollo: `POSTGRES_HOST=localhost`. En Docker: `POSTGRES_HOST=postgres`.

---

## CI

`.github/workflows/ci.yml` corre en cada push y PR a `main`. Dos jobs en paralelo:

| Job | Qué hace |
|---|---|
| `lint` | `ruff check src/ tests/` + `mypy src/` |
| `test` | `pytest tests/unit/` con cobertura mínima del 50% |

Los integration tests (`tests/integration/`) no corren en CI — requieren postgres + redis.

---

## Traza y monitoreo

[LangSmith](https://smith.langchain.com) — configurar `LANGCHAIN_API_KEY` y `LANGCHAIN_PROJECT` en `.env` para habilitar tracing.
