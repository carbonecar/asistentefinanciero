"""Pure functions for portfolio performance calculation — no side effects."""

from decimal import Decimal

from financial_assistant.domain.models.market_data import OHLCV
from financial_assistant.domain.models.portfolio import Portfolio


def compute_ohlcv_return(records: list[OHLCV]) -> Decimal:
    if len(records) < 2:
        return Decimal("0")
    first = records[0].close
    last = records[-1].close
    if first == 0:
        return Decimal("0")
    return (last - first) / first


def compute_portfolio_return(
    portfolio: Portfolio, latest_prices: dict[str, Decimal]
) -> Decimal:
    total_cost = portfolio.total_cost_usd()
    if total_cost == 0:
        return Decimal("0")

    current_value = Decimal("0")
    for position in portfolio.positions:
        price = latest_prices.get(position.ticker)
        if price is not None:
            current_value += position.quantity * price
        else:
            current_value += position.total_cost_usd

    return (current_value - total_cost) / total_cost


def compute_opportunity_cost(portfolio_return: Decimal, benchmark_return: Decimal) -> Decimal:
    """Positive value means portfolio outperformed the benchmark."""
    return portfolio_return - benchmark_return
