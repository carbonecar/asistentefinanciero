from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from financial_assistant.application.dtos.requests import AuditPortfolioQuery
from financial_assistant.application.services.audit_service import AuditService
from financial_assistant.domain.models.market_data import OHLCV
from financial_assistant.domain.models.portfolio import AssetType, Portfolio, Position


def make_records(ticker: str, start: float, end: float, n: int = 5) -> list[OHLCV]:
    step = (end - start) / max(n - 1, 1)
    return [
        OHLCV(
            ticker=ticker,
            date=date(2024, 1, i + 1),
            open=Decimal(str(start + i * step)),
            high=Decimal(str(start + i * step + 2)),
            low=Decimal(str(start + i * step - 2)),
            close=Decimal(str(round(start + i * step, 4))),
            volume=500_000,
        )
        for i in range(n)
    ]


@pytest.fixture
def portfolio():
    return Portfolio(
        user_id=42,
        positions=[
            Position("AAPL", AssetType.STOCK, Decimal("10"), Decimal("100")),
        ],
    )


@pytest.fixture
def mock_portfolio_repo(portfolio):
    repo = AsyncMock()
    repo.get_by_user_id.return_value = portfolio
    return repo


@pytest.fixture
def mock_market_gateway():
    gw = AsyncMock()
    gw.fetch_ohlcv.return_value = make_records("AAPL", 100, 130)

    def _fetch_benchmark(symbol: str) -> list[OHLCV]:
        if symbol == "^MERV":
            return make_records("^MERV", 800_000, 950_000)
        return make_records("^GSPC", 4000, 4400)

    gw.fetch_benchmark.side_effect = _fetch_benchmark
    return gw


@pytest.mark.asyncio
async def test_audit_returns_report(mock_portfolio_repo, mock_market_gateway):
    service = AuditService(mock_portfolio_repo, mock_market_gateway)
    report = await service.audit(AuditPortfolioQuery(user_id=42, period="1y"))

    assert report is not None
    assert report.user_id == 42
    assert report.portfolio_return > Decimal("0")
    assert len(report.comparisons) == 2
    benchmark_names = [c.benchmark_name for c in report.comparisons]
    assert "S&P 500" in benchmark_names
    assert "Merval" in benchmark_names


@pytest.mark.asyncio
async def test_audit_empty_portfolio(mock_market_gateway):
    repo = AsyncMock()
    repo.get_by_user_id.return_value = Portfolio(user_id=99)

    service = AuditService(repo, mock_market_gateway)
    report = await service.audit(AuditPortfolioQuery(user_id=99))
    assert report is None
