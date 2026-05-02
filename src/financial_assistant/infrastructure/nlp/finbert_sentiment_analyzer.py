import logging
from typing import Any

from financial_assistant.domain.models.news import NewsArticle, SentimentResult

logger = logging.getLogger(__name__)

_MODEL_NAME = "mrm8488/distilroberta-finetuned-financial-news-sentiment-analysis"
_LABEL_MAP = {"positive": 1.0, "negative": -1.0, "neutral": 0.0}
_MAX_TOKENS = 512


class FinBERTSentimentAnalyzer:
    """
    Sentiment analyzer using a DistilRoBERTa model fine-tuned on financial news.
    Model: mrm8488/distilroberta-finetuned-financial-news-sentiment-analysis
    Labels: positive / negative / neutral  (same as SentimentResult.label)

    The pipeline is loaded lazily on first call and cached for subsequent ones.
    """

    def __init__(self) -> None:
        self._pipeline: Any = None

    def _get_pipeline(self) -> Any:
        if self._pipeline is None:
            from transformers import pipeline  # pylint: disable=import-outside-toplevel

            logger.info("[FinBERT] Loading model %s (first call — may take a moment)", _MODEL_NAME)
            self._pipeline = pipeline(
                "text-classification",
                model=_MODEL_NAME,
                truncation=True,
                max_length=_MAX_TOKENS,
            )
            logger.info("[FinBERT] Model loaded.")
        return self._pipeline

    def score(self, ticker: str, articles: list[NewsArticle]) -> SentimentResult:
        if not articles:
            return SentimentResult(
                ticker=ticker,
                score=0.0,
                label="neutral",
                article_count=0,
                representative_headlines=(),
            )

        pipe = self._get_pipeline()

        texts = [a.full_text[:1024] for a in articles]  # hard cap before tokenizer
        try:
            predictions: list[dict[str, Any]] = pipe(texts, batch_size=8)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("[FinBERT] Inference failed for %s — falling back to neutral", ticker)
            # article_count=0 distinguishes this fallback from a genuine neutral result
            # (genuine neutral always has article_count > 0 because the pipeline ran).
            return SentimentResult(
                ticker=ticker,
                score=0.0,
                label="neutral",
                article_count=0,
                representative_headlines=(),
            )

        numeric_scores: list[float] = []
        for pred in predictions:
            raw_label: str = pred.get("label", "neutral").lower()
            confidence: float = float(pred.get("score", 0.5))
            # Map to [-1, 1] weighted by model confidence
            polarity = _LABEL_MAP.get(raw_label, 0.0)
            numeric_scores.append(polarity * confidence)

        avg_score = sum(numeric_scores) / len(numeric_scores)

        if avg_score > 0.05:
            label = "positive"
        elif avg_score < -0.05:
            label = "negative"
        else:
            label = "neutral"

        return SentimentResult(
            ticker=ticker,
            score=round(avg_score, 4),
            label=label,
            article_count=len(articles),
            representative_headlines=tuple(a.title for a in articles[:3] if a.title),
        )
