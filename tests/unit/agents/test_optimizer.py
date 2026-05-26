"""Unit tests for PortfolioOptimizer — invariants only, no exact value assertions."""

from datetime import date
from decimal import Decimal
from math import isfinite

import pytest

from financial_assistant.agents.quant.optimizer import PortfolioOptimizer
from financial_assistant.domain.models.market_data import OHLCV


def _make_prices(ticker: str, prices: list[float]) -> list[OHLCV]:
    return [
        OHLCV(
            ticker=ticker,
            date=date(2024, 1, i + 1),
            open=Decimal(str(p)),
            high=Decimal(str(p + 1)),
            low=Decimal(str(p - 1)),
            close=Decimal(str(p)),
            volume=100_000,
        )
        for i, p in enumerate(prices)
    ]


@pytest.fixture
def optimizer() -> PortfolioOptimizer:
    return PortfolioOptimizer(risk_free_rate=0.05, sentiment_lambda=0.15)


@pytest.fixture
def two_asset_input() -> dict:
    return {
        "AAPL": _make_prices("AAPL", [100, 102, 101, 105, 107, 106, 110, 112, 111, 115]),
        "GOOGL": _make_prices("GOOGL", [200, 198, 202, 205, 203, 207, 210, 208, 212, 215]),
    }


@pytest.fixture
def four_asset_input() -> dict:
    return {
        "AAPL": _make_prices("AAPL", [100, 102, 101, 105, 107, 106, 110, 112, 111, 115]),
        "GOOGL": _make_prices("GOOGL", [200, 198, 202, 205, 203, 207, 210, 208, 212, 215]),
        "GLD": _make_prices("GLD", [150, 151, 149, 152, 153, 151, 154, 155, 153, 156]),
        "KO": _make_prices("KO", [50, 51, 50, 52, 53, 52, 54, 55, 54, 56]),
    }


class TestMinimumVarianceWeights:
    def test_weights_sum_to_one(self, optimizer, two_asset_input):
        result = optimizer.minimum_variance(two_asset_input)
        assert result is not None
        assert abs(sum(result.weights.values()) - 1.0) < 1e-4

    def test_all_weights_bounded(self, optimizer, two_asset_input):
        result = optimizer.minimum_variance(two_asset_input)
        assert result is not None
        assert all(0.0 <= w <= 1.0 for w in result.weights.values())

    def test_weights_keys_match_tickers(self, optimizer, two_asset_input):
        result = optimizer.minimum_variance(two_asset_input)
        assert result is not None
        assert set(result.weights.keys()) == set(two_asset_input.keys())

    def test_metrics_are_finite(self, optimizer, two_asset_input):
        result = optimizer.minimum_variance(two_asset_input)
        assert result is not None
        assert isfinite(result.expected_annual_return)
        assert isfinite(result.annual_volatility)
        assert isfinite(result.sharpe_ratio)

    def test_volatility_is_positive(self, optimizer, two_asset_input):
        result = optimizer.minimum_variance(two_asset_input)
        assert result is not None
        assert result.annual_volatility > 0

    def test_four_assets(self, optimizer, four_asset_input):
        result = optimizer.minimum_variance(four_asset_input)
        assert result is not None
        assert abs(sum(result.weights.values()) - 1.0) < 1e-4

    def test_expected_returns_per_ticker_present(self, optimizer, two_asset_input):
        result = optimizer.minimum_variance(two_asset_input)
        assert result is not None
        assert set(result.expected_returns_per_ticker.keys()) == set(two_asset_input.keys())


class TestEdgeCases:
    def test_single_ticker_returns_none(self, optimizer):
        data = {"AAPL": _make_prices("AAPL", [100, 102, 104, 106, 108])}
        assert optimizer.minimum_variance(data) is None

    def test_empty_input_returns_none(self, optimizer):
        assert optimizer.minimum_variance({}) is None

    def test_empty_records_returns_none(self, optimizer):
        assert optimizer.minimum_variance({"AAPL": [], "GOOGL": []}) is None


class TestSentimentAdjustment:
    def test_sentiment_adjusts_expected_return(self, optimizer, two_asset_input):
        base = optimizer.minimum_variance(two_asset_input)
        adjusted = optimizer.minimum_variance(two_asset_input, sentiment_map={"AAPL": 1.0})
        assert base is not None and adjusted is not None
        assert adjusted.expected_returns_per_ticker["AAPL"] > base.expected_returns_per_ticker["AAPL"]

    def test_negative_sentiment_decreases_expected_return(self, optimizer, two_asset_input):
        base = optimizer.minimum_variance(two_asset_input)
        adjusted = optimizer.minimum_variance(two_asset_input, sentiment_map={"AAPL": -1.0})
        assert base is not None and adjusted is not None
        assert adjusted.expected_returns_per_ticker["AAPL"] < base.expected_returns_per_ticker["AAPL"]

    def test_sentiment_changes_weights(self, optimizer, two_asset_input):
        # same objective (max_sharpe), different μ input → different weights
        base = optimizer.minimum_variance(two_asset_input)
        adjusted = optimizer.minimum_variance(two_asset_input, sentiment_map={"AAPL": 1.0})
        assert base is not None and adjusted is not None
        assert base.weights != adjusted.weights

    def test_sentiment_weights_still_valid(self, optimizer, two_asset_input):
        result = optimizer.minimum_variance(two_asset_input, sentiment_map={"AAPL": 1.0})
        assert result is not None
        assert abs(sum(result.weights.values()) - 1.0) < 1e-4
        assert all(0.0 <= w <= 1.0 for w in result.weights.values())

    def test_unknown_ticker_in_sentiment_map_is_ignored(self, optimizer, two_asset_input):
        result = optimizer.minimum_variance(two_asset_input, sentiment_map={"UNKNOWN": 0.9})
        assert result is not None
        assert abs(sum(result.weights.values()) - 1.0) < 1e-4

    def test_zero_sentiment_has_no_effect_on_mu(self, optimizer, two_asset_input):
        base = optimizer.minimum_variance(two_asset_input)
        adjusted = optimizer.minimum_variance(two_asset_input, sentiment_map={"AAPL": 0.0})
        assert base is not None and adjusted is not None
        assert base.expected_returns_per_ticker["AAPL"] == adjusted.expected_returns_per_ticker["AAPL"]
