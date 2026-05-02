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

        warnings: list[str] = []
        if use_sentiment and not news_results:
            warnings.append(
                "No se aplicó el ajuste por sentimiento en la optimización porque"
                " las noticias/sentimiento no estaban disponibles en este turno."
                " La optimización se realizó solo con datos de mercado."
            )
            logger.warning("[Quant] use_sentiment=True but news_results unavailable for user %s", user_id)

        try:
            query = OptimizePortfolioQuery(user_id=user_id, use_sentiment=use_sentiment)
            result = await quant_service.optimize(query, sentiment_results=news_results)
            return {"quant_result": result, "errors": warnings}
        except Exception as exc:
            logger.error("Quant failed for user %s: %s", user_id, exc)
            return {"quant_result": None, "errors": warnings + [str(exc)]}

    return quant_node
