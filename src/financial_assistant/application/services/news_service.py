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

    async def analyze_sentiment(self, query: NewsQuery) -> dict[str, list[DailySentiment]]:
        """Return daily sentiment for the last 60 days.
        Reads from DB when pre-computed data is available; falls back to live Finnhub."""
        today = date.today()
        from_date = today - timedelta(days=60)

        if self._repo:
            cached = await self._repo.get_by_tickers(query.tickers, from_date, today)
            # Use DB for tickers that have data; compute live only for those that don't
            missing = [t for t in query.tickers if not cached.get(t)]
            if not missing:
                return cached
            live = await self._analyze_range(missing, from_date, today)
            return {**cached, **live}

        return await self._analyze_range(query.tickers, from_date, today)

    async def analyze_historical_sentiment(
        self, query: HistoricalNewsQuery
    ) -> dict[str, list[DailySentiment]]:
        """Same as analyze_sentiment but with an explicit lookback window."""
        today = date.today()
        from_date = today - timedelta(days=query.lookback_days)
        return await self._analyze_range(query.tickers, from_date, today)

    async def _analyze_range(
        self, tickers: list[str], from_date: date, to_date: date
    ) -> dict[str, list[DailySentiment]]:
        result: dict[str, list[DailySentiment]] = {}

        for ticker in tickers:
            articles = await self._gateway.fetch_articles_in_range(
                ticker=ticker,
                from_date=from_date,
                to_date=to_date,
            )

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

        return result
