from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class BenchmarkComparison:
    benchmark_name: str
    benchmark_return: Decimal
    portfolio_return: Decimal

    @property
    def opportunity_cost(self) -> Decimal:
        """Positive means portfolio outperformed the benchmark."""
        return self.portfolio_return - self.benchmark_return


@dataclass
class AuditReport:
    user_id: int
    period_label: str  # e.g. "last 12 months"
    portfolio_return: Decimal
    comparisons: list[BenchmarkComparison] = field(default_factory=list)
    top_performer: str = ""
    worst_performer: str = ""
    positions: list[dict[str, object]] = field(default_factory=list)


@dataclass(frozen=True)
class OptimizedWeights:
    weights: dict[str, float]  # ticker -> weight [0,1]
    expected_annual_return: float
    annual_volatility: float
    sharpe_ratio: float


@dataclass
class SimulationResult:
    horizon_days: int
    percentile_5: list[float]
    percentile_50: list[float]
    percentile_95: list[float]
    initial_value: float


@dataclass
class QuantResult:
    user_id: int
    optimized_weights: OptimizedWeights | None = None
    simulation: SimulationResult | None = None
    sentiment_adjusted: bool = False
