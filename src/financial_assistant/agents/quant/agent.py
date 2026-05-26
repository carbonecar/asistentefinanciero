import logging

from financial_assistant.agents.state import AgentState
from financial_assistant.application.dtos.requests import OptimizePortfolioQuery
from financial_assistant.application.services.quant_service import QuantService
from financial_assistant.domain.services.optimizer import (
    MaxSharpeStrategy,
    MinVolatilitySentimentStrategy,
    MinVolatilityStrategy,
    OptimizationStrategy,
)

logger = logging.getLogger(__name__)

_STRATEGY_MAP: dict[str, OptimizationStrategy] = {
    "max_sharpe": MaxSharpeStrategy(),
    "min_volatility": MinVolatilityStrategy(),
    "min_vol_sentiment": MinVolatilitySentimentStrategy(),
}


def make_quant_node(
    quant_service: QuantService,
    result_key: str = "quant_result",
    force_no_sentiment: bool = False,
) -> object:
    async def quant_node(state: AgentState) -> dict:  # type: ignore[type-arg]
        user_id = state["user_id"]
        use_sentiment = False if force_no_sentiment else state.get("use_sentiment", False)
        news_results = None if force_no_sentiment else state.get("news_results")
        strategy_key = state.get("optimization_strategy", "max_sharpe")
        strategy = _STRATEGY_MAP.get(strategy_key, MaxSharpeStrategy())

        try:
            query = OptimizePortfolioQuery(
                user_id=user_id,
                use_sentiment=use_sentiment,
                optimization_strategy=strategy.name,
            )
            result = await quant_service.optimize(query, sentiment_results=news_results, strategy=strategy)
            has_weights = result is not None and result.optimized_weights is not None
            logger.info("Quant result for user %s: result=%s has_weights=%s", user_id, result is not None, has_weights)
            return {result_key: result, "errors": []}
        except Exception as exc:
            logger.error("Quant failed for user %s: %s", user_id, exc)
            return {result_key: None, "errors": [str(exc)]}

    return quant_node
