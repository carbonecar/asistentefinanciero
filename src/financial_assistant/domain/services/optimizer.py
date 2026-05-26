import logging
from abc import ABC, abstractmethod

import numpy as np
import pandas as pd
from pypfopt import EfficientFrontier, expected_returns, risk_models

from financial_assistant.domain.models.analysis import OptimizedWeights
from financial_assistant.domain.models.market_data import OHLCV

logger = logging.getLogger(__name__)


class OptimizationStrategy(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def apply(self, ef: EfficientFrontier, risk_free_rate: float) -> None: ...

    def preprocess(
        self,
        mu: "pd.Series",
        S: "pd.DataFrame",
        _sentiment_map: dict[str, float],
        _lambda_: float,
    ) -> tuple["pd.Series", "pd.DataFrame"]:
        """Hook called before building EfficientFrontier. Default: no-op."""
        return mu, S


class MaxSharpeStrategy(OptimizationStrategy):
    @property
    def name(self) -> str:
        return "max_sharpe"

    def apply(self, ef: EfficientFrontier, risk_free_rate: float) -> None:
        ef.max_sharpe(risk_free_rate=risk_free_rate)

    def preprocess(
        self,
        mu: "pd.Series",
        S: "pd.DataFrame",
        sentiment_map: dict[str, float],
        lambda_: float,
    ) -> tuple["pd.Series", "pd.DataFrame"]:
        """Adjusts expected returns: μ_adj[i] = μ[i] * (1 + λ * s[i])."""
        adjusted = mu.copy()
        for ticker, score in sentiment_map.items():
            if ticker in adjusted.index:
                adjusted[ticker] = adjusted[ticker] * (1 + lambda_ * score)
        return adjusted, S


class MinVolatilityStrategy(OptimizationStrategy):
    @property
    def name(self) -> str:
        return "min_volatility"

    def apply(self, ef: EfficientFrontier, _risk_free_rate: float) -> None:
        ef.min_volatility()


class MinVolatilitySentimentStrategy(OptimizationStrategy):
    """Min-volatility with sentiment-aware covariance scaling.

    Scales the diagonal of Σ by (1 - λ * s[i]): positive sentiment reduces
    perceived variance, negative sentiment inflates it, steering the optimizer
    away from assets with bad news without touching expected returns.

    Formula: Σ̃[i,i] = Σ[i,i] * (1 - λ * s[i]),  off-diagonal unchanged.
    """

    @property
    def name(self) -> str:
        return "min_vol_sentiment"

    def apply(self, ef: EfficientFrontier, _risk_free_rate: float) -> None:
        ef.min_volatility()

    def preprocess(
        self,
        mu: "pd.Series",
        S: "pd.DataFrame",
        sentiment_map: dict[str, float],
        lambda_: float,
    ) -> tuple["pd.Series", "pd.DataFrame"]:
        """Scales Σ diagonal: Σ̃[i,i] = Σ[i,i] * (1 - λ * s[i])."""
        tickers = list(S.columns)
        scale = np.ones(len(tickers))
        for i, ticker in enumerate(tickers):
            if ticker in sentiment_map:
                scale[i] = max(1e-6, 1.0 - lambda_ * sentiment_map[ticker])
        arr = S.to_numpy(copy=True, dtype=float)
        np.fill_diagonal(arr, np.diag(arr) * scale)
        return mu, pd.DataFrame(arr, index=S.index, columns=S.columns)


class PortfolioOptimizer:
    def __init__(self, risk_free_rate: float = 0.05, sentiment_lambda: float = 0.15) -> None:
        self._risk_free_rate = risk_free_rate
        self._lambda = sentiment_lambda

    def optimize(
        self,
        ohlcv_by_ticker: dict[str, list[OHLCV]],
        sentiment_map: dict[str, float] | None = None,
        strategy: OptimizationStrategy = MaxSharpeStrategy(),
    ) -> OptimizedWeights | None:
        """Optimiza los pesos del portafolio según la estrategia indicada.

        Construye μ y Σ históricos, delega el preprocesamiento de sentimiento a
        `strategy.preprocess()` (cada estrategia decide si ajusta μ, Σ, o ambos),
        y luego aplica la optimización vía `strategy.apply()`.

        Args:
            ohlcv_by_ticker: Precios de cierre históricos por ticker.
                Se requieren al menos 2 tickers con datos para poder optimizar.
            sentiment_map: Score de sentimiento por ticker en [-1, 1].
                Cómo se usa depende de la estrategia (ver `preprocess()`).
            strategy: Estrategia de optimización a aplicar.
                - `MaxSharpeStrategy`: maximiza Sharpe; ajusta μ con sentimiento.
                - `MinVolatilityStrategy`: minimiza volatilidad; ignora sentimiento.
                - `MinVolatilitySentimentStrategy`: minimiza volatilidad escalando Σ.

        Returns:
            `OptimizedWeights` con pesos, métricas de performance y nombre de
            la estrategia usada. `None` si hay menos de 2 tickers con datos o
            si PyPortfolioOpt no converge.
        """
        prices_df = self._build_prices_df(ohlcv_by_ticker)
        if prices_df.empty or len(prices_df.columns) < 2:
            return None

        mu = expected_returns.mean_historical_return(prices_df)
        S = risk_models.sample_cov(prices_df)  # pylint: disable=invalid-name

        mu, S = strategy.preprocess(mu, S, sentiment_map or {}, self._lambda)

        ef = EfficientFrontier(mu, S, weight_bounds=(0, 1))

        try:
            strategy.apply(ef, self._risk_free_rate)
            weights = ef.clean_weights()
            perf = ef.portfolio_performance(verbose=False, risk_free_rate=self._risk_free_rate)
            return OptimizedWeights(
                weights=dict(weights),
                expected_annual_return=round(float(perf[0]), 4),
                annual_volatility=round(float(perf[1]), 4),
                sharpe_ratio=round(float(perf[2]), 4),
                expected_returns_per_ticker={t: round(float(mu[t]), 4) for t in mu.index},
                optimization_strategy=strategy.name,
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.error(
                "PortfolioOptimizer failed (strategy=%s sentiment=%s): %s",
                strategy.name,
                bool(sentiment_map),
                exc,
                exc_info=True,
            )
            return None

    def _build_prices_df(self, ohlcv_by_ticker: dict[str, list[OHLCV]]) -> "pd.DataFrame":
        series: dict[str, pd.Series] = {}
        for ticker, records in ohlcv_by_ticker.items():
            if records:
                series[ticker] = pd.Series({r.date: float(r.close) for r in records}, name=ticker)
        if not series:
            return pd.DataFrame()
        df = pd.DataFrame(series).sort_index()
        return df.dropna(how="all")
