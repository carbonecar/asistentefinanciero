from decimal import Decimal

from financial_assistant.application.dtos.requests import AddPositionCommand
from financial_assistant.domain.models.portfolio import Portfolio, Position
from financial_assistant.domain.ports.repositories import IPortfolioRepository


class PortfolioService:
    def __init__(self, repository: IPortfolioRepository) -> None:
        self._repository = repository

    async def get_or_create(self, user_id: int) -> Portfolio:
        portfolio = await self._repository.get_by_user_id(user_id)
        if portfolio is None:
            portfolio = Portfolio(user_id=user_id)
            await self._repository.save(portfolio)
        return portfolio

    async def add_position(self, cmd: AddPositionCommand) -> Portfolio:
        await self.get_or_create(cmd.user_id)
        position = Position(
            ticker=cmd.ticker,
            asset_type=cmd.asset_type,
            quantity=cmd.quantity,
            avg_cost_usd=cmd.avg_cost_usd,
            currency=cmd.currency,
        )
        await self._repository.upsert_position(cmd.user_id, position)
        portfolio = await self._repository.get_by_user_id(cmd.user_id)
        return portfolio  # type: ignore[return-value]

    async def remove_position(self, user_id: int, ticker: str) -> None:
        await self._repository.delete_position(user_id, ticker)
