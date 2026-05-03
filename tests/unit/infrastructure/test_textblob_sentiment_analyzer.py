"""
Unit tests for TextBlobSentimentAnalyzer.score().

Covers:
- Empty articles: early return path; analysis_failed=False, model_name is set.
- Normal path: successful scoring; analysis_failed=False, model_name is set;
  article_count, score, label and representative_headlines preserved.
- Traceability fields: model_name not empty on all paths; analysis_failed=False
  on all paths (TextBlob has no inference-failure path).
- Backwards compatibility: existing SentimentResult fields unchanged.

TextBlob is a pure-Python library — no GPU, no network, no mocks needed.
"""

from datetime import UTC, datetime

from financial_assistant.domain.models.news import NewsArticle
from financial_assistant.infrastructure.nlp.sentiment_analyzer import (
    TextBlobSentimentAnalyzer,
    _MODEL_NAME,
)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _article(title: str = "Company reports strong earnings", description: str = "Revenue up 10%") -> NewsArticle:
    return NewsArticle(
        title=title,
        description=description,
        url="https://example.com/news",
        published_at=datetime.now(tz=UTC),
        source="Reuters",
        content="",
    )


# ---------------------------------------------------------------------------
# Empty articles — early return path
# ---------------------------------------------------------------------------


class TestTextBlobEmptyArticles:
    def test_analysis_failed_is_false_for_empty_articles(self):
        result = TextBlobSentimentAnalyzer().score("AAPL", [])
        assert result.analysis_failed is False

    def test_model_name_is_set_for_empty_articles(self):
        result = TextBlobSentimentAnalyzer().score("AAPL", [])
        assert result.model_name == _MODEL_NAME

    def test_model_name_is_not_empty_for_empty_articles(self):
        result = TextBlobSentimentAnalyzer().score("AAPL", [])
        assert result.model_name != ""

    def test_article_count_is_zero_for_empty_articles(self):
        result = TextBlobSentimentAnalyzer().score("AAPL", [])
        assert result.article_count == 0

    def test_label_is_neutral_for_empty_articles(self):
        result = TextBlobSentimentAnalyzer().score("AAPL", [])
        assert result.label == "neutral"

    def test_score_is_zero_for_empty_articles(self):
        result = TextBlobSentimentAnalyzer().score("AAPL", [])
        assert result.score == 0.0

    def test_headlines_empty_for_empty_articles(self):
        result = TextBlobSentimentAnalyzer().score("AAPL", [])
        assert result.representative_headlines == ()

    def test_ticker_preserved_for_empty_articles(self):
        result = TextBlobSentimentAnalyzer().score("TSLA", [])
        assert result.ticker == "TSLA"


# ---------------------------------------------------------------------------
# Normal path — articles present
# ---------------------------------------------------------------------------


class TestTextBlobNormalPath:
    def test_analysis_failed_is_false_on_success(self):
        result = TextBlobSentimentAnalyzer().score("AAPL", [_article()])
        assert result.analysis_failed is False

    def test_model_name_is_set_on_success(self):
        result = TextBlobSentimentAnalyzer().score("AAPL", [_article()])
        assert result.model_name == _MODEL_NAME

    def test_model_name_is_not_empty_on_success(self):
        result = TextBlobSentimentAnalyzer().score("AAPL", [_article()])
        assert result.model_name != ""

    def test_article_count_equals_input_length(self):
        articles = [_article(f"headline {i}") for i in range(5)]
        result = TextBlobSentimentAnalyzer().score("AAPL", articles)
        assert result.article_count == 5

    def test_ticker_preserved_on_success(self):
        result = TextBlobSentimentAnalyzer().score("TSLA", [_article()])
        assert result.ticker == "TSLA"

    def test_representative_headlines_taken_from_articles(self):
        articles = [_article("Headline A"), _article("Headline B")]
        result = TextBlobSentimentAnalyzer().score("AAPL", articles)
        assert "Headline A" in result.representative_headlines
        assert "Headline B" in result.representative_headlines

    def test_representative_headlines_capped_at_three(self):
        articles = [_article(f"Title {i}") for i in range(6)]
        result = TextBlobSentimentAnalyzer().score("AAPL", articles)
        assert len(result.representative_headlines) <= 3

    def test_score_is_float_in_valid_range(self):
        result = TextBlobSentimentAnalyzer().score("AAPL", [_article()])
        assert -1.0 <= result.score <= 1.0

    def test_label_is_one_of_valid_values(self):
        result = TextBlobSentimentAnalyzer().score("AAPL", [_article()])
        assert result.label in ("positive", "negative", "neutral")


# ---------------------------------------------------------------------------
# Traceability — model_name and analysis_failed consistent on all paths
# ---------------------------------------------------------------------------


class TestTextBlobTraceability:
    """
    Verifica que todo SentimentResult producido por TextBlobSentimentAnalyzer
    tenga model_name explícito y analysis_failed correcto en ambos paths,
    alineado con el invariante establecido en el Cambio 2 para FinBERT.
    """

    def test_all_paths_carry_same_model_name(self):
        results = [
            TextBlobSentimentAnalyzer().score("AAPL", []),
            TextBlobSentimentAnalyzer().score("AAPL", [_article()]),
        ]
        for r in results:
            assert r.model_name == _MODEL_NAME, f"model_name faltante en {r}"

    def test_model_name_not_empty_on_any_path(self):
        results = [
            TextBlobSentimentAnalyzer().score("TSLA", []),
            TextBlobSentimentAnalyzer().score("TSLA", [_article()]),
        ]
        for r in results:
            assert r.model_name != ""

    def test_analysis_failed_is_false_on_all_paths(self):
        # TextBlob no tiene path de falla técnica — analysis_failed siempre False.
        results = [
            TextBlobSentimentAnalyzer().score("AAPL", []),
            TextBlobSentimentAnalyzer().score("AAPL", [_article()]),
        ]
        for r in results:
            assert r.analysis_failed is False
