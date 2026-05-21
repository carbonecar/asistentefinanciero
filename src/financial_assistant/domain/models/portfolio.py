from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum


class AssetType(StrEnum):
    STOCK = "stock"
    BOND_ON = "bond_on"  # Obligación Negociable
    ETF = "etf"
    CRYPTO = "crypto"


@dataclass(frozen=True)
class Position:
    ticker: str
    asset_type: AssetType
    quantity: Decimal
    avg_cost_usd: Decimal
    currency: str = "USD"
    purchase_date: date | None = None

    @property
    def total_cost_usd(self) -> Decimal:
        return self.quantity * self.avg_cost_usd


@dataclass
class Portfolio:
    user_id: int
    positions: list[Position] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def tickers(self) -> list[str]:
        return [p.ticker for p in self.positions]

    def total_cost_usd(self) -> Decimal:
        return sum((p.total_cost_usd for p in self.positions), Decimal("0"))

    def get_position(self, ticker: str) -> Position | None:
        return next((p for p in self.positions if p.ticker == ticker), None)

    def is_empty(self) -> bool:
        return len(self.positions) == 0
