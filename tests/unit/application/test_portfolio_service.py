from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from financial_assistant.application.dtos.requests import AddPositionCommand
from financial_assistant.application.services.portfolio_service import PortfolioService
from financial_assistant.domain.models.portfolio import AssetType, Portfolio, Position


@pytest.fixture
def mock_repo():
    repo = AsyncMock()
    repo.get_by_user_id.return_value = Portfolio(
        user_id=1,
        positions=[
            Position("AAPL", AssetType.STOCK, Decimal("10"), Decimal("150"))
        ],
    )
    return repo


@pytest.mark.asyncio
async def test_get_or_create_existing(mock_repo):
    service = PortfolioService(mock_repo)
    portfolio = await service.get_or_create(user_id=1)
    assert portfolio.user_id == 1
    mock_repo.save.assert_not_called()


@pytest.mark.asyncio
async def test_get_or_create_new(mock_repo):
    mock_repo.get_by_user_id.return_value = None
    service = PortfolioService(mock_repo)
    await service.get_or_create(user_id=99)
    mock_repo.save.assert_called_once()


@pytest.mark.asyncio
async def test_add_position(mock_repo):
    service = PortfolioService(mock_repo)
    cmd = AddPositionCommand(
        user_id=1,
        ticker="MSFT",
        asset_type=AssetType.STOCK,
        quantity=Decimal("5"),
        avg_cost_usd=Decimal("300"),
    )
    await service.add_position(cmd)
    mock_repo.upsert_position.assert_called_once()
    call_args = mock_repo.upsert_position.call_args
    assert call_args[0][0] == 1
    assert call_args[0][1].ticker == "MSFT"
