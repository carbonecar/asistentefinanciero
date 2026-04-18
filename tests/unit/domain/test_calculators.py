from datetime import date
from decimal import Decimal

from financial_assistant.agents.auditor.calculators import (
    compute_ohlcv_return,
    compute_opportunity_cost,
    compute_portfolio_return,
)
from financial_assistant.domain.models.market_data import OHLCV
from financial_assistant.domain.models.portfolio import AssetType, Portfolio, Position


def make_ohlcv(ticker: str, start_close: float, end_close: float) -> list[OHLCV]:
    return [
        OHLCV(
            ticker, date(2024, 1, 1), Decimal("100"), Decimal("100"), Decimal("100"), Decimal(str(start_close)), 1000
        ),
        OHLCV(ticker, date(2024, 6, 1), Decimal("100"), Decimal("100"), Decimal("100"), Decimal(str(end_close)), 1000),
    ]


def test_ohlcv_return_positive():
    records = make_ohlcv("X", 100, 120)
    result = compute_ohlcv_return(records)
    assert result == Decimal("0.2")


def test_ohlcv_return_negative():
    records = make_ohlcv("X", 200, 160)
    result = compute_ohlcv_return(records)
    assert result == Decimal("-0.2")


def test_ohlcv_return_empty():
    assert compute_ohlcv_return([]) == Decimal("0")


def test_ohlcv_return_single():
    records = make_ohlcv("X", 100, 110)
    assert compute_ohlcv_return(records[:1]) == Decimal("0")


def test_portfolio_return():
    portfolio = Portfolio(
        user_id=1,
        positions=[
            Position("AAPL", AssetType.STOCK, Decimal("10"), Decimal("100")),
        ],
    )
    latest_prices = {"AAPL": Decimal("120")}
    result = compute_portfolio_return(portfolio, latest_prices)
    assert result == Decimal("0.2")


def test_portfolio_return_empty():
    assert compute_portfolio_return(Portfolio(user_id=1), {}) == Decimal("0")


def test_opportunity_cost_outperform():
    result = compute_opportunity_cost(Decimal("0.25"), Decimal("0.15"))
    assert result == Decimal("0.10")


def test_opportunity_cost_underperform():
    result = compute_opportunity_cost(Decimal("0.05"), Decimal("0.15"))
    assert result == Decimal("-0.10")
