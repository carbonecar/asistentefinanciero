from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from financial_assistant.domain.models.portfolio import AssetType, Portfolio, Position
from financial_assistant.domain.ports.repositories import IPortfolioRepository
from financial_assistant.infrastructure.db.models import PortfolioORM, PositionORM


class PostgresPortfolioRepository(IPortfolioRepository): # type: ignore[misc]
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_by_user_id(self, user_id: int) -> Portfolio | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(PortfolioORM)
                .options(selectinload(PortfolioORM.positions))
                .where(PortfolioORM.user_id == user_id)
            )
            orm = result.scalar_one_or_none()
            if orm is None:
                return None
            return self._to_domain(orm)

    async def save(self, portfolio: Portfolio) -> None:
        async with self._session_factory() as session:
            now = datetime.now(UTC)
            orm = PortfolioORM(
                user_id=portfolio.user_id,
                created_at=now,
                updated_at=now,
            )
            session.add(orm)
            await session.commit()

    async def upsert_position(self, user_id: int, position: Position) -> None:
        async with self._session_factory() as session:
            portfolio_result = await session.execute(select(PortfolioORM).where(PortfolioORM.user_id == user_id))
            portfolio_orm = portfolio_result.scalar_one_or_none()
            if portfolio_orm is None:
                now = datetime.now(UTC)
                portfolio_orm = PortfolioORM(user_id=user_id, created_at=now, updated_at=now)
                session.add(portfolio_orm)
                await session.flush()

            existing_result = await session.execute(
                select(PositionORM).where(
                    PositionORM.portfolio_id == portfolio_orm.id,
                    PositionORM.ticker == position.ticker,
                )
            )
            existing = existing_result.scalar_one_or_none()
            if existing:
                existing.quantity = position.quantity
                existing.avg_cost_usd = position.avg_cost_usd
                existing.currency = position.currency
            else:
                session.add(
                    PositionORM(
                        portfolio_id=portfolio_orm.id,
                        ticker=position.ticker,
                        asset_type=position.asset_type.value,
                        quantity=position.quantity,
                        avg_cost_usd=position.avg_cost_usd,
                        currency=position.currency,
                    )
                )

            portfolio_orm.updated_at = datetime.now(UTC)
            await session.commit()

    async def delete_position(self, user_id: int, ticker: str) -> None:
        async with self._session_factory() as session:
            portfolio_result = await session.execute(select(PortfolioORM).where(PortfolioORM.user_id == user_id))
            portfolio_orm = portfolio_result.scalar_one_or_none()
            if portfolio_orm is None:
                return

            position_result = await session.execute(
                select(PositionORM).where(
                    PositionORM.portfolio_id == portfolio_orm.id,
                    PositionORM.ticker == ticker,
                )
            )
            position_orm = position_result.scalar_one_or_none()
            if position_orm:
                await session.delete(position_orm)
                await session.commit()

    def _to_domain(self, orm: PortfolioORM) -> Portfolio:
        positions = [
            Position(
                ticker=p.ticker,
                asset_type=AssetType(p.asset_type),
                quantity=p.quantity,
                avg_cost_usd=p.avg_cost_usd,
                currency=p.currency,
            )
            for p in orm.positions
        ]
        return Portfolio(
            user_id=orm.user_id,
            positions=positions,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )
