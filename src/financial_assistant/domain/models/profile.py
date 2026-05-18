from dataclasses import dataclass
from enum import StrEnum


class RiskTolerance(StrEnum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class FinancialGoal(StrEnum):
    PRESERVE_CAPITAL = "preserve_capital"
    GROW_CAPITAL = "grow_capital"
    GENERATE_INCOME = "generate_income"
    SPECULATION = "speculation"


@dataclass
class FinancialProfile:
    risk_tolerance: RiskTolerance | None = None
    investment_horizon_months: int | None = None
    available_capital_usd: float | None = None
    financial_goal: FinancialGoal | None = None
    needs_liquidity: bool | None = None
    has_debt: bool | None = None
    experience_years: int | None = None
    currency_preference: str = "USD"
    country: str = "AR"
