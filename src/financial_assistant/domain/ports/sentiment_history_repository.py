from abc import ABC, abstractmethod
from datetime import date

from financial_assistant.domain.models.news import DailySentiment


class ISentimentHistoryRepository(ABC):
    @abstractmethod
    async def save(self, records: list[DailySentiment]) -> None:
        """Upsert daily sentiment records (on conflict by ticker+date: update)."""
        ...

    @abstractmethod
    async def get_by_tickers(
        self,
        tickers: list[str],
        from_date: date,
        to_date: date,
    ) -> dict[str, list[DailySentiment]]:
        """Return daily sentiment keyed by ticker, sorted by date ascending."""
        ...

    @abstractmethod
    async def get_latest_date(self, ticker: str) -> date | None:
        """Return the most recent date stored for this ticker, or None."""
        ...
