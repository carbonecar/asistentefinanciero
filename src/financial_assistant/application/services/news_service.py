from typing import Protocol

from financial_assistant.application.dtos.requests import NewsQuery
from financial_assistant.domain.models.news import NewsArticle, SentimentResult
from financial_assistant.domain.ports.news_gateway import INewsGateway


class SentimentAnalyzerProtocol(Protocol):
    """
    Protocol for sentiment analysis of news articles related to financial assets.
    This interface is for checking the sentiment analysis signture
    Nobody implements this directrly. mypy will check that the actual implementation
    (e.g. TextBlobSentimentAnalyzer) matches this protocol.
    """

    def score(self, ticker: str, articles: list[NewsArticle]) -> SentimentResult: ...


class NewsService:
    def __init__(
        self,
        gateway: INewsGateway,
        sentiment_analyzer: SentimentAnalyzerProtocol,
    ) -> None:
        self._gateway = gateway
        self._sentiment = sentiment_analyzer

    async def analyze_sentiment(self, query: NewsQuery) -> list[SentimentResult]:
        results: list[SentimentResult] = []
        for ticker in query.tickers:
            articles = await self._gateway.fetch_articles(
                query=f"{ticker} stock finance",
                max_results=query.max_articles_per_ticker,
            )
            if not articles:
                # article_count=0 signals "no coverage" — _build_data_summary displays
                # "sin análisis disponible" to the user via the I-1/I-3 invariant.
                results.append(
                    SentimentResult(
                        ticker=ticker,
                        score=0.0,
                        label="neutral",
                        article_count=0,
                        representative_headlines=(),
                    )
                )
                continue
            result = self._sentiment.score(ticker, articles)
            results.append(result)
        return results
