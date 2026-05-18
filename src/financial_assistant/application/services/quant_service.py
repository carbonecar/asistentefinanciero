from abc import ABC

from financial_assistant.application.dtos.requests import OptimizePortfolioQuery
from financial_assistant.domain.models.analysis import OptimizedWeights, QuantResult, RebalancingTrade, SimulationResult
from financial_assistant.domain.models.market_data import OHLCV
from financial_assistant.domain.models.news import SentimentResult
from financial_assistant.domain.ports.market_gateway import IMarketDataGateway
from financial_assistant.domain.ports.repositories import IPortfolioRepository


class OptimizerProtocol(ABC):
    def minimum_variance(
        self, ohlcv_by_ticker: dict[str, list[OHLCV]], sentiment_map: dict[str, float]
    ) -> OptimizedWeights | None:
        raise NotImplementedError


class SimulatorProtocol(ABC):
    def simulate(
        self, weights: OptimizedWeights | None, ohlcv_by_ticker: dict[str, list[OHLCV]], initial_value: float
    ) -> SimulationResult | None:
        raise NotImplementedError


class QuantService:
    def __init__(
        self,
        portfolio_repo: IPortfolioRepository,
        market_gateway: IMarketDataGateway,
        optimizer: OptimizerProtocol,
        simulator: SimulatorProtocol,
    ) -> None:
        self._portfolio_repo = portfolio_repo
        self._market_gateway = market_gateway
        self._optimizer = optimizer
        self._simulator = simulator

    async def optimize(
        self,
        query: OptimizePortfolioQuery,
        sentiment_results: list[SentimentResult] | None = None,
    ) -> QuantResult | None:
        portfolio = await self._portfolio_repo.get_by_user_id(query.user_id)
        if not portfolio or portfolio.is_empty():
            return None

        ohlcv_by_ticker = {}
        for ticker in portfolio.tickers():
            records = await self._market_gateway.fetch_ohlcv(ticker, period="1y")
            ohlcv_by_ticker[ticker] = records

        sentiment_map = {r.ticker: r.score for r in sentiment_results} if sentiment_results else {}

        weights = self._optimizer.minimum_variance(
            ohlcv_by_ticker,
            sentiment_map if query.use_sentiment else {},
        )

        # Pesos actuales por valor de mercado
        current_values = {
            pos.ticker: float(pos.quantity) * float(ohlcv_by_ticker[pos.ticker][-1].close)
            for pos in portfolio.positions
            if pos.ticker in ohlcv_by_ticker and ohlcv_by_ticker[pos.ticker]
        }
        total_market_value = sum(current_values.values())
        current_weights = (
            {t: v / total_market_value for t, v in current_values.items()} if total_market_value > 0 else {}
        )

        # Propuesta de rebalanceo: delta entre pesos actuales y pesos optimizados
        rebalancing_trades: list[RebalancingTrade] = []
        if weights and total_market_value > 0:
            all_tickers = set(current_weights) | set(weights.weights)
            for ticker in all_tickers:
                current_w = current_weights.get(ticker, 0.0)
                target_w = weights.weights.get(ticker, 0.0)
                delta = target_w - current_w
                rebalancing_trades.append(
                    RebalancingTrade(
                        ticker=ticker,
                        current_weight=round(current_w, 4),
                        target_weight=round(target_w, 4),
                        delta_weight=round(delta, 4),
                        trade_value_usd=round(delta * total_market_value, 2),
                    )
                )
            rebalancing_trades.sort(key=lambda x: abs(x.delta_weight), reverse=True)

        simulation = self._simulator.simulate(
            weights, ohlcv_by_ticker, total_market_value or float(portfolio.total_cost_usd())
        )

        return QuantResult(
            user_id=query.user_id,
            optimized_weights=weights,
            simulation=simulation,
            sentiment_adjusted=query.use_sentiment and bool(sentiment_map),
            current_weights=current_weights,
            rebalancing_trades=rebalancing_trades,
        )
