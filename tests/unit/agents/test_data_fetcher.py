"""
Unit tests for the DataFetcher agent.

All tests use unittest.mock — no DB or network required.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from financial_assistant.agents.data_fetcher.agent import _normalize_tickers, make_data_fetcher_node
from financial_assistant.domain.models.market_data import OHLCV

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ohlcv(ticker: str, close: float = 100.0, d: date = date(2024, 1, 2)) -> OHLCV:
    return OHLCV(
        ticker=ticker,
        date=d,
        open=Decimal(str(close)),
        high=Decimal(str(close)),
        low=Decimal(str(close)),
        close=Decimal(str(close)),
        volume=1000,
    )


def _make_state(**kwargs) -> dict:
    base = {
        "user_id": 42,
        "user_message": "test",
        "messages": [],
        "intents": ["data_fetch"],
        "active_tickers": [],
        "period": "1y",
        "use_sentiment": False,
        "market_data_result": None,
        "audit_report": None,
        "quant_result": None,
        "news_results": None,
        "final_response": None,
        "errors": [],
    }
    base.update(kwargs)
    return base


def _make_service(ohlcv_by_ticker: dict) -> MagicMock:
    svc = MagicMock()
    svc.fetch_and_persist = AsyncMock(return_value=ohlcv_by_ticker)
    return svc


# ---------------------------------------------------------------------------
# _normalize_tickers — unit tests
# ---------------------------------------------------------------------------


class TestNormalizeTickers:
    def test_uppercase(self):
        valid, rejected = _normalize_tickers(["aapl"])
        assert valid == ["AAPL"]
        assert rejected == []

    def test_strip_whitespace(self):
        valid, rejected = _normalize_tickers(["  AAPL  "])
        assert valid == ["AAPL"]
        assert rejected == []

    def test_deduplication(self):
        valid, rejected = _normalize_tickers(["AAPL", "aapl", "AAPL"])
        assert valid == ["AAPL"]
        assert rejected == []

    def test_empty_string_dropped_silently(self):
        valid, rejected = _normalize_tickers(["", "AAPL"])
        assert valid == ["AAPL"]
        assert rejected == []

    def test_dotted_ticker(self):
        valid, rejected = _normalize_tickers(["GGAL.BA"])
        assert valid == ["GGAL.BA"]
        assert rejected == []

    def test_caret_ticker(self):
        valid, rejected = _normalize_tickers(["^GSPC"])
        assert valid == ["^GSPC"]
        assert rejected == []

    def test_invalid_ticker_with_special_chars(self):
        valid, rejected = _normalize_tickers(["AAPL!", "MSFT"])
        assert valid == ["MSFT"]
        assert len(rejected) == 1

    def test_too_long_ticker(self):
        long_ticker = "A" * 21
        valid, rejected = _normalize_tickers([long_ticker])
        assert valid == []
        assert len(rejected) == 1

    def test_preserves_order(self):
        valid, _ = _normalize_tickers(["MSFT", "AAPL", "GOOG"])
        assert valid == ["MSFT", "AAPL", "GOOG"]

    def test_empty_input(self):
        valid, rejected = _normalize_tickers([])
        assert valid == []
        assert rejected == []

    def test_non_string_item(self):
        valid, rejected = _normalize_tickers([123, "AAPL"])  # type: ignore[list-item]
        assert valid == ["AAPL"]
        assert len(rejected) == 1

    def test_mixed_valid_and_invalid(self):
        valid, rejected = _normalize_tickers(["AAPL", "bad ticker!", "GD30"])
        assert valid == ["AAPL", "GD30"]
        assert len(rejected) == 1

    def test_hyphenated_ticker(self):
        valid, rejected = _normalize_tickers(["BRK-B"])
        assert valid == ["BRK-B"]
        assert rejected == []


# ---------------------------------------------------------------------------
# data_fetcher_node — unit tests
# ---------------------------------------------------------------------------


class TestDataFetcherNode:
    @pytest.mark.asyncio
    async def test_empty_tickers_returns_empty_result(self):
        svc = _make_service({})
        portfolio_service = MagicMock()
        node = make_data_fetcher_node(svc, portfolio_service)
        result = await node(_make_state(active_tickers=[]))
        assert result["market_data_result"] == {}
        assert result["errors"] == []
        svc.fetch_and_persist.assert_not_called()

    @pytest.mark.asyncio
    async def test_none_tickers_returns_empty_result(self):
        svc = _make_service({})
        portfolio_service = MagicMock()
        node = make_data_fetcher_node(svc, portfolio_service)
        result = await node(_make_state(active_tickers=None))
        assert result["market_data_result"] == {}
        assert result["errors"] == []
        svc.fetch_and_persist.assert_not_called()

    @pytest.mark.asyncio
    async def test_all_invalid_tickers_returns_error(self):
        svc = _make_service({})
        portfolio_service = MagicMock()
        node = make_data_fetcher_node(svc, portfolio_service)
        result = await node(_make_state(active_tickers=["bad!", "also bad!"]))
        assert result["market_data_result"] == {}
        assert result["errors"]
        svc.fetch_and_persist.assert_not_called()

    @pytest.mark.asyncio
    async def test_successful_fetch_returns_ok_entries(self):
        records = [
            _make_ohlcv("AAPL", 150.0, date(2023, 1, 2)),
            _make_ohlcv("AAPL", 175.0, date(2024, 1, 2)),
        ]
        svc = _make_service({"AAPL": records})
        portfolio_service = MagicMock()
        node = make_data_fetcher_node(svc, portfolio_service)
        result = await node(_make_state(active_tickers=["AAPL"]))

        md = result["market_data_result"]
        assert md["AAPL"]["ok"] is True
        assert md["AAPL"]["records_count"] == 2
        assert md["AAPL"]["latest_close"] == pytest.approx(175.0)
        assert md["AAPL"]["first_close"] == pytest.approx(150.0)
        assert md["AAPL"]["latest_date"] == "2024-01-02"
        assert md["AAPL"]["first_date"] == "2023-01-02"
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_ticker_with_no_data_marked_as_failed(self):
        svc = _make_service({"GD30": []})
        portfolio_service = MagicMock()
        node = make_data_fetcher_node(svc, portfolio_service)
        result = await node(_make_state(active_tickers=["GD30"]))

        md = result["market_data_result"]
        assert md["GD30"]["ok"] is False
        assert md["GD30"]["latest_close"] is None
        assert result["errors"]

    @pytest.mark.asyncio
    async def test_partial_failure_sets_error_with_both_lists(self):
        records = [_make_ohlcv("AAPL", 175.0)]
        svc = _make_service({"AAPL": records, "INVALID": []})
        portfolio_service = MagicMock()
        node = make_data_fetcher_node(svc, portfolio_service)
        result = await node(_make_state(active_tickers=["AAPL", "INVALID"]))

        md = result["market_data_result"]
        assert md["AAPL"]["ok"] is True
        assert md["INVALID"]["ok"] is False
        assert result["errors"]
        assert any("INVALID" in e for e in result["errors"])
        assert any("AAPL" in e for e in result["errors"])

    @pytest.mark.asyncio
    async def test_service_exception_returns_error(self):
        svc = MagicMock()
        svc.fetch_and_persist = AsyncMock(side_effect=RuntimeError("DB connection lost"))
        portfolio_service = MagicMock()
        node = make_data_fetcher_node(svc, portfolio_service)
        result = await node(_make_state(active_tickers=["AAPL"]))

        assert result["market_data_result"] == {}
        assert any("DB connection lost" in e for e in result["errors"])

    @pytest.mark.asyncio
    async def test_deduplication_before_service_call(self):
        records = [_make_ohlcv("AAPL", 175.0)]
        svc = _make_service({"AAPL": records})
        portfolio_service = MagicMock()
        node = make_data_fetcher_node(svc, portfolio_service)
        await node(_make_state(active_tickers=["AAPL", "aapl", "AAPL"]))

        called_cmd = svc.fetch_and_persist.call_args[0][0]
        assert called_cmd.tickers == ["AAPL"]  # solo uno

    @pytest.mark.asyncio
    async def test_lowercase_normalized_before_service(self):
        records = [_make_ohlcv("MSFT", 300.0)]
        svc = _make_service({"MSFT": records})
        portfolio_service = MagicMock()
        node = make_data_fetcher_node(svc, portfolio_service)
        await node(_make_state(active_tickers=["msft"]))

        called_cmd = svc.fetch_and_persist.call_args[0][0]
        assert called_cmd.tickers == ["MSFT"]

    @pytest.mark.asyncio
    async def test_all_fail_error_message_mentions_tickers(self):
        svc = _make_service({"AAPL": [], "MSFT": []})
        portfolio_service = MagicMock()
        node = make_data_fetcher_node(svc, portfolio_service)
        result = await node(_make_state(active_tickers=["AAPL", "MSFT"]))

        assert result["errors"]
        assert any("AAPL" in e or "MSFT" in e for e in result["errors"])

    @pytest.mark.asyncio
    async def test_ba_ticker_failure_includes_hint(self):
        svc = _make_service({"GGAL.BA": []})
        portfolio_service = MagicMock()
        node = make_data_fetcher_node(svc, portfolio_service)
        result = await node(_make_state(active_tickers=["GGAL.BA"]))

        assert result["errors"]
        assert any(".BA" in e or "BYMA" in e for e in result["errors"])

    @pytest.mark.asyncio
    async def test_ba_ticker_success_no_hint(self):
        records = [_make_ohlcv("GGAL.BA", 1200.0)]
        svc = _make_service({"GGAL.BA": records})
        portfolio_service = MagicMock()
        node = make_data_fetcher_node(svc, portfolio_service)
        result = await node(_make_state(active_tickers=["GGAL.BA"]))

        assert result["errors"] == []
        assert result["market_data_result"]["GGAL.BA"]["ok"] is True

    @pytest.mark.asyncio
    async def test_rejected_tickers_reported_when_others_succeed(self):
        records = [_make_ohlcv("AAPL", 175.0)]
        svc = _make_service({"AAPL": records})
        portfolio_service = MagicMock()
        node = make_data_fetcher_node(svc, portfolio_service)
        result = await node(_make_state(active_tickers=["AAPL", "bad!"]))

        assert result["market_data_result"]["AAPL"]["ok"] is True
        assert result["errors"]
        assert any("bad!" in e for e in result["errors"])

    @pytest.mark.asyncio
    async def test_mixed_ba_and_us_failure_hint_specific(self):
        records = [_make_ohlcv("AAPL", 175.0)]
        svc = _make_service({"AAPL": records, "GD30.BA": []})
        portfolio_service = MagicMock()
        node = make_data_fetcher_node(svc, portfolio_service)
        result = await node(_make_state(active_tickers=["AAPL", "GD30.BA"]))

        assert result["errors"]
        assert any("GD30.BA" in e for e in result["errors"])
        assert any("AAPL" in e for e in result["errors"])


# ---------------------------------------------------------------------------
# YFinanceGateway — timeout and logging tests
# ---------------------------------------------------------------------------


class TestYFinanceGateway:
    @pytest.mark.asyncio
    async def test_timeout_returns_empty_list(self):
        import asyncio
        from unittest.mock import patch

        from financial_assistant.infrastructure.market.yfinance_gateway import YFinanceGateway

        gateway = YFinanceGateway(timeout=0.001)  # 1ms → always times out

        async def slow_executor(executor, fn):
            await asyncio.sleep(1)
            return []

        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(side_effect=asyncio.TimeoutError)
            # Simulate timeout via wait_for
            result = await gateway.fetch_ohlcv("AAPL", period="1y")

        assert result == []

    @pytest.mark.asyncio
    async def test_timeout_is_configurable(self):
        from financial_assistant.infrastructure.market.yfinance_gateway import (
            _DEFAULT_TIMEOUT_SECONDS,
            YFinanceGateway,
        )

        gw_default = YFinanceGateway()
        gw_custom = YFinanceGateway(timeout=10.0)

        assert gw_default._timeout == _DEFAULT_TIMEOUT_SECONDS
        assert gw_custom._timeout == 10.0
