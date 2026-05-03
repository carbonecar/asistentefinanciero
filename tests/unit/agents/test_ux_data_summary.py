"""
Unit tests for _build_data_summary — article_count warning logic.

Covers the three cases added by change I-3:
- article_count == 0  → "sin análisis disponible"
- 0 < article_count < 3 → "baja cantidad de artículos"
- article_count >= 3  → no warning appended

All other _build_data_summary paths (audit, quant, market_data, fx) are
left untouched; only the news_results block is exercised here.

No LangGraph execution, no LLM, no network.
"""

from financial_assistant.agents.ux_agent.agent import _build_data_summary
from financial_assistant.domain.models.news import SentimentResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_STATE: dict = {
    "user_id": 1,
    "user_message": "",
    "messages": [],
    "intents": ["news"],
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


def _state_with(news_results: list[SentimentResult]) -> dict:
    return {**_BASE_STATE, "news_results": news_results}


def _sentiment(ticker: str = "AAPL", article_count: int = 5) -> SentimentResult:
    return SentimentResult(
        ticker=ticker,
        score=0.45,
        label="positive",
        article_count=article_count,
        representative_headlines=("Headline A", "Headline B") if article_count > 0 else (),
    )


# ---------------------------------------------------------------------------
# article_count == 0  (FinBERT failure fallback after change I-1)
# ---------------------------------------------------------------------------


class TestArticleCountZero:
    def _summary(self, ticker: str = "AAPL") -> str:
        return _build_data_summary(_state_with([_sentiment(ticker, article_count=0)]))

    def test_contains_sin_analisis_disponible(self):
        assert "sin análisis disponible" in self._summary()

    def test_contains_ticker_in_warning(self):
        assert "[AAPL]" in self._summary()

    def test_score_line_still_present(self):
        # The main ticker line is always written regardless of article_count.
        assert "AAPL: positive" in self._summary()
        assert "0 articles" in self._summary()

    def test_no_baja_cantidad_message(self):
        assert "baja cantidad" not in self._summary()

    def test_different_ticker_uses_correct_label(self):
        summary = _build_data_summary(_state_with([_sentiment("TSLA", article_count=0)]))
        assert "[TSLA]" in summary
        assert "sin análisis disponible" in summary


# ---------------------------------------------------------------------------
# 0 < article_count < 3  (low sample warning)
# ---------------------------------------------------------------------------


class TestArticleCountLow:
    def test_one_article_triggers_baja_cantidad(self):
        summary = _build_data_summary(_state_with([_sentiment(article_count=1)]))
        assert "baja cantidad de artículos" in summary

    def test_two_articles_triggers_baja_cantidad(self):
        summary = _build_data_summary(_state_with([_sentiment(article_count=2)]))
        assert "baja cantidad de artículos" in summary

    def test_contains_ticker_in_warning(self):
        summary = _build_data_summary(_state_with([_sentiment("MSFT", article_count=1)]))
        assert "[MSFT]" in summary

    def test_score_line_still_present(self):
        summary = _build_data_summary(_state_with([_sentiment(article_count=1)]))
        assert "AAPL: positive" in summary

    def test_no_sin_analisis_message(self):
        summary = _build_data_summary(_state_with([_sentiment(article_count=2)]))
        assert "sin análisis disponible" not in summary


# ---------------------------------------------------------------------------
# article_count >= 3  (normal path — no warning)
# ---------------------------------------------------------------------------


class TestArticleCountNormal:
    def test_three_articles_no_warning(self):
        summary = _build_data_summary(_state_with([_sentiment(article_count=3)]))
        assert "sin análisis disponible" not in summary
        assert "baja cantidad" not in summary

    def test_ten_articles_no_warning(self):
        summary = _build_data_summary(_state_with([_sentiment(article_count=10)]))
        assert "sin análisis disponible" not in summary
        assert "baja cantidad" not in summary

    def test_score_and_label_present(self):
        summary = _build_data_summary(_state_with([_sentiment(article_count=5)]))
        assert "positive" in summary
        assert "+0.450" in summary

    def test_headlines_still_shown(self):
        summary = _build_data_summary(_state_with([_sentiment(article_count=5)]))
        assert "Headline A" in summary
        assert "Headline B" in summary


# ---------------------------------------------------------------------------
# Multiple tickers — each gets its own warning independently
# ---------------------------------------------------------------------------


class TestMultipleTickers:
    def test_mixed_counts_each_ticker_correct(self):
        results = [
            _sentiment("AAPL", article_count=0),   # failure
            _sentiment("TSLA", article_count=2),   # low
            _sentiment("MSFT", article_count=8),   # normal
        ]
        summary = _build_data_summary(_state_with(results))
        assert "[AAPL]" in summary and "sin análisis disponible" in summary
        assert "[TSLA]" in summary and "baja cantidad de artículos" in summary
        assert "MSFT: positive" in summary
        assert summary.index("[AAPL]") < summary.index("[TSLA]")

    def test_normal_ticker_has_no_warning_when_mixed(self):
        results = [
            _sentiment("AAPL", article_count=0),
            _sentiment("MSFT", article_count=8),
        ]
        summary = _build_data_summary(_state_with(results))
        # MSFT section must not contain either warning string
        msft_section = summary[summary.index("MSFT"):]
        assert "sin análisis disponible" not in msft_section
        assert "baja cantidad" not in msft_section


# ---------------------------------------------------------------------------
# Helpers for positions / sell summary tests
# ---------------------------------------------------------------------------


def _data_fetch_state(positions: list[dict]) -> dict:
    return {**_BASE_STATE, "intents": ["data_fetch"], "positions": positions}


def _buy(ticker: str = "AAPL", qty: float = 10.0, price: float = 180.0) -> dict:
    return {"ticker": ticker, "quantity": qty, "avg_cost_usd": price, "asset_type": "stock", "action": "buy"}


def _sell(ticker: str = "AAPL", qty: float = 5.0, price: float = 200.0) -> dict:
    return {"ticker": ticker, "quantity": qty, "avg_cost_usd": price, "asset_type": "stock", "action": "sell"}


# ---------------------------------------------------------------------------
# Compras registradas / pendientes
# ---------------------------------------------------------------------------


class TestPositionsBuySummary:
    def test_buy_with_price_appears_in_registered_section(self):
        summary = _build_data_summary(_data_fetch_state([_buy("AAPL", qty=10.0, price=180.0)]))
        assert "POSICIONES REGISTRADAS" in summary
        assert "AAPL" in summary
        assert "10" in summary
        assert "180" in summary

    def test_buy_without_price_appears_in_pending_section(self):
        pos = _buy("TSLA", qty=5.0, price=0.0)
        summary = _build_data_summary(_data_fetch_state([pos]))
        assert "POSICIONES PENDIENTES" in summary
        assert "TSLA" in summary
        assert "POSICIONES REGISTRADAS" not in summary

    def test_buy_without_price_not_in_registered_section(self):
        pos = _buy("MSFT", qty=3.0, price=0.0)
        summary = _build_data_summary(_data_fetch_state([pos]))
        assert "POSICIONES REGISTRADAS" not in summary

    def test_multiple_buys_separated_correctly(self):
        positions = [
            _buy("AAPL", qty=10.0, price=180.0),
            _buy("TSLA", qty=5.0, price=0.0),
        ]
        summary = _build_data_summary(_data_fetch_state(positions))
        assert "POSICIONES REGISTRADAS" in summary
        assert "POSICIONES PENDIENTES" in summary
        assert "AAPL" in summary
        assert "TSLA" in summary

    def test_no_positions_section_when_intent_is_not_data_fetch(self):
        state = {**_BASE_STATE, "intents": ["audit"], "positions": [_buy("AAPL")]}
        summary = _build_data_summary(state)
        assert "POSICIONES REGISTRADAS" not in summary
        assert "POSICIONES PENDIENTES" not in summary

    def test_no_positions_section_when_positions_empty(self):
        summary = _build_data_summary(_data_fetch_state([]))
        assert "POSICIONES REGISTRADAS" not in summary
        assert "POSICIONES PENDIENTES" not in summary

    def test_default_action_treated_as_buy(self):
        pos = {"ticker": "GOOG", "quantity": 2.0, "avg_cost_usd": 150.0, "asset_type": "stock"}
        summary = _build_data_summary(_data_fetch_state([pos]))
        assert "POSICIONES REGISTRADAS" in summary
        assert "GOOG" in summary


# ---------------------------------------------------------------------------
# Salidas informadas
# ---------------------------------------------------------------------------


class TestSellSummary:
    def test_sell_appears_in_salidas_section(self):
        summary = _build_data_summary(_data_fetch_state([_sell("AAPL", qty=5.0, price=200.0)]))
        assert "SALIDAS INFORMADAS" in summary
        assert "AAPL" in summary
        assert "5" in summary

    def test_sell_with_price_shows_price(self):
        summary = _build_data_summary(_data_fetch_state([_sell("AAPL", qty=5.0, price=200.0)]))
        assert "200" in summary

    def test_sell_without_price_shows_sin_precio(self):
        pos = _sell("AAPL", qty=5.0, price=0.0)
        summary = _build_data_summary(_data_fetch_state([pos]))
        assert "SALIDAS INFORMADAS" in summary
        assert "sin precio de referencia" in summary

    def test_sell_does_not_appear_in_registered_section(self):
        summary = _build_data_summary(_data_fetch_state([_sell("AAPL")]))
        assert "POSICIONES REGISTRADAS" not in summary

    def test_buy_and_sell_both_shown_in_correct_sections(self):
        positions = [_buy("MSFT", qty=10.0, price=300.0), _sell("AAPL", qty=5.0, price=200.0)]
        summary = _build_data_summary(_data_fetch_state(positions))
        assert "POSICIONES REGISTRADAS" in summary
        assert "SALIDAS INFORMADAS" in summary
        assert "MSFT" in summary
        assert "AAPL" in summary

    def test_sell_section_not_shown_when_no_sells(self):
        summary = _build_data_summary(_data_fetch_state([_buy("AAPL", price=180.0)]))
        assert "SALIDAS INFORMADAS" not in summary
