import asyncio
import logging
from datetime import datetime, timezone
from functools import partial

import yfinance as yf

from financial_assistant.domain.models.news import NewsArticle
from financial_assistant.domain.ports.news_gateway import INewsGateway

logger = logging.getLogger(__name__)


class YFinanceNewsGateway(INewsGateway):
    """Adapter for Yahoo Finance news via yfinance.

    The INewsGateway contract uses a free-text ``query`` string.  For
    Yahoo Finance the news endpoint is per-ticker, so we extract the
    first whitespace-delimited token of the query as the ticker symbol
    (e.g. ``"AAPL stock finance"`` → ``"AAPL"``).
    """

    async def fetch_articles(self, query: str, max_results: int = 20) -> list[NewsArticle]:
        ticker_symbol = query.split()[0] if query.strip() else ""
        if not ticker_symbol:
            return []

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, partial(self._fetch_sync, ticker_symbol, max_results)
        )

    def _fetch_sync(self, ticker_symbol: str, max_results: int) -> list[NewsArticle]:
        try:
            raw_news: list[dict] = yf.Ticker(ticker_symbol).news or []
        except Exception:  # pylint: disable=broad-exception-caught
            logger.warning("[YFinanceNews] Failed to fetch news for %s", ticker_symbol)
            return []

        articles: list[NewsArticle] = []
        for item in raw_news[:max_results]:
            # yfinance >=0.2.50 nests all fields under item["content"]
            payload: dict = item.get("content") or item

            # Parse publish date — new format uses ISO string, old format uses unix timestamp
            pub_date_raw = payload.get("pubDate") or payload.get("displayTime")
            if pub_date_raw:
                try:
                    published_at = datetime.fromisoformat(
                        pub_date_raw.replace("Z", "+00:00")
                    )
                except (ValueError, AttributeError):
                    published_at = datetime.now(tz=timezone.utc)
            else:
                ts = payload.get("providerPublishTime")
                try:
                    published_at = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else datetime.now(tz=timezone.utc)
                except (TypeError, ValueError, OSError):
                    published_at = datetime.now(tz=timezone.utc)

            title = payload.get("title") or ""
            summary = payload.get("summary") or payload.get("description") or ""

            # URL: new format uses canonicalUrl.url or clickThroughUrl.url
            canonical = payload.get("canonicalUrl") or payload.get("clickThroughUrl") or {}
            url = canonical.get("url") if isinstance(canonical, dict) else ""
            url = url or payload.get("link") or ""

            # Source name
            provider = payload.get("provider") or {}
            source = (provider.get("displayName") if isinstance(provider, dict) else None) or payload.get("publisher") or "Yahoo Finance"

            articles.append(
                NewsArticle(
                    title=title,
                    description=summary,
                    url=url,
                    published_at=published_at,
                    source=source,
                    content=summary,
                )
            )

        return articles
