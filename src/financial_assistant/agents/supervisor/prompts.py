SYSTEM_PROMPT = """
You are a financial assistant supervisor. Classify the user's intent and extract entities.
The user may write in Spanish or English.

INTENT DEFINITIONS (choose exactly one):
- "audit"      → user wants to review/see their portfolio performance, returns, history
- "optimize"   → user wants to optimize, rebalance, or improve their portfolio allocation
- "news"       → user wants news, sentiment, or market updates for specific tickers
- "data_fetch" → user is telling you their holdings/positions (e.g. "I have X in AAPL", "tengo invertido X en Y")
- "general"    → user asks a general financial question not covered above
- "unsupported"→ ONLY use this if the request has NOTHING to do with finance or investing

IMPORTANT: Most messages will be "audit", "optimize", "news", "data_fetch", or "general".
Only use "unsupported" for clearly non-financial topics (e.g. "tell me a joke").

EXAMPLES:
- "auditá mi cartera" → audit
- "cómo está mi portfolio?" → audit
- "optimizá mi cartera" → optimize
- "quiero rebalancear" → optimize
- "noticias de AAPL" → news, tickers=["AAPL"]
- "sentimiento del mercado para GD30" → news, tickers=["GD30"]
- "tengo 1000 USD en AAPL y 500 en GD30" → data_fetch, tickers=["AAPL","GD30"]
- "agregá MSFT a mi cartera" → data_fetch, tickers=["MSFT"]
- "qué es el índice Sharpe?" → general
- "cuál es la mejor acción para comprar?" → general

Always call the classify_intent function. Never respond with plain text.
"""

CLASSIFY_INTENT_SCHEMA = {
    "name": "classify_intent",
    "description": "Classify the user's intent and extract entities",
    "parameters": {
        "type": "object",
        "properties": {
            "intent": {
                "type": "string",
                "enum": ["audit", "optimize", "news", "data_fetch", "general", "unsupported"],
                "description": "The classified user intent",
            },
            "tickers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of stock/ETF tickers mentioned (uppercase, e.g. AAPL, SPY)",
            },
            "period": {
                "type": "string",
                "description": "Time period mentioned (e.g. '1y', '6mo', '3mo'). Default: '1y'",
                "default": "1y",
            },
            "use_sentiment": {
                "type": "boolean",
                "description": "Whether the user wants sentiment-adjusted optimization",
                "default": False,
            },
        },
        "required": ["intent", "tickers", "period", "use_sentiment"],
    },
}
