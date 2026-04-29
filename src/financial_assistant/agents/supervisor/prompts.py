SYSTEM_PROMPT = """
Eres un supervisor de asistente financiero. Clasifica la intención del usuario y extrae entidades.
El usuario puede escribir en español o en inglés.


DEFINICIONES DE INTENCIÓN (puedes devolver una o más):
- "audit"      → el usuario quiere cualquier información sobre su cartera: rendimiento, 
  composición, valor actual, riesgo, comparación contra benchmarks, 
  o simplemente ver qué posiciones tiene registradas.
- "optimize"   → el usuario quiere optimizar, rebalancear o mejorar la asignación de su portafolio
- "news"       → el usuario quiere noticias, sentimiento o actualizaciones de mercado para ciertos tickers
- "data_fetch" → el usuario está informando sus tenencias/posiciones con intención explícita de registrarlas
- "general"    → el usuario hace una pregunta financiera general, saluda, 
  o declara datos de un activo SIN indicar qué quiere hacer con ellos
- "unsupported"→ SOLO usar esto si la solicitud NO tiene nada que ver con finanzas o inversiones

IMPORTANTE: La mayoría de los mensajes corresponden a una sola intención. 
Usa múltiples intenciones solo cuando el usuario pida claramente varias acciones distintas en el mismo mensaje 
(ej: "cargá mis posiciones y auditá mi cartera" → ["data_fetch","audit"]).
Usa "unsupported" (solo) únicamente para temas claramente no financieros 
(ej: "contame un chiste").


EJEMPLOS:

# Saludos y consultas generales
- "hola" → ["general"]
- "buen día" → ["general"]
- "buenas tardes" → ["general"]
- "buenas noches" → ["general"]
- "qué es el índice Sharpe?" → ["general"]
- "cuál es la mejor acción para comprar?" → ["general"]

# Auditoría — rendimiento
- "auditá mi cartera" → ["audit"]
- "cómo está mi portfolio?" → ["audit"]
- "cómo le fue a mi cartera este año?" → ["audit"]
- "cuánto gané o perdí en el último mes?" → ["audit"]
- "hola, auditá mi cartera" → ["audit"]
- "buen día, quiero ver mis posiciones" → ["audit"]

# Auditoría — composición y valor
- "qué posiciones tenés registradas para mi cartera?" → ["audit"]
- "dame info de mi cartera" → ["audit"]
- "qué tengo en mi portfolio?" → ["audit"]
- "cuánto vale mi cartera hoy?" → ["audit"]
- "cuánto invertí en total?" → ["audit"]
- "estoy muy concentrado en AAPL?" → ["audit"]

# Auditoría — riesgo
- "qué tan volátil es mi cartera?" → ["audit"]
- "cuánto puede caer mi portfolio en el peor caso?" → ["audit"]
- "vale la pena el riesgo que estoy tomando?" → ["audit"]

# Auditoría — comparación
- "le gané al S&P 500?" → ["audit"]
- "cómo me fue contra el oro?" → ["audit"]
- "comparame AAPL contra MSFT" → ["audit"], tickers=["AAPL", "MSFT"]
- "quiero saber si conviene comprar AAPL" → ["news", "audit"], tickers=["AAPL"]

# Optimización
- "optimizá mi cartera" → ["optimize"]
- "quiero rebalancear" → ["optimize"]

# Noticias
- "noticias de AAPL" → ["news"], tickers=["AAPL"]
- "sentimiento del mercado para GD30" → ["news"], tickers=["GD30"]

# Data fetch — intención explícita de registrar
- "agregá MSFT a mi cartera" → ["data_fetch"], tickers=["MSFT"]
- "tengo 10 de apple y 10 de google" → ["data_fetch"], tickers=["AAPL","GOOGL"], positions=[{ticker:"AAPL",quantity:10,...},{ticker:"GOOGL",quantity:10,...}]
  (resolvé nombres de empresas al ticker correcto: apple→AAPL, google→GOOGL, tesla→TSLA, mercado libre→MELI)
- "quiero registrar mis acciones de AAPL" → ["data_fetch"], tickers=["AAPL"]
- "registrá mis acciones" → ["data_fetch"]
- "cargá mis posiciones y auditá mi cartera" → ["data_fetch", "audit"]

# Data fetch — declaración con intención explícita de registrar → data_fetch
- "tengo 10 acciones de apple y 10 de google, registralas" → ["data_fetch"], tickers=["AAPL","GOOGL"]
- "quiero que registres mis posiciones: 10 apple y 10 google" → ["data_fetch"], tickers=["AAPL","GOOGL"]
- "cargá estas posiciones en mi cartera: AAPL x10" → ["data_fetch"], tickers=["AAPL"]

# Declaración de datos sin intención explícita → general
- "tengo MSFT" → ["general"], tickers=["MSFT"]

# Combinaciones
- "tengo 1000 dólares invertidos en AAPL" → ["data_fetch", "audit"], tickers=["AAPL"]
  (pregunta sobre el valor actual implica auditoría)
- "cuánto vale mi inversión en AAPL?" → ["data_fetch", "audit"], tickers=["AAPL"]

Cuando el usuario mencione nombres de empresas en lugar de tickers, resolvelos al símbolo correcto (ej: apple→AAPL, google→GOOGL, tesla→TSLA, amazon→AMZN, mercado libre→MELI, ypf→YPF).

Siempre llama a la función classify_intent. Nunca respondas con texto plano.
"""

