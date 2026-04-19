import asyncio
from datetime import datetime
from decimal import Decimal
from functools import partial
from typing import Literal

import yfinance as yf

from financial_assistant.domain.models.market_data import OHLCV
from financial_assistant.domain.ports.market_gateway import IMarketDataGateway


class YFinanceGateway(IMarketDataGateway):  # type: ignore[misc]
    """Adapter that wraps yfinance (sync) and exposes async interface."""

    async def fetch_ohlcv(self, ticker: str, period: str = "1y") -> list[OHLCV]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(self._fetch_sync, ticker, period))

    async def fetch_benchmark(self, benchmark: Literal["SPY", "^GSPC", "GC=F"]) -> list[OHLCV]:
        return await self.fetch_ohlcv(benchmark, period="1y")

    def _fetch_sync(self, ticker: str, period: str) -> list[OHLCV]:
        try:
            data = yf.download(ticker, period=period, auto_adjust=True, progress=False)
            if data.empty:
                return []
            records: list[OHLCV] = []
            for idx, row in data.iterrows():
                records.append(
                    OHLCV(
                        ticker=ticker,
                        date=idx.date() if hasattr(idx, "date") else datetime.fromisoformat(str(idx)).date(),
                        open=Decimal(str(round(float(row["Open"]), 6))),
                        high=Decimal(str(round(float(row["High"]), 6))),
                        low=Decimal(str(round(float(row["Low"]), 6))),
                        close=Decimal(str(round(float(row["Close"]), 6))),
                        volume=int(row["Volume"]),
                    )
                )
            return records
        except Exception:  # pylint: disable=broad-exception-caught
            return []
