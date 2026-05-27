from datetime import date, timedelta

from financial_assistant.application.dtos.requests import AuditPortfolioQuery
from financial_assistant.domain.models.analysis import AuditReport, BenchmarkComparison
from financial_assistant.domain.models.market_data import OHLCV
from financial_assistant.domain.ports.market_gateway import IMarketDataGateway
from financial_assistant.domain.ports.repositories import IMarketDataRepository, IPortfolioRepository
from financial_assistant.domain.services.calculators import (
    compute_ohlcv_return,
    compute_portfolio_return,
)

_PERIOD_DAYS: dict[str, int] = {
    "1d": 1,
    "5d": 5,
    "1mo": 30,
    "3mo": 91,
    "6mo": 182,
    "1y": 365,
    "2y": 730,
    "5y": 1825,
    "10y": 3650,
    "max": 10950,  # ~30 years
}


def _period_to_date_range(period: str) -> tuple[date, date]:
    end = date.today()
    if period == "ytd":
        start = date(end.year, 1, 1)
    else:
        days = _PERIOD_DAYS.get(period, 365)
        start = end - timedelta(days=days)
    return start, end


class AuditService:
    def __init__(
        self,
        portfolio_repo: IPortfolioRepository,
        market_gateway: IMarketDataGateway,
        market_data_repo: IMarketDataRepository | None = None,
    ) -> None:
        self._portfolio_repo = portfolio_repo
        self._market_gateway = market_gateway
        self._market_data_repo = market_data_repo

    async def _get_ohlcv(self, ticker: str, period: str) -> list[OHLCV]:
        """Try DB cache first; fall back to live gateway if empty."""
        if self._market_data_repo is not None:
            start, end = _period_to_date_range(period)
            cached: list[OHLCV] = await self._market_data_repo.get_ohlcv(ticker, start, end)
            if cached:
                return cached
        live: list[OHLCV] = await self._market_gateway.fetch_ohlcv(ticker, period=period)
        if live and self._market_data_repo is not None:
            await self._market_data_repo.save_ohlcv(live)
        return live

    async def audit(self, query: AuditPortfolioQuery) -> AuditReport | None:
        portfolio = await self._portfolio_repo.get_by_user_id(query.user_id)
        if not portfolio or portfolio.is_empty():
            return None

        market_data: dict[str, list[OHLCV]] = {}
        for ticker in portfolio.tickers():
            records = await self._get_ohlcv(ticker, query.period)
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
            positions=[
                {
                    "ticker": p.ticker,
                    "quantity": float(p.quantity),
                    "avg_cost_usd": float(p.avg_cost_usd),
                    "current_price": float(latest_prices.get(p.ticker, p.avg_cost_usd)),
                    "current_value": float(p.quantity * latest_prices.get(p.ticker, p.avg_cost_usd)),
                }
                for p in portfolio.positions
            ],
        )
