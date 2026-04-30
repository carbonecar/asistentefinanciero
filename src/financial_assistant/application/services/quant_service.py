from abc import ABC

from financial_assistant.application.dtos.requests import OptimizePortfolioQuery
from financial_assistant.domain.models.analysis import OptimizedWeights, QuantResult, SimulationResult
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

        total_value = float(portfolio.total_cost_usd())
        simulation = self._simulator.simulate(weights, ohlcv_by_ticker, total_value)

        return QuantResult(
            user_id=query.user_id,
            optimized_weights=weights,
            simulation=simulation,
            sentiment_adjusted=query.use_sentiment and bool(sentiment_map),
        )
