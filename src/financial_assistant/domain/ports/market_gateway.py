from abc import ABC, abstractmethod
from typing import Literal

from financial_assistant.domain.models.market_data import OHLCV


class IMarketDataGateway(ABC):
    @abstractmethod
    async def fetch_ohlcv(self, ticker: str, period: str = "1y") -> list[OHLCV]: ...

    @abstractmethod
    async def fetch_benchmark(
        self, benchmark: Literal["SPY", "^GSPC", "GC=F"]
    ) -> list[OHLCV]: ...
