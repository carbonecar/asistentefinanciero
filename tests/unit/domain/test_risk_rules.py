import pytest

from financial_assistant.domain.models.profile import FinancialGoal, FinancialProfile, RiskTolerance
from financial_assistant.domain.models.risk import WarningLevel
from financial_assistant.domain.services.risk_rules import (
    CONCENTRATION_CRITICAL_THRESHOLD,
    CONCENTRATION_HIGH_THRESHOLD,
    SHORT_HORIZON_MONTHS,
    build_quant_explanation,
    check_concentration,
    check_debt_before_investment,
    check_direct_order,
    check_missing_profile,
    check_short_horizon,
)


# ---------------------------------------------------------------------------
# check_concentration
# ---------------------------------------------------------------------------


def test_concentration_critical_at_50_percent():
    weights = {"AAPL": 0.50, "GOOG": 0.50}
    warnings = check_concentration(weights)
    codes = [w.code for w in warnings]
    assert "CONCENTRATION_CRITICAL" in codes


def test_concentration_critical_above_50_percent():
    weights = {"TSLA": 0.80, "MSFT": 0.20}
    warnings = check_concentration(weights)
    assert any(w.code == "CONCENTRATION_CRITICAL" and "TSLA" in w.message for w in warnings)


def test_concentration_high_at_30_percent():
    weights = {"AAPL": 0.30, "GOOG": 0.40, "MSFT": 0.30}
    warnings = check_concentration(weights)
    codes = [w.code for w in warnings]
    assert "CONCENTRATION_HIGH" in codes


def test_concentration_high_level_is_high():
    weights = {"AAPL": 0.35}
    warnings = check_concentration(weights)
    assert all(w.level == WarningLevel.HIGH for w in warnings if w.code == "CONCENTRATION_HIGH")


def test_concentration_critical_level_is_critical():
    weights = {"AAPL": 0.60}
    warnings = check_concentration(weights)
    assert all(w.level == WarningLevel.CRITICAL for w in warnings if w.code == "CONCENTRATION_CRITICAL")


def test_concentration_no_warning_below_threshold():
    weights = {"AAPL": 0.25, "GOOG": 0.25, "MSFT": 0.25, "AMZN": 0.25}
    warnings = check_concentration(weights)
    assert warnings == []


def test_concentration_multiple_tickers_one_flagged():
    weights = {"AAPL": 0.60, "GOOG": 0.20, "MSFT": 0.20}
    warnings = check_concentration(weights)
    assert len(warnings) == 1
    assert "AAPL" in warnings[0].message


def test_concentration_empty_portfolio_no_warning():
    assert check_concentration({}) == []


def test_concentration_boundary_just_below_high():
    weights = {"AAPL": CONCENTRATION_HIGH_THRESHOLD - 0.01}
    assert check_concentration(weights) == []


def test_concentration_boundary_exactly_critical():
    weights = {"AAPL": CONCENTRATION_CRITICAL_THRESHOLD}
    warnings = check_concentration(weights)
    assert any(w.code == "CONCENTRATION_CRITICAL" for w in warnings)


# ---------------------------------------------------------------------------
# check_missing_profile
# ---------------------------------------------------------------------------


def test_missing_profile_none_returns_single_medium_warning():
    warnings = check_missing_profile(None)
    assert len(warnings) == 1
    assert warnings[0].code == "MISSING_PROFILE"
    assert warnings[0].level == WarningLevel.MEDIUM


def test_missing_risk_tolerance_returns_warning():
    profile = FinancialProfile(risk_tolerance=None, investment_horizon_months=12)
    warnings = check_missing_profile(profile)
    codes = [w.code for w in warnings]
    assert "MISSING_RISK_TOLERANCE" in codes


def test_missing_horizon_returns_high_warning():
    profile = FinancialProfile(risk_tolerance=RiskTolerance.MODERATE, investment_horizon_months=None)
    warnings = check_missing_profile(profile)
    assert any(w.code == "MISSING_HORIZON" and w.level == WarningLevel.HIGH for w in warnings)


def test_both_fields_missing_returns_two_warnings():
    profile = FinancialProfile(risk_tolerance=None, investment_horizon_months=None)
    warnings = check_missing_profile(profile)
    codes = [w.code for w in warnings]
    assert "MISSING_RISK_TOLERANCE" in codes
    assert "MISSING_HORIZON" in codes


def test_complete_profile_no_warnings():
    profile = FinancialProfile(
        risk_tolerance=RiskTolerance.MODERATE,
        investment_horizon_months=24,
    )
    assert check_missing_profile(profile) == []


# ---------------------------------------------------------------------------
# check_short_horizon
# ---------------------------------------------------------------------------


def test_short_horizon_3_months_warning():
    profile = FinancialProfile(investment_horizon_months=3)
    warnings = check_short_horizon(profile)
    assert len(warnings) == 1
    assert warnings[0].code == "SHORT_HORIZON_OPTIMIZATION"
    assert warnings[0].level == WarningLevel.HIGH


