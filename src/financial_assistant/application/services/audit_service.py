from decimal import Decimal

from financial_assistant.application.dtos.requests import AuditPortfolioQuery
from financial_assistant.domain.models.analysis import AuditReport, BenchmarkComparison
from financial_assistant.domain.models.market_data import OHLCV
from financial_assistant.domain.models.portfolio import Portfolio
from financial_assistant.domain.ports.market_gateway import IMarketDataGateway
from financial_assistant.domain.ports.repositories import IPortfolioRepository


class AuditService:
    def __init__(
        self,
        portfolio_repo: IPortfolioRepository,
        market_gateway: IMarketDataGateway,
    ) -> None:
        self._portfolio_repo = portfolio_repo
        self._market_gateway = market_gateway

    async def audit(self, query: AuditPortfolioQuery) -> AuditReport | None:
        portfolio = await self._portfolio_repo.get_by_user_id(query.user_id)
        if not portfolio or portfolio.is_empty():
            return None

        market_data: dict[str, list[OHLCV]] = {}
        for ticker in portfolio.tickers():
            records = await self._market_gateway.fetch_ohlcv(ticker, period=query.period)
            market_data[ticker] = records

        sp500 = await self._market_gateway.fetch_benchmark("^GSPC")
        portfolio_return = self._compute_portfolio_return(portfolio, market_data)
        sp500_return = self._compute_ohlcv_return(sp500)

        comparisons = [
            BenchmarkComparison("S&P 500", sp500_return, portfolio_return),
        ]

        returns_by_ticker = {
            ticker: self._compute_ohlcv_return(records) for ticker, records in market_data.items() if records
        }
        top = max(returns_by_ticker, key=lambda t: returns_by_ticker[t], default="")
        worst = min(returns_by_ticker, key=lambda t: returns_by_ticker[t], default="")

        return AuditReport(
            user_id=query.user_id,
            period_label=f"last {query.period}",
            portfolio_return=portfolio_return,
            comparisons=comparisons,
            top_performer=top,
            worst_performer=worst,
        )

    def _compute_portfolio_return(self, portfolio: Portfolio, market_data: dict[str, list[OHLCV]]) -> Decimal:
        total_cost = portfolio.total_cost_usd()
        if total_cost == 0:
            return Decimal("0")

        total_value = Decimal("0")
        for position in portfolio.positions:
            records = market_data.get(position.ticker, [])
            if records:
                latest_price = records[-1].close
                total_value += position.quantity * latest_price
            else:
                total_value += position.total_cost_usd

        return (total_value - total_cost) / total_cost

    def _compute_ohlcv_return(self, records: list[OHLCV]) -> Decimal:
        if len(records) < 2:
            return Decimal("0")
        first_close = records[0].close
        last_close = records[-1].close
        if first_close == 0:
            return Decimal("0")
        return (last_close - first_close) / first_close
