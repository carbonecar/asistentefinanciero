from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class OHLCV:
    ticker: str
    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

    @property
    def daily_return(self) -> Decimal:
        if self.open == 0:
            return Decimal("0")
        return (self.close - self.open) / self.open


@dataclass(frozen=True)
class Quote:
    ticker: str
    price: Decimal
    currency: str = "USD"


@dataclass(frozen=True)
class BenchmarkData:
    name: str  # "SP500", "MEP", etc.
    records: tuple[OHLCV, ...]

    def total_return(self) -> Decimal:
        if len(self.records) < 2:
            return Decimal("0")
        first = self.records[0].close
        last = self.records[-1].close
        if first == 0:
            return Decimal("0")
        return (last - first) / first
