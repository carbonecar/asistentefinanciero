from decimal import Decimal

from financial_assistant.domain.models.portfolio import AssetType, Portfolio, Position


def test_portfolio_total_cost():
    portfolio = Portfolio(
        user_id=1,
        positions=[
            Position("AAPL", AssetType.STOCK, Decimal("10"), Decimal("150")),
            Position("SPY", AssetType.ETF, Decimal("5"), Decimal("400")),
        ],
    )
    assert portfolio.total_cost_usd() == Decimal("3500")


def test_portfolio_tickers():
    portfolio = Portfolio(
        user_id=1,
        positions=[
            Position("AAPL", AssetType.STOCK, Decimal("10"), Decimal("150")),
            Position("MSFT", AssetType.STOCK, Decimal("3"), Decimal("300")),
        ],
    )
    assert set(portfolio.tickers()) == {"AAPL", "MSFT"}


def test_portfolio_is_empty():
    assert Portfolio(user_id=1).is_empty()
    portfolio = Portfolio(
        user_id=1,
        positions=[Position("AAPL", AssetType.STOCK, Decimal("1"), Decimal("100"))],
    )
    assert not portfolio.is_empty()


def test_get_position_existing():
    pos = Position("AAPL", AssetType.STOCK, Decimal("5"), Decimal("150"))
    portfolio = Portfolio(user_id=1, positions=[pos])
    assert portfolio.get_position("AAPL") == pos


def test_get_position_missing():
    portfolio = Portfolio(user_id=1)
    assert portfolio.get_position("TSLA") is None
