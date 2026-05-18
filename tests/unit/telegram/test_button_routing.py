"""
Tests para la corrección de routing de botones y mensajes de estado de noticias.

Cubre:
- El botón "Agregar posición" usa callback_data "intent:data_fetch" (no "add_position").
- INTENT_MESSAGES mapea "data_fetch" y "news", no "add_position".
- _build_data_summary distingue news_results=None (no corrió) vs news_results=[]
  (corrió pero sin resultados) vs news_results=[...] (con resultados).
"""

from financial_assistant.agents.ux_agent.agent import _build_data_summary
from financial_assistant.telegram.handlers.message_handler import INTENT_MESSAGES
from financial_assistant.telegram.keyboards.inline_keyboards import main_menu_keyboard

# ---------------------------------------------------------------------------
# Botón "Agregar posición" — callback_data correcto
# ---------------------------------------------------------------------------


class TestButtonCallbackData:
    def test_add_position_button_uses_data_fetch(self):
        kb = main_menu_keyboard()
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "intent:data_fetch" in callbacks

    def test_add_position_button_not_invalid_intent(self):
        kb = main_menu_keyboard()
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "intent:add_position" not in callbacks

    def test_all_button_intents_are_valid(self):
        from financial_assistant.agents.state import VALID_INTENTS
        kb = main_menu_keyboard()
        for row in kb.inline_keyboard:
            for btn in row:
                if btn.callback_data and btn.callback_data.startswith("intent:"):
                    intent = btn.callback_data.split(":")[1]
                    assert intent in VALID_INTENTS, f"Intent '{intent}' is not valid"

    def test_audit_button_present(self):
        kb = main_menu_keyboard()
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "intent:audit" in callbacks

    def test_optimize_button_present(self):
        kb = main_menu_keyboard()
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "intent:optimize" in callbacks

    def test_news_button_present(self):
        kb = main_menu_keyboard()
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "intent:news" in callbacks


# ---------------------------------------------------------------------------
# INTENT_MESSAGES — claves correctas
# ---------------------------------------------------------------------------


class TestIntentMessages:
    def test_data_fetch_key_present(self):
        assert "data_fetch" in INTENT_MESSAGES

    def test_add_position_key_not_present(self):
        assert "add_position" not in INTENT_MESSAGES

    def test_news_message_uses_portfolio_wording(self):
        assert "portfolio" in INTENT_MESSAGES["news"].lower() or "noticias" in INTENT_MESSAGES["news"].lower()

    def test_audit_key_present(self):
        assert "audit" in INTENT_MESSAGES

    def test_optimize_key_present(self):
        assert "optimize" in INTENT_MESSAGES


# ---------------------------------------------------------------------------
# _build_data_summary — distinción news_results None vs [] vs [...]
# ---------------------------------------------------------------------------

_BASE = {
    "user_id": 1,
    "user_message": "noticias de mi portfolio",
    "messages": [],
    "intents": ["news"],
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


class TestNewsResultsStatusMessages:
    def test_none_results_with_news_intent_shows_fallback(self):
        state = {**_BASE, "news_results": None}
        summary = _build_data_summary(state)
        assert "NEWS STATUS" in summary

    def test_empty_list_with_news_intent_shows_no_articles_message(self):
        state = {**_BASE, "news_results": []}
        summary = _build_data_summary(state)
        assert "NEWS STATUS" in summary
        assert "No se encontraron artículos" in summary

    def test_empty_list_without_news_intent_shows_nothing(self):
        state = {**_BASE, "intents": ["general"], "news_results": []}
        summary = _build_data_summary(state)
        assert "NEWS" not in summary

    def test_none_results_without_news_intent_shows_nothing(self):
        state = {**_BASE, "intents": ["general"], "news_results": None}
        summary = _build_data_summary(state)
        assert "NEWS" not in summary

    def test_empty_list_message_does_not_mention_newsapi_key(self):
        state = {**_BASE, "news_results": []}
        summary = _build_data_summary(state)
        assert "NEWSAPI_KEY" not in summary

    def test_none_results_message_does_not_mention_newsapi_key(self):
        state = {**_BASE, "news_results": None}
        summary = _build_data_summary(state)
        assert "NEWSAPI_KEY" not in summary
