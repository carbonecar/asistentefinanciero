import logging

from financial_assistant.agents.state import AgentState
from financial_assistant.application.dtos.requests import NewsQuery
from financial_assistant.application.services.news_service import NewsService

logger = logging.getLogger(__name__)


def make_news_scout_node(news_service: NewsService):  # type: ignore[no-untyped-def]
    async def news_scout_node(state: AgentState) -> dict:  # type: ignore[type-arg]
        tickers = state.get("active_tickers") or []

        if not tickers:
            return {"news_results": [], "error": None}

        try:
            query = NewsQuery(tickers=tickers)
            results = await news_service.analyze_sentiment(query)
            return {"news_results": results, "error": None}
        except Exception as exc:
            logger.error("NewsScout failed: %s", exc)
            return {"news_results": [], "error": str(exc)}

    return news_scout_node
