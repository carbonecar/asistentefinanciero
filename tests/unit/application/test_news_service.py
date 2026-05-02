"""
Unit tests for NewsService.analyze_sentiment — B-3 fix and normal path.

Covers:
- When the gateway returns no articles for a ticker, a SentimentResult with
  article_count=0 is included in the output (B-3: silent skip eliminated).
- When articles are returned, the sentiment analyzer is called and its result
  is included normally.
- Multiple tickers: each produces its own SentimentResult regardless of
  whether articles were found.

No network, no DB, no real model — only AsyncMock / MagicMock.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from financial_assistant.application.dtos.requests import NewsQuery
from financial_assistant.application.services.news_service import NewsService
from financial_assistant.domain.models.news import NewsArticle, SentimentResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _article(title: str = "Apple beats estimates") -> NewsArticle:
    return NewsArticle(
        title=title,
        description="Revenue up",
        url="https://example.com",
        published_at=datetime.now(tz=UTC),
        source="Reuters",
        content="",
    )


def _sentiment(ticker: str, article_count: int = 5) -> SentimentResult:
    return SentimentResult(
        ticker=ticker,
        score=0.45,
        label="positive",
        article_count=article_count,
        representative_headlines=("Headline A",),
    )


def _make_service(
    articles_by_ticker: dict[str, list[NewsArticle]],
    analyzer_result: SentimentResult | None = None,
) -> NewsService:
    """
    Build a NewsService with mocked gateway and analyzer.

    gateway.fetch_articles returns articles_by_ticker[ticker] (empty list if missing).
    analyzer.score returns analyzer_result if provided; otherwise a generic positive result.
    """

    async def _fetch(query: str, max_results: int = 20) -> list[NewsArticle]:
        ticker = query.split()[0]
        return articles_by_ticker.get(ticker, [])

    gateway = MagicMock()
    gateway.fetch_articles = AsyncMock(side_effect=_fetch)

    analyzer = MagicMock()
    analyzer.score = MagicMock(
        side_effect=lambda ticker, arts: analyzer_result or _sentiment(ticker, len(arts))
    )

    return NewsService(gateway=gateway, sentiment_analyzer=analyzer)


# ---------------------------------------------------------------------------
# B-3 fix: ticker with no articles produces SentimentResult(article_count=0)
# ---------------------------------------------------------------------------


class TestNoArticlesTicker:
    @pytest.mark.asyncio
    async def test_result_included_for_ticker_with_no_articles(self):
        service = _make_service(articles_by_ticker={"AAPL": []})
        results = await service.analyze_sentiment(NewsQuery(tickers=["AAPL"]))
        assert len(results) == 1
        assert results[0].ticker == "AAPL"

    @pytest.mark.asyncio
    async def test_article_count_is_zero_when_no_articles(self):
        service = _make_service(articles_by_ticker={"AAPL": []})
        results = await service.analyze_sentiment(NewsQuery(tickers=["AAPL"]))
        assert results[0].article_count == 0

    @pytest.mark.asyncio
    async def test_label_is_neutral_when_no_articles(self):
        service = _make_service(articles_by_ticker={"AAPL": []})
        results = await service.analyze_sentiment(NewsQuery(tickers=["AAPL"]))
        assert results[0].label == "neutral"

    @pytest.mark.asyncio
    async def test_score_is_zero_when_no_articles(self):
        service = _make_service(articles_by_ticker={"AAPL": []})
        results = await service.analyze_sentiment(NewsQuery(tickers=["AAPL"]))
        assert results[0].score == 0.0

    @pytest.mark.asyncio
    async def test_headlines_empty_when_no_articles(self):
        service = _make_service(articles_by_ticker={"AAPL": []})
        results = await service.analyze_sentiment(NewsQuery(tickers=["AAPL"]))
        assert results[0].representative_headlines == ()

    @pytest.mark.asyncio
    async def test_analyzer_not_called_when_no_articles(self):
        gateway = MagicMock()
        gateway.fetch_articles = AsyncMock(return_value=[])
        analyzer = MagicMock()
        analyzer.score = MagicMock()

        service = NewsService(gateway=gateway, sentiment_analyzer=analyzer)
        await service.analyze_sentiment(NewsQuery(tickers=["AAPL"]))

        analyzer.score.assert_not_called()


# ---------------------------------------------------------------------------
# Normal path: articles present → analyzer called → result appended
# ---------------------------------------------------------------------------


class TestNormalPath:
    @pytest.mark.asyncio
    async def test_result_includes_analyzer_output(self):
        articles = [_article()]
        service = _make_service({"AAPL": articles}, analyzer_result=_sentiment("AAPL", 1))
        results = await service.analyze_sentiment(NewsQuery(tickers=["AAPL"]))
        assert results[0].ticker == "AAPL"
        assert results[0].article_count == 1

    @pytest.mark.asyncio
    async def test_analyzer_called_with_correct_ticker_and_articles(self):
        articles = [_article("Big news")]
        gateway = MagicMock()
        gateway.fetch_articles = AsyncMock(return_value=articles)
        analyzer = MagicMock()
        analyzer.score = MagicMock(return_value=_sentiment("AAPL", 1))

        service = NewsService(gateway=gateway, sentiment_analyzer=analyzer)
        await service.analyze_sentiment(NewsQuery(tickers=["AAPL"]))

        analyzer.score.assert_called_once_with("AAPL", articles)

    @pytest.mark.asyncio
    async def test_result_count_equals_ticker_count_when_all_have_articles(self):
        service = _make_service({"AAPL": [_article()], "TSLA": [_article()]})
        results = await service.analyze_sentiment(NewsQuery(tickers=["AAPL", "TSLA"]))
        assert len(results) == 2


# ---------------------------------------------------------------------------
# Multiple tickers — mixed coverage
# ---------------------------------------------------------------------------


class TestMultipleTickers:
    @pytest.mark.asyncio
    async def test_all_tickers_present_in_results_when_mixed(self):
        # AAPL has articles, TSLA does not
        service = _make_service({"AAPL": [_article()], "TSLA": []})
        results = await service.analyze_sentiment(NewsQuery(tickers=["AAPL", "TSLA"]))
        tickers = [r.ticker for r in results]
        assert "AAPL" in tickers
        assert "TSLA" in tickers

    @pytest.mark.asyncio
    async def test_result_count_equals_ticker_count_regardless_of_coverage(self):
        service = _make_service({"AAPL": [_article()], "TSLA": [], "MSFT": []})
        results = await service.analyze_sentiment(NewsQuery(tickers=["AAPL", "TSLA", "MSFT"]))
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_ticker_without_articles_has_article_count_zero(self):
        service = _make_service({"AAPL": [_article()], "TSLA": []})
        results = await service.analyze_sentiment(NewsQuery(tickers=["AAPL", "TSLA"]))
        tsla = next(r for r in results if r.ticker == "TSLA")
        assert tsla.article_count == 0

    @pytest.mark.asyncio
    async def test_ticker_with_articles_has_correct_article_count(self):
        service = _make_service({"AAPL": [_article(), _article()], "TSLA": []})
        results = await service.analyze_sentiment(NewsQuery(tickers=["AAPL", "TSLA"]))
        aapl = next(r for r in results if r.ticker == "AAPL")
        assert aapl.article_count == 2

    @pytest.mark.asyncio
    async def test_empty_tickers_list_returns_empty(self):
        service = _make_service({})
        results = await service.analyze_sentiment(NewsQuery(tickers=[]))
        assert results == []
