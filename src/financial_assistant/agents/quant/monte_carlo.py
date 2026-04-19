import numpy as np

from financial_assistant.domain.models.analysis import OptimizedWeights, SimulationResult
from financial_assistant.domain.models.market_data import OHLCV


class MonteCarloSimulator:
    def __init__(self, n_simulations: int = 5000, horizon_days: int = 252) -> None:
        self._n = n_simulations
        self._horizon = horizon_days

    def simulate(
        self,
        weights: OptimizedWeights,
        ohlcv_by_ticker: dict[str, list[OHLCV]],
        initial_value: float,
    ) -> SimulationResult:
        params = self._build_returns_matrix(weights, ohlcv_by_ticker)
        if params is None:
            return self._empty_result()

        mu, sigma = params

        # Geometric Brownian Motion: S(t) = S(0) * exp((mu - 0.5*sigma^2)*dt + sigma*sqrt(dt)*Z)
        dt = 1.0
        paths = np.zeros((self._n, self._horizon))
        paths[:, 0] = initial_value

        for t in range(1, self._horizon):
            z = np.random.standard_normal(self._n)
            paths[:, t] = paths[:, t - 1] * np.exp((mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * z)

        return SimulationResult(
            horizon_days=self._horizon,
            percentile_5=np.percentile(paths, 5, axis=0).tolist(),
            percentile_50=np.percentile(paths, 50, axis=0).tolist(),
            percentile_95=np.percentile(paths, 95, axis=0).tolist(),
            initial_value=initial_value,
        )

    def _build_returns_matrix(
        self,
        weights: OptimizedWeights,
        ohlcv_by_ticker: dict[str, list[OHLCV]],
    ) -> tuple[float, float] | None:
        """Compute weighted portfolio mu and sigma for GBM simulation."""
        weighted_mu = 0.0
        weighted_var = 0.0
        for ticker, weight in weights.weights.items():
            records = ohlcv_by_ticker.get(ticker)
            if not records or len(records) < 2:
                continue
            closes = np.array([float(r.close) for r in records])
            daily_returns = np.diff(closes) / closes[:-1]
            weighted_mu += weight * daily_returns.mean()
            weighted_var += (weight**2) * daily_returns.var()
        if weighted_var == 0:
            return None
        return float(weighted_mu), float(np.sqrt(weighted_var))

    def _empty_result(self) -> SimulationResult:
        return SimulationResult(
            horizon_days=self._horizon,
            percentile_5=[],
            percentile_50=[],
            percentile_95=[],
            initial_value=0.0,
        )
