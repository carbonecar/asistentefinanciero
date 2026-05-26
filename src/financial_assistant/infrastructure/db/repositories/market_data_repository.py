import logging
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from financial_assistant.domain.models.market_data import OHLCV, Quote
from financial_assistant.domain.ports.repositories import IMarketDataRepository
from financial_assistant.infrastructure.db.models import OHLCVRecordORM

logger = logging.getLogger(__name__)

_MAX_DAILY_CHANGE = 3.0  # rechaza si algún día cambia más de 3x (300%)


def _is_valid_price_sequence(records: list[OHLCV]) -> bool:
    if len(records) < 2:
        return True
    closes = [float(r.close) for r in records]
    for i in range(1, len(closes)):
        if closes[i - 1] > 0 and closes[i] / closes[i - 1] > _MAX_DAILY_CHANGE:
            logger.error(
                "[OHLCV] Precio anómalo detectado en %s: %.2f → %.2f (ratio %.1fx) — no se persiste",
                records[i].ticker,
                closes[i - 1],
                closes[i],
                closes[i] / closes[i - 1],
            )
            return False
    return True


class PostgresMarketDataRepository(IMarketDataRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save_ohlcv(self, records: list[OHLCV]) -> None:
        if not records:
            return
        if not _is_valid_price_sequence(records):
            return
        async with self._session_factory() as session:
            stmt = insert(OHLCVRecordORM).values(
                [
                    {
                        "ticker": r.ticker,
                        "date": r.date,
                        "open": r.open,
                        "high": r.high,
                        "low": r.low,
                        "close": r.close,
                        "volume": r.volume,
                    }
                    for r in records
                ]
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_ohlcv_ticker_date",
                set_={
                    "open": stmt.excluded.open,
                    "high": stmt.excluded.high,
                    "low": stmt.excluded.low,
                    "close": stmt.excluded.close,
                    "volume": stmt.excluded.volume,
                },
            )
            await session.execute(stmt)
            await session.commit()

    async def get_ohlcv(self, ticker: str, start: date, end: date) -> list[OHLCV]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(OHLCVRecordORM)
                .where(
                    OHLCVRecordORM.ticker == ticker,
                    OHLCVRecordORM.date >= start,
                    OHLCVRecordORM.date <= end,
                )
                .order_by(OHLCVRecordORM.date)
            )
            return [self._to_domain(r) for r in result.scalars().all()]

    async def get_latest_quote(self, ticker: str) -> Quote | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(OHLCVRecordORM)
                .where(OHLCVRecordORM.ticker == ticker)
                .order_by(OHLCVRecordORM.date.desc())
                .limit(1)
            )
            orm = result.scalar_one_or_none()
            if orm is None:
                return None
            return Quote(ticker=ticker, price=orm.close)

    def _to_domain(self, orm: OHLCVRecordORM) -> OHLCV:
        return OHLCV(
            ticker=orm.ticker,
            date=orm.date,
            open=Decimal(str(orm.open)),
            high=Decimal(str(orm.high)),
            low=Decimal(str(orm.low)),
            close=Decimal(str(orm.close)),
            volume=orm.volume,
        )
