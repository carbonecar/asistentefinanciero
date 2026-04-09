import pandas as pd

from financial_assistant.domain.models.analysis import OptimizedWeights
from financial_assistant.domain.models.market_data import OHLCV


class PortfolioOptimizer:
    def __init__(self, risk_free_rate: float = 0.05, sentiment_lambda: float = 0.15) -> None:
        self._risk_free_rate = risk_free_rate
        self._lambda = sentiment_lambda

    def minimum_variance(
        self,
        ohlcv_by_ticker: dict[str, list[OHLCV]],
        sentiment_map: dict[str, float] | None = None,
    ) -> OptimizedWeights | None:
        from pypfopt import EfficientFrontier, expected_returns, risk_models  # type: ignore[import-untyped]  # pylint: disable=import-outside-toplevel

        prices_df = self._build_prices_df(ohlcv_by_ticker)
        if prices_df.empty or len(prices_df.columns) < 2:
            return None

        mu = expected_returns.mean_historical_return(prices_df)
        if sentiment_map:
            mu = self._apply_sentiment(mu, sentiment_map)

        S = risk_models.sample_cov(prices_df)  # pylint: disable=invalid-name
        ef = EfficientFrontier(mu, S, weight_bounds=(0, 1))
        ef.add_objective(lambda w: 1e-3 * (w**2).sum())  # L2 regularization

        try:
            ef.min_volatility()
            weights = ef.clean_weights()
            perf = ef.portfolio_performance(verbose=False, risk_free_rate=self._risk_free_rate)
            return OptimizedWeights(
                weights=dict(weights),
                expected_annual_return=round(float(perf[0]), 4),
                annual_volatility=round(float(perf[1]), 4),
                sharpe_ratio=round(float(perf[2]), 4),
            )
        except Exception:  # pylint: disable=broad-exception-caught
            return None

    def _apply_sentiment(self, mu: "pd.Series", sentiment_map: dict[str, float]) -> "pd.Series":  # type: ignore[name-defined]
        adjusted = mu.copy()
        for ticker, score in sentiment_map.items():
            if ticker in adjusted.index:
                adjusted[ticker] = adjusted[ticker] * (1 + self._lambda * score)
        return adjusted

    def _build_prices_df(self, ohlcv_by_ticker: dict[str, list[OHLCV]]) -> "pd.DataFrame":  # type: ignore[name-defined]
        series: dict[str, "pd.Series"] = {}  # type: ignore[name-defined]
        for ticker, records in ohlcv_by_ticker.items():
            if records:
                series[ticker] = pd.Series(
                    {r.date: float(r.close) for r in records}, name=ticker
                )
        if not series:
            return pd.DataFrame()
        df = pd.DataFrame(series).sort_index()
        return df.dropna(how="all")
