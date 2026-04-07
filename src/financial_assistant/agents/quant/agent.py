import logging

from financial_assistant.agents.state import AgentState
from financial_assistant.application.dtos.requests import OptimizePortfolioQuery
from financial_assistant.application.services.quant_service import QuantService

logger = logging.getLogger(__name__)


def make_quant_node(quant_service: QuantService):  # type: ignore[no-untyped-def]
    async def quant_node(state: AgentState) -> dict:  # type: ignore[type-arg]
        user_id = state["user_id"]
        use_sentiment = state.get("use_sentiment", False)
        news_results = state.get("news_results")

        try:
            query = OptimizePortfolioQuery(user_id=user_id, use_sentiment=use_sentiment)
            result = await quant_service.optimize(query, sentiment_results=news_results)
            return {"quant_result": result, "error": None}
        except Exception as exc:
            logger.error("Quant failed for user %s: %s", user_id, exc)
            return {"quant_result": None, "error": str(exc)}

    return quant_node
