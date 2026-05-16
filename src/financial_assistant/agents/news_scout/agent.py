import logging

from financial_assistant.agents.state import AgentState
from financial_assistant.application.dtos.requests import NewsQuery
from financial_assistant.application.services.news_service import NewsService
from financial_assistant.application.services.portfolio_service import PortfolioService

logger = logging.getLogger(__name__)


def make_news_scout_node(news_service: NewsService, portfolio_service: PortfolioService) -> object:
    async def news_scout_node(state: AgentState) -> dict:  # type: ignore[type-arg]
        tickers = state.get("active_tickers") or []
        user_id: int = state.get("user_id", 0)

        # Cuando optimize+use_sentiment=True el usuario no menciona tickers explícitos;
        # se usan los tickers del portfolio como fuente para el análisis de sentimiento.
        if not tickers and state.get("use_sentiment") and "optimize" in (state.get("intents") or []):
            try:
                portfolio = await portfolio_service.get_or_create(user_id)
                tickers = list(portfolio.tickers())
                logger.info("NewsScout: using portfolio tickers for sentiment: %s", tickers)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logger.error("NewsScout: failed to load portfolio tickers: %s", exc)

        if not tickers:
            logger.warning(
                "NewsScout: no tickers in state for user %s — supervisor did not extract tickers from message %r",
                user_id,
                state.get("user_message", ""),
            )
            return {
                "news_results": [],
                "errors": [
                    "No se detectaron tickers en el mensaje. Mencioná el ticker específico (ej: AAPL, GGAL.BA)."
                ],
            }

        try:
            query = NewsQuery(tickers=tickers)
            results = await news_service.analyze_sentiment(query)
            return {"news_results": results, "errors": []}
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.error("NewsScout failed: %s", exc)
            return {"news_results": [], "errors": [str(exc)]}

    return news_scout_node