def test_short_horizon_boundary_exactly_limit():
    profile = FinancialProfile(investment_horizon_months=SHORT_HORIZON_MONTHS)
    warnings = check_short_horizon(profile)
    assert any(w.code == "SHORT_HORIZON_OPTIMIZATION" for w in warnings)


def test_horizon_above_limit_no_warning():
    profile = FinancialProfile(investment_horizon_months=SHORT_HORIZON_MONTHS + 1)
    assert check_short_horizon(profile) == []


def test_horizon_12_months_no_warning():
    profile = FinancialProfile(investment_horizon_months=12)
    assert check_short_horizon(profile) == []


def test_missing_horizon_in_profile_no_short_horizon_warning():
    profile = FinancialProfile(investment_horizon_months=None)
    assert check_short_horizon(profile) == []


def test_none_profile_no_short_horizon_warning():
    assert check_short_horizon(None) == []


# ---------------------------------------------------------------------------
# check_debt_before_investment
# ---------------------------------------------------------------------------


def test_debt_flag_true_returns_high_warning():
    profile = FinancialProfile(has_debt=True)
    warnings = check_debt_before_investment(profile)
    assert len(warnings) == 1
    assert warnings[0].code == "DEBT_BEFORE_INVESTMENT"
    assert warnings[0].level == WarningLevel.HIGH


def test_debt_flag_false_no_warning():
    profile = FinancialProfile(has_debt=False)
    assert check_debt_before_investment(profile) == []


def test_debt_flag_none_no_warning():
    profile = FinancialProfile(has_debt=None)
    assert check_debt_before_investment(profile) == []


def test_none_profile_no_debt_warning():
    assert check_debt_before_investment(None) == []


# ---------------------------------------------------------------------------
# check_direct_order
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("msg", [
    "comprá AAPL",
    "vendé todo",
    "invertí en Tesla",
    "ejecutá la orden",
    "Compra acciones de MELI",
    "Vende mis ETFs",
    "decime qué comprar",
    "decime qué vender",
    "decime qué invertir",
    "decime comprar AAPL",
    "vendé todo y comprá Nvidia",
])
def test_direct_order_detected(msg):
    warnings = check_direct_order(msg)
    assert len(warnings) == 1
    assert warnings[0].code == "DIRECT_ORDER_REQUEST"
    assert warnings[0].level == WarningLevel.CRITICAL


@pytest.mark.parametrize("msg", [
    "quiero que registres 10 acciones de AAPL",
    "registrá una posición de GOOG",
    "auditar mi cartera",
    "optimizá mi portfolio",
    "qué noticias hay de TSLA",
    "dame el dólar MEP",
    "¿vale la pena esperar para comprar?",
    "antes de comprar quiero analizar el riesgo",
])
def test_no_direct_order_not_flagged(msg):
    assert check_direct_order(msg) == []


# ---------------------------------------------------------------------------
# build_quant_explanation
# ---------------------------------------------------------------------------


def test_explanation_card_contains_assumptions():
    card = build_quant_explanation()
    assert len(card.assumptions) > 0


def test_explanation_card_contains_risk_free_rate():
    card = build_quant_explanation(risk_free_rate=0.05)
    assert card.risk_free_rate == 0.05
    assert any("5%" in a for a in card.assumptions)


def test_explanation_card_contains_limitations():
    card = build_quant_explanation()
    assert len(card.limitations) > 0


def test_explanation_card_sources_include_yfinance():
    card = build_quant_explanation()
    assert any("yfinance" in s for s in card.sources)


def test_explanation_card_with_sentiment_lambda():
    card = build_quant_explanation(sentiment_lambda=0.15)
    assert card.sentiment_lambda == 0.15


def test_explanation_card_without_sentiment_no_lambda():
    card = build_quant_explanation(sentiment_lambda=None)
    assert card.sentiment_lambda is None


def test_explanation_card_includes_warnings():
    from financial_assistant.domain.models.risk import RiskWarning, WarningLevel
    w = RiskWarning(code="TEST", level=WarningLevel.HIGH, message="test")
    card = build_quant_explanation(warnings=[w])
    assert len(card.warnings) == 1
    assert card.warnings[0].code == "TEST"


def test_explanation_card_empty_warnings_by_default():
    card = build_quant_explanation()
    assert card.warnings == []


def test_explanation_card_method_mentions_pypfopt():
    card = build_quant_explanation()
    assert "PyPortfolioOpt" in card.method


def test_explanation_card_uncertainty_note_mentions_percentiles():
    card = build_quant_explanation()
    assert "P5" in card.uncertainty_note and "P95" in card.uncertainty_note


def test_explanation_card_custom_benchmarks():
    card = build_quant_explanation(benchmarks_used=["S&P 500", "Nasdaq"])
    assert "Nasdaq" in card.benchmarks_used
