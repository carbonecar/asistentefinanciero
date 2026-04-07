from typing import Annotated, Any

from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage
from typing_extensions import TypedDict

from financial_assistant.domain.models.analysis import AuditReport, QuantResult
from financial_assistant.domain.models.news import SentimentResult


class AgentState(TypedDict):
    # ---- Input ----
    user_id: int
    user_message: str
    messages: Annotated[list[BaseMessage], add_messages]

    # ---- Routing (set by supervisor) ----
    intent: str  # "audit" | "optimize" | "news" | "data_fetch" | "general"
    active_tickers: list[str]
    period: str  # e.g. "1y", "6mo"
    use_sentiment: bool

    # ---- Agent outputs (accumulated) ----
    market_data_result: dict[str, Any] | None
    audit_report: AuditReport | None
    quant_result: QuantResult | None
    news_results: list[SentimentResult] | None

    # ---- Final ----
    final_response: str | None
    error: str | None
