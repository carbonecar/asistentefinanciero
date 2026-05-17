from abc import ABC, abstractmethod
from datetime import date

from financial_assistant.domain.models.news import NewsArticle


class IHistoricalNewsGateway(ABC):
    """Port for fetching news articles within a specific date range for a ticker."""

    @abstractmethod
    async def fetch_articles_in_range(
        self,
        ticker: str,
        from_date: date,
        to_date: date,
    ) -> list[NewsArticle]: ...
