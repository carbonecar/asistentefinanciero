"""
Unit tests for QuantService.optimize — sentiment_map filtering.

Verifies that SentimentResult entries with article_count=0 are excluded from
the sentiment_map passed to the optimizer.  article_count=0 means no articles
were found or FinBERT failed; score=0.0 in that case is absence-of-data, not
a confirmed neutral signal (Kondratenko §4 / Arratia §4).

No DB, no network — only AsyncMock / MagicMock.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from decimal import Decimal

from financial_assistant.application.dtos.requests import OptimizePortfolioQuery
from financial_assistant.application.services.quant_service import QuantService
from financial_assistant.domain.models.analysis import OptimizedWeights, QuantResult
from financial_assistant.domain.models.news import SentimentResult
from financial_assistant.domain.models.portfolio import AssetType, Portfolio, Position

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _portfolio_with(tickers: list[str]) -> Portfolio:
    positions = [
        Position(ticker=t, quantity=Decimal("10"), avg_cost_usd=Decimal("100"), asset_type=AssetType.STOCK)
        for t in tickers
    ]
    return Portfolio(user_id=1, positions=positions)


def _sentiment(ticker: str, article_count: int, score: float = 0.5) -> SentimentResult:
    return SentimentResult(
        ticker=ticker,
        score=score,
        label="positive" if score > 0.05 else "neutral",
        article_count=article_count,
        representative_headlines=(),
    )


def _make_service(captured_map: dict) -> QuantService:
    """
    Build a QuantService whose optimizer captures the sentiment_map it receives.
    The captured map is written into `captured_map` so tests can inspect it.
    """
    portfolio = _portfolio_with(["AAPL", "TSLA"])

    repo = MagicMock()
    repo.get_by_user_id = AsyncMock(return_value=portfolio)

    gateway = MagicMock()
    gateway.fetch_ohlcv = AsyncMock(return_value=[])

    weights = OptimizedWeights(
        weights={"AAPL": 0.6, "TSLA": 0.4},
        expected_annual_return=0.12,
        annual_volatility=0.18,
        sharpe_ratio=0.67,
    )

    def _capture_minimum_variance(ohlcv_by_ticker, sentiment_map):
        captured_map.update(sentiment_map)
        return weights

    optimizer = MagicMock()
    optimizer.minimum_variance = MagicMock(side_effect=_capture_minimum_variance)

    simulator = MagicMock()
    simulator.simulate = MagicMock(return_value=None)

    return QuantService(
        portfolio_repo=repo,
        market_gateway=gateway,
        optimizer=optimizer,
        simulator=simulator,
    )


# ---------------------------------------------------------------------------
# Filtering: article_count=0 must not enter sentiment_map
# ---------------------------------------------------------------------------


class TestSentimentMapFiltering:
    @pytest.mark.asyncio
    async def test_article_count_zero_excluded_from_sentiment_map(self):
        captured: dict = {}
        service = _make_service(captured)
        query = OptimizePortfolioQuery(user_id=1, use_sentiment=True)

        sentiment = [
            _sentiment("AAPL", article_count=5, score=0.6),
            _sentiment("TSLA", article_count=0, score=0.0),  # failure fallback
        ]
        await service.optimize(query, sentiment_results=sentiment)

        assert "TSLA" not in captured, (
            "article_count=0 is absence-of-data, not confirmed neutral — "
            "must not contaminate the sentiment_map"
        )

    @pytest.mark.asyncio
    async def test_article_count_zero_excluded_even_with_nonzero_score(self):
        """Edge case: score != 0.0 but article_count=0 must still be excluded."""
        captured: dict = {}
        service = _make_service(captured)
        query = OptimizePortfolioQuery(user_id=1, use_sentiment=True)

        sentiment = [
            _sentiment("AAPL", article_count=5, score=0.4),
            _sentiment("TSLA", article_count=0, score=0.3),
        ]
        await service.optimize(query, sentiment_results=sentiment)

        assert "TSLA" not in captured

    @pytest.mark.asyncio
    async def test_valid_tickers_remain_in_sentiment_map(self):
        captured: dict = {}
        service = _make_service(captured)
        query = OptimizePortfolioQuery(user_id=1, use_sentiment=True)

        sentiment = [
            _sentiment("AAPL", article_count=5, score=0.6),
            _sentiment("TSLA", article_count=0, score=0.0),
        ]
        await service.optimize(query, sentiment_results=sentiment)

        assert "AAPL" in captured
        assert captured["AAPL"] == pytest.approx(0.6)

    @pytest.mark.asyncio
    async def test_all_zero_article_count_produces_empty_sentiment_map(self):
        captured: dict = {}
        service = _make_service(captured)
        query = OptimizePortfolioQuery(user_id=1, use_sentiment=True)

        sentiment = [
            _sentiment("AAPL", article_count=0, score=0.0),
            _sentiment("TSLA", article_count=0, score=0.0),
        ]
        await service.optimize(query, sentiment_results=sentiment)

        assert captured == {}

    @pytest.mark.asyncio
    async def test_none_sentiment_results_produces_empty_map(self):
        captured: dict = {}
        service = _make_service(captured)
        query = OptimizePortfolioQuery(user_id=1, use_sentiment=True)

        await service.optimize(query, sentiment_results=None)

        assert captured == {}

    @pytest.mark.asyncio
    async def test_all_valid_article_counts_all_included(self):
        captured: dict = {}
        service = _make_service(captured)
        query = OptimizePortfolioQuery(user_id=1, use_sentiment=True)

        sentiment = [
            _sentiment("AAPL", article_count=3, score=0.5),
            _sentiment("TSLA", article_count=1, score=-0.2),
        ]
        await service.optimize(query, sentiment_results=sentiment)

        assert "AAPL" in captured
        assert "TSLA" in captured

    @pytest.mark.asyncio
    async def test_use_sentiment_false_passes_empty_map_regardless(self):
        captured: dict = {}
        service = _make_service(captured)
        query = OptimizePortfolioQuery(user_id=1, use_sentiment=False)

        sentiment = [_sentiment("AAPL", article_count=5, score=0.6)]
        await service.optimize(query, sentiment_results=sentiment)

        assert captured == {}
