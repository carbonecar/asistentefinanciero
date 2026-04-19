import asyncio
import logging
from datetime import datetime
from functools import partial

from financial_assistant.domain.models.news import NewsArticle
from financial_assistant.domain.ports.news_gateway import INewsGateway

logger = logging.getLogger(__name__)


class NewsAPIGateway(INewsGateway):  # type: ignore[misc]
    """Adapter for newsapi.org — wraps sync client in thread executor."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        if not api_key:
            logger.warning("NewsAPIGateway: NEWSAPI_KEY not set — news fetching is disabled")

    async def fetch_articles(self, query: str, max_results: int = 20) -> list[NewsArticle]:
        if not self._api_key:
            logger.debug("NewsAPIGateway: skipping fetch (no API key) for query=%r", query)
            return []
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(self._fetch_sync, query, max_results))

    def _fetch_sync(self, query: str, max_results: int) -> list[NewsArticle]:
        try:
            from newsapi import NewsApiClient

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
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.error("NewsAPIGateway._fetch_sync failed for query=%r: %s", query, exc)
            return []
