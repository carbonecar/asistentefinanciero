from abc import ABC, abstractmethod
from datetime import date

from financial_assistant.domain.models.market_data import OHLCV, Quote
from financial_assistant.domain.models.portfolio import Portfolio, Position


class IPortfolioRepository(ABC):
    @abstractmethod
    async def get_by_user_id(self, user_id: int) -> Portfolio | None: ...

    @abstractmethod
    async def save(self, portfolio: Portfolio) -> None: ...

    @abstractmethod
    async def upsert_position(self, user_id: int, position: Position) -> None: ...

    @abstractmethod
    async def delete_position(self, user_id: int, ticker: str) -> None: ...


class IMarketDataRepository(ABC):
    @abstractmethod
    async def save_ohlcv(self, records: list[OHLCV]) -> None: ...

    @abstractmethod
    async def get_ohlcv(self, ticker: str, start: date, end: date) -> list[OHLCV]: ...

    @abstractmethod
    async def get_latest_quote(self, ticker: str) -> Quote | None: ...
