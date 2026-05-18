from dataclasses import dataclass, field
from enum import StrEnum


class WarningLevel(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class RiskWarning:
    code: str
    level: WarningLevel
    message: str
    detail: str = ""


@dataclass
class ExplanationCard:
    method: str
    data_period: str
    risk_free_rate: float
    benchmarks_used: list[str]
    assumptions: list[str]
    limitations: list[str]
    uncertainty_note: str
    sources: list[str]
    sentiment_lambda: float | None = None
    warnings: list[RiskWarning] = field(default_factory=list)
