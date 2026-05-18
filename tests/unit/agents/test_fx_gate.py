"""
Unit tests for _user_requested_fx_or_ars() and the TIPO DE CAMBIO gate in _build_data_summary.

Cubre:
- Mensajes que NO deben activar el tipo de cambio (registros simples en USD)
- Señales explícitas que SÍ activan el tipo de cambio (pesos, ARS, MEP, CCL, etc.)
- _build_data_summary no incluye la sección cuando no se pidió ARS
- _build_data_summary sí incluye la sección cuando se pidió ARS
"""

from datetime import datetime
from decimal import Decimal

from financial_assistant.agents.ux_agent.agent import _build_data_summary, _user_requested_fx_or_ars
from financial_assistant.domain.models.fx import ExchangeRate

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_STATE: dict = {
    "user_id": 1,
    "user_message": "",
    "messages": [],
    "intents": ["data_fetch"],
    "active_tickers": ["AAPL"],
    "period": "1y",
    "use_sentiment": False,
    "positions": [],
    "market_data_result": None,
    "audit_report": None,
    "quant_result": None,
    "news_results": None,
    "exchange_rates": None,
    "final_response": None,
    "errors": [],
}

_NOW = datetime(2024, 1, 2, 12, 0)


def _rate(
    casa: str = "oficial", nombre: str = "Oficial", compra: float = 1000.0, venta: float = 1050.0
) -> ExchangeRate:
    return ExchangeRate(
        casa=casa,
        nombre=nombre,
        compra=Decimal(str(compra)),
        venta=Decimal(str(venta)),
        updated_at=_NOW,
    )


def _state_with_rates(user_message: str, rates: list[ExchangeRate] | None = None) -> dict:
    return {
        **_BASE_STATE,
        "user_message": user_message,
        "exchange_rates": rates if rates is not None else [_rate()],
    }


# ---------------------------------------------------------------------------
# _user_requested_fx_or_ars — mensajes que NO activan ARS
# ---------------------------------------------------------------------------


class TestFxGateNegative:
    def test_simple_usd_registration(self):
        assert not _user_requested_fx_or_ars("Registrá 10 AAPL a 180 dólares")

    def test_dolares_plural_does_not_trigger(self):
        assert not _user_requested_fx_or_ars("a 180 dólares")

    def test_audit_request(self):
        assert not _user_requested_fx_or_ars("Auditá mi cartera")

    def test_optimize_request(self):
        assert not _user_requested_fx_or_ars("Optimizá mi portfolio")

    def test_news_request(self):
        assert not _user_requested_fx_or_ars("Noticias de AAPL")

    def test_sell_without_ars(self):
        assert not _user_requested_fx_or_ars("Vendí 5 MSFT a 300 dólares")

    def test_empty_string(self):
        assert not _user_requested_fx_or_ars("")

    def test_greeting(self):
        assert not _user_requested_fx_or_ars("hola")

    def test_ambiguous_yes(self):
        assert not _user_requested_fx_or_ars("sí")


# ---------------------------------------------------------------------------
# _user_requested_fx_or_ars — señales que SÍ activan ARS
# ---------------------------------------------------------------------------


class TestFxGatePositive:
    def test_pesos(self):
        assert _user_requested_fx_or_ars("pasalo a pesos")

    def test_peso_singular(self):
        assert _user_requested_fx_or_ars("equivalente en peso")

    def test_ars_uppercase(self):
        assert _user_requested_fx_or_ars("en ARS")

    def test_ars_lowercase(self):
        assert _user_requested_fx_or_ars("en ars")

    def test_equivalente(self):
        assert _user_requested_fx_or_ars("quiero el equivalente")

    def test_tipo_de_cambio(self):
        assert _user_requested_fx_or_ars("qué tipo de cambio usar")

    def test_dolar_oficial(self):
        assert _user_requested_fx_or_ars("dólar oficial")

    def test_dolar_sin_acento_oficial(self):
        assert _user_requested_fx_or_ars("dolar oficial")

    def test_dolar_blue(self):
        assert _user_requested_fx_or_ars("dólar blue")

    def test_dolar_mep(self):
        assert _user_requested_fx_or_ars("dólar MEP")

    def test_dolar_ccl(self):
        assert _user_requested_fx_or_ars("dólar CCL")

    def test_dolar_mayorista(self):
        assert _user_requested_fx_or_ars("dólar mayorista")

    def test_standalone_mep(self):
        assert _user_requested_fx_or_ars("usar MEP")

    def test_standalone_ccl(self):
        assert _user_requested_fx_or_ars("con CCL")

    def test_standalone_blue(self):
        assert _user_requested_fx_or_ars("blue")

    def test_standalone_oficial(self):
        assert _user_requested_fx_or_ars("oficial")

    def test_standalone_mayorista(self):
        assert _user_requested_fx_or_ars("mayorista")

    def test_contado_con_liquidacion(self):
        assert _user_requested_fx_or_ars("contado con liquidación")

    def test_contado_con_liquidacion_sin_acento(self):
        assert _user_requested_fx_or_ars("contado con liquidacion")

    def test_full_sentence_with_mep(self):
        assert _user_requested_fx_or_ars("Registrá 5 MSFT a 300 dólares y pasalo a pesos con dólar MEP")

    def test_full_sentence_with_pesos(self):
        assert _user_requested_fx_or_ars("Registrá 10 AAPL a 180 dólares y pasalo a pesos")

    def test_case_insensitive_mep(self):
        assert _user_requested_fx_or_ars("dólar mep")

    def test_case_insensitive_ccl(self):
        assert _user_requested_fx_or_ars("dólar ccl")


# ---------------------------------------------------------------------------
# _build_data_summary — gate de TIPO DE CAMBIO
# ---------------------------------------------------------------------------


class TestBuildDataSummaryFxGate:
    def test_no_fx_section_when_not_requested(self):
        state = _state_with_rates("Registrá 10 AAPL a 180 dólares")
        assert "TIPO DE CAMBIO" not in _build_data_summary(state)

    def test_fx_section_present_when_pesos_requested(self):
        state = _state_with_rates("pasalo a pesos")
        assert "TIPO DE CAMBIO" in _build_data_summary(state)

    def test_fx_section_present_when_mep_requested(self):
        state = _state_with_rates("con dólar MEP")
        assert "TIPO DE CAMBIO" in _build_data_summary(state)

    def test_fx_section_present_when_full_sentence(self):
        state = _state_with_rates("Registrá 10 AAPL a 180 dólares y pasalo a pesos con dólar oficial")
        assert "TIPO DE CAMBIO" in _build_data_summary(state)

    def test_no_fx_section_when_rates_none(self):
        state = {**_BASE_STATE, "user_message": "pasalo a pesos", "exchange_rates": None}
        assert "TIPO DE CAMBIO" not in _build_data_summary(state)

    def test_no_fx_section_when_rates_empty_list(self):
        state = {**_BASE_STATE, "user_message": "pasalo a pesos", "exchange_rates": []}
        assert "TIPO DE CAMBIO" not in _build_data_summary(state)

    def test_rate_values_shown_when_requested(self):
        state = _state_with_rates("en pesos", [_rate("oficial", "Oficial", 1000.0, 1050.0)])
        summary = _build_data_summary(state)
        assert "Oficial" in summary
        assert "1,050" in summary or "1050" in summary

    def test_audit_intent_no_fx_even_with_rates(self):
        state = {
            **_BASE_STATE,
            "intents": ["audit"],
            "user_message": "Auditá mi cartera",
            "exchange_rates": [_rate()],
        }
        assert "TIPO DE CAMBIO" not in _build_data_summary(state)
