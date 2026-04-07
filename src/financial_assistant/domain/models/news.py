from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class NewsArticle:
    title: str
    description: str
    url: str
    published_at: datetime
    source: str
    content: str = ""

    @property
    def full_text(self) -> str:
        return f"{self.title}. {self.description} {self.content}".strip()


@dataclass(frozen=True)
class SentimentResult:
    ticker: str
    score: float  # [-1.0, 1.0] — negative to positive
    label: str  # "positive", "negative", "neutral"
    article_count: int
    representative_headlines: tuple[str, ...]
