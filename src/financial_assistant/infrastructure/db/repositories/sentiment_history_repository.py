from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from financial_assistant.domain.models.news import DailySentiment
from financial_assistant.domain.ports.sentiment_history_repository import ISentimentHistoryRepository
from financial_assistant.infrastructure.db.models import SentimentHistoryORM


class PostgresSentimentHistoryRepository(ISentimentHistoryRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save(self, records: list[DailySentiment]) -> None:
        if not records:
            return
        async with self._session_factory() as session:
            stmt = insert(SentimentHistoryORM).values(
                [
                    {
                        "ticker": r.ticker,
                        "date": r.date,
                        "score": r.score,
                        "label": r.label,
                        "article_count": r.article_count,
                    }
                    for r in records
                ]
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_sentiment_ticker_date",
                set_={
                    "score": stmt.excluded.score,
                    "label": stmt.excluded.label,
                    "article_count": stmt.excluded.article_count,
                },
            )
            await session.execute(stmt)
            await session.commit()

    async def get_by_tickers(
        self,
        tickers: list[str],
        from_date: date,
        to_date: date,
    ) -> dict[str, list[DailySentiment]]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(SentimentHistoryORM)
                .where(
                    SentimentHistoryORM.ticker.in_(tickers),
                    SentimentHistoryORM.date >= from_date,
                    SentimentHistoryORM.date <= to_date,
                )
                .order_by(SentimentHistoryORM.ticker, SentimentHistoryORM.date)
            )
            rows = result.scalars().all()

        by_ticker: dict[str, list[DailySentiment]] = defaultdict(list)
        for row in rows:
            by_ticker[row.ticker].append(
                DailySentiment(
                    date=row.date,
                    ticker=row.ticker,
                    score=row.score,
                    label=row.label,
                    article_count=row.article_count,
                )
            )
        return dict(by_ticker)

    async def get_latest_date(self, ticker: str) -> date | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(SentimentHistoryORM.date)
                .where(SentimentHistoryORM.ticker == ticker)
                .order_by(SentimentHistoryORM.date.desc())
                .limit(1)
            )
            row = result.scalar_one_or_none()
        return row if row is None else row
