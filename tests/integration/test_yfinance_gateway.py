"""
Integration tests — require network access.
Run with: pytest tests/integration/ -v -m integration
"""

import pytest

from financial_assistant.infrastructure.market.yfinance_gateway import YFinanceGateway

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_fetch_aapl_ohlcv():
    gateway = YFinanceGateway()
    records = await gateway.fetch_ohlcv("AAPL", period="1mo")
    assert len(records) > 10
    assert all(r.ticker == "AAPL" for r in records)
    assert all(r.close > 0 for r in records)


@pytest.mark.asyncio
async def test_fetch_spy_benchmark():
    gateway = YFinanceGateway()
    records = await gateway.fetch_benchmark("SPY")
    assert len(records) > 100


@pytest.mark.asyncio
async def test_fetch_unknown_ticker_returns_empty():
    gateway = YFinanceGateway()
    records = await gateway.fetch_ohlcv("ZZZZZZZ_DOES_NOT_EXIST")
    assert records == []
