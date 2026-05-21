import asyncio
import logging
from datetime import UTC, date, datetime, timedelta
from functools import partial
from typing import Any

import httpx

from financial_assistant.domain.models.news import NewsArticle
from financial_assistant.domain.ports.historical_news_gateway import IHistoricalNewsGateway
from financial_assistant.domain.ports.news_gateway import INewsGateway

logger = logging.getLogger(__name__)

_BASE_URL = "https://finnhub.io/api/v1/company-news"
_TIMEOUT_SECONDS = 15.0
_LOOKBACK_DAYS = 60
_CHUNK_DAYS = 7  # split range into weekly chunks to bypass per-request article limits


class FinnhubNewsGateway(INewsGateway, IHistoricalNewsGateway):
    """Adapter for Finnhub /company-news endpoint.

    Implements both INewsGateway (recent news) and IHistoricalNewsGateway
    (date-range news) so it can replace YFinanceNewsGateway entirely.

    Free tier: 60 calls/minute, historical data available.
    API docs: https://finnhub.io/docs/api/company-news
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    # ------------------------------------------------------------------
    # INewsGateway - used by NewsService.analyze_sentiment
    # Fetches the last 60 days of news for the ticker extracted from query.
    # ------------------------------------------------------------------
    async def fetch_articles(self, query: str, max_results: int = 20) -> list[NewsArticle]:
        ticker = query.split()[0] if query.strip() else ""
        if not ticker:
            return []
        today = date.today()
        articles = await self.fetch_articles_in_range(
            ticker=ticker,
            from_date=today - timedelta(days=_LOOKBACK_DAYS),
            to_date=today,
        )
        return articles[:max_results]

    # ------------------------------------------------------------------
    # IHistoricalNewsGateway - used by NewsService.analyze_historical_sentiment
    # Splits the range into weekly chunks to get full coverage.
    # ------------------------------------------------------------------
    async def fetch_articles_in_range(
        self,
        ticker: str,
        from_date: date,
        to_date: date,
    ) -> list[NewsArticle]:
        if not self._api_key:
            logger.warning("[Finnhub] No API key configured - returning empty")
            return []

        # Build weekly chunks: [from_date, from_date+7), [from_date+7, from_date+14), …
        chunks: list[tuple[date, date]] = []
        chunk_start = from_date
        while chunk_start < to_date:
            chunk_end = min(chunk_start + timedelta(days=_CHUNK_DAYS), to_date)
            chunks.append((chunk_start, chunk_end))
            chunk_start = chunk_end

        loop = asyncio.get_running_loop()
        all_articles: list[NewsArticle] = []
        for chunk_from, chunk_to in chunks:
            batch = await loop.run_in_executor(
                None, partial(self._fetch_sync, ticker, chunk_from, chunk_to)
            )
            all_articles.extend(batch)

        # Deduplicate by URL and filter out articles outside the requested range
        seen: set[str] = set()
        result: list[NewsArticle] = []
        for article in all_articles:
            art_date = article.published_at.date()
            if art_date < from_date or art_date > to_date:
                continue
            key = article.url or article.title
            if key in seen:
                continue
            seen.add(key)
            result.append(article)

        return sorted(result, key=lambda a: a.published_at)

    def _fetch_sync(self, ticker: str, from_date: date, to_date: date) -> list[NewsArticle]:
        params = {
            "symbol": ticker,
            "from": from_date.isoformat(),
            "to": to_date.isoformat(),
            "token": self._api_key,
        }
        try:
            with httpx.Client(timeout=_TIMEOUT_SECONDS) as client:
                response = client.get(_BASE_URL, params=params)
                response.raise_for_status()
                items: list[dict[str, Any]] = response.json() or []
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("[Finnhub] Failed to fetch news for %s (%s -> %s)", ticker, from_date, to_date)
            return []

        articles: list[NewsArticle] = []
        for item in items:
            try:
                published_at = datetime.fromtimestamp(item["datetime"], tz=UTC)
            except (KeyError, TypeError, ValueError, OSError):
                published_at = datetime.now(tz=UTC)

            headline = item.get("headline") or ""
            summary = item.get("summary") or ""

            articles.append(
                NewsArticle(
                    title=headline,
                    description=summary,
                    url=item.get("url") or "",
                    published_at=published_at,
                    source=item.get("source") or "Finnhub",
                    content=summary,
                )
            )

        return articles
