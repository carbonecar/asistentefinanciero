"""
Tests de integración para la capa de advertencias de riesgo en el UX agent.

Cubre:
- check_direct_order se ejecuta en _build_data_summary para CUALQUIER intent,
  incluyendo "general" (no solo cuando quant/auditor corrieron).
- "vendé todo y comprá Nvidia" genera un RiskWarning CRITICAL visible en el resumen.
- risk_warnings del state (de quant/auditor) y de check_direct_order se combinan
  sin perderse unos a otros.
- Flujos normales (audit, optimize, news, data_fetch) sin lenguaje de orden directa
  no generan falsos positivos de DIRECT_ORDER_REQUEST.
- La acumulación con operator.add produce la unión de listas, no un reemplazo.

Sin LangGraph real, sin LLM, sin red.
"""

import operator

import pytest

from financial_assistant.agents.ux_agent.agent import _build_data_summary
from financial_assistant.domain.models.risk import RiskWarning, WarningLevel
from financial_assistant.domain.services.risk_rules import check_direct_order

# ---------------------------------------------------------------------------
# Estado mínimo válido para _build_data_summary
# ---------------------------------------------------------------------------

_BASE = {
    "user_id": 1,
    "user_message": "",
    "messages": [],
    "intents": ["general"],
    "active_tickers": [],
    "period": "1y",
    "use_sentiment": False,
    "positions": [],
    "market_data_result": None,
    "audit_report": None,
    "quant_result": None,
    "news_results": None,
    "exchange_rates": None,
    "financial_profile": None,
    "risk_warnings": [],
    "explanation_card": None,
    "final_response": None,
    "errors": [],
}


def _state(**overrides) -> dict:  # type: ignore[type-arg]
    return {**_BASE, **overrides}


def _warning(code: str, level: WarningLevel = WarningLevel.HIGH, msg: str = "test") -> RiskWarning:
    return RiskWarning(code=code, level=level, message=msg)


# ---------------------------------------------------------------------------
# check_direct_order corre para intent "general"
# ---------------------------------------------------------------------------


class TestDirectOrderForGeneralIntent:
    def test_vende_todo_compra_nvidia_is_critical_in_summary(self):
        state = _state(intents=["general"], user_message="vendé todo y comprá Nvidia")
        summary = _build_data_summary(state)
        assert "DIRECT_ORDER_REQUEST" in summary
        assert "ADVERTENCIAS DE RIESGO" in summary

    def test_level_critical_present_in_summary(self):
        state = _state(intents=["general"], user_message="vendé todo")
        summary = _build_data_summary(state)
        assert "CRITICAL" in summary.upper()

    def test_direct_order_runs_even_when_risk_warnings_empty(self):
        state = _state(intents=["general"], user_message="comprá AAPL", risk_warnings=[])
        summary = _build_data_summary(state)
        assert "DIRECT_ORDER_REQUEST" in summary

    def test_direct_order_runs_for_optimize_intent(self):
        state = _state(intents=["optimize"], user_message="comprá Tesla")
        summary = _build_data_summary(state)
        assert "DIRECT_ORDER_REQUEST" in summary

    def test_direct_order_runs_for_audit_intent(self):
        state = _state(intents=["audit"], user_message="vendé mis acciones")
        summary = _build_data_summary(state)
        assert "DIRECT_ORDER_REQUEST" in summary

    def test_decime_que_comprar_triggers_warning(self):
        state = _state(intents=["general"], user_message="decime qué comprar")
        summary = _build_data_summary(state)
        assert "DIRECT_ORDER_REQUEST" in summary

    def test_decime_vender_triggers_warning(self):
        state = _state(intents=["general"], user_message="decime qué vender")
        summary = _build_data_summary(state)
        assert "DIRECT_ORDER_REQUEST" in summary

    def test_invertí_todo_en_triggers_warning(self):
        state = _state(intents=["general"], user_message="invertí todo en MELI")
        summary = _build_data_summary(state)
        assert "DIRECT_ORDER_REQUEST" in summary


# ---------------------------------------------------------------------------
# Flujos normales no generan falsos positivos
# ---------------------------------------------------------------------------


class TestNoFalsePositives:
    @pytest.mark.parametrize("msg,intent", [
        ("auditá mi cartera", "audit"),
        ("optimizá mi portfolio", "optimize"),
        ("noticias de AAPL", "news"),
        ("registrá 10 acciones de TSLA a 180", "data_fetch"),
        ("quiero saber el dólar MEP", "general"),
        ("¿cómo está mi cartera?", "general"),
        ("cuánto rindió AAPL el último año", "general"),
        ("", "general"),
    ])
    def test_no_direct_order_warning(self, msg, intent):
        state = _state(intents=[intent], user_message=msg)
        summary = _build_data_summary(state)
        assert "DIRECT_ORDER_REQUEST" not in summary


