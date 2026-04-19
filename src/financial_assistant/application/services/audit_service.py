from financial_assistant.application.dtos.requests import AuditPortfolioQuery
from financial_assistant.domain.models.analysis import AuditReport, BenchmarkComparison
from financial_assistant.domain.models.market_data import OHLCV
from financial_assistant.domain.ports.market_gateway import IMarketDataGateway
from financial_assistant.domain.ports.repositories import IPortfolioRepository
from financial_assistant.domain.services.calculators import (
    compute_ohlcv_return,
    compute_portfolio_return,
)


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

        latest_prices = {ticker: records[-1].close for ticker, records in market_data.items() if records}
        portfolio_return = compute_portfolio_return(portfolio, latest_prices)
        sp500_return = compute_ohlcv_return(sp500)

        comparisons = [
            BenchmarkComparison("S&P 500", sp500_return, portfolio_return),
        ]

        returns_by_ticker = {
            ticker: compute_ohlcv_return(records) for ticker, records in market_data.items() if records
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
