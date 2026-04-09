from financial_assistant.domain.models.news import NewsArticle, SentimentResult


class TextBlobSentimentAnalyzer:
    """
    Lightweight sentiment analyzer using TextBlob polarity scores.
    score in [-1.0, 1.0]: polarity averaged across all article texts.
    """

    def score(self, ticker: str, articles: list[NewsArticle]) -> SentimentResult:
        from textblob import TextBlob  # type: ignore[import-untyped]  # pylint: disable=import-outside-toplevel

        scores: list[float] = []
        for article in articles:
            blob = TextBlob(article.full_text)
            scores.append(blob.sentiment.polarity)

        if not scores:
            return SentimentResult(
                ticker=ticker,
                score=0.0,
                label="neutral",
                article_count=0,
                representative_headlines=(),
            )

        avg_score = sum(scores) / len(scores)
        label = "neutral"
        if avg_score > 0.05:
            label = "positive"
        elif avg_score < -0.05:
            label = "negative"

        headlines = tuple(a.title for a in articles[:3] if a.title)

        return SentimentResult(
            ticker=ticker,
            score=round(avg_score, 4),
            label=label,
            article_count=len(articles),
            representative_headlines=headlines,
        )
