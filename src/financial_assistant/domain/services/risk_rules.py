import re

from financial_assistant.domain.models.profile import FinancialProfile
from financial_assistant.domain.models.risk import ExplanationCard, RiskWarning, WarningLevel

CONCENTRATION_CRITICAL_THRESHOLD = 0.50
CONCENTRATION_HIGH_THRESHOLD = 0.30
SHORT_HORIZON_MONTHS = 6

_DIRECT_ORDER_RE = re.compile(
    r"\b(?:comprá|compra|vendé|vende|invertí|invierte|"
    r"ejecutá|ejecuta|realizá|realiza|hacé\s+la\s+operaci[oó]n|"
    r"decime\s+(?:qu[eé]\s+)?(?:comprar?|vender?|invertir?))\b",
    re.IGNORECASE | re.UNICODE,
)


def check_concentration(current_weights: dict[str, float]) -> list[RiskWarning]:
    warnings: list[RiskWarning] = []
    for ticker, weight in current_weights.items():
        if weight >= CONCENTRATION_CRITICAL_THRESHOLD:
            warnings.append(RiskWarning(
                code="CONCENTRATION_CRITICAL",
                level=WarningLevel.CRITICAL,
                message=(
                    f"Tu cartera tiene {weight:.0%} concentrado en {ticker}. "
                    "Una concentración tan alta implica riesgo elevado ante movimientos adversos de ese activo."
                ),
                detail=f"weight={weight:.4f} ticker={ticker}",
            ))
        elif weight >= CONCENTRATION_HIGH_THRESHOLD:
            warnings.append(RiskWarning(
                code="CONCENTRATION_HIGH",
                level=WarningLevel.HIGH,
                message=(
                    f"{ticker} representa {weight:.0%} de tu cartera. "
                    "Considerá si esa concentración es compatible con tu tolerancia al riesgo."
                ),
                detail=f"weight={weight:.4f} ticker={ticker}",
            ))
    return warnings


def check_missing_profile(profile: FinancialProfile | None) -> list[RiskWarning]:
    if profile is None:
        return [RiskWarning(
            code="MISSING_PROFILE",
            level=WarningLevel.MEDIUM,
            message=(
                "No tengo información sobre tu perfil de riesgo ni horizonte de inversión. "
                "La optimización se realizó con parámetros estándar."
            ),
            detail="FinancialProfile not provided",
        )]
    warnings: list[RiskWarning] = []
    if profile.risk_tolerance is None:
        warnings.append(RiskWarning(
            code="MISSING_RISK_TOLERANCE",
            level=WarningLevel.MEDIUM,
            message="No indicaste tu tolerancia al riesgo (conservador / moderado / agresivo).",
            detail="risk_tolerance=None",
        ))
    if profile.investment_horizon_months is None:
        warnings.append(RiskWarning(
            code="MISSING_HORIZON",
            level=WarningLevel.HIGH,
            message=(
                "No indicaste tu horizonte temporal. "
                "La optimización de mínima varianza asume un horizonte largo (≥1 año). "
                "Si planeás usar el capital antes, los resultados pueden no ser adecuados."
            ),
            detail="investment_horizon_months=None",
        ))
    return warnings


def check_short_horizon(profile: FinancialProfile | None) -> list[RiskWarning]:
    if profile is None or profile.investment_horizon_months is None:
        return []
    if profile.investment_horizon_months <= SHORT_HORIZON_MONTHS:
        return [RiskWarning(
            code="SHORT_HORIZON_OPTIMIZATION",
            level=WarningLevel.HIGH,
            message=(
                f"Tu horizonte de {profile.investment_horizon_months} mes(es) es corto para optimización de cartera. "
                "Los modelos de optimización están diseñados para horizontes de 1 año o más. "
                "Para horizontes cortos, la liquidez y la preservación del capital suelen ser más relevantes."
            ),
            detail=f"horizon_months={profile.investment_horizon_months}",
        )]
    return []


def check_debt_before_investment(profile: FinancialProfile | None) -> list[RiskWarning]:
    if profile is not None and profile.has_debt:
        return [RiskWarning(
            code="DEBT_BEFORE_INVESTMENT",
            level=WarningLevel.HIGH,
            message=(
                "Mencionaste que tenés deudas. "
                "En muchos casos, cancelar deudas de alto interés antes de invertir "
                "tiene un retorno garantizado equivalente a la tasa de la deuda. "
                "Considerá consultar este punto con un asesor financiero."
            ),
            detail="has_debt=True",
        )]
    return []


def check_direct_order(user_message: str) -> list[RiskWarning]:
    if _DIRECT_ORDER_RE.search(user_message):
        return [RiskWarning(
            code="DIRECT_ORDER_REQUEST",
            level=WarningLevel.CRITICAL,
            message=(
                "Este asistente no ejecuta órdenes de compra ni venta. "
                "Solo registra movimientos que vos informás y analiza tu cartera. "
                "Para operar, usá tu broker o asesor financiero habilitado."
            ),
            detail="user_message contains direct order verb",
        )]
    return []


def build_quant_explanation(
    data_period: str = "1 año",
    risk_free_rate: float = 0.05,
    sentiment_lambda: float | None = None,
    benchmarks_used: list[str] | None = None,
    warnings: list[RiskWarning] | None = None,
) -> ExplanationCard:
    return ExplanationCard(
        method="Mínima varianza con regularización L2 (PyPortfolioOpt)",
        data_period=f"{data_period} de datos históricos de precios de cierre (yfinance)",
        risk_free_rate=risk_free_rate,
        sentiment_lambda=sentiment_lambda,
        benchmarks_used=benchmarks_used or ["S&P 500 (^GSPC)", "Merval (^MERV)"],
        assumptions=[
            f"Tasa libre de riesgo: {risk_free_rate:.0%} anual",
            "Los retornos históricos estiman el comportamiento futuro (no garantía)",
            "La correlación entre activos se mantiene estable (covarianza constante)",
            "Sin costos de transacción ni impuestos en la simulación",
            "Pesos entre 0% y 100% (sin venta en corto ni apalancamiento)",
        ],
        limitations=[
            "No considera perfil de riesgo personalizado si no fue indicado",
            "No considera liquidez individual de cada activo",
            "No ajusta por inflación argentina",
            "La simulación Monte Carlo usa GBM (log-normal); los mercados reales tienen colas pesadas",
        ],
        uncertainty_note=(
            "La proyección muestra tres escenarios (pesimista P5, mediano P50, optimista P95) "
            "basados en 5.000 simulaciones. Los resultados reales pueden diferir significativamente."
        ),
        sources=["yfinance (precios de mercado)", "dolarapi.com (tipos de cambio)"],
        warnings=warnings or [],
    )
