import logging

from financial_assistant.agents.state import AgentState
from financial_assistant.application.dtos.requests import OptimizePortfolioQuery
from financial_assistant.application.services.quant_service import QuantService
from financial_assistant.domain.services.risk_rules import (
    build_quant_explanation,
    check_concentration,
    check_missing_profile,
    check_short_horizon,
)

logger = logging.getLogger(__name__)


def make_quant_node(quant_service: QuantService):  # type: ignore[no-untyped-def]
    async def quant_node(state: AgentState) -> dict:  # type: ignore[type-arg]
        user_id = state["user_id"]
        use_sentiment = state.get("use_sentiment", False)
        news_results = state.get("news_results")
        profile = state.get("financial_profile")

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

            current_weights = result.current_weights if result else {}
            risk_warnings = (
                check_missing_profile(profile)
                + check_short_horizon(profile)
                + check_concentration(current_weights)
            )

            explanation = build_quant_explanation(
                sentiment_lambda=0.15 if use_sentiment else None,
                warnings=risk_warnings,
            )

            logger.info("[Quant] risk_warnings=%d for user %s", len(risk_warnings), user_id)
            return {
                "quant_result": result,
                "risk_warnings": risk_warnings,
                "explanation_card": explanation,
                "errors": warnings,
            }
        except Exception as exc:
            logger.error("Quant failed for user %s: %s", user_id, exc)
            return {"quant_result": None, "errors": warnings + [str(exc)]}

    return quant_node
