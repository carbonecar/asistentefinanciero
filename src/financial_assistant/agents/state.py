import operator
from typing import Annotated, Any, Literal

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from financial_assistant.domain.models.analysis import AuditReport, QuantResult
from financial_assistant.domain.models.fx import ExchangeRate
from financial_assistant.domain.models.news import DailySentiment

Intent = Literal["audit", "optimize", "news", "data_fetch", "general", "unsupported"]
FALLBACK_INTENT: list[Intent] = ["unsupported"]


class Node:
    SUPERVISOR = "supervisor"
    DATA_FETCHER = "data_fetcher"
    AUDITOR = "auditor"
    QUANT = "quant"
    NEWS_SCOUT = "news_scout"
    FX_FETCHER = "fx_fetcher"
    UX_AGENT = "ux_agent"
    UNSUPPORTED = "unsupported"
    POST_FETCH_ROUTER = "post_fetch_router"
    SENTIMENT_ROUTER = "sentiment_router"
    QUANT_NO_SENTIMENT = "quant_no_sentiment"


NODE_FOR_INTENT: dict[str, str] = {
    "data_fetch": Node.DATA_FETCHER,
    "audit": Node.AUDITOR,
    "optimize": Node.QUANT,
    "news": Node.NEWS_SCOUT,
    "general": Node.UX_AGENT,
    "unsupported": Node.UNSUPPORTED,
}
VALID_INTENTS: frozenset[str] = frozenset(NODE_FOR_INTENT)

# Intents that must complete before others can fan-out in parallel.
# When mixed with other intents, these run first; post_fetch_router dispatches the rest.
BLOCKING_INTENTS: frozenset[str] = frozenset({"data_fetch"})

# "general" skips specialists but still passes through fx_fetcher before ux_agent.
# This dict overrides the logical node from NODE_FOR_INTENT to the actual graph target.
ROUTING_OVERRIDES: dict[str, str] = {
    Node.UX_AGENT: Node.FX_FETCHER,
}


class AgentState(TypedDict):
    # ---- Input ----
    user_id: int
    user_message: str
    messages: Annotated[list[BaseMessage], add_messages]

    # ---- Routing (set by supervisor) ----
    intents: list[Intent]
    active_tickers: list[str]
    period: str  # e.g. "1y", "6mo"
    use_sentiment: bool
    positions: list[dict[str, Any]]  # [{ticker, quantity, avg_cost_usd, asset_type}]
    optimization_strategy: str  # "max_sharpe" | "min_volatility"

    # ---- Agent outputs (accumulated) ----
    market_data_result: dict[str, Any] | None
    audit_report: AuditReport | None
    quant_result: QuantResult | None
    news_results: dict[str, list[DailySentiment]] | None
    news_headlines: dict[str, list[dict[str, object]]] | None  # recent articles with per-article sentiment
    exchange_rates: list[ExchangeRate] | None

    # ---- Final ----
    final_response: str | None
    errors: Annotated[list[str], operator.add]
