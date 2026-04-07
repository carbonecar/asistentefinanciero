from dataclasses import dataclass
from decimal import Decimal

from financial_assistant.domain.models.portfolio import AssetType


@dataclass(frozen=True)
class AddPositionCommand:
    user_id: int
    ticker: str
    asset_type: AssetType
    quantity: Decimal
    avg_cost_usd: Decimal
    currency: str = "USD"


@dataclass(frozen=True)
class FetchMarketDataCommand:
    tickers: list[str]
    period: str = "1y"


@dataclass(frozen=True)
class AuditPortfolioQuery:
    user_id: int
    period: str = "1y"


@dataclass(frozen=True)
class OptimizePortfolioQuery:
    user_id: int
    use_sentiment: bool = False


@dataclass(frozen=True)
class NewsQuery:
    tickers: list[str]
    max_articles_per_ticker: int = 10
