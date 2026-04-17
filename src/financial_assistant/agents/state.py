from typing import Annotated, Any, Literal

from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage
from typing_extensions import TypedDict

Intent = Literal["audit", "optimize", "news", "data_fetch", "general", "unsupported"]


class Node:
    SUPERVISOR = "supervisor"
    DATA_FETCHER = "data_fetcher"
    AUDITOR = "auditor"
    QUANT = "quant"
    NEWS_SCOUT = "news_scout"
    FX_FETCHER = "fx_fetcher"
    UX_AGENT = "ux_agent"
    UNSUPPORTED = "unsupported"


NODE_FOR_INTENT: dict[str, str] = {
    "audit": Node.AUDITOR,
    "optimize": Node.QUANT,
    "news": Node.NEWS_SCOUT,
    "data_fetch": Node.DATA_FETCHER,
    "general": Node.UX_AGENT,
    "unsupported": Node.UNSUPPORTED,
}
VALID_INTENTS: frozenset[str] = frozenset(NODE_FOR_INTENT)

from financial_assistant.domain.models.analysis import AuditReport, QuantResult
from financial_assistant.domain.models.fx import ExchangeRate
from financial_assistant.domain.models.news import SentimentResult


class AgentState(TypedDict):
    # ---- Input ----
    user_id: int
    user_message: str
    messages: Annotated[list[BaseMessage], add_messages]

    # ---- Routing (set by supervisor) ----
    intents: list[Intent]  #Intent
    active_tickers: list[str]
    period: str  # e.g. "1y", "6mo"
    use_sentiment: bool

    # ---- Agent outputs (accumulated) ----
    market_data_result: dict[str, Any] | None
    audit_report: AuditReport | None
    quant_result: QuantResult | None
    news_results: list[SentimentResult] | None
    exchange_rates: list[ExchangeRate] | None

    # ---- Final ----
    final_response: str | None
    error: str | None
