from collections import defaultdict
from datetime import date, timedelta
from typing import Protocol

from financial_assistant.application.dtos.requests import HistoricalNewsQuery, NewsQuery
from financial_assistant.domain.models.news import DailySentiment, NewsArticle
from financial_assistant.domain.ports.historical_news_gateway import IHistoricalNewsGateway
from financial_assistant.domain.ports.sentiment_history_repository import ISentimentHistoryRepository


class SentimentAnalyzerProtocol(Protocol):
    """
    Protocol for sentiment analysis of news articles related to financial assets.
    This interface is for checking the sentiment analysis signture
    Nobody implements this directrly. mypy will check that the actual implementation
    (e.g. FinBERTSentimentAnalyzer) matches this protocol.
    """

    def score(self, ticker: str, articles: list[NewsArticle]) -> "SentimentResultProtocol": ...


class SentimentResultProtocol(Protocol):
    score: float
    label: str


class NewsService:
    def __init__(
        self,
        gateway: IHistoricalNewsGateway,
        sentiment_analyzer: SentimentAnalyzerProtocol,
        sentiment_repo: ISentimentHistoryRepository | None = None,
    ) -> None:
        self._gateway = gateway
        self._sentiment = sentiment_analyzer
        self._repo = sentiment_repo

    # Maximum number of recent headlines to surface per ticker
    _MAX_HEADLINES = 5
    # Days to look back when fetching fresh headlines for DB-cached tickers
    _HEADLINE_LOOKBACK_DAYS = 7

    async def analyze_sentiment(
        self, query: NewsQuery
    ) -> tuple[dict[str, list[DailySentiment]], dict[str, list[str]]]:
        """Return (daily_sentiment, recent_headlines) for the last 60 days.
        Sentiment for pre-computed tickers comes from DB; headlines always fetched live."""
        today = date.today()
        from_date = today - timedelta(days=60)

        if self._repo:
            cached = await self._repo.get_by_tickers(query.tickers, from_date, today)
            missing = [t for t in query.tickers if not cached.get(t)]

            # Tickers fully covered by DB — fetch headlines separately (no FinBERT)
            cached_tickers = [t for t in query.tickers if cached.get(t)]
            cached_headlines = await self._fetch_headlines(
                cached_tickers, today - timedelta(days=self._HEADLINE_LOOKBACK_DAYS), today
            )

            if not missing:
                return cached, cached_headlines

            live_sentiment, live_headlines = await self._analyze_range(missing, from_date, today)
            return {**cached, **live_sentiment}, {**cached_headlines, **live_headlines}

        return await self._analyze_range(query.tickers, from_date, today)

    async def analyze_historical_sentiment(
        self, query: HistoricalNewsQuery
    ) -> dict[str, list[DailySentiment]]:
        """Same as analyze_sentiment but with an explicit lookback window (no headlines)."""
        today = date.today()
        from_date = today - timedelta(days=query.lookback_days)
        sentiment, _ = await self._analyze_range(query.tickers, from_date, today)
        return sentiment

    async def _fetch_headlines(
        self, tickers: list[str], from_date: date, to_date: date
    ) -> dict[str, list[str]]:
        """Fetch recent article titles without running sentiment analysis."""
        result: dict[str, list[str]] = {}
        for ticker in tickers:
            articles = await self._gateway.fetch_articles_in_range(
                ticker=ticker, from_date=from_date, to_date=to_date
            )
            sorted_articles = sorted(articles, key=lambda a: a.published_at, reverse=True)
            result[ticker] = [a.title for a in sorted_articles[: self._MAX_HEADLINES] if a.title]
        return result

    async def _analyze_range(
        self, tickers: list[str], from_date: date, to_date: date
    ) -> tuple[dict[str, list[DailySentiment]], dict[str, list[str]]]:
        result: dict[str, list[DailySentiment]] = {}
        headlines: dict[str, list[str]] = {}

        for ticker in tickers:
            articles = await self._gateway.fetch_articles_in_range(
                ticker=ticker,
                from_date=from_date,
                to_date=to_date,
            )

            # Collect most recent headlines before grouping by day
            sorted_articles = sorted(articles, key=lambda a: a.published_at, reverse=True)
            headlines[ticker] = [
                a.title for a in sorted_articles[: self._MAX_HEADLINES] if a.title
            ]

            by_day: dict[date, list[NewsArticle]] = defaultdict(list)
            for article in articles:
                by_day[article.published_at.date()].append(article)

            daily: list[DailySentiment] = []
            for day in sorted(by_day):
                day_articles = by_day[day]
                sentiment = self._sentiment.score(ticker, day_articles)
                daily.append(
                    DailySentiment(
                        date=day,
                        ticker=ticker,
                        score=sentiment.score,
                        label=sentiment.label,
                        article_count=len(day_articles),
                    )
                )

            result[ticker] = daily

        return result, headlines
