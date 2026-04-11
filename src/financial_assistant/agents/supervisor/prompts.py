SYSTEM_PROMPT = """
You are a financial assistant supervisor. Your job is to classify the user's intent
and extract relevant entities from their message.

Available intents:
- "audit": User wants to see historical portfolio performance vs benchmarks
- "optimize": User wants portfolio optimization (efficient frontier / min variance)
- "news": User wants news sentiment for specific tickers
- "data_fetch": User wants to add/update their portfolio positions
- "unsupported": The request does not match any of the above intents

Respond by calling the classify_intent function with the extracted information.
If you cannot identify specific tickers, use an empty list.
"""

CLASSIFY_INTENT_SCHEMA = {
    "name": "classify_intent",
    "description": "Classify the user's intent and extract entities",
    "parameters": {
        "type": "object",
        "properties": {
            "intent": {
                "type": "string",
                "enum": ["audit", "optimize", "news", "data_fetch", "unsupported"],
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
