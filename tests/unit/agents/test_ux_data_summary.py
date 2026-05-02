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
    "quantity": 0,
    "avg_cost_usd": 0,
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
