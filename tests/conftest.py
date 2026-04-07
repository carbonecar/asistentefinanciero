from datetime import date
from decimal import Decimal

import pytest

from financial_assistant.domain.models.market_data import OHLCV
from financial_assistant.domain.models.portfolio import AssetType, Portfolio, Position


@pytest.fixture
def sample_portfolio() -> Portfolio:
    return Portfolio(
        user_id=12345,
        positions=[
            Position(
                ticker="AAPL",
                asset_type=AssetType.STOCK,
                quantity=Decimal("10"),
                avg_cost_usd=Decimal("150.00"),
            ),
            Position(
                ticker="SPY",
                asset_type=AssetType.ETF,
                quantity=Decimal("5"),
                avg_cost_usd=Decimal("400.00"),
            ),
        ],
    )


@pytest.fixture
def sample_ohlcv() -> list[OHLCV]:
    return [
        OHLCV(
            ticker="AAPL",
            date=date(2024, 1, i + 1),
            open=Decimal("150.00"),
            high=Decimal("155.00"),
            low=Decimal("148.00"),
            close=Decimal(str(150 + i * 2)),
            volume=1_000_000,
        )
        for i in range(10)
    ]