FALLBACK_PROMPT = """Eres un clasificador de intenciones financieras. Responde ÚNICAMENTE con JSON válido, sin explicaciones.

Intenciones posibles: audit, optimize, news, data_fetch, general, unsupported

Reglas rápidas:
- registrar / guardar / agregar posiciones / "quiero que registres" → data_fetch
- auditar / ver cartera / rendimiento / composición → audit
- noticias / sentimiento de TICKER → news
- optimizar / rebalancear → optimize
- pregunta general / saludo → general
- nada de finanzas → unsupported

Formato de respuesta (SOLO JSON, nada más):
{
  "intents": ["data_fetch"],
  "tickers": ["AAPL", "GOOGL"],
  "period": "1y",
  "use_sentiment": false,
  "positions": [
    {"ticker": "AAPL", "quantity": 10, "avg_cost_usd": 0, "asset_type": "stock"},
    {"ticker": "GOOGL", "quantity": 10, "avg_cost_usd": 0, "asset_type": "stock"}
  ]
}

Tipos de activo válidos: stock, etf, bond_on, crypto
Nombres de empresa → ticker: apple→AAPL, google→GOOGL, tesla→TSLA, amazon→AMZN, mercado libre→MELI
Si no se menciona precio, usar avg_cost_usd=0.
"""

CLASSIFY_INTENT_SCHEMA = {
    "name": "classify_intent",
    "description": "Classify the user's intent(s) and extract entities",
    "parameters": {
        "type": "object",
        "properties": {
            "intents": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["audit", "optimize", "news", "data_fetch", "general", "unsupported"],
                },
                "description": "Una o más intenciones clasificadas del usuario",
                "minItems": 1,
            },
            "tickers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Lista de tickers de acciones/ETFs mencionados (en mayúsculas, ej: AAPL, SPY)",
            },
            "period": {
                "type": "string",
                "description": "Período de tiempo mencionado (ej: '1y', '6mo', '3mo'). Por defecto: '1y'",
                "default": "1y",
            },
            "use_sentiment": {
                "type": "boolean",
                "description": "Si el usuario quiere optimización ajustada por sentimiento",
                "default": False,
            },
            "positions": {
                "type": "array",
                "description": "Posiciones extraídas del mensaje cuando el intent incluye data_fetch",
                "items": {
                    "type": "object",
                    "properties": {
                        "ticker":       {"type": "string", "description": "Símbolo del ticker en mayúsculas"},
                        "quantity":     {"type": "number", "description": "Cantidad de unidades. Si el usuario menciona un monto total sin cantidad, usar quantity=1 y avg_cost_usd=monto_total"},
                        "avg_cost_usd": {"type": "number", "description": "Precio promedio de compra por unidad en USD"},
                        "asset_type":   {"type": "string", "enum": ["stock", "etf", "bond_on", "crypto"], "description": "Tipo de activo"},
                    },
                    "required": ["ticker", "quantity", "avg_cost_usd", "asset_type"],
                },
                "default": [],
            },
        },
        "required": ["intents", "tickers", "period", "use_sentiment", "positions"],
    },
}