from abc import ABC, abstractmethod

from financial_assistant.domain.models.news import NewsArticle


class INewsGateway(ABC):
    @abstractmethod
    async def fetch_articles(self, query: str, max_results: int = 20) -> list[NewsArticle]: ...
