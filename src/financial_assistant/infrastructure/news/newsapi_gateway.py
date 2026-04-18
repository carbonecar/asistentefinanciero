import asyncio
from datetime import datetime
from functools import partial

from financial_assistant.domain.models.news import NewsArticle
from financial_assistant.domain.ports.news_gateway import INewsGateway


class NewsAPIGateway(INewsGateway):
    """Adapter for newsapi.org — wraps sync client in thread executor."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def fetch_articles(self, query: str, max_results: int = 20) -> list[NewsArticle]:
        if not self._api_key:
            return []
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(self._fetch_sync, query, max_results))

    def _fetch_sync(self, query: str, max_results: int) -> list[NewsArticle]:
        try:
            from newsapi import NewsApiClient  # type: ignore[import-untyped]  # pylint: disable=import-outside-toplevel

            client = NewsApiClient(api_key=self._api_key)
            response = client.get_everything(
                q=query,
                language="en",
                sort_by="publishedAt",
                page_size=min(max_results, 100),
            )
            articles = []
            for item in response.get("articles") or []:
                try:
                    published_at = datetime.fromisoformat(item["publishedAt"].replace("Z", "+00:00"))
                except (ValueError, KeyError):
                    published_at = datetime.utcnow()

                articles.append(
                    NewsArticle(
                        title=item.get("title") or "",
                        description=item.get("description") or "",
                        url=item.get("url") or "",
                        published_at=published_at,
                        source=item.get("source", {}).get("name", ""),
                        content=item.get("content") or "",
                    )
                )
            return articles
        except Exception:  # pylint: disable=broad-exception-caught
            return []
