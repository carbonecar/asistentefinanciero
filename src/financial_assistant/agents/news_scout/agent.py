import logging

from financial_assistant.agents.state import AgentState
from financial_assistant.application.dtos.requests import NewsQuery
from financial_assistant.application.services.news_service import NewsService

logger = logging.getLogger(__name__)


def make_news_scout_node(news_service: NewsService):  # type: ignore[no-untyped-def]
    async def news_scout_node(state: AgentState) -> dict:  # type: ignore[type-arg]
        tickers = state.get("active_tickers") or []

        if not tickers:
            logger.warning(
                "NewsScout: no tickers in state for user %s — supervisor did not extract tickers from message %r",
                state.get("user_id"),
                state.get("user_message", ""),
            )
            return {
                "news_results": [],
                "errors": [
                    "No se detectaron tickers en el mensaje. "
                    "Mencioná el ticker específico (ej: AAPL, GGAL.BA)."
                ],
            }

        try:
            query = NewsQuery(tickers=tickers)
            results = await news_service.analyze_sentiment(query)
            return {"news_results": results, "errors": []}
        except Exception as exc:
            logger.error("NewsScout failed: %s", exc)
            return {"news_results": [], "errors": [str(exc)]}

    return news_scout_node
