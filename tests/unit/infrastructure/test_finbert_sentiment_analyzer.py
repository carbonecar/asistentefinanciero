"""
Unit tests for FinBERTSentimentAnalyzer.score().

Covers:
- Fallback when pipeline inference raises: article_count=0 distinguishes
  technical failure from genuine neutral result; analysis_failed=True.
- Normal path: successful inference produces correct label/score/article_count;
  analysis_failed=False, model_name is set.
- Empty articles: early return path; analysis_failed=False, model_name is set.
- Traceability fields: analysis_failed and model_name across all paths.
- Backwards compatibility: SentimentResult constructors without the new fields
  still work via default values.

No real model is loaded — the internal _pipeline attribute is replaced with
a MagicMock so _get_pipeline() returns it directly (lazy-load is skipped).
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock

from financial_assistant.domain.models.news import NewsArticle, SentimentResult
from financial_assistant.infrastructure.nlp.finbert_sentiment_analyzer import (
    _MODEL_NAME,
    FinBERTSentimentAnalyzer,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _article(title: str = "Apple beats earnings", description: str = "Revenue up 10%") -> NewsArticle:
    return NewsArticle(
        title=title,
        description=description,
        url="https://example.com/news",
        published_at=datetime.now(tz=UTC),
        source="Reuters",
        content="",
    )


def _analyzer_failing() -> FinBERTSentimentAnalyzer:
    """Analyzer whose pipeline raises RuntimeError on every call."""
    analyzer = FinBERTSentimentAnalyzer()
    analyzer._pipeline = MagicMock(side_effect=RuntimeError("CUDA out of memory"))
    return analyzer


def _analyzer_with(predictions: list[dict]) -> FinBERTSentimentAnalyzer:
    """Analyzer whose pipeline returns a fixed list of predictions."""
    analyzer = FinBERTSentimentAnalyzer()
    analyzer._pipeline = MagicMock(return_value=predictions)
    return analyzer


# ---------------------------------------------------------------------------
# Fallback behavior when pipeline raises
# ---------------------------------------------------------------------------


class TestFinBERTFallbackOnInferenceFailure:
    def test_score_is_zero(self):
        result = _analyzer_failing().score("AAPL", [_article()])
        assert result.score == 0.0

    def test_label_is_neutral(self):
        result = _analyzer_failing().score("AAPL", [_article()])
        assert result.label == "neutral"

    def test_article_count_is_zero(self):
        # Key assertion: failure is distinguishable from genuine neutral because
        # genuine neutral always has article_count > 0 (the pipeline ran).
        articles = [_article(f"headline {i}") for i in range(5)]
        result = _analyzer_failing().score("AAPL", articles)
        assert result.article_count == 0

    def test_representative_headlines_is_empty(self):
        result = _analyzer_failing().score("AAPL", [_article("Important news")])
        assert result.representative_headlines == ()

    def test_ticker_is_preserved(self):
        result = _analyzer_failing().score("TSLA", [_article()])
        assert result.ticker == "TSLA"

    def test_failure_distinguishable_from_genuine_neutral(self):
        # With 3 articles available but inference crashed, article_count must be 0.
        # A genuine neutral calculated over 3 articles would have article_count=3.
        articles = [_article(f"title {i}") for i in range(3)]
        result = _analyzer_failing().score("AAPL", articles)
        assert result.article_count == 0, (
            "article_count=0 on failure; genuine neutral returns article_count>0"
        )

    def test_analysis_failed_is_true(self):
        result = _analyzer_failing().score("AAPL", [_article()])
        assert result.analysis_failed is True

    def test_model_name_is_set_on_failure(self):
        result = _analyzer_failing().score("AAPL", [_article()])
        assert result.model_name == _MODEL_NAME


# ---------------------------------------------------------------------------
# Normal path — successful inference
# ---------------------------------------------------------------------------


class TestFinBERTNormalPath:
    def test_positive_prediction_produces_positive_label(self):
        result = _analyzer_with([{"label": "positive", "score": 0.9}]).score("AAPL", [_article()])
        assert result.label == "positive"
        assert result.score > 0.05

    def test_negative_prediction_produces_negative_label(self):
        result = _analyzer_with([{"label": "negative", "score": 0.85}]).score("AAPL", [_article()])
        assert result.label == "negative"
        assert result.score < -0.05

    def test_article_count_equals_input_length(self):
        articles = [_article(f"headline {i}") for i in range(5)]
        predictions = [{"label": "positive", "score": 0.8}] * 5
        result = _analyzer_with(predictions).score("AAPL", articles)
        assert result.article_count == 5

    def test_representative_headlines_taken_from_articles(self):
        articles = [_article("Headline A"), _article("Headline B")]
        predictions = [{"label": "positive", "score": 0.9}] * 2
        result = _analyzer_with(predictions).score("AAPL", articles)
        assert "Headline A" in result.representative_headlines
        assert "Headline B" in result.representative_headlines

    def test_score_is_weighted_by_confidence(self):
        # polarity=+1.0, confidence=0.6 → score = 1.0 * 0.6 = 0.6
        result = _analyzer_with([{"label": "positive", "score": 0.6}]).score("AAPL", [_article()])
        assert abs(result.score - 0.6) < 1e-4

    def test_near_zero_score_produces_neutral_label(self):
        # avg polarity*confidence ≈ 0.0 → label = "neutral" (threshold ±0.05)
        predictions = [{"label": "positive", "score": 0.04}]
        result = _analyzer_with(predictions).score("AAPL", [_article()])
        assert result.label == "neutral"

    def test_analysis_failed_is_false_on_success(self):
        result = _analyzer_with([{"label": "positive", "score": 0.9}]).score("AAPL", [_article()])
        assert result.analysis_failed is False

    def test_model_name_is_set_on_success(self):
        result = _analyzer_with([{"label": "positive", "score": 0.9}]).score("AAPL", [_article()])
        assert result.model_name == _MODEL_NAME


# ---------------------------------------------------------------------------
# Empty articles — early return path
# ---------------------------------------------------------------------------


class TestFinBERTEmptyArticles:
    def test_empty_list_returns_neutral(self):
        result = FinBERTSentimentAnalyzer().score("AAPL", [])
        assert result.label == "neutral"
        assert result.score == 0.0

    def test_empty_list_article_count_is_zero(self):
        result = FinBERTSentimentAnalyzer().score("AAPL", [])
        assert result.article_count == 0

    def test_empty_list_headlines_is_empty(self):
        result = FinBERTSentimentAnalyzer().score("AAPL", [])
        assert result.representative_headlines == ()

    def test_empty_list_does_not_load_pipeline(self):
        # _pipeline must remain None — no model load for empty input.
        analyzer = FinBERTSentimentAnalyzer()
        analyzer.score("AAPL", [])
        assert analyzer._pipeline is None

    def test_analysis_failed_is_false_for_empty_articles(self):
        # Empty articles is not a technical failure — the model was never invoked.
        result = FinBERTSentimentAnalyzer().score("AAPL", [])
        assert result.analysis_failed is False

    def test_model_name_is_set_for_empty_articles(self):
        result = FinBERTSentimentAnalyzer().score("AAPL", [])
        assert result.model_name == _MODEL_NAME


# ---------------------------------------------------------------------------
# Traceability fields — all fields across all paths
# ---------------------------------------------------------------------------


class TestSentimentResultTraceability:
    """
    Consolidates traceability assertions: every SentimentResult produced by
    FinBERTSentimentAnalyzer must carry model_name and a correct analysis_failed
    flag, regardless of path (success / inference failure / empty input).
    """

    def test_failure_path_flags_are_mutually_exclusive_with_success(self):
        failing = _analyzer_failing().score("AAPL", [_article()])
        success = _analyzer_with([{"label": "positive", "score": 0.9}]).score("AAPL", [_article()])
        assert failing.analysis_failed is True
        assert success.analysis_failed is False

    def test_all_paths_carry_same_model_name(self):
        results = [
            _analyzer_failing().score("AAPL", [_article()]),
            _analyzer_with([{"label": "neutral", "score": 0.5}]).score("AAPL", [_article()]),
            FinBERTSentimentAnalyzer().score("AAPL", []),
        ]
        for r in results:
            assert r.model_name == _MODEL_NAME, f"model_name missing in {r}"

    def test_model_name_is_not_empty_string_on_any_path(self):
        results = [
            _analyzer_failing().score("TSLA", [_article()]),
            _analyzer_with([{"label": "negative", "score": 0.8}]).score("TSLA", [_article()]),
            FinBERTSentimentAnalyzer().score("TSLA", []),
        ]
        for r in results:
            assert r.model_name != ""


# ---------------------------------------------------------------------------
# Backwards compatibility — SentimentResult without new fields still works
# ---------------------------------------------------------------------------


class TestSentimentResultBackwardsCompat:
    def test_constructor_without_new_fields_uses_defaults(self):
        # Existing code that builds SentimentResult without analysis_failed /
        # model_name (e.g. NewsService fallback, test helpers) must keep working.
        result = SentimentResult(
            ticker="AAPL",
            score=0.0,
            label="neutral",
            article_count=0,
            representative_headlines=(),
        )
        assert result.analysis_failed is False
        assert result.model_name == ""

    def test_explicit_analysis_failed_true_is_preserved(self):
        result = SentimentResult(
            ticker="AAPL",
            score=0.0,
            label="neutral",
            article_count=0,
            representative_headlines=(),
            analysis_failed=True,
            model_name="test-model",
        )
        assert result.analysis_failed is True
        assert result.model_name == "test-model"