# ---------------------------------------------------------------------------
# Combinación de state risk_warnings + check_direct_order
# ---------------------------------------------------------------------------


class TestWarningCombination:
    def test_state_warnings_and_direct_order_both_appear(self):
        existing = _warning("CONCENTRATION_CRITICAL", WarningLevel.CRITICAL, "concentración alta")
        state = _state(
            intents=["optimize"],
            user_message="comprá más AAPL",
            risk_warnings=[existing],
        )
        summary = _build_data_summary(state)
        assert "CONCENTRATION_CRITICAL" in summary
        assert "DIRECT_ORDER_REQUEST" in summary

    def test_multiple_state_warnings_all_appear(self):
        w1 = _warning("MISSING_PROFILE", WarningLevel.MEDIUM, "falta perfil")
        w2 = _warning("SHORT_HORIZON_OPTIMIZATION", WarningLevel.HIGH, "horizonte corto")
        state = _state(intents=["optimize"], user_message="quiero optimizar", risk_warnings=[w1, w2])
        summary = _build_data_summary(state)
        assert "MISSING_PROFILE" in summary
        assert "SHORT_HORIZON_OPTIMIZATION" in summary
        assert "DIRECT_ORDER_REQUEST" not in summary  # mensaje neutro

    def test_state_warnings_not_lost_when_direct_order_also_fires(self):
        w1 = _warning("CONCENTRATION_HIGH", WarningLevel.HIGH, "concentración alta en TSLA")
        state = _state(
            intents=["audit", "optimize"],
            user_message="vendé TSLA",
            risk_warnings=[w1],
        )
        summary = _build_data_summary(state)
        assert "CONCENTRATION_HIGH" in summary
        assert "DIRECT_ORDER_REQUEST" in summary

    def test_no_warnings_section_when_nothing_fires(self):
        state = _state(intents=["general"], user_message="hola, cómo estás", risk_warnings=[])
        summary = _build_data_summary(state)
        assert "ADVERTENCIAS DE RIESGO" not in summary


# ---------------------------------------------------------------------------
# Acumulación con operator.add (comportamiento LangGraph)
# ---------------------------------------------------------------------------


class TestRiskWarningsAccumulation:
    def test_operator_add_concatenates_two_lists(self):
        w1 = _warning("W1")
        w2 = _warning("W2")
        result = operator.add([w1], [w2])
        assert len(result) == 2
        assert result[0].code == "W1"
        assert result[1].code == "W2"

    def test_operator_add_with_empty_initial(self):
        w1 = _warning("W1")
        result = operator.add([], [w1])
        assert len(result) == 1
        assert result[0].code == "W1"

    def test_operator_add_two_empty_lists(self):
        assert operator.add([], []) == []

    def test_quant_and_auditor_warnings_would_accumulate(self):
        """Simula el efecto de dos nodos devolviendo risk_warnings con operator.add."""
        quant_warnings = [_warning("MISSING_PROFILE", WarningLevel.MEDIUM)]
        auditor_warnings = [_warning("CONCENTRATION_CRITICAL", WarningLevel.CRITICAL)]
        merged = operator.add(operator.add([], quant_warnings), auditor_warnings)
        assert len(merged) == 2
        codes = [w.code for w in merged]
        assert "MISSING_PROFILE" in codes
        assert "CONCENTRATION_CRITICAL" in codes


# ---------------------------------------------------------------------------
# Verificación del initial_state correcto
# ---------------------------------------------------------------------------


class TestInitialStateFields:
    def test_base_state_has_financial_profile(self):
        assert "financial_profile" in _BASE
        assert _BASE["financial_profile"] is None

    def test_base_state_has_risk_warnings_empty_list(self):
        assert "risk_warnings" in _BASE
        assert _BASE["risk_warnings"] == []

    def test_base_state_has_explanation_card(self):
        assert "explanation_card" in _BASE
        assert _BASE["explanation_card"] is None

    def test_build_data_summary_accepts_state_with_new_fields(self):
        state = _state(intents=["general"], user_message="auditá mi cartera")
        summary = _build_data_summary(state)
        assert isinstance(summary, str)
        assert len(summary) > 0
