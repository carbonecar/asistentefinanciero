import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from functools import partial
from typing import Literal

import pandas as pd
import yfinance as yf

from financial_assistant.domain.models.market_data import OHLCV
from financial_assistant.domain.ports.market_gateway import IMarketDataGateway

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 30.0


class YFinanceGateway(IMarketDataGateway):  # type: ignore[misc]
    """Adapter that wraps yfinance (sync) and exposes async interface.

    fetch_ohlcv enforces a per-ticker timeout so a hanging yfinance call
    never blocks the event loop indefinitely.
    """

    def __init__(self, timeout: float = _DEFAULT_TIMEOUT_SECONDS) -> None:
        self._timeout = timeout

    async def fetch_ohlcv(self, ticker: str, period: str = "1y") -> list[OHLCV]:
        loop = asyncio.get_running_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, partial(self._fetch_sync, ticker, period)),
                timeout=self._timeout,
            )
        except TimeoutError:
            logger.error(
                "[YFinance] Timeout (%.0fs) fetching %s (period=%s) — source unresponsive",
                self._timeout, ticker, period,
            )
            return []

    async def fetch_benchmark(self, benchmark: Literal["SPY", "^GSPC", "GC=F"]) -> list[OHLCV]:
        return await self.fetch_ohlcv(benchmark, period="1y")

    def _fetch_sync(self, ticker: str, period: str) -> list[OHLCV]:
        try:
            data = yf.download(ticker, period=period, auto_adjust=True, progress=False)
            if data.empty:
                logger.warning(
                    "[YFinance] No data returned for %s (period=%s) — "
                    "ticker may not exist or have no history for this period",
                    ticker, period,
                )
                return []
            # yfinance >= 0.2 returns MultiIndex columns when downloading a single ticker
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
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
            logger.debug("[YFinance] %s — fetched %d records", ticker, len(records))
            return records
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.error(
                "[YFinance] Exception fetching %s (period=%s): %s",
                ticker, period, exc, exc_info=True,
            )
            return []
